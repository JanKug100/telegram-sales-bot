import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes


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
# /start COMMAND
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🏠 MAIN MENU",
        reply_markup=main_menu_keyboard()
    )


# ==============================
# START BOT
# ==============================

def main():

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(
        CommandHandler("start", start)
    )

    print("Bot is running...")

    application.run_polling()


if __name__ == "__main__":
    main()
    
