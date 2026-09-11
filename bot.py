import os
import sqlite3
from datetime import datetime
from contextlib import closing

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

import db
from config import PRODUCTS

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN", "").strip()
SUPPORT = os.getenv("SUPPORT_USERNAME", "YourSupportUsername").strip()
BINANCE_PAY_ID = os.getenv("BINANCE_PAY_ID", "").strip()

def load_admin_ids():
    raw = os.getenv("ADMIN_IDS", "")
    ids = set()
    for part in raw.replace(",", " ").split():
        try:
            ids.add(int(part.strip()))
        except (TypeError, ValueError):
            pass
    return ids


def get_admin_ids():
    # Reload on every admin command so Railway variable changes are picked up
    # after a restart without relying on a stale module-level value.
    return load_admin_ids()


def is_admin(user_id):
    return int(user_id) in get_admin_ids()


ADMIN_IDS = load_admin_ids()

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Put it in Railway Variables.")

db.init_db()


def main_menu():
    # Native Telegram inline menu: stable 2-column layout.
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧑‍💼 My Profile", callback_data="profile"),
         InlineKeyboardButton("🛍️ BUY PRODUCTS", callback_data="products")],
        [InlineKeyboardButton("📦 MY ORDERS", callback_data="orders"),
         InlineKeyboardButton("💳 ADD BALANCE", callback_data="payments")],
        [InlineKeyboardButton("👥 REFER", callback_data="refer"),
         InlineKeyboardButton("🎧 SUPPORT", callback_data="support")],
    ])


def back_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Main Menu", callback_data="home")]
    ])


