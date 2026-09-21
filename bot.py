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
        [
            "📱 Communication Apps",
            "🔐 BUY VPN"
        ],
        [
            "🧑‍💻 Verification Services",
            "🌐 BUY Proxy"
        ],
        [
            "🧑‍💼 My Profile",
            "🛍️ Buy More Products"
        ],
        [
            "💰 Add Balance",
            "📦 My Orders"
        ],
        [
            "👥 Refer",
            "🎧 Support"
        ],
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
        "🏠 MAIN MENU\n\n"
        "Welcome to the store!\n\n"
        "Choose an option below.",
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

    # Telegram Name
    telegram_name = user.full_name

    # Telegram Username
    if user.username:
        username = f"@{user.username}"
    else:
        username = "@N/A"

    # Telegram User ID
    user_id = user.id

    # Temporary values
    # পরবর্তীতে Database থেকে আসবে।
    balance = 0.00
    total_refs = 0
    ref_income = 0.00

    # Referral Link
    bot_username = context.bot.username

    if bot_username:
        referral_link = (
            f"https://t.me/{bot_username}?start=ref_{user_id}"
        )
    else:
        referral_link = "Referral link unavailable"

    # Account Dashboard
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

    await update.message.reply_text(
        profile_text,
        reply_markup=main_menu_keyboard()
    )


# ==========================================
# BUY MORE PRODUCTS MENU
# ==========================================

