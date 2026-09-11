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

        CREATE TABLE IF NOT EXISTS balance_requests (
            request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            approved_at TEXT
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


def create_balance_request(user_id, amount):
    with closing(connect()) as con:
        cur = con.execute(
            "INSERT INTO balance_requests(user_id, amount, status) VALUES(?,?,?)",
            (user_id, amount, "PENDING"),
        )
        con.commit()
        return cur.lastrowid


def get_balance_request(request_id):
    with closing(connect()) as con:
        return con.execute(
            "SELECT * FROM balance_requests WHERE request_id=?",
            (request_id,),
        ).fetchone()


def update_balance_request_status(request_id, status):
    with closing(connect()) as con:
        con.execute(
            "UPDATE balance_requests SET status=? WHERE request_id=?",
            (status, request_id),
        )
        con.commit()


def approve_balance_request(request_id):
    """Approve and credit a balance request exactly once."""
    with closing(connect()) as con:
        con.execute("BEGIN IMMEDIATE")
        req = con.execute(
            "SELECT user_id, amount, status FROM balance_requests WHERE request_id=?",
            (request_id,),
        ).fetchone()
        if not req:
            con.rollback()
            return None
        if req["status"] == "APPROVED":
            user = con.execute("SELECT balance FROM users WHERE user_id=?", (req["user_id"],)).fetchone()
            con.rollback()
            return float(user["balance"]) if user else None
        if req["status"] not in ("PENDING", "WAITING_PAYMENT"):
            con.rollback()
            return None
        user = con.execute("SELECT balance FROM users WHERE user_id=?", (req["user_id"],)).fetchone()
        if not user:
            con.rollback()
            return None
        cur = con.execute(
            "UPDATE balance_requests SET status='APPROVED', approved_at=CURRENT_TIMESTAMP WHERE request_id=? AND status IN ('PENDING','WAITING_PAYMENT')",
            (request_id,),
        )
        if cur.rowcount != 1:
            con.rollback()
            return None
        con.execute(
            "UPDATE users SET balance=balance+? WHERE user_id=?",
            (float(req["amount"]), req["user_id"]),
        )
        new_balance = con.execute(
            "SELECT balance FROM users WHERE user_id=?",
            (req["user_id"],),
        ).fetchone()["balance"]
        con.commit()
        return float(new_balance)


def get_product_stock(product_id):
    with closing(connect()) as con:
        row = con.execute("SELECT COUNT(*) AS c FROM inventory WHERE product_id=? AND status='AVAILABLE'", (product_id,)).fetchone()
        return int(row["c"]) if row else 0

def purchase_from_balance_qty(order_id, user_id, product_id, qty, total):
    with closing(connect()) as con:
        con.execute("BEGIN IMMEDIATE")
        order = con.execute("SELECT status FROM orders WHERE order_id=? AND user_id=?", (order_id,user_id)).fetchone()
        user = con.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not order or not user or float(user["balance"]) + 1e-9 < float(total):
            con.rollback(); return [], "INSUFFICIENT_BALANCE"
        items = con.execute("SELECT id,email,password FROM inventory WHERE product_id=? AND status='AVAILABLE' ORDER BY id LIMIT ?", (product_id, qty)).fetchall()
        if len(items) < qty:
            con.rollback(); return [], "OUT_OF_STOCK"
        now = __import__('datetime').datetime.now().strftime("%Y-%m-%d %I:%M %p")
        for item in items:
            cur = con.execute("UPDATE inventory SET status='SOLD', sold_to=?, sold_at=? WHERE id=? AND status='AVAILABLE'", (user_id, now, item["id"]))
            if cur.rowcount != 1:
                con.rollback(); return [], "RESERVATION_FAILED"
            con.execute("INSERT INTO orders(order_id,user_id,product_id,quantity,total,payment_method,status) VALUES(?,?,?,?,?,?,?) ON CONFLICT(order_id) DO NOTHING", (order_id,user_id,product_id,qty,total,'Balance','DELIVERED')) if False else None
        cur = con.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?", (float(total), user_id, float(total)))
        if cur.rowcount != 1:
            con.rollback(); return [], "INSUFFICIENT_BALANCE"
        con.execute("UPDATE orders SET status='DELIVERED', payment_method='Balance' WHERE order_id=?", (order_id,))
        new_balance = float(con.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()["balance"])
        con.commit()
        return [{"email":r["email"],"password":r["password"],"delivered_at":now,"new_balance":new_balance} for r in items], "DELIVERED"