def balance_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Balance", callback_data="add_balance")],
        [InlineKeyboardButton("💳 My Balance", callback_data="show_balance")],
        [InlineKeyboardButton("⬅️ Main Menu", callback_data="home")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    referred_by = None

    if context.args:
        raw_ref = str(context.args[0])
        if raw_ref.startswith("ref_"):
            raw_ref = raw_ref[4:]
        if raw_ref.isdigit():
            candidate = int(raw_ref)
            if candidate != u.id:
                referred_by = candidate

    db.upsert_user(u.id, u.full_name, u.username, referred_by)

    await update.message.reply_text(
        "🏠 MAIN MENU\n"
        "━━━━━━━━━━━━━━━━\n"
        "Welcome to the store!\n\n"
        "Choose an option below.",
        reply_markup=main_menu(),
    )


def get_order(order_id):
    with closing(db.connect()) as con:
        return con.execute(
            "SELECT * FROM orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()


def update_order_status(order_id, status):
    with closing(db.connect()) as con:
        con.execute(
            "UPDATE orders SET status = ? WHERE order_id = ?",
            (status, order_id),
        )
        con.commit()


def deliver_one_item(order_id, user_id, product_id):
    """Atomically reserve one available inventory item for this order."""
    with closing(db.connect()) as con:
        con.execute("BEGIN IMMEDIATE")

        order = con.execute(
            "SELECT status, quantity FROM orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()

        if not order:
            con.rollback()
            return None, "ORDER_NOT_FOUND"

        if order["status"] == "DELIVERED":
            con.rollback()
            return None, "ALREADY_DELIVERED"

        item = con.execute(
            """
            SELECT id, email, password
            FROM inventory
            WHERE product_id = ? AND status = 'AVAILABLE'
            ORDER BY id ASC
            LIMIT 1
            """,
            (product_id,),
        ).fetchone()

        if not item:
            con.rollback()
            return None, "OUT_OF_STOCK"

        now = datetime.now().strftime("%Y-%m-%d %I:%M %p")

        con.execute(
            """
            UPDATE inventory
            SET status = 'SOLD', sold_to = ?, sold_at = ?
            WHERE id = ? AND status = 'AVAILABLE'
            """,
            (user_id, now, item["id"]),
        )

        if con.total_changes != 1:
            con.rollback()
            return None, "RESERVATION_FAILED"

        con.execute(
            "UPDATE orders SET status = 'DELIVERED' WHERE order_id = ?",
            (order_id,),
        )
        con.commit()

        return {
            "email": item["email"],
            "password": item["password"],
            "delivered_at": now,
        }, "DELIVERED"


def purchase_from_balance(order_id, user_id, product_id, total):
    """Atomically debit balance, reserve stock, and mark order delivered."""
    with closing(db.connect()) as con:
        con.execute("BEGIN IMMEDIATE")
        order = con.execute(
            "SELECT status FROM orders WHERE order_id=? AND user_id=?",
            (order_id, user_id),
        ).fetchone()
        if not order:
            con.rollback()
            return None, "ORDER_NOT_FOUND"
        if order["status"] == "DELIVERED":
            con.rollback()
            return None, "ALREADY_DELIVERED"
        user = con.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not user or float(user["balance"]) + 1e-9 < float(total):
            con.rollback()
            return None, "INSUFFICIENT_BALANCE"
        item = con.execute(
            "SELECT id,email,password FROM inventory WHERE product_id=? AND status='AVAILABLE' ORDER BY id ASC LIMIT 1",
            (product_id,),
        ).fetchone()
        if not item:
            con.rollback()
            return None, "OUT_OF_STOCK"
        now = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        cur = con.execute(
            "UPDATE inventory SET status='SOLD', sold_to=?, sold_at=? WHERE id=? AND status='AVAILABLE'",
            (user_id, now, item["id"]),
        )
        if cur.rowcount != 1:
            con.rollback()
            return None, "RESERVATION_FAILED"
        cur = con.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?",
            (float(total), user_id, float(total)),
        )
        if cur.rowcount != 1:
            con.rollback()
            return None, "INSUFFICIENT_BALANCE"
        con.execute("UPDATE orders SET status='DELIVERED', payment_method='Balance' WHERE order_id=?", (order_id,))
        con.commit()
        return {
            "email": item["email"],
            "password": item["password"],
            "delivered_at": now,
            "new_balance": float(user["balance"]) - float(total),
        }, "DELIVERED"


async def send_delivery(context, order, product, deliveries):
    if isinstance(deliveries, dict):
        deliveries = [deliveries]
    lines = [
        "🎉 DELIVERY SUCCESSFUL!",
        "━━━━━━━━━━━━━━━━",
        f"🧾 Order ID: #{order['order_id']}",
        f"📦 Item: {product['name']}",
        f"🏷 Category: {product['category']}",
        f"🔢 Quantity: {order['quantity']}",
        f"💰 Total Price: ${order['total']:.2f}",
        "",
    ]
    for i, item in enumerate(deliveries, 1):
        lines += [f"{i}. 📧 Email / Username: {item['email']}", f"🔑 Password: {item['password']}", ""]
    if deliveries and "new_balance" in deliveries[0]:
        lines.append(f"💳 Remaining Balance: ${deliveries[0]['new_balance']:.2f}")
    if deliveries:
        lines.append(f"🕒 {deliveries[-1].get('delivered_at','')}")
    await context.bot.send_message(chat_id=order["user_id"], text="\n".join(lines))


async def process_purchase(q, context, u, pid, qty):
    p = PRODUCTS.get(pid)
    if not p or not p.get("active", 1) or p.get("coming_soon"):
        await q.edit_message_text("❌ Product unavailable.", reply_markup=back_button())
        return
    if qty < 1:
        await q.edit_message_text("❌ Quantity must be at least 1.", reply_markup=back_button())
        return
    stock = db.get_product_stock(pid)
    if qty > stock:
        await q.edit_message_text(
            f"❌ NOT ENOUGH STOCK\\n\\nRequested: {qty}\\nAvailable: {stock}\\n\\nContact @{SUPPORT.lstrip('@')}.",
            reply_markup=back_button(),
        )
        return
    total = round(float(p["price"]) * qty, 2)
    user = db.get_user(u.id)
    if not user:
        db.upsert_user(u.id, u.full_name, u.username, None)
        user = db.get_user(u.id)
    if float(user["balance"]) + 1e-9 >= total:
        order_id = db.create_order(u.id, pid, qty, total, "Balance")
        order = get_order(order_id)
        deliveries, result = purchase_from_balance_qty(order_id, u.id, pid, qty, total)
        if result == "DELIVERED":
            await send_delivery(context, order, p, deliveries)
            await q.edit_message_text(
                f"✅ PURCHASE COMPLETED\\n\\nOrder: #{order_id}\\nQuantity: {qty}\\n"
                f"Total: ${total:.2f}\\nRemaining Balance: ${deliveries[0]['new_balance']:.2f}",
                reply_markup=back_button(),
            )
            return
        update_order_status(order_id, "OUT_OF_STOCK" if result == "OUT_OF_STOCK" else "CANCELLED")
    order_id = db.create_order(u.id, pid, qty, total, "Binance Pay")
    await q.edit_message_text(
        f"🧾 ORDER #{order_id}\\n\\n📦 Product: {p['name']}\\n🔢 Quantity: {qty}\\n"
        f"💵 Total: ${total:.2f}\\n💳 Balance: ${float(user['balance']):.2f}\\n\\n"
        "Please pay the full amount using Binance Pay.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🟡 Binance Pay", callback_data=f"paybin:{order_id}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="home")],
        ]),
    )


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    u = update.effective_user
    data = q.data

    if data == "home":
        await q.edit_message_text("🏠 MAIN MENU", reply_markup=main_menu())
        return

    if data == "profile":
        user = db.get_user(u.id)
        refs = db.get_ref_count(u.id)
        username = f"@{user['username']}" if user["username"] else "@N/A"
        bot = await context.bot.get_me()
        ref_link = f"https://t.me/{bot.username}?start=ref_{u.id}"

        text = (
            "👤 ACCOUNT DASHBOARD\n"
            "━━━━━━━━━━━━━━━━\n"
            f"🏷 Name: {user['name']}\n"
            f"🔰 Username: {username}\n"
            f"🆔 User ID: {u.id}\n"
            "━━━━━━━━━━━━━━━━\n"
            f"💳 Balance: ${user['balance']:.2f}\n\n"
            f"🎯 Ref Link: {ref_link}\n"
            f"📊 Total Refs: {refs}\n"
            f"🎁 Ref Income: ${user['ref_income']:.2f}"
        )
        await q.edit_message_text(text, reply_markup=back_button())
        return

    if data == "products":
        cats = sorted({p["category"] for p in PRODUCTS.values()})
        rows = [[InlineKeyboardButton(c, callback_data="cat:" + c)] for c in cats]
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="home")])
        await q.edit_message_text(
            "🛍️ BUY PRODUCTS",
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return

    if data.startswith("cat:"):
        cat = data[4:]
        groups = []
        for pid, p in PRODUCTS.items():
            if p["category"] == cat:
                g = p.get("group_name") or "Other"
                if g not in groups:
                    groups.append(g)
        if len(groups) <= 1:
            rows = []
            for pid, p in PRODUCTS.items():
                if p["category"] == cat:
                    label = "⏳ " + p["name"] if p.get("coming_soon") else f"{p['name']} — ${p['price']:.2f}"
                    rows.append([InlineKeyboardButton(label, callback_data="product:" + pid)])
            rows.append([InlineKeyboardButton("⬅️ Back", callback_data="products")])
            await q.edit_message_text(f"🛍️ {cat}", reply_markup=InlineKeyboardMarkup(rows))
            return
        rows = [[InlineKeyboardButton(g, callback_data=f"group:{cat}|{g}")] for g in groups]
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="products")])
        await q.edit_message_text(f"🛍️ {cat}\n\nSelect a group:", reply_markup=InlineKeyboardMarkup(rows))
        return

    if data.startswith("group:"):
        cat, group = data[6:].split("|", 1)
        rows = []
        for pid, p in PRODUCTS.items():
            if p["category"] == cat and (p.get("group_name") or "Other") == group:
                label = "⏳ " + p["name"] if p.get("coming_soon") else f"{p['name']} — ${p['price']:.2f}"
                rows.append([InlineKeyboardButton(label, callback_data="product:" + pid)])
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="cat:" + cat)])
        await q.edit_message_text(f"🛍️ {group}", reply_markup=InlineKeyboardMarkup(rows))
        return

    if data.startswith("product:"):
        pid = data[8:]
        p = PRODUCTS.get(pid)
        if not p:
            await q.edit_message_text("Product not found.", reply_markup=back_button())
            return
        if p.get("coming_soon") or not p.get("active", 1):
            await q.edit_message_text("⏳ COMING SOON\n\nThis product is not available yet.", reply_markup=back_button())
            return
        stock = db.get_product_stock(pid)
        if stock <= 0:
            await q.edit_message_text(f"❌ OUT OF STOCK\n\nContact @{SUPPORT.lstrip('@')} for help.", reply_markup=back_button())
            return
        text = (f"🛍️ {p['name']}\n\n💰 Price: ${p['price']:.2f} each\n"
                f"📦 Available: {stock}\n\nSelect quantity:")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("1", callback_data=f"qty:{pid}:1"),
             InlineKeyboardButton("2", callback_data=f"qty:{pid}:2"),
             InlineKeyboardButton("5", callback_data=f"qty:{pid}:5"),
             InlineKeyboardButton("10", callback_data=f"qty:{pid}:10")],
            [InlineKeyboardButton("✏️ Custom Quantity", callback_data=f"customqty:{pid}")],
            [InlineKeyboardButton("⬅️ Back", callback_data="cat:" + p["category"])],
        ])
        await q.edit_message_text(text, reply_markup=kb)
        return

    if data.startswith("customqty:"):
        pid = data.split(":", 1)[1]
        context.user_data["awaiting_qty"] = pid
        await q.edit_message_text("✏️ Send the quantity as a whole number.\n\nExample: 7", reply_markup=back_button())
        return

    if data.startswith("qty:"):
        _, pid, qty_raw = data.split(":", 2)
        try:
            qty = int(qty_raw)
        except ValueError:
            await q.edit_message_text("❌ Invalid quantity.", reply_markup=back_button())
            return
        await process_purchase(q, context, u, pid, qty)
        return

    if data.startswith("buy:"):
        pid = data[4:]
        await process_purchase(q, context, u, pid, 1)
        return

    if data.startswith("paybin:"):
        order_id = data.split(":", 1)[1]
        order = get_order(order_id)
        if not order:
            await q.edit_message_text("❌ Order not found.", reply_markup=back_button())
            return

        text = (
            "🟡 BINANCE PAY\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"🧾 Order ID: #{order_id}\n"
            f"💰 Amount: ${order['total']:.2f}\n\n"
            "🆔 Binance Pay ID:\n"
            f"{BINANCE_PAY_ID}\n\n"
            "Please send the exact amount using Binance Pay.\n\n"
            "After completing the payment, press:\n"
            "✅ I Have Paid"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ I Have Paid", callback_data=f"paid:{order_id}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="home")],
        ])
        await q.edit_message_text(text, reply_markup=kb)
        return

    if data.startswith("paid:"):
        order_id = data.split(":", 1)[1]
        order = get_order(order_id)
        if not order:
            await q.edit_message_text("❌ Order not found.", reply_markup=back_button())
            return

        if order["status"] in ("WAITING_PAYMENT", "CONFIRMED", "DELIVERED"):
            await q.edit_message_text(
                f"⏳ Order #{order_id} is already being processed.",
                reply_markup=back_button(),
            )
            return

        update_order_status(order_id, "WAITING_PAYMENT")
        product = PRODUCTS.get(order["product_id"], {"name": order["product_id"]})
        admin_text = (
            "🔔 NEW PAYMENT REPORT\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"🧾 Order ID: #{order_id}\n"
            f"👤 User ID: {order['user_id']}\n"
            f"📦 Product: {product['name']}\n"
            f"💰 Amount: ${order['total']:.2f}\n"
            "💳 Payment: Binance Pay\n"
            "📌 Status: WAITING PAYMENT\n\n"
            "Please verify the payment manually."
        )
        admin_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve:{order_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject:{order_id}"),
            ]
        ])

        for admin_id in get_admin_ids():
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_text,
                    reply_markup=admin_kb,
                )
            except Exception as e:
                print(f"Admin notification error: {e}")

        await q.edit_message_text(
            "✅ PAYMENT SUBMITTED\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"🧾 Order ID: #{order_id}\n\n"
            "Your payment report has been sent to our admin.\n\n"
            "⏳ Please wait while your payment is verified.",
            reply_markup=back_button(),
        )
        return

    if data.startswith("approve:"):
        if not is_admin(u.id):
            await q.answer("⛔ Admin only.", show_alert=True)
            return

        order_id = data.split(":", 1)[1]
        order = get_order(order_id)
        if not order:
            await q.edit_message_text("❌ Order not found.")
            return

        if order["status"] == "DELIVERED":
            await q.edit_message_text(f"✅ Order #{order_id} was already delivered.")
            return

        if order["status"] not in ("WAITING_PAYMENT", "PENDING"):
            await q.edit_message_text(
                f"ℹ️ Order #{order_id} status is already {order['status']}."
            )
            return

        product = PRODUCTS.get(order["product_id"], {"name": order["product_id"], "category": "Product"})
        delivery, result = deliver_one_item(
            order_id,
            order["user_id"],
            order["product_id"],
        )

        if result == "OUT_OF_STOCK":
            update_order_status(order_id, "CONFIRMED")
            try:
                await context.bot.send_message(
                    chat_id=order["user_id"],
                    text=(
                        "✅ PAYMENT CONFIRMED\n"
                        "━━━━━━━━━━━━━━━━\n\n"
                        f"🧾 Order ID: #{order_id}\n"
                        f"💰 Amount: ${order['total']:.2f}\n\n"
                        "Your payment has been verified successfully.\n\n"
                        "⚠️ Your product is temporarily out of stock.\n"
                        "Delivery will be completed after stock is available."
                    ),
                )
            except Exception as e:
                print(f"User notification error: {e}")

            await q.edit_message_text(
                f"⚠️ Order #{order_id} approved, but product is OUT OF STOCK."
            )
            return

        if result == "ALREADY_DELIVERED":
            await q.edit_message_text(f"✅ Order #{order_id} was already delivered.")
            return

        if result != "DELIVERED":
            await q.edit_message_text(
                f"❌ Delivery failed for order #{order_id}. Please check Railway logs."
            )
            return

        try:
            await send_delivery(context, order, product, delivery)
        except Exception as e:
            print(f"Delivery notification error: {e}")
            # The inventory item is already marked SOLD and the order DELIVERED.
            # Keep that state to prevent duplicate delivery.

        await q.edit_message_text(
            f"✅ Order #{order_id} approved and DELIVERED."
        )
        return

    if data.startswith("reject:"):
        if not is_admin(u.id):
            await q.answer("⛔ Admin only.", show_alert=True)
            return

        order_id = data.split(":", 1)[1]
        order = get_order(order_id)
        if not order:
            await q.edit_message_text("❌ Order not found.")
            return

        if order["status"] == "DELIVERED":
            await q.edit_message_text("❌ This order has already been delivered.")
            return

        update_order_status(order_id, "REJECTED")

        try:
            await context.bot.send_message(
                chat_id=order["user_id"],
                text=(
                    "❌ PAYMENT REJECTED\n"
                    "━━━━━━━━━━━━━━━━\n\n"
                    f"🧾 Order ID: #{order_id}\n\n"
                    "We could not verify your payment.\n\n"
                    "Please contact support if you believe this is an error."
                ),
            )
        except Exception as e:
            print(f"User notification error: {e}")

        await q.edit_message_text(f"❌ Order #{order_id} rejected.")
        return

    if data == "orders":
        rows = db.get_orders(u.id)
        if not rows:
            text = "📦 MY ORDERS\n\nNo orders yet."
        else:
            text = "📦 MY ORDERS\n━━━━━━━━━━━━━━━━\n"
            for r in rows:
                p = PRODUCTS.get(r["product_id"], {"name": r["product_id"]})
                text += (
                    f"#{r['order_id']} — {p['name']} — "
                    f"${r['total']:.2f} — {r['status']}\n"
                )

        await q.edit_message_text(text, reply_markup=back_button())
        return

    if data == "payments":
        user = db.get_user(u.id)
        balance = user["balance"] if user else 0.0
        await q.edit_message_text(
            "💰 PAYMENT METHODS\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"💳 Your Balance: ${balance:.2f}\n\n"
            "🟡 Binance Pay\n"
            "Add balance using Binance Pay.\n"
            "Payment verification is handled manually by admin.\n\n"
            "🔵 USDT TRC20\n"
            "Coming later.",
            reply_markup=balance_menu(),
        )
        return

    if data == "show_balance":
        user = db.get_user(u.id)
        balance = user["balance"] if user else 0.0
        await q.edit_message_text(
            "💳 MY BALANCE\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"Available Balance: ${balance:.2f}\n\n"
            "Use your balance for future purchases without making a new payment.",
            reply_markup=balance_menu(),
        )
        return

    if data == "add_balance":
        context.user_data["awaiting_balance_amount"] = True
        await q.edit_message_text(
            "➕ ADD BALANCE\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "Enter the amount in USD you want to add.\n\n"
            "Examples: 10, 25.50, 100\n\n"
            "❌ Send /cancel to cancel.",
            reply_markup=back_button(),
        )
        return

    if data.startswith("balpay:"):
        request_id = data.split(":", 1)[1]
        request = db.get_balance_request(request_id)
        if not request or request["user_id"] != u.id:
            await q.edit_message_text("❌ Balance request not found.", reply_markup=back_button())
            return
        await q.edit_message_text(
            "🟡 ADD BALANCE — BINANCE PAY\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"🧾 Request ID: #{request_id}\n"
            f"💰 Amount: ${request['amount']:.2f}\n\n"
            "🆔 Binance Pay ID:\n"
            f"{BINANCE_PAY_ID}\n\n"
            "Please send the exact amount using Binance Pay.\n\n"
            "After completing the payment, press:\n"
            "✅ I Have Paid",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ I Have Paid", callback_data=f"balpaid:{request_id}")],
                [InlineKeyboardButton("❌ Cancel", callback_data="home")],
            ]),
        )
        return

    if data.startswith("balpaid:"):
        request_id = data.split(":", 1)[1]
        request = db.get_balance_request(request_id)
        if not request or request["user_id"] != u.id:
            await q.edit_message_text("❌ Balance request not found.", reply_markup=back_button())
            return
        if request["status"] != "PENDING":
            await q.edit_message_text(
                f"⏳ Balance request #{request_id} is already {request['status']}.",
                reply_markup=back_button(),
            )
            return
        db.update_balance_request_status(request_id, "WAITING_PAYMENT")
        admin_text = (
            "💰 NEW BALANCE PAYMENT\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"🧾 Request ID: #{request_id}\n"
            f"👤 User ID: {request['user_id']}\n"
            f"💵 Add Balance: ${request['amount']:.2f}\n"
            "💳 Payment: Binance Pay\n"
            "📌 Status: WAITING PAYMENT\n\n"
            "Please verify the payment manually."
        )
        admin_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"balapprove:{request_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"balreject:{request_id}"),
        ]])
        for admin_id in get_admin_ids():
            try:
                await context.bot.send_message(chat_id=admin_id, text=admin_text, reply_markup=admin_kb)
            except Exception as e:
                print(f"Admin balance notification error: {e}")
        await q.edit_message_text(
            "✅ BALANCE PAYMENT SUBMITTED\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"🧾 Request ID: #{request_id}\n"
            f"💰 Amount: ${request['amount']:.2f}\n\n"
            "⏳ Please wait while admin verifies your payment.",
            reply_markup=back_button(),
        )
        return

    if data.startswith("balapprove:"):
        if not is_admin(u.id):
            await q.answer("⛔ Admin only.", show_alert=True)
            return
        request_id = data.split(":", 1)[1]
        request = db.get_balance_request(request_id)
        if not request:
            await q.edit_message_text("❌ Balance request not found.")
            return
        if request["status"] == "APPROVED":
            await q.edit_message_text(f"✅ Balance request #{request_id} was already approved.")
            return
        if request["status"] not in ("WAITING_PAYMENT", "PENDING"):
            await q.edit_message_text(f"ℹ️ Request #{request_id} status is {request['status']}.")
            return
        new_balance = db.approve_balance_request(request_id)
        if new_balance is None:
            await q.edit_message_text("❌ Could not approve this balance request.")
            return
        try:
            await context.bot.send_message(
                chat_id=request["user_id"],
                text=(
                    "✅ BALANCE ADDED\n"
                    "━━━━━━━━━━━━━━━━\n\n"
                    f"🧾 Request ID: #{request_id}\n"
                    f"💰 Added: ${request['amount']:.2f}\n"
                    f"💳 New Balance: ${new_balance:.2f}\n\n"
                    "Your balance is now ready to use for future purchases."
                ),
            )
        except Exception as e:
            print(f"Balance user notification error: {e}")
        await q.edit_message_text(
            f"✅ Balance request #{request_id} approved.\n"
            f"💰 Added: ${request['amount']:.2f}\n"
            f"💳 New Balance: ${new_balance:.2f}"
        )
        return

    if data.startswith("balreject:"):
        if not is_admin(u.id):
            await q.answer("⛔ Admin only.", show_alert=True)
            return
        request_id = data.split(":", 1)[1]
        request = db.get_balance_request(request_id)
        if not request:
            await q.edit_message_text("❌ Balance request not found.")
            return
        if request["status"] == "APPROVED":
            await q.edit_message_text("❌ This balance has already been added.")
            return
        db.update_balance_request_status(request_id, "REJECTED")
        try:
            await context.bot.send_message(
                chat_id=request["user_id"],
                text=(
                    "❌ BALANCE PAYMENT REJECTED\n"
                    "━━━━━━━━━━━━━━━━\n\n"
                    f"🧾 Request ID: #{request_id}\n"
                    f"💰 Amount: ${request['amount']:.2f}\n\n"
                    "We could not verify your payment.\n"
                    "Please contact support if you believe this is an error."
                ),
            )
        except Exception as e:
            print(f"Balance reject notification error: {e}")
        await q.edit_message_text(f"❌ Balance request #{request_id} rejected.")
        return

    if data == "refer":
        bot = await context.bot.get_me()
        link = f"https://t.me/{bot.username}?start=ref_{u.id}"
        refs = db.get_ref_count(u.id)
        user = db.get_user(u.id)

        await q.edit_message_text(
            "👥 REFER & EARN\n"
            "━━━━━━━━━━━━━━━━\n"
            f"🎯 Your link:\n{link}\n\n"
            f"📊 Total Refs: {refs}\n"
            f"🎁 Ref Income: ${user['ref_income']:.2f}",
            reply_markup=back_button(),
        )
        return

    if data == "support":
        await q.edit_message_text(
            "🎧 SUPPORT\n"
            "━━━━━━━━━━━━━━━━\n"
            f"Contact: @{SUPPORT.lstrip('@')}",
            reply_markup=back_button(),
        )
        return


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_qty"):
        pid = context.user_data.pop("awaiting_qty")
        try:
            qty = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("❌ Invalid quantity. Send a whole number, e.g. 5.")
            return
        qmsg = update.message
        class QWrap:
            from_user = qmsg.from_user
            async def edit_message_text(self, *args, **kwargs):
                return await qmsg.reply_text(*args, **kwargs)
        await process_purchase(QWrap(), context, update.effective_user, pid, qty)
        return
    if not context.user_data.get("awaiting_balance_amount"):
        return
    raw = update.message.text.strip().replace(",", "")
    if raw.lower() == "/cancel":
        context.user_data.pop("awaiting_balance_amount", None)
        await update.message.reply_text("❌ Add Balance cancelled.", reply_markup=main_menu())
        return
    try:
        amount = float(raw)
    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Enter a valid USD amount, e.g. 10 or 25.50")
        return
    if amount <= 0:
        await update.message.reply_text("❌ Amount must be greater than $0.")
        return
    if amount > 10000:
        await update.message.reply_text("❌ Maximum balance top-up is $10,000.")
        return
    amount = round(amount, 2)
    u = update.effective_user
    db.upsert_user(u.id, u.full_name, u.username, None)
    request_id = db.create_balance_request(u.id, amount)
    context.user_data.pop("awaiting_balance_amount", None)
    await update.message.reply_text(
        "💰 ADD BALANCE\n━━━━━━━━━━━━━━━━\n\n"
        f"💵 Amount: ${amount:.2f}\n\nChoose Binance Pay to continue.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🟡 Pay with Binance Pay", callback_data=f"balpay:{request_id}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="home")],
        ]),
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ids = get_admin_ids()
    await update.message.reply_text(
        "🆔 YOUR TELEGRAM ID\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"<code>{uid}</code>\n\n"
        f"Admin status: {'✅ YES' if uid in ids else '❌ NO'}\n"
        f"Loaded ADMIN_IDS: <code>{', '.join(map(str, sorted(ids))) or 'EMPTY'}</code>",
        parse_mode="HTML",
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ids = get_admin_ids()

    if uid not in ids:
        await update.message.reply_text(
            "⛔ ADMIN ACCESS DENIED\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"Your Telegram ID:\n<code>{uid}</code>\n\n"
            f"Loaded ADMIN_IDS:\n<code>{', '.join(map(str, sorted(ids))) or 'EMPTY'}</code>\n\n"
            "If this is your ID, put it in Railway → Variables → ADMIN_IDS, "
            "then redeploy/restart the service.",
            parse_mode="HTML",
        )
        return

    await update.message.reply_text(
        "🛠️ ADMIN PANEL\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Choose an admin action:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard")],
            [InlineKeyboardButton("📦 Stock", callback_data="admin_stock")],
            [InlineKeyboardButton("💰 Payments", callback_data="admin_payments")],
            [InlineKeyboardButton("💳 Balance Requests", callback_data="admin_balances")],
            [InlineKeyboardButton("🧾 Orders", callback_data="admin_orders")],
            [InlineKeyboardButton("👥 Users", callback_data="admin_users")],
            [InlineKeyboardButton("🎁 Referrals", callback_data="admin_refs")],
            [InlineKeyboardButton("⬅️ Main Menu", callback_data="home")],
        ]),
    )