async def buy_products(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    keyboard = [
        [
            InlineKeyboardButton(
                "📧 Email Accounts",
                callback_data="email_accounts"
            ),
            InlineKeyboardButton(
                "⭐ Premium Apps",
                callback_data="premium_apps"
            )
        ],
        [
            InlineKeyboardButton(
                "💻 Software & Tools",
                callback_data="software_tools"
            ),
            InlineKeyboardButton(
                "🎮 Gaming Products",
                callback_data="gaming_products"
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 Main Menu",
                callback_data="main_menu"
            )
        ]
    ]

    await update.message.reply_text(
        "🛍️ BUY MORE PRODUCTS\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Select a product category:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# EMAIL ACCOUNTS
# ==========================================

async def email_accounts(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="buy_more_products"
            )
        ]
    ]

    await query.edit_message_text(
        "📧 EMAIL ACCOUNTS\n\n"
        "🚧 Products will be available soon.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# PREMIUM APPS
# ==========================================

async def premium_apps(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="buy_more_products"
            )
        ]
    ]

    await query.edit_message_text(
        "⭐ PREMIUM APPS\n\n"
        "🚧 Products will be available soon.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# SOFTWARE & TOOLS
# ==========================================

async def software_tools(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="buy_more_products"
            )
        ]
    ]

    await query.edit_message_text(
        "💻 SOFTWARE & TOOLS\n\n"
        "🚧 Products will be available soon.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# GAMING PRODUCTS
# ==========================================

async def gaming_products(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="buy_more_products"
            )
        ]
    ]

    await query.edit_message_text(
        "🎮 GAMING PRODUCTS\n\n"
        "🚧 Products will be available soon.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# BACK TO BUY MORE PRODUCTS
# ==========================================

async def back_to_buy_more_products(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "📧 Email Accounts",
                callback_data="email_accounts"
            ),
            InlineKeyboardButton(
                "⭐ Premium Apps",
                callback_data="premium_apps"
            )
        ],
        [
            InlineKeyboardButton(
                "💻 Software & Tools",
                callback_data="software_tools"
            ),
            InlineKeyboardButton(
                "🎮 Gaming Products",
                callback_data="gaming_products"
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 Main Menu",
                callback_data="main_menu"
            )
        ]
    ]

    await query.edit_message_text(
        "🛍️ BUY MORE PRODUCTS\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Select a product category:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# COMMUNICATION APPS
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
                "🏠 Main Menu",
                callback_data="main_menu"
            )
        ]
    ]

    await query.edit_message_text(
        "💬 COMMUNICATION APPS",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# GOOGLE VOICE
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

    await query.edit_message_text(
        "📱 Google Voice",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# TEXTNOW
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

    await query.edit_message_text(
        "📱 TextNow",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# TEXTFREE
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

    await query.edit_message_text(
        "📱 TextFree",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# SIDELINE
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

    await query.edit_message_text(
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

    await query.edit_message_text(
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

    await query.edit_message_text(
        "📱 TextPlus\n\n"
        "💰 Price: $ (Admin controlled)\n"
        "📦 Available from stock.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# BUY VPN
# ==========================================

async def buy_vpn(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "03 Days",
                callback_data="vpn_03_days"
            ),
            InlineKeyboardButton(
                "07 Days",
                callback_data="vpn_07_days"
            )
        ],
        [
            InlineKeyboardButton(
                "14 Days",
                callback_data="vpn_14_days"
            ),
            InlineKeyboardButton(
                "30 Days",
                callback_data="vpn_30_days"
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 Main Menu",
                callback_data="main_menu"
            )
        ]
    ]

    await query.edit_message_text(
        "🔐 BUY VPN\n\n"
        "📅 Select Validity:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# VPN - 03 DAYS
# ==========================================

async def vpn_03_days(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "Express VPN ($)",
                callback_data="vpn_product_express_3"
            ),
            InlineKeyboardButton(
                "CyberGhost VPN ($)",
                callback_data="vpn_product_cyberghost_3"
            )
        ],
        [
            InlineKeyboardButton(
                "Vypr VPN ($)",
                callback_data="vpn_product_vypr_3"
            ),
            InlineKeyboardButton(
                "Panda VPN ($)",
                callback_data="vpn_product_panda_3"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="buy_vpn"
            )
        ]
    ]

    await query.edit_message_text(
        "Select a VPN (3 Days):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# VPN - 07 DAYS PAGE 1
# ==========================================

async def vpn_07_days(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "Express VPN ($)",
                callback_data="vpn_product_express_7"
            ),
            InlineKeyboardButton(
                "Nord VPN ($)",
                callback_data="vpn_product_nord_7"
            )
        ],
        [
            InlineKeyboardButton(
                "PIA VPN ($)",
                callback_data="vpn_product_pia_7"
            ),
            InlineKeyboardButton(
                "IPVanish VPN ($)",
                callback_data="vpn_product_ipvanish_7"
            )
        ],
        [
            InlineKeyboardButton(
                "Surfshark VPN ($)",
                callback_data="vpn_product_surfshark_7"
            ),
            InlineKeyboardButton(
                "HotspotShield VPN ($)",
                callback_data="vpn_product_hotspotshield_7"
            )
        ],
        [
            InlineKeyboardButton(
                "HMA VPN ($)",
                callback_data="vpn_product_hma_7"
            ),
            InlineKeyboardButton(
                "Pure VPN ($)",
                callback_data="vpn_product_pure_7"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="buy_vpn"
            ),
            InlineKeyboardButton(
                "Next ➡️",
                callback_data="vpn_07_page_2"
            )
        ]
    ]

    await query.edit_message_text(
        "Select a VPN (7 Days):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# VPN - 07 DAYS PAGE 2
# ==========================================

async def vpn_07_page_2(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "Turbo VPN ($)",
                callback_data="vpn_product_turbo_7"
            ),
            InlineKeyboardButton(
                "Avast VPN ($)",
                callback_data="vpn_product_avast_7"
            )
        ],
        [
            InlineKeyboardButton(
                "AdGuard VPN ($)",
                callback_data="vpn_product_adguard_7"
            ),
            InlineKeyboardButton(
                "Norton VPN ($)",
                callback_data="vpn_product_norton_7"
            )
        ],
        [
            InlineKeyboardButton(
                "AVG VPN ($)",
                callback_data="vpn_product_avg_7"
            ),
            InlineKeyboardButton(
                "X-VPN ($)",
                callback_data="vpn_product_x_7"
            )
        ],
        [
            InlineKeyboardButton(
                "Sky VPN ($)",
                callback_data="vpn_product_sky_7"
            ),
            InlineKeyboardButton(
                "Potato VPN ($)",
                callback_data="vpn_product_potato_7"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="vpn_07_days"
            ),
            InlineKeyboardButton(
                "Next ➡️",
                callback_data="vpn_07_page_3"
            )
        ]
    ]

    await query.edit_message_text(
        "Select a VPN (7 Days):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# VPN - 07 DAYS PAGE 3
# ==========================================

async def vpn_07_page_3(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "Bitdefender VPN ($)",
                callback_data="vpn_product_bitdefender_7"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="vpn_07_page_2"
            )
        ]
    ]

    await query.edit_message_text(
        "Select a VPN (7 Days):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# VPN - 14 DAYS
# ==========================================

async def vpn_14_days(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "Octohide ($)",
                callback_data="vpn_product_octohide_14"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="buy_vpn"
            )
        ]
    ]

    await query.edit_message_text(
        "Select a VPN (14 Days):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# VPN - 30 DAYS
# ==========================================

async def vpn_30_days(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "Express VPN (1 Device) ($)",
                callback_data="vpn_product_express_30"
            ),
            InlineKeyboardButton(
                "Nord VPN ($)",
                callback_data="vpn_product_nord_30"
            )
        ],
        [
            InlineKeyboardButton(
                "PIA VPN (1 Device) ($)",
                callback_data="vpn_product_pia_30"
            ),
            InlineKeyboardButton(
                "Avast VPN ($)",
                callback_data="vpn_product_avast_30"
            )
        ],
        [
            InlineKeyboardButton(
                "Bitdefender VPN ($)",
                callback_data="vpn_product_bitdefender_30"
            ),
            InlineKeyboardButton(
                "HMA VPN ($)",
                callback_data="vpn_product_hma_30"
            )
        ],
        [
            InlineKeyboardButton(
                "Mysterium VPN ($)",
                callback_data="vpn_product_mysterium_30"
            ),
            InlineKeyboardButton(
                "MYSTERIUM DARK ($)",
                callback_data="vpn_product_mysterium_dark_30"
            )
        ],
        [
            InlineKeyboardButton(
                "Windscribe VPN ($)",
                callback_data="vpn_product_windscribe_30"
            ),
            InlineKeyboardButton(
                "Proton VPN ($)",
                callback_data="vpn_product_proton_30"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="buy_vpn"
            )
        ]
    ]

    await query.edit_message_text(
        "Select a VPN (30 Days):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# BUY PROXY - COMING SOON
# ==========================================

async def buy_proxy(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "🏠 Main Menu",
                callback_data="main_menu"
            )
        ]
    ]

    await query.edit_message_text(
        "🌐 BUY PROXY\n\n"
        "🚧 Coming soon.",
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
                "🏠 Main Menu",
                callback_data="main_menu"
            )
        ]
    ]

    await query.edit_message_text(
        "🧑‍💻 VERIFICATION SERVICES\n\n"
        "🚧 Coming soon.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# VPN PRODUCT PLACEHOLDER
# ==========================================

async def vpn_product_not_ready(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "🚧 This VPN purchase system is not connected yet.\n\n"
        "💰 Price will be controlled from Admin Panel.\n"
        "📦 Stock and automatic delivery will be connected later.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 Back",
                    callback_data="buy_vpn"
                )
            ]
        ])
    )


