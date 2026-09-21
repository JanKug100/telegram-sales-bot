import os

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from config import (
    BOT_TOKEN,
    SUPPORT_USERNAME,
    STORE_NAME,
    DEFAULT_REFERRAL_COMMISSION,
    DEFAULT_REFERRAL_DEPOSIT_LIMIT,
)

from db import (
    init_db,
    get_user,
    create_user,
    update_user,
    get_balance,
    get_setting,
    database_health_check,
)


# ============================================================
# BOT INFORMATION
# ============================================================

BOT_USERNAME = None


# ============================================================
# DATABASE / USER HELPERS
# ============================================================

def ensure_user(update: Update):

    user = update.effective_user

    if not user:
        return None

    existing_user = get_user(user.id)

    if not existing_user:

        create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )

    else:

        update_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )

    return get_user(user.id)


# ============================================================
# MAIN MENU
# ============================================================

def main_menu_keyboard():

    keyboard = [

        [
            InlineKeyboardButton(
                "📱 Communication Apps",
                callback_data="communication_apps"
            ),
            InlineKeyboardButton(
                "🔐 BUY VPN",
                callback_data="buy_vpn"
            ),
        ],

        [
            InlineKeyboardButton(
                "🧑‍💻 Verification Services",
                callback_data="verification_service"
            ),
            InlineKeyboardButton(
                "🌐 BUY Proxy",
                callback_data="buy_proxy"
            ),
        ],

        [
            InlineKeyboardButton(
                "🧑‍💼 My Profile",
                callback_data="my_profile"
            ),
            InlineKeyboardButton(
                "🛍️ Buy More Products",
                callback_data="buy_more_products"
            ),
        ],

        [
            InlineKeyboardButton(
                "💰 Add Balance",
                callback_data="add_balance"
            ),
            InlineKeyboardButton(
                "📦 My Orders",
                callback_data="my_orders"
            ),
        ],

        [
            InlineKeyboardButton(
                "👥 Refer",
                callback_data="refer"
            ),
            InlineKeyboardButton(
                "🎧 Support",
                callback_data="support"
            ),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# ============================================================
# SIMPLE BACK BUTTON
# ============================================================

def back_main_keyboard():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🏠 Main Menu",
                callback_data="main_menu"
            )
        ]
    ])


# ============================================================
# START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if not user:
        return

    # --------------------------------------------------------
    # Referral information
    # --------------------------------------------------------

    referred_by = None

    if context.args:

        referral_argument = context.args[0]

        if referral_argument.startswith("ref_"):

            referral_id = referral_argument.replace(
                "ref_",
                "",
                1
            )

            if referral_id.isdigit():

                referred_by = int(referral_id)

    # --------------------------------------------------------
    # Create/update user
    # --------------------------------------------------------

    existing_user = get_user(user.id)

    if not existing_user:

        create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            referred_by=referred_by,
        )

    else:

        update_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )

    # --------------------------------------------------------
    # Welcome
    # --------------------------------------------------------

    await update.message.reply_text(

        f"🏠 {STORE_NAME}\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Welcome to the store!\n\n"
        "Choose an option below.",

        reply_markup=main_menu_keyboard()
    )


# ============================================================
# SHOW MAIN MENU
# ============================================================

async def show_main_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    await query.edit_message_text(

        f"🏠 {STORE_NAME}\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Choose an option below.",

        reply_markup=main_menu_keyboard()
    )


# ============================================================
# MY PROFILE
# ============================================================