async def admin_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("⛔ Admin only.", show_alert=True)
        return
    await q.answer()
    data = q.data

    if data == "admin_dashboard":
        try:
            rows = db.get_products_stock()
            users = db.get_all_users_count() if hasattr(db, "get_all_users_count") else None
            text = "📊 ADMIN DASHBOARD\n━━━━━━━━━━━━━━━━\n\n"
            if users is not None:
                text += f"👥 Users: {users}\n"
            text += f"📦 Product types: {len(rows)}\n"
            text += "\nUse /stock for exact available stock."
        except Exception as e:
            text = f"📊 ADMIN DASHBOARD\n\nCould not load dashboard: {e}"
    elif data == "admin_stock":
        rows = db.get_products_stock()
        if not rows:
            text = "📦 STOCK\n━━━━━━━━━━━━━━━━\n\nStock is empty."
        else:
            text = "📦 STOCK\n━━━━━━━━━━━━━━━━\n\n"
            for r in rows:
                p = PRODUCTS.get(r["product_id"], {"name": r["product_id"]})
                text += f"• {p['name']}: {r['c']}\n"
    elif data == "admin_payments":
        text = "💰 PAYMENTS\n━━━━━━━━━━━━━━━━\n\nPending payment reports appear here when customers press I Have Paid."
    elif data == "admin_balances":
        text = "💳 BALANCE REQUESTS\n━━━━━━━━━━━━━━━━\n\nBalance payment reports appear here when customers press I Have Paid."
    elif data == "admin_orders":
        text = "🧾 ORDERS\n━━━━━━━━━━━━━━━━\n\nUse /orders to open the admin order view."
    elif data == "admin_users":
        text = "👥 USERS\n━━━━━━━━━━━━━━━━\n\nUse /myid to verify your own Telegram ID."
    elif data == "admin_refs":
        rate = float(db.get_setting("REFERRAL_RATE", "0.05"))
        limit = int(db.get_setting("REFERRAL_DEPOSIT_LIMIT", "10"))
        text = (
            "🎁 REFERRALS\n━━━━━━━━━━━━━━━━\n\n"
            f"Commission: {rate * 100:.2f}%\n"
            f"Deposit limit: first {limit}\n\n"
            "Change: /refrate 7.5 or /reflimit 20"
        )
    else:
        text = "🛠️ ADMIN PANEL"

    await q.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_back")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="home")],
        ]),
    )