# ==========================================
# COMMUNICATION PRODUCT PLACEHOLDER
# ==========================================

async def product_not_ready(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "🚧 This product purchase system is not connected yet.\n\n"
        "💰 Price will be controlled from Admin Panel.\n"
        "📦 Stock and automatic delivery will be connected later.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 Back",
                    callback_data="communication_apps"
                )
            ]
        ])
    )


# ==========================================
# INLINE MAIN MENU
# ==========================================

async def back_to_main_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    await query.message.reply_text(
        "🏠 MAIN MENU",
        reply_markup=main_menu_keyboard()
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

    # ======================================
    # COMMUNICATION APPS
    # ======================================

    if text == "📱 Communication Apps":

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
                    "🏠 Main Menu",
                    callback_data="main_menu"
                )
            ]
        ]

        await update.message.reply_text(
            "💬 COMMUNICATION APPS",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ======================================
    # BUY VPN
    # ======================================

    elif text == "🔐 BUY VPN":

        keyboard = [
            [
                InlineKeyboardButton(
                    "03 Days",
                    callback_data="vpn_03_days"
                ),
                InlineKeyboardButton(
                    "07 Days",
                    callback_data="vpn_07_days"
                )
            ],
            [
                InlineKeyboardButton(
                    "14 Days",
                    callback_data="vpn_14_days"
                ),
                InlineKeyboardButton(
                    "30 Days",
                    callback_data="vpn_30_days"
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 Main Menu",
                    callback_data="main_menu"
                )
            ]
        ]

        await update.message.reply_text(
            "🔐 BUY VPN\n\n"
            "📅 Select Validity:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ======================================
    # VERIFICATION SERVICES
    # ======================================

    elif text == "🧑‍💻 Verification Services":

        keyboard = [
            [
                InlineKeyboardButton(
                    "🏠 Main Menu",
                    callback_data="main_menu"
                )
            ]
        ]

        await update.message.reply_text(
            "🧑‍💻 VERIFICATION SERVICES\n\n"
            "🚧 Coming soon.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ======================================
    # BUY PROXY
    # ======================================

    elif text == "🌐 BUY Proxy":

        keyboard = [
            [
                InlineKeyboardButton(
                    "🏠 Main Menu",
                    callback_data="main_menu"
                )
            ]
        ]

        await update.message.reply_text(
            "🌐 BUY PROXY\n\n"
            "🚧 Coming soon.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ======================================
    # MY PROFILE
    # ======================================

    elif text == "🧑‍💼 My Profile":

        await my_profile(update, context)

    # ======================================
    # BUY MORE PRODUCTS
    # ======================================

    elif text == "🛍️ Buy More Products":

        await buy_products(update, context)

    # ======================================
    # ADD BALANCE
    # ======================================

    elif text == "💰 Add Balance":

        await update.message.reply_text(
            "💰 ADD BALANCE\n\n"
            "🚧 Payment system is not connected yet."
        )

    # ======================================
    # MY ORDERS
    # ======================================

    elif text == "📦 My Orders":

        await update.message.reply_text(
            "📦 MY ORDERS\n\n"
            "🚧 Order system is not connected yet."
        )

    # ======================================
    # REFER
    # ======================================

    elif text == "👥 Refer":

        user = update.effective_user
        bot_username = context.bot.username

        if bot_username:
            referral_link = (
                f"https://t.me/{bot_username}?start=ref_{user.id}"
            )
        else:
            referral_link = "Referral link unavailable"

        await update.message.reply_text(
            "👥 REFERRAL PROGRAM\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"🎯 Your Referral Link:\n"
            f"{referral_link}\n\n"
            f"💰 Commission: {REFERRAL_COMMISSION}%\n"
            f"📌 Commission applies to the first "
            f"{REFERRAL_DEPOSIT_LIMIT} deposits.\n\n"
            "📊 Total Referrals: 0\n"
            "🎁 Referral Income: $0.00"
        )

    # ======================================
    # SUPPORT
    # ======================================

    elif text == "🎧 Support":

        await update.message.reply_text(
            "🎧 SUPPORT\n\n"
            "For support, please contact:\n"
            "@JanKug"
        )


# ==========================================
# START BOT
# ==========================================

def main():

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is missing. "
            "Please add BOT_TOKEN in Railway Variables."
        )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # ======================================
    # /START
    # ======================================

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # ======================================
    # MESSAGE HANDLER
    # ======================================

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    # ======================================
    # MAIN MENU CALLBACK
    # ======================================

    application.add_handler(
        CallbackQueryHandler(
            back_to_main_menu,
            pattern="^main_menu$"
        )
    )

    # ======================================
    # COMMUNICATION APPS
    # ======================================

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

    # ======================================
    # BUY MORE PRODUCTS
    # ======================================

    application.add_handler(
        CallbackQueryHandler(
            back_to_buy_more_products,
            pattern="^buy_more_products$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            email_accounts,
            pattern="^email_accounts$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            premium_apps,
            pattern="^premium_apps$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            software_tools,
            pattern="^software_tools$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            gaming_products,
            pattern="^gaming_products$"
        )
    )

    # ======================================
    # BUY VPN
    # ======================================

    application.add_handler(
        CallbackQueryHandler(
            buy_vpn,
            pattern="^buy_vpn$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            vpn_03_days,
            pattern="^vpn_03_days$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            vpn_07_days,
            pattern="^vpn_07_days$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            vpn_07_page_2,
            pattern="^vpn_07_page_2$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            vpn_07_page_3,
            pattern="^vpn_07_page_3$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            vpn_14_days,
            pattern="^vpn_14_days$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            vpn_30_days,
            pattern="^vpn_30_days$"
        )
    )

    # ======================================
    # BUY PROXY
    # ======================================

    application.add_handler(
        CallbackQueryHandler(
            buy_proxy,
            pattern="^buy_proxy$"
        )
    )

    # ======================================
    # VERIFICATION SERVICE
    # ======================================

    application.add_handler(
        CallbackQueryHandler(
            verification_service,
            pattern="^verification_service$"
        )
    )

    # ======================================
    # VPN PRODUCTS
    # ======================================

    application.add_handler(
        CallbackQueryHandler(
            vpn_product_not_ready,
            pattern="^vpn_product_"
        )
    )

    # ======================================
    # COMMUNICATION PRODUCTS
    # ======================================

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
