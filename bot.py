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

ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Put it in Railway Variables.")

db.init_db()


def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧑‍💼 My Profile", callback_data="profile")],
        [InlineKeyboardButton("🛍️ Buy Products", callback_data="products")],
        [InlineKeyboardButton("📦 My Orders", callback_data="orders")],
        [InlineKeyboardButton("💰 Payment Methods", callback_data="payments")],
        [InlineKeyboardButton("👥 Refer", callback_data="refer")],
        [InlineKeyboardButton("🎧 Support", callback_data="support")],
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

    if context.args and context.args[0].isdigit():
        candidate = int(context.args[0])
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


async def send_delivery(context, order, product, delivery):
    text = (
        "🎉 DELIVERY SUCCESSFUL!\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"🧾 Order ID: #{order['order_id']}\n"
        f"📦 Item: {product['name']}\n"
        f"🏷 Category: {product['category']}\n"
        f"🔢 Quantity: {order['quantity']}\n"
        f"💰 Total Price: ${order['total']:.2f}\n\n"
        "📧 Email / Username:\n"
        f"{delivery['email']}\n\n"
        "🔑 Password:\n"
        f"{delivery['password']}\n\n"
        + (f"💳 Remaining Balance: ${delivery['new_balance']:.2f}\n\n" if 'new_balance' in delivery else "")
        + f"🕒 {delivery['delivered_at']}"
    )

    await context.bot.send_message(
        chat_id=order["user_id"],
        text=text,
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
        ref_link = f"https://t.me/{bot.username}?start={u.id}"

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
        rows = []
        for pid, p in PRODUCTS.items():
            if p["category"] == cat:
                rows.append([
                    InlineKeyboardButton(
                        f"{p['name']} — ${p['price']:.2f}",
                        callback_data="product:" + pid,
                    )
                ])
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="products")])
        await q.edit_message_text(
            f"🛍️ {cat}",
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return

    if data.startswith("product:"):
        pid = data[8:]
        p = PRODUCTS.get(pid)
        if not p:
            await q.edit_message_text("Product not found.", reply_markup=back_button())
            return

        text = (
            f"🛍️ {p['name']}\n\n"
            f"💰 Price: ${p['price']:.2f}\n"
            "🔢 Quantity: 1\n\n"
            "Choose an action:"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 Buy — $%.2f" % p["price"], callback_data="buy:" + pid)],
            [InlineKeyboardButton("⬅️ Back", callback_data="cat:" + p["category"])],
        ])
        await q.edit_message_text(text, reply_markup=kb)
        return

    if data.startswith("buy:"):
        pid = data[4:]
        p = PRODUCTS.get(pid)
        if not p:
            await q.edit_message_text("Product not found.", reply_markup=back_button())
            return

        user = db.get_user(u.id)
        if not user:
            db.upsert_user(u.id, u.full_name, u.username, None)
            user = db.get_user(u.id)

        # Enough balance: create order, debit balance and deliver immediately.
        if float(user["balance"]) + 1e-9 >= float(p["price"]):
            order_id = db.create_order(u.id, pid, 1, p["price"], "Balance")
            order = get_order(order_id)
            delivery, result = purchase_from_balance(order_id, u.id, pid, p["price"])

            if result == "DELIVERED":
                try:
                    await send_delivery(context, order, p, delivery)
                except Exception as e:
                    print(f"Delivery notification error: {e}")
                await q.edit_message_text(
                    "✅ PURCHASE COMPLETED\n"
                    "━━━━━━━━━━━━━━━━\n\n"
                    f"🧾 Order ID: #{order_id}\n"
                    f"📦 Product: {p['name']}\n"
                    f"💳 Paid from Balance: ${p['price']:.2f}\n"
                    f"💰 Remaining Balance: ${delivery['new_balance']:.2f}\n\n"
                    "📦 Your product has been delivered.",
                    reply_markup=back_button(),
                )
                return

            if result == "OUT_OF_STOCK":
                update_order_status(order_id, "OUT_OF_STOCK")
                await q.edit_message_text(
                    "⚠️ OUT OF STOCK\n\n"
                    "This product is currently unavailable. Your balance was not charged.",
                    reply_markup=back_button(),
                )
                return

            if result != "INSUFFICIENT_BALANCE":
                update_order_status(order_id, "CANCELLED")
                await q.edit_message_text(
                    "❌ Purchase failed. Your balance was not charged.",
                    reply_markup=back_button(),
                )
                return

            # Race-safe fallback: if balance changed before the transaction, use Binance Pay.
            update_order_status(order_id, "CANCELLED")

        order_id = db.create_order(u.id, pid, 1, p["price"], "Binance Pay")
        user = db.get_user(u.id)
        text = (
            f"🧾 ORDER #{order_id}\n\n"
            f"📦 Product: {p['name']}\n"
            f"💵 Total: ${p['price']:.2f}\n"
            f"💳 Your Balance: ${user['balance']:.2f}\n\n"
            "Your balance is not enough for this purchase.\n"
            "Please pay the full amount using Binance Pay."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🟡 Binance Pay", callback_data=f"paybin:{order_id}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="home")],
        ])
        await q.edit_message_text(text, reply_markup=kb)
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

        for admin_id in ADMIN_IDS:
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
        if u.id not in ADMIN_IDS:
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
        if u.id not in ADMIN_IDS:
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
        for admin_id in ADMIN_IDS:
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
        if u.id not in ADMIN_IDS:
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
        if u.id not in ADMIN_IDS:
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
        link = f"https://t.me/{bot.username}?start={u.id}"
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


async def addstock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
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
    if update.effective_user.id not in ADMIN_IDS:
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
    if update.effective_user.id not in ADMIN_IDS:
        return

    await update.message.reply_text(
        "📦 ADMIN ORDERS\n\n"
        "Payment reports will appear here in Telegram when customers press 'I Have Paid'."
    )


def run():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addstock", addstock))
    app.add_handler(CommandHandler("stock", stock))
    app.add_handler(CommandHandler("orders", orders))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(CallbackQueryHandler(callback))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    run()
