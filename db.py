import sqlite3
from typing import Optional, Any

DATABASE_FILE = "sales_bot.db"


def get_connection():
    connection = sqlite3.connect(DATABASE_FILE, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def _column_exists(cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row["name"] == column for row in cursor.fetchall())


def _add_column_if_missing(cursor, table: str, definition: str, column: str):
    if not _column_exists(cursor, table, column):
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def init_db():
    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("BEGIN")
        cursor.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT, first_name TEXT, last_name TEXT, balance REAL NOT NULL DEFAULT 0.0,
            is_blocked INTEGER NOT NULL DEFAULT 0, referral_code TEXT UNIQUE, referred_by INTEGER,
            total_referrals INTEGER NOT NULL DEFAULT 0, referral_income REAL NOT NULL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referred_by) REFERENCES users(id))""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT, emoji TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0, is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER, product_key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL, description TEXT, price REAL NOT NULL DEFAULT 0.0,
            product_type TEXT NOT NULL DEFAULT 'stock', validity_days INTEGER,
            is_active INTEGER NOT NULL DEFAULT 1, sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL, stock_content TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'available', order_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sold_at TIMESTAMP, FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS product_stock_fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL, field_name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(product_id, field_name),
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1, unit_price REAL NOT NULL DEFAULT 0.0,
            total_amount REAL NOT NULL DEFAULT 0.0, status TEXT NOT NULL DEFAULT 'pending',
            delivery_status TEXT NOT NULL DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (product_id) REFERENCES products(id))""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL, stock_id INTEGER,
            delivered_content TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
            FOREIGN KEY (stock_id) REFERENCES stock(id) ON DELETE SET NULL)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS balance_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, transaction_type TEXT NOT NULL,
            amount REAL NOT NULL, balance_before REAL NOT NULL, balance_after REAL NOT NULL,
            reference TEXT, description TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id))""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, payment_method TEXT NOT NULL,
            amount REAL NOT NULL, currency TEXT NOT NULL DEFAULT 'USD', exchange_rate REAL, local_amount REAL,
            payment_reference TEXT, transaction_id TEXT, status TEXT NOT NULL DEFAULT 'pending',
            admin_note TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, approved_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id))""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS payment_methods (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, method_type TEXT NOT NULL,
            details TEXT, currency TEXT NOT NULL DEFAULT 'USD', exchange_rate REAL,
            is_active INTEGER NOT NULL DEFAULT 1, sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS referral_commissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER NOT NULL, referred_user_id INTEGER NOT NULL,
            payment_id INTEGER, commission_rate REAL NOT NULL, commission_amount REAL NOT NULL,
            deposit_number INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referrer_id) REFERENCES users(id), FOREIGN KEY (referred_user_id) REFERENCES users(id),
            FOREIGN KEY (payment_id) REFERENCES payments(id))""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, admin_telegram_id INTEGER NOT NULL, action TEXT NOT NULL,
            target_type TEXT, target_id INTEGER, details TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS purchase_intents (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL, unit_price REAL NOT NULL, total_amount REAL NOT NULL,
            payment_required REAL NOT NULL DEFAULT 0.0, status TEXT NOT NULL DEFAULT 'pending_payment',
            payment_id INTEGER, order_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, completed_at TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(product_id) REFERENCES products(id),
            FOREIGN KEY(payment_id) REFERENCES payments(id), FOREIGN KEY(order_id) REFERENCES orders(id))""")

        _add_column_if_missing(cursor, "payments", "purchase_intent_id INTEGER", "purchase_intent_id")
        _add_column_if_missing(cursor, "payments", "confirmed_by INTEGER", "confirmed_by")
        _add_column_if_missing(cursor, "payments", "confirmed_at TIMESTAMP", "confirmed_at")
        _add_column_if_missing(cursor, "orders", "payment_id INTEGER", "payment_id")
        _add_column_if_missing(cursor, "orders", "purchase_intent_id INTEGER", "purchase_intent_id")

        default_settings = {
            "store_name": "JanKug Store", "support_username": "@JanKug",
            "referral_commission": "5", "referral_deposit_limit": "10",
            "binance_pay_id": "Not configured yet", "usd_bdt_rate": "127",
        }
        for key, value in default_settings.items():
            cursor.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (key, value))

        categories = [
            ("Communication Apps", "Communication application products", "📱", 1),
            ("VPN & Proxy", "VPN and proxy products", "🔐", 2),
            ("Verification Services", "Verification services", "📲", 3),
        ]
        for name, description, emoji, sort_order in categories:
            cursor.execute("SELECT id FROM categories WHERE name=?", (name,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO categories(name,description,emoji,sort_order) VALUES(?,?,?,?)",
                               (name, description, emoji, sort_order))

        cursor.execute("SELECT id FROM categories WHERE name='Communication Apps'")
        comm_id = cursor.fetchone()["id"]
        cursor.execute("SELECT id FROM categories WHERE name='VPN & Proxy'")
        vpn_id = cursor.fetchone()["id"]
        product_seed = [
            (comm_id,"gv_old","Google Voice Old",5.00,None),(comm_id,"gv_new","Google Voice New",3.50,None),
            (comm_id,"tn_web","TextNow Web",3.00,None),(comm_id,"tn_phone","TextNow Phone",1.70,None),
            (comm_id,"tf_web","TextFree Web",2.00,None),(comm_id,"tf_phone","TextFree Phone",2.00,None),
            (comm_id,"sl_web","Sideline Web",2.00,None),(comm_id,"sl_phone","Sideline Phone",2.00,None),
            (comm_id,"talkatone","Talkatone",2.00,None),(comm_id,"textplus","TextPlus",2.00,None),
            (vpn_id,"express_3","Express VPN — 3 Days",1.00,3),(vpn_id,"cyberghost_3","CyberGhost VPN — 3 Days",1.00,3),
            (vpn_id,"vypr_3","Vypr VPN — 3 Days",1.00,3),(vpn_id,"panda_3","Panda VPN — 3 Days",1.00,3),
            (vpn_id,"express_7","Express VPN — 7 Days",1.50,7),(vpn_id,"nord_7","Nord VPN — 7 Days",1.50,7),
            (vpn_id,"pia_7","PIA VPN — 7 Days",1.50,7),(vpn_id,"ipvanish_7","IPVanish VPN — 7 Days",1.50,7),
            (vpn_id,"surfshark_7","Surfshark VPN — 7 Days",1.50,7),(vpn_id,"hotspotshield_7","HotspotShield VPN — 7 Days",1.50,7),
            (vpn_id,"hma_7","HMA VPN — 7 Days",1.50,7),(vpn_id,"pure_7","Pure VPN — 7 Days",1.50,7),
            (vpn_id,"turbo_7","Turbo VPN — 7 Days",1.50,7),(vpn_id,"avast_7","Avast VPN — 7 Days",1.50,7),
            (vpn_id,"adguard_7","AdGuard VPN — 7 Days",1.50,7),(vpn_id,"norton_7","Norton VPN — 7 Days",1.50,7),
            (vpn_id,"avg_7","AVG VPN — 7 Days",1.50,7),(vpn_id,"x_7","X-VPN — 7 Days",1.50,7),
            (vpn_id,"sky_7","Sky VPN — 7 Days",1.50,7),(vpn_id,"potato_7","Potato VPN — 7 Days",1.50,7),
            (vpn_id,"bitdefender_7","Bitdefender VPN — 7 Days",1.50,7),(vpn_id,"octohide_14","Octohide — 14 Days",2.00,14),
            (vpn_id,"express_30","Express VPN (1 Device) — 30 Days",3.00,30),(vpn_id,"nord_30","Nord VPN — 30 Days",3.00,30),
            (vpn_id,"pia_30","PIA VPN (1 Device) — 30 Days",3.00,30),(vpn_id,"avast_30","Avast VPN — 30 Days",3.00,30),
            (vpn_id,"bitdefender_30","Bitdefender VPN — 30 Days",3.00,30),(vpn_id,"hma_30","HMA VPN — 30 Days",3.00,30),
            (vpn_id,"mysterium_30","Mysterium VPN — 30 Days",3.00,30),(vpn_id,"mysterium_dark_30","Mysterium Dark — 30 Days",3.00,30),
            (vpn_id,"windscribe_30","Windscribe VPN — 30 Days",3.00,30),(vpn_id,"proton_30","Proton VPN — 30 Days",3.00,30),
        ]
        for category_id, key, name, price, validity in product_seed:
            cursor.execute("SELECT id FROM products WHERE product_key=?", (key,))
            if not cursor.fetchone():
                cursor.execute("""INSERT INTO products(category_id,product_key,name,price,product_type,validity_days)
                                  VALUES(?,?,?,?,?,?)""", (category_id,key,name,price,"stock",validity))

        # Existing Communication Apps products get the same sensible default fields
        # used by the current Add Stock screen. Admins can change these anytime.
        comm_products = cursor.execute("SELECT id FROM products WHERE category_id=?", (comm_id,)).fetchall()
        default_fields = ["Email / Username", "Password"]
        for product_row in comm_products:
            product_id = int(product_row["id"])
            for order, field_name in enumerate(default_fields, 1):
                cursor.execute("""INSERT OR IGNORE INTO product_stock_fields(product_id,field_name,sort_order)
                                  VALUES(?,?,?)""", (product_id, field_name, order))

        cursor.execute("SELECT id FROM payment_methods WHERE method_type='binance_pay'")
        if not cursor.fetchone():
            cursor.execute("""INSERT INTO payment_methods(name,method_type,details,currency,is_active,sort_order)
                              VALUES(?,?,?,?,1,1)""",
                           ("Binance Pay","binance_pay","Use Binance Pay ID shown by the store.","USD"))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_user(telegram_id: int):
    connection=get_connection(); cursor=connection.cursor()
    cursor.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
    row=cursor.fetchone(); connection.close(); return row


def create_user(telegram_id: int, username: Optional[str]=None, first_name: Optional[str]=None,
                last_name: Optional[str]=None, referred_by: Optional[int]=None):
    connection=get_connection(); cursor=connection.cursor()
    try:
        cursor.execute("BEGIN")
        cursor.execute("""INSERT OR IGNORE INTO users(telegram_id,username,first_name,last_name,referred_by)
                          VALUES(?,?,?,?,?)""",(telegram_id,username,first_name,last_name,referred_by))
        if cursor.rowcount == 1 and referred_by:
            cursor.execute("UPDATE users SET total_referrals=total_referrals+1 WHERE id=?", (referred_by,))
        connection.commit()
    except Exception:
        connection.rollback(); raise
    finally: connection.close()


def update_user(telegram_id: int, username: Optional[str]=None, first_name: Optional[str]=None,
                last_name: Optional[str]=None):
    connection=get_connection(); cursor=connection.cursor()
    cursor.execute("""UPDATE users SET username=?,first_name=?,last_name=?,updated_at=CURRENT_TIMESTAMP
                      WHERE telegram_id=?""",(username,first_name,last_name,telegram_id))
    connection.commit(); connection.close()


def get_balance(telegram_id: int) -> float:
    row=get_user(telegram_id); return float(row["balance"]) if row else 0.0


def change_balance(telegram_id: int, amount: float, transaction_type: str,
                   reference: Optional[str]=None, description: Optional[str]=None):
    connection=get_connection(); cursor=connection.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute("SELECT id,balance FROM users WHERE telegram_id=?", (telegram_id,)); user=cursor.fetchone()
        if not user: raise ValueError("User does not exist.")
        before=float(user["balance"]); after=before+float(amount)
        if after < -1e-9: raise ValueError("Insufficient balance.")
        cursor.execute("UPDATE users SET balance=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(round(after,8),user["id"]))
        cursor.execute("""INSERT INTO balance_transactions(user_id,transaction_type,amount,balance_before,balance_after,reference,description)
                          VALUES(?,?,?,?,?,?,?)""",(user["id"],transaction_type,float(amount),before,round(after,8),reference,description))
        connection.commit(); return round(after,8)
    except Exception:
        connection.rollback(); raise
    finally: connection.close()


def get_setting(key: str, default: Optional[str]=None):
    connection=get_connection(); cursor=connection.cursor()
    cursor.execute("SELECT value FROM settings WHERE key=?",(key,))
    row=cursor.fetchone(); connection.close(); return row["value"] if row else default


def set_setting(key: str, value: Any):
    connection=get_connection(); cursor=connection.cursor()
    cursor.execute("""INSERT INTO settings(key,value,updated_at) VALUES(?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP""",(key,str(value)))
    connection.commit(); connection.close()


def get_product_by_key(product_key: str):
    connection=get_connection(); cursor=connection.cursor(); cursor.execute("SELECT * FROM products WHERE product_key=?",(product_key,))
    row=cursor.fetchone(); connection.close(); return row


def get_product(product_id: int):
    connection=get_connection(); cursor=connection.cursor(); cursor.execute("SELECT * FROM products WHERE id=?",(product_id,))
    row=cursor.fetchone(); connection.close(); return row


def get_available_stock_count(product_id: int) -> int:
    connection=get_connection(); cursor=connection.cursor()
    cursor.execute("SELECT COUNT(*) AS total FROM stock WHERE product_id=? AND status='available'",(product_id,))
    row=cursor.fetchone(); connection.close(); return int(row["total"])


def create_purchase_intent(telegram_id:int, product_id:int, quantity:int, payment_required:float):
    if quantity < 1: raise ValueError("Quantity must be at least 1.")
    connection=get_connection(); cursor=connection.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        user=cursor.execute("SELECT id FROM users WHERE telegram_id=?",(telegram_id,)).fetchone()
        product=cursor.execute("SELECT price FROM products WHERE id=? AND is_active=1",(product_id,)).fetchone()
        if not user or not product: raise ValueError("User or product not found.")
        total=round(float(product["price"])*quantity,2)
        payment_required=max(0.0,round(float(payment_required),2))
        cursor.execute("""INSERT INTO purchase_intents(user_id,product_id,quantity,unit_price,total_amount,payment_required,status)
                          VALUES(?,?,?,?,?,?,?)""",(user["id"],product_id,quantity,float(product["price"]),total,payment_required,
                          "pending_payment" if payment_required>0 else "ready"))
        pid=cursor.lastrowid; connection.commit(); return pid
    except Exception:
        connection.rollback(); raise
    finally: connection.close()


def get_purchase_intent(intent_id:int):
    connection=get_connection(); cursor=connection.cursor()
    cursor.execute("""SELECT pi.*,u.telegram_id,p.product_key,p.name,p.price
        FROM purchase_intents pi JOIN users u ON u.id=pi.user_id JOIN products p ON p.id=pi.product_id WHERE pi.id=?""",(intent_id,))
    row=cursor.fetchone(); connection.close(); return row


def create_payment(telegram_id:int, amount:float, payment_method:str, purchase_intent_id:Optional[int]=None,
                   currency="USD", exchange_rate=None, local_amount=None):
    connection=get_connection(); cursor=connection.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        user=cursor.execute("SELECT id FROM users WHERE telegram_id=?",(telegram_id,)).fetchone()
        if not user: raise ValueError("User does not exist.")
        cursor.execute("""INSERT INTO payments(user_id,payment_method,amount,currency,exchange_rate,local_amount,status,purchase_intent_id)
                          VALUES(?,?,?,?,?,?,?,?)""",(user["id"],payment_method,float(amount),currency,exchange_rate,local_amount,"pending",purchase_intent_id))
        payment_id=cursor.lastrowid
        if purchase_intent_id:
            cursor.execute("UPDATE purchase_intents SET payment_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending_payment'",(payment_id,purchase_intent_id))
        connection.commit(); return payment_id
    except Exception:
        connection.rollback(); raise
    finally: connection.close()


def get_payment(payment_id:int):
    connection=get_connection(); cursor=connection.cursor()
    cursor.execute("""SELECT pay.*,u.telegram_id,pi.product_id,pi.quantity,pi.total_amount,pi.status AS purchase_status
        FROM payments pay JOIN users u ON u.id=pay.user_id LEFT JOIN purchase_intents pi ON pi.id=pay.purchase_intent_id WHERE pay.id=?""",(payment_id,))
    row=cursor.fetchone(); connection.close(); return row


def submit_payment_reference(payment_id:int, transaction_id:str):
    connection=get_connection(); cursor=connection.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        payment=cursor.execute("SELECT * FROM payments WHERE id=?",(payment_id,)).fetchone()
        if not payment: raise ValueError("Payment not found.")
        if payment["status"]!="pending": raise ValueError("Payment is no longer pending.")
        cursor.execute("UPDATE payments SET transaction_id=?,payment_reference=?,admin_note=NULL WHERE id=?",(transaction_id.strip(),transaction_id.strip(),payment_id))
        connection.commit()
    except Exception:
        connection.rollback(); raise
    finally: connection.close()


def _complete_purchase_locked(cursor, intent_id:int, payment_id:Optional[int]=None, confirmed_by:Optional[int]=None):
    intent=cursor.execute("""SELECT pi.*,u.telegram_id,u.balance,p.name,p.price,p.product_type,c.name AS category_name FROM purchase_intents pi
                            JOIN users u ON u.id=pi.user_id JOIN products p ON p.id=pi.product_id
                            LEFT JOIN categories c ON c.id=p.category_id WHERE pi.id=?""",(intent_id,)).fetchone()
    if not intent: raise ValueError("Purchase intent not found.")
    if intent["status"]=="completed":
        return {"already_completed":True,"order_id":intent["order_id"],"telegram_id":intent["telegram_id"],"delivered":[]}
    if intent["status"] not in ("ready","pending_payment"): raise ValueError("Purchase is not payable/completable.")
    quantity=int(intent["quantity"]); total=float(intent["total_amount"])
    available=cursor.execute("SELECT id,stock_content FROM stock WHERE product_id=? AND status='available' ORDER BY id LIMIT ?",(intent["product_id"],quantity)).fetchall()
    if len(available)<quantity: raise ValueError(f"Only {len(available)} item(s) are currently in stock.")
    balance=float(intent["balance"])
    if balance+1e-9<total: raise ValueError("Insufficient balance to complete purchase.")
    before=balance; after=round(balance-total,8)
    cursor.execute("UPDATE users SET balance=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(after,intent["user_id"]))
    cursor.execute("""INSERT INTO balance_transactions(user_id,transaction_type,amount,balance_before,balance_after,reference,description)
                      VALUES(?,?,?,?,?,?,?)""",(intent["user_id"],"purchase",-total,before,after,f"purchase:{intent_id}",f"Purchase #{intent_id}: {intent['name']} x{quantity}"))
    cursor.execute("""INSERT INTO orders(user_id,product_id,quantity,unit_price,total_amount,status,delivery_status,payment_id,purchase_intent_id,completed_at)
                      VALUES(?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",(intent["user_id"],intent["product_id"],quantity,intent["unit_price"],total,"completed","delivered",payment_id,intent_id))
    order_id=cursor.lastrowid; delivered=[]
    for item in available:
        cursor.execute("UPDATE stock SET status='sold',order_id=?,sold_at=CURRENT_TIMESTAMP WHERE id=? AND status='available'",(order_id,item["id"]))
        if cursor.rowcount!=1: raise ValueError("Stock changed while processing. Please try again.")
        cursor.execute("INSERT INTO order_items(order_id,stock_id,delivered_content) VALUES(?,?,?)",(order_id,item["id"],item["stock_content"]))
        delivered.append(item["stock_content"])
    cursor.execute("UPDATE purchase_intents SET status='completed',order_id=?,updated_at=CURRENT_TIMESTAMP,completed_at=CURRENT_TIMESTAMP WHERE id=?",(order_id,intent_id))
    return {"already_completed":False,"order_id":order_id,"telegram_id":intent["telegram_id"],"delivered":delivered,"total":total,"balance_after":after,"product_name":intent["name"],"quantity":quantity,
            "product_id":int(intent["product_id"]),"product_type":intent["product_type"],"category_name":intent["category_name"]}


def complete_purchase(intent_id:int):
    connection=get_connection(); cursor=connection.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE"); result=_complete_purchase_locked(cursor,intent_id); connection.commit(); return result
    except Exception:
        connection.rollback(); raise
    finally: connection.close()


def confirm_payment(payment_id:int, admin_id:int):
    connection=get_connection(); cursor=connection.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        payment=cursor.execute("SELECT * FROM payments WHERE id=?",(payment_id,)).fetchone()
        if not payment: raise ValueError("Payment not found.")
        if payment["status"]=="paid":
            intent_id=payment["purchase_intent_id"]
            result={"payment_id":payment_id,"already_paid":True,"purchase":None}
            if intent_id: result["purchase"]=_complete_purchase_locked(cursor,intent_id,payment_id,admin_id)
            connection.commit(); return result
        if payment["status"]!="pending": raise ValueError(f"Payment status is {payment['status']}.")
        user=cursor.execute("SELECT id,balance FROM users WHERE id=?",(payment["user_id"],)).fetchone()
        before=float(user["balance"]); amount=float(payment["amount"]); after=round(before+amount,8)
        cursor.execute("UPDATE users SET balance=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(after,user["id"]))
        cursor.execute("""INSERT INTO balance_transactions(user_id,transaction_type,amount,balance_before,balance_after,reference,description)
                          VALUES(?,?,?,?,?,?,?)""",(user["id"],"payment",amount,before,after,f"payment:{payment_id}",f"Payment #{payment_id} confirmed"))
        cursor.execute("UPDATE payments SET status='paid',approved_at=CURRENT_TIMESTAMP,confirmed_at=CURRENT_TIMESTAMP,confirmed_by=? WHERE id=?",(admin_id,payment_id))
        intent_id=payment["purchase_intent_id"]; purchase=None
        if intent_id:
            cursor.execute("UPDATE purchase_intents SET status='ready',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending_payment'",(intent_id,))
            purchase=_complete_purchase_locked(cursor,intent_id,payment_id,admin_id)
        connection.commit(); return {"payment_id":payment_id,"already_paid":False,"purchase":purchase}
    except Exception:
        connection.rollback(); raise
    finally: connection.close()


def cancel_payment(payment_id:int, admin_id:int, note:Optional[str]=None):
    connection=get_connection(); cursor=connection.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        payment=cursor.execute("SELECT purchase_intent_id,status FROM payments WHERE id=?",(payment_id,)).fetchone()
        if not payment: raise ValueError("Payment not found.")
        if payment["status"]!="pending": raise ValueError("Payment is no longer pending.")
        cursor.execute("UPDATE payments SET status='cancelled',admin_note=?,confirmed_by=?,confirmed_at=CURRENT_TIMESTAMP WHERE id=?",(note,admin_id,payment_id))
        if payment["purchase_intent_id"]:
            cursor.execute("UPDATE purchase_intents SET status='cancelled',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending_payment'",(payment["purchase_intent_id"],))
        connection.commit()
    except Exception:
        connection.rollback(); raise
    finally: connection.close()


def get_recent_orders(telegram_id:int, hours:int=24, limit:int=20):
    connection=get_connection(); cursor=connection.cursor()
    cursor.execute("""SELECT o.*,p.name FROM orders o JOIN users u ON u.id=o.user_id JOIN products p ON p.id=o.product_id
                      WHERE u.telegram_id=? AND o.created_at >= datetime('now', ?) ORDER BY o.id DESC LIMIT ?""",(telegram_id,f"-{hours} hours",limit))
    rows=cursor.fetchall(); connection.close(); return rows


def get_order_items(order_id:int):
    connection=get_connection(); cursor=connection.cursor()
    cursor.execute("SELECT * FROM order_items WHERE order_id=? ORDER BY id",(order_id,))
    rows=cursor.fetchall(); connection.close(); return rows


def get_pending_payment(payment_id:int):
    return get_payment(payment_id)


# =========================
# STAGE 5A ADMIN HELPERS
# =========================

def admin_dashboard_stats():
    con=get_connection(); cur=con.cursor()
    try:
        total_users=cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_products=cur.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        available_stock=cur.execute("SELECT COUNT(*) FROM stock WHERE status='available'").fetchone()[0]
        total_sales=cur.execute("SELECT COALESCE(SUM(total_amount),0) FROM orders WHERE status='completed'").fetchone()[0]
        sales_24h=cur.execute("SELECT COALESCE(SUM(total_amount),0) FROM orders WHERE status='completed' AND created_at >= datetime('now','-24 hours')").fetchone()[0]
        sales_7d=cur.execute("SELECT COALESCE(SUM(total_amount),0) FROM orders WHERE status='completed' AND created_at >= datetime('now','-7 days')").fetchone()[0]
        sales_30d=cur.execute("SELECT COALESCE(SUM(total_amount),0) FROM orders WHERE status='completed' AND created_at >= datetime('now','-30 days')").fetchone()[0]
        return {"total_users":int(total_users),"total_products":int(total_products),"available_stock":int(available_stock),
                "total_sales":float(total_sales or 0),"sales_24h":float(sales_24h or 0),
                "sales_7d":float(sales_7d or 0),"sales_30d":float(sales_30d or 0)}
    finally:
        con.close()


def admin_list_products():
    con=get_connection(); cur=con.cursor()
    try:
        return cur.execute("""SELECT p.*,c.name AS category_name,
            (SELECT COUNT(*) FROM stock s WHERE s.product_id=p.id AND s.status='available') AS available_stock,
            (SELECT COUNT(*) FROM stock s WHERE s.product_id=p.id AND s.status='sold') AS sold_stock
            FROM products p LEFT JOIN categories c ON c.id=p.category_id
            ORDER BY COALESCE(c.sort_order,999),p.sort_order,p.id""").fetchall()
    finally: con.close()


def admin_get_product(product_id:int):
    con=get_connection(); cur=con.cursor()
    try:
        return cur.execute("""SELECT p.*,c.name AS category_name,
            (SELECT COUNT(*) FROM stock s WHERE s.product_id=p.id AND s.status='available') AS available_stock,
            (SELECT COUNT(*) FROM stock s WHERE s.product_id=p.id AND s.status='sold') AS sold_stock
            FROM products p LEFT JOIN categories c ON c.id=p.category_id WHERE p.id=?""",(product_id,)).fetchone()
    finally: con.close()


def admin_list_categories():
    con=get_connection(); cur=con.cursor()
    try:
        return cur.execute("SELECT * FROM categories WHERE is_active=1 ORDER BY sort_order,id").fetchall()
    finally: con.close()


def admin_create_product(category_id:int, product_key:str, name:str, price:float,
                         description:Optional[str]=None, product_type:str="stock",
                         validity_days:Optional[int]=None):
    con=get_connection(); cur=con.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        if not cur.execute("SELECT id FROM categories WHERE id=? AND is_active=1",(category_id,)).fetchone():
            raise ValueError("Category not found or inactive.")
        if cur.execute("SELECT id FROM products WHERE product_key=?",(product_key,)).fetchone():
            raise ValueError("Product key already exists.")
        cur.execute("""INSERT INTO products(category_id,product_key,name,description,price,product_type,validity_days,is_active)
                       VALUES(?,?,?,?,?,?,?,1)""",
                    (category_id,product_key,name,description,float(price),product_type,validity_days))
        pid=cur.lastrowid
        category_name=cur.execute("SELECT name FROM categories WHERE id=?",(category_id,)).fetchone()
        if category_name and str(category_name["name"]).lower()=="communication apps":
            for order, field_name in enumerate(("Email / Username", "Password"), 1):
                cur.execute("INSERT OR IGNORE INTO product_stock_fields(product_id,field_name,sort_order) VALUES(?,?,?)",
                            (pid, field_name, order))
        con.commit(); return pid
    except Exception:
        con.rollback(); raise
    finally: con.close()


def admin_update_product(product_id:int, *, name=None, price=None, is_active=None,
                         category_id=None, description=None):
    con=get_connection(); cur=con.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        p=cur.execute("SELECT * FROM products WHERE id=?",(product_id,)).fetchone()
        if not p: raise ValueError("Product not found.")
        values=[]; sets=[]
        if name is not None: sets.append("name=?"); values.append(str(name))
        if price is not None: sets.append("price=?"); values.append(float(price))
        if is_active is not None: sets.append("is_active=?"); values.append(int(is_active))
        if category_id is not None: sets.append("category_id=?"); values.append(int(category_id))
        if description is not None: sets.append("description=?"); values.append(str(description))
        if sets:
            sets.append("updated_at=CURRENT_TIMESTAMP")
            values.append(product_id)
            cur.execute(f"UPDATE products SET {','.join(sets)} WHERE id=?",values)
        con.commit()
    except Exception:
        con.rollback(); raise
    finally: con.close()


def admin_delete_product(product_id:int):
    con=get_connection(); cur=con.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        p=cur.execute("SELECT id,name FROM products WHERE id=?",(product_id,)).fetchone()
        if not p: raise ValueError("Product not found.")
        stock_count=cur.execute("SELECT COUNT(*) FROM stock WHERE product_id=?",(product_id,)).fetchone()[0]
        order_count=cur.execute("SELECT COUNT(*) FROM orders WHERE product_id=?",(product_id,)).fetchone()[0]
        if stock_count or order_count:
            cur.execute("UPDATE products SET is_active=0,updated_at=CURRENT_TIMESTAMP WHERE id=?",(product_id,))
            result="Product has existing stock/order history, so it was safely deactivated."
        else:
            cur.execute("DELETE FROM products WHERE id=?",(product_id,))
            result="Product removed permanently."
        con.commit(); return result
    except Exception:
        con.rollback(); raise
    finally: con.close()


def admin_log(admin_telegram_id:int, action:str, target_type:Optional[str]=None,
              target_id:Optional[int]=None, details:Optional[str]=None):
    con=get_connection(); cur=con.cursor()
    try:
        cur.execute("""INSERT INTO admin_logs(admin_telegram_id,action,target_type,target_id,details)
                       VALUES(?,?,?,?,?)""",(admin_telegram_id,action,target_type,target_id,details))
        con.commit()
    finally: con.close()


def database_health_check() -> bool:
    try:
        connection=get_connection(); cursor=connection.cursor(); cursor.execute("SELECT 1")
        result=cursor.fetchone(); connection.close(); return result is not None
    except Exception: return False


# =========================
# STAGE 5B STOCK HELPERS
# =========================

def admin_get_stock_fields(product_id=None, field_id=None):
    con=get_connection(); cur=con.cursor()
    try:
        if field_id is not None:
            return cur.execute("""SELECT * FROM product_stock_fields WHERE id=?""",(field_id,)).fetchall()
        return cur.execute("""SELECT * FROM product_stock_fields WHERE product_id=? ORDER BY sort_order,id""",(product_id,)).fetchall()
    finally:
        con.close()


def admin_add_stock_field(product_id:int, field_name:str, admin_telegram_id:int):
    name=str(field_name or "").strip()
    if not name: raise ValueError("Field name cannot be empty.")
    if len(name)>50: raise ValueError("Field name must be 1-50 characters.")
    con=get_connection(); cur=con.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        if not cur.execute("SELECT id FROM products WHERE id=?",(product_id,)).fetchone():
            raise ValueError("Product not found.")
        exists=cur.execute("SELECT id FROM product_stock_fields WHERE product_id=? AND lower(field_name)=lower(?)",(product_id,name)).fetchone()
        if exists: raise ValueError("A field with this name already exists for this product.")
        max_order=cur.execute("SELECT COALESCE(MAX(sort_order),0) FROM product_stock_fields WHERE product_id=?",(product_id,)).fetchone()[0]
        cur.execute("INSERT INTO product_stock_fields(product_id,field_name,sort_order) VALUES(?,?,?)",(product_id,name,int(max_order)+1))
        field_id=cur.lastrowid
        cur.execute("INSERT INTO admin_logs(admin_telegram_id,action,target_type,target_id,details) VALUES(?,?,?,?,?)",
                    (admin_telegram_id,"add_stock_field","stock_field",field_id,f"product={product_id}; name={name}"))
        con.commit(); return field_id
    except Exception:
        con.rollback(); raise
    finally:
        con.close()


def admin_rename_stock_field(field_id:int, field_name:str, admin_telegram_id:int):
    name=str(field_name or "").strip()
    if not name: raise ValueError("Field name cannot be empty.")
    if len(name)>50: raise ValueError("Field name must be 1-50 characters.")
    con=get_connection(); cur=con.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        row=cur.execute("SELECT * FROM product_stock_fields WHERE id=?",(field_id,)).fetchone()
        if not row: raise ValueError("Field not found.")
        exists=cur.execute("SELECT id FROM product_stock_fields WHERE product_id=? AND lower(field_name)=lower(?) AND id<>?",(row["product_id"],name,field_id)).fetchone()
        if exists: raise ValueError("A field with this name already exists for this product.")
        cur.execute("UPDATE product_stock_fields SET field_name=? WHERE id=?",(name,field_id))
        cur.execute("INSERT INTO admin_logs(admin_telegram_id,action,target_type,target_id,details) VALUES(?,?,?,?,?)",
                    (admin_telegram_id,"rename_stock_field","stock_field",field_id,f"name={name}"))
        con.commit()
    except Exception:
        con.rollback(); raise
    finally:
        con.close()


def admin_remove_stock_field(field_id:int):
    con=get_connection(); cur=con.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        row=cur.execute("SELECT id,product_id FROM product_stock_fields WHERE id=?",(field_id,)).fetchone()
        if not row: raise ValueError("Field not found.")
        cur.execute("DELETE FROM product_stock_fields WHERE id=?",(field_id,))
        # Keep the remaining field order clean.
        remaining=cur.execute("SELECT id FROM product_stock_fields WHERE product_id=? ORDER BY sort_order,id",(row["product_id"],)).fetchall()
        for order,item in enumerate(remaining,1):
            cur.execute("UPDATE product_stock_fields SET sort_order=? WHERE id=?",(order,item["id"]))
        con.commit()
    except Exception:
        con.rollback(); raise
    finally:
        con.close()


def admin_stock_summary():
    con=get_connection(); cur=con.cursor()
    try:
        return cur.execute("""SELECT p.id,p.name,p.is_active,
            (SELECT COUNT(*) FROM stock s WHERE s.product_id=p.id AND s.status='available') AS available_stock,
            (SELECT COUNT(*) FROM stock s WHERE s.product_id=p.id AND s.status='sold') AS sold_stock
            FROM products p ORDER BY p.id""").fetchall()
    finally: con.close()


def admin_stock_items(product_id=None, status="available", limit=50, stock_id=None):
    con=get_connection(); cur=con.cursor()
    try:
        if stock_id is not None:
            return cur.execute("""SELECT s.*,p.name AS product_name FROM stock s JOIN products p ON p.id=s.product_id
                                 WHERE s.id=? AND s.status=?""",(stock_id,status)).fetchall()
        if product_id is None:
            return cur.execute("""SELECT s.*,p.name AS product_name FROM stock s JOIN products p ON p.id=s.product_id
                                 WHERE s.status=? ORDER BY s.id DESC LIMIT ?""",(status,limit)).fetchall()
        return cur.execute("""SELECT s.*,p.name AS product_name FROM stock s JOIN products p ON p.id=s.product_id
                             WHERE s.product_id=? AND s.status=? ORDER BY s.id ASC LIMIT ?""",(product_id,status,limit)).fetchall()
    finally: con.close()


def admin_add_stock(product_id:int, contents, admin_telegram_id:int):
    if not contents: raise ValueError("No stock supplied.")
    con=get_connection(); cur=con.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        p=cur.execute("SELECT id,name FROM products WHERE id=?",(product_id,)).fetchone()
        if not p: raise ValueError("Product not found.")
        count=0
        for content in contents:
            value=str(content).strip()
            if not value: continue
            cur.execute("INSERT INTO stock(product_id,stock_content,status) VALUES(?,?,'available')",(product_id,value))
            count+=1
        if count==0: raise ValueError("No valid stock items supplied.")
        cur.execute("INSERT INTO admin_logs(admin_telegram_id,action,target_type,target_id,details) VALUES(?,?,?,?,?)",
                    (admin_telegram_id,"add_stock","product",product_id,f"added={count}"))
        con.commit(); return count
    except Exception:
        con.rollback(); raise
    finally: con.close()


def admin_remove_stock(stock_id:int, admin_telegram_id:int):
    con=get_connection(); cur=con.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        item=cur.execute("SELECT id,product_id,status FROM stock WHERE id=?",(stock_id,)).fetchone()
        if not item: raise ValueError("Stock item not found.")
        if item["status"]!="available": raise ValueError("Only available stock can be removed.")
        cur.execute("UPDATE stock SET status='removed',sold_at=NULL WHERE id=? AND status='available'",(stock_id,))
        if cur.rowcount!=1: raise ValueError("Stock item could not be removed.")
        cur.execute("INSERT INTO admin_logs(admin_telegram_id,action,target_type,target_id,details) VALUES(?,?,?,?,?)",
                    (admin_telegram_id,"remove_stock","stock",stock_id,"removed bad/unwanted stock"))
        con.commit(); return "Stock removed successfully."
    except Exception:
        con.rollback(); raise
    finally: con.close()
