import os

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
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

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

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
# BUY PRODUCTS MENU
# ==========================================

async def buy_products(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    keyboard = [
        [
            InlineKeyboardButton(
                "💬 Communication Apps",
                callback_data="communication_apps"
            ),
            InlineKeyboardButton(
                "🔐 VPN & Proxy",
                callback_data="vpn_proxy"
            )
        ],
        [
            InlineKeyboardButton(
                "🧑‍💻 Verification Service [coming soon]",
                callback_data="verification_service"
            )
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🛍️ BUY PRODUCTS",
        reply_markup=reply_markup
    )


# ==========================================
# COMMUNICATION APPS MENU
# ==========================================

async def communication_apps(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "Google Voice",
                callback_data="google_voice"
            ),
            InlineKeyboardButton(
                "TextNow",
                callback_data="textnow"
            )
        ],
        [
            InlineKeyboardButton(
                "TextFree",
                callback_data="textfree"
            ),
            InlineKeyboardButton(
                "Sideline",
                callback_data="sideline"
            )
        ],
        [
            InlineKeyboardButton(
                "Talkatone ($)",
                callback_data="talkatone"
            ),
            InlineKeyboardButton(
                "TextPlus ($)",
                callback_data="textplus"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="back_to_buy_products"
            )
        ]
    ]

    await query.message.reply_text(
        "💬 COMMUNICATION APPS",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# GOOGLE VOICE MENU
# ==========================================

async def google_voice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "Old GV ($)",
                callback_data="old_gv"
            ),
            InlineKeyboardButton(
                "New GV ($)",
                callback_data="new_gv"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="communication_apps"
            )
        ]
    ]

    await query.message.reply_text(
        "📱 Google Voice",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# TEXTNOW MENU
# ==========================================

async def textnow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "Web TN ($)",
                callback_data="web_tn"
            ),
            InlineKeyboardButton(
                "Phone TN ($)",
                callback_data="phone_tn"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="communication_apps"
            )
        ]
    ]

    await query.message.reply_text(
        "📱 TextNow",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# TEXTFREE MENU
# ==========================================

async def textfree(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "Web TF ($)",
                callback_data="web_tf"
            ),
            InlineKeyboardButton(
                "Phone TF ($)",
                callback_data="phone_tf"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="communication_apps"
            )
        ]
    ]

    await query.message.reply_text(
        "📱 TextFree",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# SIDELINE MENU
# ==========================================

async def sideline(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "Web SL ($)",
                callback_data="web_sl"
            ),
            InlineKeyboardButton(
                "Phone SL ($)",
                callback_data="phone_sl"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="communication_apps"
            )
        ]
    ]

    await query.message.reply_text(
        "📱 Sideline",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# TALKATONE
# ==========================================

async def talkatone(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="communication_apps"
            )
        ]
    ]

    await query.message.reply_text(
        "📱 Talkatone\n\n"
        "💰 Price: $ (Admin controlled)\n"
        "📦 Available from stock.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# TEXTPLUS
# ==========================================

async def textplus(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="communication_apps"
            )
        ]
    ]

    await query.message.reply_text(
        "📱 TextPlus\n\n"
        "💰 Price: $ (Admin controlled)\n"
        "📦 Available from stock.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# BACK TO BUY PRODUCTS
# ==========================================

async def back_to_buy_products(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "💬 Communication Apps",
                callback_data="communication_apps"
            ),
            InlineKeyboardButton(
                "🔐 VPN & Proxy",
                callback_data="vpn_proxy"
            )
        ],
        [
            InlineKeyboardButton(
                "🧑‍💻 Verification Service [coming soon]",
                callback_data="verification_service"
            )
        ]
    ]

    await query.message.reply_text(
        "🛍️ BUY PRODUCTS",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# VPN & PROXY - COMING SOON
# ==========================================

async def vpn_proxy(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="back_to_buy_products"
            )
        ]
    ]

    await query.message.reply_text(
        "🔐 VPN & Proxy\n\n"
        "🚧 This service is coming soon.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# VERIFICATION SERVICE - COMING SOON
# ==========================================

async def verification_service(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="back_to_buy_products"
            )
        ]
    ]

    await query.message.reply_text(
        "🧑‍💻 Verification Service\n\n"
        "🚧 This service is coming soon.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# PRODUCT PLACEHOLDER
# ==========================================

async def product_not_ready(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    await query.message.reply_text(
        "🚧 This product purchase system is not connected yet.\n\n"
        "It will be connected to stock, balance and automatic "
        "delivery in the next step."
    )


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

    # Buy Products button
    elif text == "🛍️ Buy Products":
        await buy_products(update, context)


# ==========================================
# START BOT
# ==========================================

def main():

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # ------------------------------------------
    # /start command
    # ------------------------------------------

    application.add_handler(
        CommandHandler("start", start)
    )

    # ------------------------------------------
    # Keyboard message handler
    # ------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    # ==========================================
    # INLINE BUTTON HANDLERS
    # ==========================================

    application.add_handler(
        CallbackQueryHandler(
            communication_apps,
            pattern="^communication_apps$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            google_voice,
            pattern="^google_voice$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            textnow,
            pattern="^textnow$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            textfree,
            pattern="^textfree$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            sideline,
            pattern="^sideline$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            talkatone,
            pattern="^talkatone$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            textplus,
            pattern="^textplus$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            back_to_buy_products,
            pattern="^back_to_buy_products$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            vpn_proxy,
            pattern="^vpn_proxy$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            verification_service,
            pattern="^verification_service$"
        )
    )

    # ------------------------------------------
    # Product buttons
    # ------------------------------------------

    application.add_handler(
        CallbackQueryHandler(
            product_not_ready,
            pattern="^(old_gv|new_gv|web_tn|phone_tn|web_tf|phone_tf)$"
        )
    )

    print("Bot is running...")

    application.run_polling()


# ==========================================
# RUN
# ==========================================

if __name__ == "__main__":
    main()
