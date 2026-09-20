import os

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# ==========================================
# BOT TOKEN
# ==========================================

BOT_TOKEN = os.getenv("BOT_TOKEN")


# ==========================================
# REFERRAL SETTINGS
# ==========================================

# বর্তমানে Referral Commission 5%
# ভবিষ্যতে Admin Panel থেকে পরিবর্তন করা যাবে।
REFERRAL_COMMISSION = 5

# প্রথম 10টি deposit-এর উপর referral commission
REFERRAL_DEPOSIT_LIMIT = 10


# ==========================================
# MAIN MENU KEYBOARD
# ==========================================

def main_menu_keyboard():

    keyboard = [
        ["🧑‍💼 My Profile", "🛍️ Buy Products"],
        ["💰 Add Balance", "📦 My Orders"],
        ["👥 Refer", "🎧 Support"],
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )


# ==========================================
# /START
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🏠 MAIN MENU",
        reply_markup=main_menu_keyboard()
    )


# ==========================================
# MY PROFILE
# ==========================================

async def my_profile(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    # ------------------------------------------
    # Telegram Name
    # ------------------------------------------

    telegram_name = user.full_name

    # ------------------------------------------
    # Telegram Username
    # ------------------------------------------

    if user.username:
        username = f"@{user.username}"
    else:
        username = "@N/A"

    # ------------------------------------------
    # Telegram User ID
    # ------------------------------------------

    user_id = user.id

    # ------------------------------------------
    # Current temporary values
    #
    # এগুলো এখন default value।
    # পরবর্তীতে Database থেকে আসবে।
    # ------------------------------------------

    balance = 0.00
    total_refs = 0
    ref_income = 0.00

    # ------------------------------------------
    # Referral Link
    # ------------------------------------------

    bot_username = context.bot.username

    if bot_username:
        referral_link = (
            f"https://t.me/{bot_username}?start=ref_{user_id}"
        )
    else:
        referral_link = "Referral link unavailable"

    # ------------------------------------------
    # Account Dashboard
    # ------------------------------------------

    profile_text = (
        "👤 ACCOUNT DASHBOARD\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🏷 Name: {telegram_name}\n"
        f"🔰 Username: {username}\n"
        f"🆔 User ID: {user_id}\n"
        "━━━━━━━━━━━━━━━━\n"
        f"💳 Balance: ${balance:.2f}\n"
        f"🎯 Ref Link: {referral_link}\n"
        f"💰 Refer {REFERRAL_COMMISSION}% commission "
        f"{{first {REFERRAL_DEPOSIT_LIMIT} time deposit}}\n"
        f"📊 Total Refs: {total_refs}\n"
        f"🎁 Ref Income: ${ref_income:.2f}"
    )

    await update.message.reply_text(profile_text)


# ==========================================
# MESSAGE HANDLER
# ==========================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    text = update.message.text

    # My Profile button
    if text == "🧑‍💼 My Profile":
        await my_profile(update, context)


# ==========================================
# START BOT
# ==========================================

def main():

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # /start command
    application.add_handler(
        CommandHandler("start", start)
    )

    # Keyboard message handler
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    print("Bot is running...")

    application.run_polling()


# ==========================================
# RUN
# ==========================================

if __name__ == "__main__":
    main()
