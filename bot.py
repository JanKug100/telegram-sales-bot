import os
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

import db
from config import PRODUCTS

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "").strip()
SUPPORT = os.getenv("SUPPORT_USERNAME", "YourSupportUsername").strip()
BINANCE_PAY_ID = os.getenv("BINANCE_PAY_ID", "").strip()
ADMIN_IDS = {
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Put it in .env")

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    referred_by = None
    if context.args and context.args[0].isdigit():
        candidate = int(context.args[0])
        if candidate != u.id:
            referred_by = candidate
    db.upsert_user(u.id, u.full_name, u.username, referred_by)

    text = (
        "🏠 MAIN MENU\n"
        "━━━━━━━━━━━━━━━━\n"
        "Welcome to the store!\n\n"
        "Choose an option below."
    )
    await update.message.reply_text(text, reply_markup=main_menu())

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
        cats = sorted(set(p["category"] for p in PRODUCTS.values()))
        rows = [[InlineKeyboardButton(c, callback_data="cat:"+c)] for c in cats]
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="home")])
        await q.edit_message_text("🛍️ BUY PRODUCTS", reply_markup=InlineKeyboardMarkup(rows))
        return

    if data.startswith("cat:"):
        cat = data[4:]
        rows = []
        for pid, p in PRODUCTS.items():
            if p["category"] == cat:
                rows.append([InlineKeyboardButton(
                    f"{p['name']} — ${p['price']:.2f}",
                    callback_data="product:"+pid
                )])
        rows.append([InlineKeyboardButton("⬅️ Back", callback_data="products")])
        await q.edit_message_text(f"🛍️ {cat}", reply_markup=InlineKeyboardMarkup(rows))
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
            [InlineKeyboardButton("🛒 Buy — $%.2f" % p["price"], callback_data="buy:"+pid)],
            [InlineKeyboardButton("⬅️ Back", callback_data="cat:"+p["category"])]
        ])
        await q.edit_message_text(text, reply_markup=kb)
        return

    if data.startswith("buy:"):
    pid = data[4:]
    p = PRODUCTS[pid]

    order_id = db.create_order(
        u.id,
        pid,
        1,
        p["price"],
        "Binance Pay"
    )

    text = (
        f"🧾 ORDER #{order_id}\n\n"
        f"📦 Product: {p['name']}\n"
        f"💵 Total: ${p['price']:.2f}\n\n"
        "💳 Payment Method\n"
        "🟡 Binance Pay\n\n"
        "Click the button below to view payment details."
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🟡 Binance Pay",
            callback_data=f"paybin:{order_id}"
        )],
        [InlineKeyboardButton(
            "❌ Cancel",
            callback_data="home"
        )]
    ])

    await q.edit_message_text(text, reply_markup=kb)
    return


if data.startswith("paybin:"):
    order_id = data.split(":")[1]

    text = (
        f"🟡 BINANCE PAY\n\n"
        f"🧾 Order ID: #{order_id}\n\n"
        f"💰 Please pay the exact order amount using Binance Pay.\n\n"
        f"🆔 Binance Pay ID:\n"
        f"{BINANCE_PAY_ID}\n\n"
        "After completing the payment, click:\n"
        "✅ I Have Paid"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "✅ I Have Paid",
            callback_data=f"paid:{order_id}"
        )],
        [InlineKeyboardButton(
            "❌ Cancel",
            callback_data="home"
        )]
    ])

    await q.edit_message_text(text, reply_markup=kb)
    return

    if data == "orders":
        rows = db.get_orders(u.id)
        if not rows:
            text = "📦 MY ORDERS\n\nNo orders yet."
        else:
            text = "📦 MY ORDERS\n━━━━━━━━━━━━━━━━\n"
            for r in rows:
                p = PRODUCTS.get(r["product_id"], {"name": r["product_id"]})
                text += f"#{r['order_id']} — {p['name']} — ${r['total']:.2f} — {r['status']}\n"
        await q.edit_message_text(text, reply_markup=back_button())
        return

    if data == "payments":
        await q.edit_message_text(
            "💰 PAYMENT METHODS\n━━━━━━━━━━━━━━━━\n"
            "🟡 Binance Pay\n"
            "🔵 USDT — TRC20\n\n"
            "Payment verification will be connected in the next version.",
            reply_markup=back_button()
        )
        return

    if data == "refer":
        bot = await context.bot.get_me()
        link = f"https://t.me/{bot.username}?start={u.id}"
        refs = db.get_ref_count(u.id)
        user = db.get_user(u.id)
        await q.edit_message_text(
            "👥 REFER & EARN\n━━━━━━━━━━━━━━━━\n"
            f"🎯 Your link:\n{link}\n\n"
            f"📊 Total Refs: {refs}\n"
            f"🎁 Ref Income: ${user['ref_income']:.2f}",
            reply_markup=back_button()
        )
        return

    if data == "support":
        await q.edit_message_text(
            f"🎧 SUPPORT\n━━━━━━━━━━━━━━━━\n"
            f"Contact: @{SUPPORT.lstrip('@')}",
            reply_markup=back_button()
        )
        return

def back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Main Menu", callback_data="home")]])

async def addstock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if len(context.args) != 3:
        await update.message.reply_text(
            "Usage:\n/addstock <product_id> <email> <password>\n\n"
            "Example product_id: piavpn_7"
        )
        return
    pid, email, password = context.args
    if pid not in PRODUCTS:
        await update.message.reply_text("Unknown product_id.")
        return
    db.add_stock(pid, email, password)
    await update.message.reply_text("✅ Stock added.")

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
        "Admin order reporting is reserved for the next admin-panel iteration."
    )

def run():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addstock", addstock))
    app.add_handler(CommandHandler("stock", stock))
    app.add_handler(CommandHandler("orders", orders))
    app.add_handler(CallbackQueryHandler(callback))
    app.run_polling()

if __name__ == "__main__":
    run()