async def admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("⛔ Admin only.", show_alert=True)
        return
    await q.answer()
    await q.edit_message_text(
        "🛠️ ADMIN PANEL\n━━━━━━━━━━━━━━━━\n\nChoose an admin action:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard")],
            [InlineKeyboardButton("📦 Stock", callback_data="admin_stock")],
            [InlineKeyboardButton("💰 Payments", callback_data="admin_payments")],
            [InlineKeyboardButton("💳 Balance Requests", callback_data="admin_balances")],
            [InlineKeyboardButton("🧾 Orders", callback_data="admin_orders")],
            [InlineKeyboardButton("👥 Users", callback_data="admin_users")],
            [InlineKeyboardButton("🎁 Referrals", callback_data="admin_refs")],
            [InlineKeyboardButton("⬅️ Main Menu", callback_data="home")],
        ]),
    )


async def addstock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if len(context.args) != 3:
        await update.message.reply_text(
            "Usage:\n/addstock <product_id> <email> <password>"
        )
        return

    pid, email, password = context.args

    if pid not in PRODUCTS:
        await update.message.reply_text("❌ Unknown product_id.")
        return

    db.add_stock(pid, email, password)
    await update.message.reply_text("✅ Stock added successfully.")


async def stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    rows = db.get_products_stock()
    if not rows:
        await update.message.reply_text("📦 Stock is empty.")
        return

    text = "📦 AVAILABLE STOCK\n━━━━━━━━━━━━━━━━\n"
    for r in rows:
        p = PRODUCTS.get(r["product_id"], {"name": r["product_id"]})
        text += f"{p['name']}: {r['c']}\n"

    await update.message.reply_text(text)


async def orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    await update.message.reply_text(
        "📦 ADMIN ORDERS\n\n"
        "Payment reports will appear here in Telegram when customers press 'I Have Paid'."
    )


def run():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("addstock", addstock))
    app.add_handler(CommandHandler("stock", stock))
    app.add_handler(CommandHandler("orders", orders))
    app.add_handler(CallbackQueryHandler(admin_back, pattern=r"^admin_back$"))
    app.add_handler(CallbackQueryHandler(admin_menu_callback, pattern=r"^admin_(dashboard|stock|payments|balances|orders|users|refs)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(CallbackQueryHandler(callback))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    run()
