import sqlite3
from typing import Optional, Any


# ==========================================
# DATABASE CONFIGURATION
# ==========================================

DATABASE_FILE = "sales_bot.db"


# ==========================================
# DATABASE CONNECTION
# ==========================================

def get_connection():
    connection = sqlite3.connect(
        DATABASE_FILE,
        timeout=30
    )

    connection.row_factory = sqlite3.Row

    connection.execute("PRAGMA foreign_keys = ON")

    return connection


# ==========================================
# DATABASE INITIALIZATION
# ==========================================

def init_db():

    connection = get_connection()

    cursor = connection.cursor()

    # ======================================
    # USERS
    # ======================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            telegram_id INTEGER UNIQUE NOT NULL,

            username TEXT,

            first_name TEXT,

            last_name TEXT,

            balance REAL NOT NULL DEFAULT 0.0,

            is_blocked INTEGER NOT NULL DEFAULT 0,

            referral_code TEXT UNIQUE,

            referred_by INTEGER,

            total_referrals INTEGER NOT NULL DEFAULT 0,

            referral_income REAL NOT NULL DEFAULT 0.0,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (referred_by)
                REFERENCES users(id)
        )
    """)

    # ======================================
    # CATEGORIES
    # ======================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            description TEXT,

            emoji TEXT,

            sort_order INTEGER NOT NULL DEFAULT 0,

            is_active INTEGER NOT NULL DEFAULT 1,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ======================================
    # PRODUCTS
    # ======================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            category_id INTEGER,

            product_key TEXT UNIQUE NOT NULL,

            name TEXT NOT NULL,

            description TEXT,

            price REAL NOT NULL DEFAULT 0.0,

            product_type TEXT NOT NULL DEFAULT 'stock',

            validity_days INTEGER,

            is_active INTEGER NOT NULL DEFAULT 1,

            sort_order INTEGER NOT NULL DEFAULT 0,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (category_id)
                REFERENCES categories(id)
                ON DELETE SET NULL
        )
    """)

    # ======================================
    # STOCK
    # ======================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            product_id INTEGER NOT NULL,

            stock_content TEXT NOT NULL,

            status TEXT NOT NULL DEFAULT 'available',

            order_id INTEGER,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            sold_at TIMESTAMP,

            FOREIGN KEY (product_id)
                REFERENCES products(id)
                ON DELETE CASCADE
        )
    """)

    # ======================================
    # ORDERS
    # ======================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,

            product_id INTEGER NOT NULL,

            quantity INTEGER NOT NULL DEFAULT 1,

            unit_price REAL NOT NULL DEFAULT 0.0,

            total_amount REAL NOT NULL DEFAULT 0.0,

            status TEXT NOT NULL DEFAULT 'pending',

            delivery_status TEXT NOT NULL DEFAULT 'pending',

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            completed_at TIMESTAMP,

            FOREIGN KEY (user_id)
                REFERENCES users(id),

            FOREIGN KEY (product_id)
                REFERENCES products(id)
        )
    """)

    # ======================================
    # ORDER ITEMS
    # ======================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            order_id INTEGER NOT NULL,

            stock_id INTEGER,

            delivered_content TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (order_id)
                REFERENCES orders(id)
                ON DELETE CASCADE,

            FOREIGN KEY (stock_id)
                REFERENCES stock(id)
                ON DELETE SET NULL
        )
    """)

    # ======================================
    # BALANCE TRANSACTIONS
    # ======================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS balance_transactions (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,

            transaction_type TEXT NOT NULL,

            amount REAL NOT NULL,

            balance_before REAL NOT NULL,

            balance_after REAL NOT NULL,

            reference TEXT,

            description TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
        )
    """)

    # ======================================
    # PAYMENTS
    # ======================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,

            payment_method TEXT NOT NULL,

            amount REAL NOT NULL,

            currency TEXT NOT NULL DEFAULT 'USD',

            exchange_rate REAL,

            local_amount REAL,

            payment_reference TEXT,

            transaction_id TEXT,

            status TEXT NOT NULL DEFAULT 'pending',

            admin_note TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            approved_at TIMESTAMP,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
        )
    """)

    # ======================================
    # PAYMENT METHODS
    # ======================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payment_methods (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            method_type TEXT NOT NULL,

            details TEXT,

            currency TEXT NOT NULL DEFAULT 'USD',

            exchange_rate REAL,

            is_active INTEGER NOT NULL DEFAULT 1,

            sort_order INTEGER NOT NULL DEFAULT 0,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ======================================
    # REFERRAL COMMISSIONS
    # ======================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS referral_commissions (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            referrer_id INTEGER NOT NULL,

            referred_user_id INTEGER NOT NULL,

            payment_id INTEGER,

            commission_rate REAL NOT NULL,

            commission_amount REAL NOT NULL,

            deposit_number INTEGER,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (referrer_id)
                REFERENCES users(id),

            FOREIGN KEY (referred_user_id)
                REFERENCES users(id),

            FOREIGN KEY (payment_id)
                REFERENCES payments(id)
        )
    """)

    # ======================================
    # SETTINGS
    # ======================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (

            key TEXT PRIMARY KEY,

            value TEXT,

            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ======================================
    # ADMIN ACTION LOG
    # ======================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_logs (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            admin_telegram_id INTEGER NOT NULL,

            action TEXT NOT NULL,

            target_type TEXT,

            target_id INTEGER,

            details TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ======================================
    # DEFAULT SETTINGS
    # ======================================

    default_settings = {

        "store_name": "JanKug Store",

        "support_username": "@JanKug",

        "referral_commission": "5",

        "referral_deposit_limit": "10",

    }

    for key, value in default_settings.items():

        cursor.execute("""
            INSERT OR IGNORE INTO settings
            (key, value)
            VALUES (?, ?)
        """, (key, value))

    # ======================================
    # DEFAULT CATEGORIES
    # ======================================

    default_categories = [

        (
            "Communication Apps",
            "Communication application products",
            "📱",
            1
        ),

        (
            "VPN & Proxy",
            "VPN and proxy products",
            "🔐",
            2
        ),

        (
            "Verification Services",
            "Verification services",
            "📲",
            3
        ),

    ]

    for name, description, emoji, sort_order in default_categories:

        cursor.execute("""
            SELECT id
            FROM categories
            WHERE name = ?
        """, (name,))

        exists = cursor.fetchone()

        if not exists:

            cursor.execute("""
                INSERT INTO categories
                (
                    name,
                    description,
                    emoji,
                    sort_order
                )
                VALUES (?, ?, ?, ?)
            """, (
                name,
                description,
                emoji,
                sort_order
            ))

    connection.commit()

    connection.close()