async def show_profile(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    user = update.effective_user

    ensure_user(update)

    balance = get_balance(user.id)

    if user.username:

        username = f"@{user.username}"

    else:

        username = "@N/A"

    bot_username = context.bot.username

    if bot_username:

        referral_link = (
            f"https://t.me/{bot_username}"
            f"?start=ref_{user.id}"
        )

    else:

        referral_link = "Referral link unavailable"

    db_user = get_user(user.id)

    total_refs = 0
    ref_income = 0.0

    if db_user:

        total_refs = db_user["total_referrals"]

        ref_income = db_user["referral_income"]

    commission = get_setting(
        "referral_commission",
        str(DEFAULT_REFERRAL_COMMISSION)
    )

    deposit_limit = get_setting(
        "referral_deposit_limit",
        str(DEFAULT_REFERRAL_DEPOSIT_LIMIT)
    )

    profile_text = (

        "👤 ACCOUNT DASHBOARD\n"
        "━━━━━━━━━━━━━━━━\n"

        f"🏷 Name: {user.full_name}\n"

        f"🔰 Username: {username}\n"

        f"🆔 User ID: {user.id}\n"

        "━━━━━━━━━━━━━━━━\n"

        f"💳 Balance: ${balance:.2f}\n"

        f"🎯 Referral Link:\n"
        f"{referral_link}\n\n"

        f"💰 Refer {commission}% commission\n"
        f"📌 First {deposit_limit} deposits\n\n"

        f"📊 Total Refs: {total_refs}\n"

        f"🎁 Ref Income: ${ref_income:.2f}"
    )

    keyboard = [

        [
            InlineKeyboardButton(
                "🔗 Refer",
                callback_data="refer"
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
        profile_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# COMMUNICATION APPS
# ============================================================

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
            ),
        ],

        [
            InlineKeyboardButton(
                "TextFree",
                callback_data="textfree"
            ),
            InlineKeyboardButton(
                "Sideline",
                callback_data="sideline"
            ),
        ],

        [
            InlineKeyboardButton(
                "Talkatone",
                callback_data="talkatone"
            ),
            InlineKeyboardButton(
                "TextPlus",
                callback_data="textplus"
            ),
        ],

        [
            InlineKeyboardButton(
                "🏠 Main Menu",
                callback_data="main_menu"
            )
        ],

    ]

    await query.edit_message_text(

        "💬 COMMUNICATION APPS\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Select a product:",

        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# GOOGLE VOICE
# ============================================================

async def google_voice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    keyboard = [

        [
            InlineKeyboardButton(
                "Old GV",
                callback_data="product_old_gv"
            ),
            InlineKeyboardButton(
                "New GV",
                callback_data="product_new_gv"
            ),
        ],

        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="communication_apps"
            )
        ],

    ]

    await query.edit_message_text(

        "📱 GOOGLE VOICE\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Choose product:",

        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# TEXTNOW
# ============================================================

async def textnow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    keyboard = [

        [
            InlineKeyboardButton(
                "Web TN",
                callback_data="product_web_tn"
            ),
            InlineKeyboardButton(
                "Phone TN",
                callback_data="product_phone_tn"
            ),
        ],

        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="communication_apps"
            )
        ],

    ]

    await query.edit_message_text(

        "📱 TEXTNOW\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Choose product:",

        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# TEXTFREE
# ============================================================

async def textfree(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    keyboard = [

        [
            InlineKeyboardButton(
                "Web TF",
                callback_data="product_web_tf"
            ),
            InlineKeyboardButton(
                "Phone TF",
                callback_data="product_phone_tf"
            ),
        ],

        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="communication_apps"
            )
        ],

    ]

    await query.edit_message_text(

        "📱 TEXTFREE\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Choose product:",

        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# SIDELINE
# ============================================================

async def sideline(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    keyboard = [

        [
            InlineKeyboardButton(
                "Web SL",
                callback_data="product_web_sl"
            ),
            InlineKeyboardButton(
                "Phone SL",
                callback_data="product_phone_sl"
            ),
        ],

        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="communication_apps"
            )
        ],

    ]

    await query.edit_message_text(

        "📱 SIDELINE\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Choose product:",

        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# TALKATONE
# ============================================================

async def talkatone(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    await query.edit_message_text(

        "📱 TALKATONE\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "💰 Price: Admin controlled\n"
        "📦 Stock: Database controlled\n\n"
        "🚧 Purchase system will be connected "
        "in the next development stage.",

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "🔙 Back",
                    callback_data="communication_apps"
                )
            ],

        ])
    )


# ============================================================
# TEXTPLUS
# ============================================================

async def textplus(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    await query.edit_message_text(

        "📱 TEXTPLUS\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "💰 Price: Admin controlled\n"
        "📦 Stock: Database controlled\n\n"
        "🚧 Purchase system will be connected "
        "in the next development stage.",

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "🔙 Back",
                    callback_data="communication_apps"
                )
            ],

        ])
    )


# ============================================================
# COMMUNICATION PRODUCT PLACEHOLDER
# ============================================================

async def communication_product(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    product_key = query.data.replace(
        "product_",
        "",
        1
    )

    await query.edit_message_text(

        f"🛍️ PRODUCT\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"Product: {product_key}\n\n"
        "💰 Price: Will be controlled "
        "from Database/Admin Panel.\n"
        "📦 Stock: Will be controlled "
        "from Database.\n\n"
        "🚧 Purchase system is the next stage.",

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "🔙 Back",
                    callback_data="communication_apps"
                )
            ],

        ])
    )


