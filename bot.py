import os
import sqlite3
from datetime import datetime
from contextlib import closing

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

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
        f"🕒 {delivery['delivered_at']}"
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

        order_id = db.create_order(u.id, pid, 1, p["price"], "Binance Pay")
        text = (
            f"🧾 ORDER #{order_id}\n\n"
            f"📦 Product: {p['name']}\n"
            f"💵 Total: ${p['price']:.2f}\n\n"
            "💳 Payment Method\n"
            "🟡 Binance Pay\n\n"
            "Click below to view payment details."
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
        await q.edit_message_text(
            "💰 PAYMENT METHODS\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "🟡 Binance Pay\n\n"
            "Payment verification is handled manually by admin.\n\n"
            "🔵 USDT TRC20\n"
            "Coming later.",
            reply_markup=back_button(),
        )
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
    app.add_handler(CallbackQueryHandler(callback))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    run()
