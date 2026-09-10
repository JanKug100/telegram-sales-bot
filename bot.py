import os
from dotenv import load_dotenv

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

import db
from config import PRODUCTS


# =========================
# ENVIRONMENT VARIABLES
# =========================

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


# =========================
# DATABASE
# =========================

db.init_db()


# =========================
# MAIN MENU
# =========================

def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🧑‍💼 My Profile",
                callback_data="profile"
            )
        ],
        [
            InlineKeyboardButton(
                "🛍️ Buy Products",
                callback_data="products"
            )
        ],
        [
            InlineKeyboardButton(
                "📦 My Orders",
                callback_data="orders"
            )
        ],
        [
            InlineKeyboardButton(
                "💰 Payment Methods",
                callback_data="payments"
            )
        ],
        [
            InlineKeyboardButton(
                "👥 Refer",
                callback_data="refer"
            )
        ],
        [
            InlineKeyboardButton(
                "🎧 Support",
                callback_data="support"
            )
        ],
    ])


def back_button():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⬅️ Main Menu",
                callback_data="home"
            )
        ]
    ])


# =========================
# START COMMAND
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    u = update.effective_user

    referred_by = None

    if context.args and context.args[0].isdigit():

        candidate = int(context.args[0])

        if candidate != u.id:
            referred_by = candidate

    db.upsert_user(
        u.id,
        u.full_name,
        u.username,
        referred_by
    )

    text = (
        "🏠 MAIN MENU\n"
        "━━━━━━━━━━━━━━━━\n"
        "Welcome to the store!\n\n"
        "Choose an option below."
    )

    await update.message.reply_text(
        text,
        reply_markup=main_menu()
    )


# =========================
# GET ORDER
# =========================

def get_order(order_id):

    with db.connect() as con:

        row = con.execute(
            """
            SELECT *
            FROM orders
            WHERE order_id = ?
            """,
            (order_id,)
        ).fetchone()

        return row


# =========================
# UPDATE ORDER STATUS
# =========================

def update_order_status(order_id, status):

    with db.connect() as con:

        con.execute(
            """
            UPDATE orders
            SET status = ?
            WHERE order_id = ?
            """,
            (status, order_id)
        )

        con.commit()


# =========================
# CALLBACK HANDLER
# =========================

async def callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    q = update.callback_query

    await q.answer()

    u = update.effective_user

    data = q.data


    # =========================
    # HOME
    # =========================

    if data == "home":

        await q.edit_message_text(
            "🏠 MAIN MENU",
            reply_markup=main_menu()
        )

        return


    # =========================
    # PROFILE
    # =========================

    if data == "profile":

        user = db.get_user(u.id)

        refs = db.get_ref_count(u.id)

        username = (
            f"@{user['username']}"
            if user["username"]
            else "@N/A"
        )

        bot = await context.bot.get_me()

        ref_link = (
            f"https://t.me/{bot.username}?start={u.id}"
        )

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

        await q.edit_message_text(
            text,
            reply_markup=back_button()
        )

        return


    # =========================
    # PRODUCTS
    # =========================

    if data == "products":

        cats = sorted(
            set(
                p["category"]
                for p in PRODUCTS.values()
            )
        )

        rows = []

        for c in cats:

            rows.append([
                InlineKeyboardButton(
                    c,
                    callback_data="cat:" + c
                )
            ])

        rows.append([
            InlineKeyboardButton(
                "⬅️ Back",
                callback_data="home"
            )
        ])

        await q.edit_message_text(
            "🛍️ BUY PRODUCTS",
            reply_markup=InlineKeyboardMarkup(rows)
        )

        return


    # =========================
    # CATEGORY
    # =========================

    if data.startswith("cat:"):

        cat = data[4:]

        rows = []

        for pid, p in PRODUCTS.items():

            if p["category"] == cat:

                rows.append([
                    InlineKeyboardButton(
                        f"{p['name']} — ${p['price']:.2f}",
                        callback_data="product:" + pid
                    )
                ])

        rows.append([
            InlineKeyboardButton(
                "⬅️ Back",
                callback_data="products"
            )
        ])

        await q.edit_message_text(
            f"🛍️ {cat}",
            reply_markup=InlineKeyboardMarkup(rows)
        )

        return


    # =========================
    # PRODUCT
    # =========================

    if data.startswith("product:"):

        pid = data[8:]

        p = PRODUCTS.get(pid)

        if not p:

            await q.edit_message_text(
                "Product not found.",
                reply_markup=back_button()
            )

            return

        text = (
            f"🛍️ {p['name']}\n\n"
            f"💰 Price: ${p['price']:.2f}\n"
            "🔢 Quantity: 1\n\n"
            "Choose an action:"
        )

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🛒 Buy — $%.2f" % p["price"],
                    callback_data="buy:" + pid
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Back",
                    callback_data="cat:" + p["category"]
                )
            ]
        ])

        await q.edit_message_text(
            text,
            reply_markup=kb
        )

        return


    # =========================
    # BUY
    # =========================

    if data.startswith("buy:"):

        pid = data[4:]

        p = PRODUCTS.get(pid)

        if not p:

            await q.edit_message_text(
                "Product not found.",
                reply_markup=back_button()