# ============================================================
# BUY VPN
# ============================================================

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
            ),
        ],

        [
            InlineKeyboardButton(
                "14 Days",
                callback_data="vpn_14_days"
            ),
            InlineKeyboardButton(
                "30 Days",
                callback_data="vpn_30_days"
            ),
        ],

        [
            InlineKeyboardButton(
                "🏠 Main Menu",
                callback_data="main_menu"
            )
        ],

    ]

    await query.edit_message_text(

        "🔐 BUY VPN\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "📅 Select validity:",

        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# VPN 03 DAYS
# ============================================================

async def vpn_03_days(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    keyboard = [

        [
            InlineKeyboardButton(
                "Express VPN",
                callback_data="vpn_product_express_3"
            ),
            InlineKeyboardButton(
                "CyberGhost VPN",
                callback_data="vpn_product_cyberghost_3"
            ),
        ],

        [
            InlineKeyboardButton(
                "Vypr VPN",
                callback_data="vpn_product_vypr_3"
            ),
            InlineKeyboardButton(
                "Panda VPN",
                callback_data="vpn_product_panda_3"
            ),
        ],

        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="buy_vpn"
            )
        ],

    ]

    await query.edit_message_text(

        "🔐 VPN — 03 DAYS\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Select a VPN:",

        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# VPN 07 DAYS PAGE 1
# ============================================================

async def vpn_07_days(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    keyboard = [

        [
            InlineKeyboardButton(
                "Express VPN",
                callback_data="vpn_product_express_7"
            ),
            InlineKeyboardButton(
                "Nord VPN",
                callback_data="vpn_product_nord_7"
            ),
        ],

        [
            InlineKeyboardButton(
                "PIA VPN",
                callback_data="vpn_product_pia_7"
            ),
            InlineKeyboardButton(
                "IPVanish VPN",
                callback_data="vpn_product_ipvanish_7"
            ),
        ],

        [
            InlineKeyboardButton(
                "Surfshark VPN",
                callback_data="vpn_product_surfshark_7"
            ),
            InlineKeyboardButton(
                "HotspotShield VPN",
                callback_data="vpn_product_hotspotshield_7"
            ),
        ],

        [
            InlineKeyboardButton(
                "HMA VPN",
                callback_data="vpn_product_hma_7"
            ),
            InlineKeyboardButton(
                "Pure VPN",
                callback_data="vpn_product_pure_7"
            ),
        ],

        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="buy_vpn"
            ),
            InlineKeyboardButton(
                "Next ➡️",
                callback_data="vpn_07_page_2"
            ),
        ],

    ]

    await query.edit_message_text(

        "🔐 VPN — 07 DAYS\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Page 1",

        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# VPN 07 DAYS PAGE 2
# ============================================================

async def vpn_07_page_2(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    keyboard = [

        [
            InlineKeyboardButton(
                "Turbo VPN",
                callback_data="vpn_product_turbo_7"
            ),
            InlineKeyboardButton(
                "Avast VPN",
                callback_data="vpn_product_avast_7"
            ),
        ],

        [
            InlineKeyboardButton(
                "AdGuard VPN",
                callback_data="vpn_product_adguard_7"
            ),
            InlineKeyboardButton(
                "Norton VPN",
                callback_data="vpn_product_norton_7"
            ),
        ],

        [
            InlineKeyboardButton(
                "AVG VPN",
                callback_data="vpn_product_avg_7"
            ),
            InlineKeyboardButton(
                "X-VPN",
                callback_data="vpn_product_x_7"
            ),
        ],

        [
            InlineKeyboardButton(
                "Sky VPN",
                callback_data="vpn_product_sky_7"
            ),
            InlineKeyboardButton(
                "Potato VPN",
                callback_data="vpn_product_potato_7"
            ),
        ],

        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="vpn_07_days"
            ),
            InlineKeyboardButton(
                "Next ➡️",
                callback_data="vpn_07_page_3"
            ),
        ],

    ]

    await query.edit_message_text(

        "🔐 VPN — 07 DAYS\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Page 2",

        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# VPN 07 DAYS PAGE 3
# ============================================================

async def vpn_07_page_3(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    keyboard = [

        [
            InlineKeyboardButton(
                "Bitdefender VPN",
                callback_data="vpn_product_bitdefender_7"
            )
        ],

        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="vpn_07_page_2"
            )
        ],

    ]

    await query.edit_message_text(

        "🔐 VPN — 07 DAYS\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Page 3",

        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# VPN 14 DAYS
# ============================================================

async def vpn_14_days(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    keyboard = [

        [
            InlineKeyboardButton(
                "Octohide",
                callback_data="vpn_product_octohide_14"
            )
        ],

        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="buy_vpn"
            )
        ],

    ]

    await query.edit_message_text(

        "🔐 VPN — 14 DAYS\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Select a VPN:",

        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# VPN 30 DAYS
# ============================================================

async def vpn_30_days(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    keyboard = [

        [
            InlineKeyboardButton(
                "Express VPN (1 Device)",
                callback_data="vpn_product_express_30"
            ),
            InlineKeyboardButton(
                "Nord VPN",
                callback_data="vpn_product_nord_30"
            ),
        ],

        [
            InlineKeyboardButton(
                "PIA VPN (1 Device)",
                callback_data="vpn_product_pia_30"
            ),
            InlineKeyboardButton(
                "Avast VPN",
                callback_data="vpn_product_avast_30"
            ),
        ],

        [
            InlineKeyboardButton(
                "Bitdefender VPN",
                callback_data="vpn_product_bitdefender_30"
            ),
            InlineKeyboardButton(
                "HMA VPN",
                callback_data="vpn_product_hma_30"
            ),
        ],

        [
            InlineKeyboardButton(
                "Mysterium VPN",
                callback_data="vpn_product_mysterium_30"
            ),
            InlineKeyboardButton(
                "MYSTERIUM DARK",
                callback_data="vpn_product_mysterium_dark_30"
            ),
        ],

        [
            InlineKeyboardButton(
                "Windscribe VPN",
                callback_data="vpn_product_windscribe_30"
            ),
            InlineKeyboardButton(
                "Proton VPN",
                callback_data="vpn_product_proton_30"
            ),
        ],

        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="buy_vpn"
            )
        ],

    ]

    await query.edit_message_text(

        "🔐 VPN — 30 DAYS\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Select a VPN:",

        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# VPN PRODUCT PLACEHOLDER
# ============================================================

async def vpn_product(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    product_key = query.data.replace(
        "vpn_product_",
        "",
        1
    )

    await query.edit_message_text(

        "🔐 VPN PRODUCT\n"
        "━━━━━━━━━━━━━━━━\n\n"

        f"Product: {product_key}\n\n"

        "💰 Price: Database controlled\n"
        "📦 Stock: Database controlled\n\n"

        "🚧 Purchase and automatic delivery "
        "will be connected in the next stage.",

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "🔙 Back",
                    callback_data="buy_vpn"
                )
            ]

        ])
    )


