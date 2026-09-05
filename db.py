import sqlite3
from contextlib import closing

DB_PATH = "sales_bot.db"

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with closing(connect()) as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            username TEXT,
            balance REAL NOT NULL DEFAULT 0,
            referred_by INTEGER,
            ref_income REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            email TEXT NOT NULL,
            password TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'AVAILABLE',
            sold_to INTEGER,
            sold_at TEXT
        );

        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            total REAL NOT NULL,
            payment_method TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        ''')
        con.commit()

def upsert_user(user_id, name, username, referred_by=None):
    with closing(connect()) as con:
        row = con.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            con.execute(
                "INSERT INTO users(user_id,name,username,referred_by) VALUES(?,?,?,?)",
                (user_id, name, username, referred_by)
            )
        else:
            con.execute(
                "UPDATE users SET name=?, username=? WHERE user_id=?",
                (name, username, user_id)
            )
        con.commit()

def get_user(user_id):
    with closing(connect()) as con:
        return con.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()

def get_ref_count(user_id):
    with closing(connect()) as con:
        return con.execute(
            "SELECT COUNT(*) AS c FROM users WHERE referred_by=?", (user_id,)
        ).fetchone()["c"]

def get_products_stock():
    with closing(connect()) as con:
        return con.execute(
            "SELECT product_id, COUNT(*) AS c FROM inventory WHERE status='AVAILABLE' GROUP BY product_id"
        ).fetchall()

def add_stock(product_id, email, password):
    with closing(connect()) as con:
        con.execute(
            "INSERT INTO inventory(product_id,email,password) VALUES(?,?,?)",
            (product_id, email, password)
        )
        con.commit()

def create_order(user_id, product_id, quantity, total, payment_method=None):
    with closing(connect()) as con:
        cur = con.execute(
            "INSERT INTO orders(user_id,product_id,quantity,total,payment_method) VALUES(?,?,?,?,?)",
            (user_id, product_id, quantity, total, payment_method)
        )
        con.commit()
        return cur.lastrowid

def get_orders(user_id, limit=10):
    with closing(connect()) as con:
        return con.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY order_id DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
