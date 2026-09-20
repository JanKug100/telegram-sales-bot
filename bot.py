import os

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# ==============================
# BOT TOKEN
# ==============================

BOT_TOKEN = os.getenv("BOT_TOKEN")


# ==============================
# MAIN MENU KEYBOARD
# ==============================

def main_menu_keyboard():
    keyboard = [
        ["🧑‍💼 My Profile", "🛍️ Buy Products"],
        ["💰 Add Balance", "📦 My Orders"],
        ["👥 Refer", "🎧 Support"]
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )


# ==============================
# /START COMMAND
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🏠 MAIN MENU",
        reply_markup=main_menu_keyboard()
    )


# ==============================
# MY PROFILE
# ==============================

async def my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    # Telegram name
    name = user.full_name

    # Telegram username
    if user.username:
        username = f"@{user.username}"
    else:
        username = "@N/A"

    # Telegram User ID
    user_id = user.id

    # Temporary values
    # এগুলো পরবর্তীতে Database/Admin Panel থেকে আসবে
    balance = 10.00
    total_refs = 20
    ref_income = 5.00
    commission = 5

    # Referral link
    bot_username = context.bot.username

    if bot_username:
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    else:
        ref_link = f"ref_{user_id}"

    profile_text = (
        "👤 ACCOUNT DASHBOARD\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🏷 Name: {name}\n"
        f"🔰 Username: {username}\n"
        f"🆔 User ID: {user_id}\n"
        "━━━━━━━━━━━━━━━━\n"
        f"💳 Balance: ${balance:.2f}\n"
        f"🎯 Ref Link: {ref_link}\n"
        f"💰 Refer {commission}% commission "
        f"{{first 10 time deposit}}\n"
        f"📊 Total Refs: {total_refs}\n"
        f"🎁 Ref Income: ${ref_income:.2f}"
    )

    await update.message.reply_text(profile_text)


# ==============================
# TEXT MESSAGE HANDLER
# ==============================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    text = update.message.text

    if text == "🧑‍💼 My Profile":
        await my_profile(update, context)


# ==============================
# START BOT
# ==============================

def main():

    application = Application.builder().token(BOT_TOKEN).build()

    # /start
    application.add_handler(
        CommandHandler("start", start)
    )

    # Keyboard buttons
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    print("Bot is running...")

    application.run_polling()


# ==============================
# RUN
# ==============================

if __name__ == "__main__":
    main()