# ============================================================
# BUY PROXY
# ============================================================

async def buy_proxy(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    await query.edit_message_text(

        "🌐 BUY PROXY\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "🚧 Coming soon.",

        reply_markup=back_main_keyboard()
    )


# ============================================================
# VERIFICATION SERVICES
# ============================================================

async def verification_service(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    await query.edit_message_text(

        "🧑‍💻 VERIFICATION SERVICES\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "🚧 Coming soon.",

        reply_markup=back_main_keyboard()
    )


# ============================================================
# BUY MORE PRODUCTS
# ============================================================

async def buy_more_products(
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
            ),
        ],

        [
            InlineKeyboardButton(
                "💻 Software & Tools",
                callback_data="software_tools"
            ),
            InlineKeyboardButton(
                "🎮 Gaming Products",
                callback_data="gaming_products"
            ),
        ],

        [
            InlineKeyboardButton(
                "🏠 Main Menu",
                callback_data="main_menu"
            )
        ],

    ]

    await query.edit_message_text(

        "🛍️ BUY MORE PRODUCTS\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Select a category:",

        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================
# COMING SOON CATEGORY
# ============================================================

async def coming_soon_category(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    await query.edit_message_text(

        "🚧 COMING SOON\n\n"
        "This category will be available soon.",

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "🔙 Back",
                    callback_data="buy_more_products"
                )
            ]

        ])
    )


# ============================================================
# ADD BALANCE
# ============================================================

