import os


# ==========================================
# BOT CONFIGURATION
# ==========================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ==========================================
# ADMIN CONFIGURATION
# ==========================================

# Example:
# ADMIN_IDS=123456789,987654321

ADMIN_IDS = []

admin_ids_raw = os.getenv("ADMIN_IDS", "")

if admin_ids_raw:
    for admin_id in admin_ids_raw.split(","):
        admin_id = admin_id.strip()

        if admin_id.isdigit():
            ADMIN_IDS.append(int(admin_id))


# ==========================================
# STORE CONFIGURATION
# ==========================================

STORE_NAME = "JanKug Store"

SUPPORT_USERNAME = "@JanKug"


# ==========================================
# REFERRAL CONFIGURATION
# ==========================================

DEFAULT_REFERRAL_COMMISSION = 5.0

DEFAULT_REFERRAL_DEPOSIT_LIMIT = 10


# ==========================================
# DATABASE
# ==========================================

DATABASE_FILE = "sales_bot.db"