# ==========================================
# USER FUNCTIONS
# ==========================================

def get_user(telegram_id: int):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM users
        WHERE telegram_id = ?
    """, (telegram_id,))

    user = cursor.fetchone()

    connection.close()

    return user


def create_user(
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    referred_by: Optional[int] = None
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO users
        (
            telegram_id,
            username,
            first_name,
            last_name,
            referred_by
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        telegram_id,
        username,
        first_name,
        last_name,
        referred_by
    ))

    connection.commit()

    connection.close()


def update_user(
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        UPDATE users
        SET
            username = ?,
            first_name = ?,
            last_name = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE telegram_id = ?
    """, (
        username,
        first_name,
        last_name,
        telegram_id
    ))

    connection.commit()

    connection.close()


# ==========================================
# BALANCE
# ==========================================

def get_balance(telegram_id: int) -> float:

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT balance
        FROM users
        WHERE telegram_id = ?
    """, (telegram_id,))

    row = cursor.fetchone()

    connection.close()

    if not row:
        return 0.0

    return float(row["balance"])


def change_balance(
    telegram_id: int,
    amount: float,
    transaction_type: str,
    reference: Optional[str] = None,
    description: Optional[str] = None
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT balance
        FROM users
        WHERE telegram_id = ?
    """, (telegram_id,))

    user = cursor.fetchone()

    if not user:

        connection.close()

        raise ValueError("User does not exist.")

    balance_before = float(user["balance"])

    balance_after = balance_before + amount

    if balance_after < 0:

        connection.close()

        raise ValueError("Insufficient balance.")

    cursor.execute("""
        UPDATE users
        SET
            balance = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE telegram_id = ?
    """, (
        balance_after,
        telegram_id
    ))

    cursor.execute("""
        INSERT INTO balance_transactions
        (
            user_id,
            transaction_type,
            amount,
            balance_before,
            balance_after,
            reference,
            description
        )
        SELECT
            id,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?
        FROM users
        WHERE telegram_id = ?
    """, (
        transaction_type,
        amount,
        balance_before,
        balance_after,
        reference,
        description,
        telegram_id
    ))

    connection.commit()

    connection.close()

    return balance_after


# ==========================================
# SETTINGS
# ==========================================

def get_setting(
    key: str,
    default: Optional[str] = None
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT value
        FROM settings
        WHERE key = ?
    """, (key,))

    row = cursor.fetchone()

    connection.close()

    if not row:
        return default

    return row["value"]


def set_setting(
    key: str,
    value: Any
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO settings
        (
            key,
            value,
            updated_at
        )
        VALUES (?, ?, CURRENT_TIMESTAMP)

        ON CONFLICT(key)
        DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
    """, (
        key,
        str(value)
    ))

    connection.commit()

    connection.close()


# ==========================================
# PRODUCTS
# ==========================================

def get_product_by_key(product_key: str):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM products
        WHERE product_key = ?
    """, (product_key,))

    product = cursor.fetchone()

    connection.close()

    return product


def get_product(product_id: int):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM products
        WHERE id = ?
    """, (product_id,))

    product = cursor.fetchone()

    connection.close()

    return product


def get_available_stock_count(product_id: int) -> int:

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM stock
        WHERE product_id = ?
        AND status = 'available'
    """, (product_id,))

    row = cursor.fetchone()

    connection.close()

    return int(row["total"])


# ==========================================
# DATABASE HEALTH CHECK
# ==========================================

def database_health_check() -> bool:

    try:

        connection = get_connection()

        cursor = connection.cursor()

        cursor.execute("SELECT 1")

        result = cursor.fetchone()

        connection.close()

        return result is not None

    except Exception:

        return False