async def add_balance(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    await query.edit_message_text(

        "💰 ADD BALANCE\n"
        "━━━━━━━━━━━━━━━━\n\n"

        "Payment system is not connected yet.\n\n"

        "💳 Payment methods will be added "
        "after the purchase and balance "
        "system is completed.",

        reply_markup=back_main_keyboard()
    )


# ============================================================
# MY ORDERS
# ============================================================

async def my_orders(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    await query.edit_message_text(

        "📦 MY ORDERS\n"
        "━━━━━━━━━━━━━━━━\n\n"

        "You don't have any orders yet.\n\n"

        "Order history will be connected "
        "to the database in the next stage.",

        reply_markup=back_main_keyboard()
    )


# ============================================================
# REFER
# ============================================================

async def refer(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    user = update.effective_user

    ensure_user(update)

    bot_username = context.bot.username

    if bot_username:

        referral_link = (
            f"https://t.me/{bot_username}"
            f"?start=ref_{user.id}"
        )

    else:

        referral_link = "Referral link unavailable"

    db_user = get_user(user.id)

    total_refs = 0
    ref_income = 0.0

    if db_user:

        total_refs = db_user["total_referrals"]

        ref_income = db_user["referral_income"]

    commission = get_setting(
        "referral_commission",
        str(DEFAULT_REFERRAL_COMMISSION)
    )

    deposit_limit = get_setting(
        "referral_deposit_limit",
        str(DEFAULT_REFERRAL_DEPOSIT_LIMIT)
    )

    text = (

        "👥 REFERRAL PROGRAM\n"
        "━━━━━━━━━━━━━━━━\n\n"

        "🎯 Your Referral Link:\n"
        f"{referral_link}\n\n"

        f"💰 Commission: {commission}%\n"

        f"📌 Commission applies to the first "
        f"{deposit_limit} deposits.\n\n"

        f"📊 Total Referrals: {total_refs}\n"

        f"🎁 Referral Income: ${ref_income:.2f}"
    )

    await query.edit_message_text(

        text,

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "🏠 Main Menu",
                    callback_data="main_menu"
                )
            ]

        ])
    )


# ============================================================
# SUPPORT
# ============================================================

async def support(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    await query.edit_message_text(

        "🎧 SUPPORT\n"
        "━━━━━━━━━━━━━━━━\n\n"

        "For support, please contact:\n"

        f"{SUPPORT_USERNAME}",

        reply_markup=back_main_keyboard()
    )


# ============================================================
# UNKNOWN TEXT
# ============================================================

async def handle_unknown_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    await update.message.reply_text(

        "🏠 Please use the buttons below.",

        reply_markup=main_menu_keyboard()
    )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    print(
        "Bot error:",
        context.error
    )


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # Check BOT TOKEN
    # --------------------------------------------------------

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN is missing. "
            "Please add BOT_TOKEN in Railway Variables."
        )

    # --------------------------------------------------------
    # Initialize Database
    # --------------------------------------------------------

    init_db()

    # --------------------------------------------------------
    # Database Health Check
    # --------------------------------------------------------

    if not database_health_check():

        raise RuntimeError(
            "Database health check failed."
        )

    # --------------------------------------------------------
    # Build Application
    # --------------------------------------------------------

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # ========================================================
    # COMMANDS
    # ========================================================

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # ========================================================
    # MAIN MENU
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            show_main_menu,
            pattern="^main_menu$"
        )
    )

    # ========================================================
    # PROFILE
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            show_profile,
            pattern="^my_profile$"
        )
    )

    # ========================================================
    # COMMUNICATION APPS
    # ========================================================

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

    # ========================================================
    # COMMUNICATION PRODUCTS
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            communication_product,
            pattern=(
                "^product_"
            )
        )
    )

    # ========================================================
    # VPN
    # ========================================================

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

    # ========================================================
    # VPN PRODUCTS
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            vpn_product,
            pattern="^vpn_product_"
        )
    )

    # ========================================================
    # PROXY
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            buy_proxy,
            pattern="^buy_proxy$"
        )
    )

    # ========================================================
    # VERIFICATION
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            verification_service,
            pattern="^verification_service$"
        )
    )

    # ========================================================
    # BUY MORE PRODUCTS
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            buy_more_products,
            pattern="^buy_more_products$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            coming_soon_category,
            pattern=(
                "^(email_accounts|"
                "premium_apps|"
                "software_tools|"
                "gaming_products)$"
            )
        )
    )

    # ========================================================
    # ADD BALANCE
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            add_balance,
            pattern="^add_balance$"
        )
    )

    # ========================================================
    # MY ORDERS
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            my_orders,
            pattern="^my_orders$"
        )
    )

    # ========================================================
    # REFERRAL
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            refer,
            pattern="^refer$"
        )
    )

    # ========================================================
    # SUPPORT
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            support,
            pattern="^support$"
        )
    )

    # ========================================================
    # ERROR HANDLER
    # ========================================================

    application.add_error_handler(
        error_handler
    )

    # ========================================================
    # TEXT HANDLER
    # ========================================================

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_unknown_message
        )
    )

    # ========================================================
    # RUN BOT
    # ========================================================

    print(
        f"{STORE_NAME} bot is running..."
    )

    application.run_polling()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
