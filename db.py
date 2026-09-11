import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

DB_PATH = "sales_bot.db"

@contextmanager
def conn():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()

def _cols(con, table):
    return {r["name"] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}

def _add(con, table, column, definition):
    if column not in _cols(con, table):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def init_db():
    with conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY, name TEXT NOT NULL DEFAULT '',
            username TEXT, balance REAL NOT NULL DEFAULT 0,
            referred_by INTEGER, ref_income REAL NOT NULL DEFAULT 0,
            blocked INTEGER NOT NULL DEFAULT 0, disabled INTEGER NOT NULL DEFAULT 0,
            block_reason TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen TEXT
        );
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT, product_id TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL, group_name TEXT DEFAULT '', name TEXT NOT NULL,
            price REAL NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
            coming_soon INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS inventory(
            id INTEGER PRIMARY KEY AUTOINCREMENT, product_id TEXT NOT NULL,
            email TEXT NOT NULL, password TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'AVAILABLE', sold_to INTEGER,
            sold_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS orders(
            order_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            product_id TEXT NOT NULL, quantity INTEGER NOT NULL, total REAL NOT NULL,
            payment_method TEXT, status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            paid_at TEXT, delivered_at TEXT, admin_note TEXT
        );
        CREATE TABLE IF NOT EXISTS order_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL,
            inventory_id INTEGER, email TEXT NOT NULL, password TEXT NOT NULL,
            delivered_at TEXT
        );
        CREATE TABLE IF NOT EXISTS balance_requests(
            request_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            amount REAL NOT NULL, currency TEXT DEFAULT 'USD',
            usd_amount REAL, rate REAL, payment_method TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, approved_at TEXT
        );
        CREATE TABLE IF NOT EXISTS referral_deposits(
            id INTEGER PRIMARY KEY AUTOINCREMENT, referred_user_id INTEGER NOT NULL,
            referrer_id INTEGER NOT NULL, request_id INTEGER, usd_amount REAL NOT NULL,
            commission REAL NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY, value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS payment_methods(
            id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL, emoji TEXT DEFAULT '💳', currency TEXT DEFAULT 'USD',
            instructions TEXT DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS admin_actions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER NOT NULL,
            action TEXT NOT NULL, target TEXT, details TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS broadcasts(
            id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, message TEXT,
            sent INTEGER DEFAULT 0, failed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS button_settings(
            key TEXT PRIMARY KEY, text TEXT NOT NULL, row_no INTEGER DEFAULT 0, col_no INTEGER DEFAULT 0, enabled INTEGER DEFAULT 1
        );
        """)
        # Safe migration for the older V2/V1 database.
        _add(con,"users","blocked","INTEGER NOT NULL DEFAULT 0")
        _add(con,"users","disabled","INTEGER NOT NULL DEFAULT 0")
        _add(con,"users","block_reason","TEXT")
        _add(con,"users","last_seen","TEXT")
        _add(con,"products","group_name","TEXT DEFAULT ''")
        _add(con,"products","sort_order","INTEGER NOT NULL DEFAULT 0")
        _add(con,"inventory","created_at","TEXT")
        _add(con,"orders","paid_at","TEXT")
        _add(con,"orders","delivered_at","TEXT")
        _add(con,"orders","admin_note","TEXT")
        _add(con,"balance_requests","currency","TEXT DEFAULT 'USD'")
        _add(con,"balance_requests","usd_amount","REAL")
        _add(con,"balance_requests","rate","REAL")
        _add(con,"balance_requests","payment_method","TEXT")
        defaults = {
            "REFERRAL_RATE":"0.05","REFERRAL_DEPOSIT_LIMIT":"10",
            "USD_BDT_RATE":"127","LOW_STOCK_THRESHOLD":"5",
            "BALANCE_MIN":"0.10","BALANCE_MAX":"10000",
            "SUPPORT_USERNAME":"@JanKug"
        }
        for k,v in defaults.items():
            con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",(k,v))
        for code,name,emoji,currency,instructions,order in [
            ("binance","Binance Pay","🟡","USD","Send the exact USD amount to the Binance Pay ID shown by the bot.",1),
            ("bkash","bKash","🟢","BDT","Send BDT to the bKash number configured by Admin, then press I Have Paid.",2),
            ("nagad","Nagad","🔵","BDT","Send BDT to the Nagad number configured by Admin, then press I Have Paid.",3),
        ]:
            con.execute("""INSERT OR IGNORE INTO payment_methods
                (code,name,emoji,currency,instructions,enabled,sort_order)
                VALUES(?,?,?,?,?,0,?)""",(code,name,emoji,currency,instructions,order))
        # Existing old DB may not have products table populated.
        try:
            from config import PRODUCTS
            for i,(pid,p) in enumerate(PRODUCTS.items()):
                con.execute("""INSERT INTO products(product_id,category,group_name,name,price,active,coming_soon,sort_order)
                    VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(product_id) DO UPDATE SET category=excluded.category,
                    group_name=excluded.group_name, name=excluded.name""",
                    (pid,p["category"],p.get("group_name",""),p["name"],p.get("price",0),
                     p.get("active",1),p.get("coming_soon",0),i))
        except Exception:
            pass
        buttons = {
            "profile":"🧑‍💼 My Profile","products":"🛍️ BUY PRODUCTS",
            "orders":"📦 MY ORDERS","balance":"💳 ADD BALANCE",
            "refer":"👥 REFER","support":"🎧 SUPPORT"
        }
        for i,(k,t) in enumerate(buttons.items()):
            con.execute("INSERT OR IGNORE INTO button_settings(key,text,row_no,col_no,enabled) VALUES(?,?,?,?,1)",
                        (k,t,i//2,i%2))

def setting(key, default=None):
    # Self-healing guard: Railway may reuse an older sales_bot.db.
    # Always ensure the settings table exists before reading it.
    with conn() as con:
        con.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        r=con.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone()
        return r["value"] if r else default

def set_setting(key,value):
    with conn() as con:
        con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,str(value)))

def payment_methods(enabled_only=False):
    with conn() as con:
        q="SELECT * FROM payment_methods"
        if enabled_only: q+=" WHERE enabled=1"
        q+=" ORDER BY sort_order,id"
        return con.execute(q).fetchall()

def get_payment(code):
    with conn() as con:
        return con.execute("SELECT * FROM payment_methods WHERE code=?",(code,)).fetchone()

def add_payment(code,name,emoji,currency,instructions,enabled=1):
    with conn() as con:
        cur=con.execute("""INSERT INTO payment_methods(code,name,emoji,currency,instructions,enabled,sort_order)
            VALUES(?,?,?,?,?,?,COALESCE((SELECT MAX(sort_order)+1 FROM payment_methods),1))""",
            (code.lower().strip(),name,emoji or "💳",currency.upper(),instructions,enabled))
        return cur.lastrowid

def update_payment(code, **kwargs):
    allowed={"name","emoji","currency","instructions","enabled","sort_order"}
    parts=[]; vals=[]
    for k,v in kwargs.items():
        if k in allowed:
            parts.append(f"{k}=?"); vals.append(v)
    if not parts:return False
    vals.append(code)
    with conn() as con:
        cur=con.execute(f"UPDATE payment_methods SET {','.join(parts)} WHERE code=?",vals)
        return cur.rowcount==1

def upsert_user(user_id,name,username,referred_by=None):
    now=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with conn() as con:
        old=con.execute("SELECT user_id,referred_by FROM users WHERE user_id=?",(user_id,)).fetchone()
        if not old:
            con.execute("INSERT INTO users(user_id,name,username,referred_by,last_seen) VALUES(?,?,?,?,?)",
                        (user_id,name or "",username or "",referred_by,now))
        else:
            con.execute("UPDATE users SET name=?,username=?,last_seen=? WHERE user_id=?",
                        (name or "",username or "",now,user_id))

def get_user(uid):
    with conn() as con:return con.execute("SELECT * FROM users WHERE user_id=?",(uid,)).fetchone()

def categories():
    with conn() as con:return [r["category"] for r in con.execute("SELECT DISTINCT category FROM products WHERE active=1 ORDER BY MIN(sort_order)").fetchall()]

def groups(category):
    with conn() as con:return [r["group_name"] for r in con.execute("SELECT group_name,MIN(sort_order) s FROM products WHERE category=? AND active=1 AND group_name<>'' GROUP BY group_name ORDER BY s",(category,)).fetchall()]

def products(category,group_name=None):
    with conn() as con:
        if group_name is None:
            return con.execute("SELECT * FROM products WHERE category=? AND active=1 ORDER BY sort_order,id",(category,)).fetchall()
        return con.execute("SELECT * FROM products WHERE category=? AND group_name=? AND active=1 ORDER BY sort_order,id",(category,group_name)).fetchall()

def get_product(pid_or_id):
    with conn() as con:
        if isinstance(pid_or_id,int):
            return con.execute("SELECT * FROM products WHERE id=?",(pid_or_id,)).fetchone()
        return con.execute("SELECT * FROM products WHERE product_id=?",(pid_or_id,)).fetchone()

def add_product(pid,category,group,name,price,active=1,coming_soon=0):
    with conn() as con:
        con.execute("""INSERT INTO products(product_id,category,group_name,name,price,active,coming_soon,sort_order)
            VALUES(?,?,?,?,?,?,?,COALESCE((SELECT MAX(sort_order)+1 FROM products),0))""",
            (pid,category,group,name,float(price),int(active),int(coming_soon)))

def update_product(pid_or_id,**kw):
    allowed={"product_id","category","group_name","name","price","active","coming_soon","sort_order"}
    parts=[]; vals=[]
    for k,v in kw.items():
        if k in allowed:parts.append(f"{k}=?");vals.append(v)
    if not parts:return False
    vals.append(pid_or_id)
    field="id" if isinstance(pid_or_id,int) else "product_id"
    with conn() as con:return con.execute(f"UPDATE products SET {','.join(parts)} WHERE {field}=?",vals).rowcount==1

def stock_count(pid):
    with conn() as con:return con.execute("SELECT COUNT(*) c FROM inventory WHERE product_id=? AND status='AVAILABLE'",(pid,)).fetchone()["c"]

def stock_summary():
    with conn() as con:
        return con.execute("""SELECT p.id,p.product_id,p.name,p.category,p.price,
            SUM(CASE WHEN i.status='AVAILABLE' THEN 1 ELSE 0 END) available,
            SUM(CASE WHEN i.status='SOLD' THEN 1 ELSE 0 END) sold,
            SUM(CASE WHEN i.status='INVALID' THEN 1 ELSE 0 END) invalid
            FROM products p LEFT JOIN inventory i ON i.product_id=p.product_id
            GROUP BY p.id ORDER BY p.sort_order,p.id""").fetchall()

def add_stock(pid,email,password):
    with conn() as con:
        con.execute("INSERT INTO inventory(product_id,email,password,status) VALUES(?,?,?,'AVAILABLE')",(pid,email,password))

def mark_invalid(inv_id):
    with conn() as con:
        return con.execute("UPDATE inventory SET status='INVALID' WHERE id=? AND status='AVAILABLE'",(inv_id,)).rowcount==1

def create_order(uid,pid,qty,total,payment=None):
    with conn() as con:
        cur=con.execute("INSERT INTO orders(user_id,product_id,quantity,total,payment_method) VALUES(?,?,?,?,?)",(uid,pid,qty,total,payment))
        return cur.lastrowid

def get_order(oid):
    with conn() as con:return con.execute("SELECT o.*,p.name product_name FROM orders o LEFT JOIN products p ON p.product_id=o.product_id WHERE o.order_id=?",(oid,)).fetchone()

def recent_orders(uid,hours=24):
    with conn() as con:return con.execute("""SELECT o.*,p.name product_name FROM orders o LEFT JOIN products p ON p.product_id=o.product_id
        WHERE o.user_id=? AND datetime(o.created_at)>=datetime('now',?) ORDER BY o.order_id DESC""",(uid,f"-{hours} hours")).fetchall()

def order_items(oid):
    with conn() as con:return con.execute("SELECT * FROM order_items WHERE order_id=? ORDER BY id",(oid,)).fetchall()

def purchase_balance(uid,pid,qty,total):
    with conn() as con:
        con.execute("BEGIN IMMEDIATE")
        u=con.execute("SELECT balance FROM users WHERE user_id=? AND blocked=0 AND disabled=0",(uid,)).fetchone()
        if not u or float(u["balance"]) + 1e-9 < float(total): con.rollback(); return None,"INSUFFICIENT_BALANCE"
        items=con.execute("SELECT * FROM inventory WHERE product_id=? AND status='AVAILABLE' ORDER BY id LIMIT ?",(pid,qty)).fetchall()
        if len(items)<qty:con.rollback();return None,"OUT_OF_STOCK"
        now=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        con.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?",(float(total),uid,float(total)))
        for it in items:
            con.execute("UPDATE inventory SET status='SOLD',sold_to=?,sold_at=? WHERE id=? AND status='AVAILABLE'",(uid,now,it["id"]))
            con.execute("INSERT INTO order_items(order_id,inventory_id,email,password,delivered_at) VALUES((SELECT MAX(order_id) FROM orders WHERE user_id=?),?,?,?,?,?)",
                        (uid,it["id"],it["email"],it["password"],now))
        # The INSERT above uses latest user's order; caller creates order immediately before this transaction.
        con.execute("""UPDATE orders SET status='DELIVERED',payment_method='Balance',paid_at=?,delivered_at=?
                       WHERE user_id=? AND product_id=? AND status='PENDING'
                       AND order_id=(SELECT MAX(order_id) FROM orders WHERE user_id=?)""",(now,now,uid,pid,uid))
        con.commit()
        new=float(con.execute("SELECT balance FROM users WHERE user_id=?",(uid,)).fetchone()["balance"])
        return [dict(x) for x in items],new

def reserve_and_deliver_order(oid):
    with conn() as con:
        con.execute("BEGIN IMMEDIATE")
        o=con.execute("SELECT * FROM orders WHERE order_id=?",(oid,)).fetchone()
        if not o or o["status"]=="DELIVERED":return None,"DONE"
        items=con.execute("SELECT * FROM inventory WHERE product_id=? AND status='AVAILABLE' ORDER BY id LIMIT ?",(o["product_id"],o["quantity"])).fetchall()
        if len(items)<o["quantity"]:con.rollback();return None,"OUT_OF_STOCK"
        now=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        for it in items:
            con.execute("UPDATE inventory SET status='SOLD',sold_to=?,sold_at=? WHERE id=? AND status='AVAILABLE'",(o["user_id"],now,it["id"]))
            con.execute("INSERT INTO order_items(order_id,inventory_id,email,password,delivered_at) VALUES(?,?,?,?,?)",(oid,it["id"],it["email"],it["password"],now))
        con.execute("UPDATE orders SET status='DELIVERED',paid_at=?,delivered_at=? WHERE order_id=?",(now,now,oid))
        con.commit()
        return [dict(x) for x in items],"DELIVERED"

def reject_order(oid):
    with conn() as con:return con.execute("UPDATE orders SET status='REJECTED' WHERE order_id=? AND status!='DELIVERED'",(oid,)).rowcount==1

def mark_paid_waiting(oid):
    with conn() as con:return con.execute("UPDATE orders SET status='WAITING_PAYMENT' WHERE order_id=? AND status='PENDING'",(oid,)).rowcount==1

def create_balance_request(uid,amount,currency="USD",usd_amount=None,rate=None,payment_method=None):
    with conn() as con:
        cur=con.execute("""INSERT INTO balance_requests(user_id,amount,currency,usd_amount,rate,payment_method,status)
            VALUES(?,?,?,?,?,?,?)""",(uid,float(amount),currency,usd_amount,rate,payment_method,"PENDING"))
        return cur.lastrowid

def get_balance_request(rid):
    with conn() as con:return con.execute("SELECT * FROM balance_requests WHERE request_id=?",(rid,)).fetchone()

def mark_balance_waiting(rid):
    with conn() as con:return con.execute("UPDATE balance_requests SET status='WAITING_PAYMENT' WHERE request_id=? AND status='PENDING'",(rid,)).rowcount==1

def approve_balance(rid):
    with conn() as con:
        con.execute("BEGIN IMMEDIATE")
        r=con.execute("SELECT * FROM balance_requests WHERE request_id=?",(rid,)).fetchone()
        if not r or r["status"] not in ("PENDING","WAITING_PAYMENT"):con.rollback();return None
        credit=float(r["usd_amount"] if r["usd_amount"] is not None else r["amount"])
        now=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        con.execute("UPDATE balance_requests SET status='APPROVED',approved_at=? WHERE request_id=?",(now,rid))
        con.execute("UPDATE users SET balance=balance+? WHERE user_id=?",(credit,r["user_id"]))
        u=con.execute("SELECT balance,referred_by FROM users WHERE user_id=?",(r["user_id"],)).fetchone()
        rate=float(setting("REFERRAL_RATE","0.05")); limit=int(setting("REFERRAL_DEPOSIT_LIMIT","10"))
        if u and u["referred_by"] and limit>0:
            cnt=con.execute("SELECT COUNT(*) c FROM referral_deposits WHERE referred_user_id=?",(r["user_id"],)).fetchone()["c"]
            if cnt<limit:
                commission=round(credit*rate,2)
                if commission>0:
                    con.execute("UPDATE users SET balance=balance+?,ref_income=ref_income+? WHERE user_id=?",(commission,commission,u["referred_by"]))
                    con.execute("INSERT INTO referral_deposits(referred_user_id,referrer_id,request_id,usd_amount,commission) VALUES(?,?,?,?,?)",(r["user_id"],u["referred_by"],rid,credit,commission))
        con.commit()
        return credit

def reject_balance(rid):
    with conn() as con:return con.execute("UPDATE balance_requests SET status='REJECTED' WHERE request_id=? AND status!='APPROVED'",(rid,)).rowcount==1

def ref_count(uid):
    with conn() as con:return con.execute("SELECT COUNT(*) c FROM users WHERE referred_by=?",(uid,)).fetchone()["c"]

def dashboard():
    with conn() as con:
        users=con.execute("SELECT COUNT(*) c FROM users WHERE disabled=0").fetchone()["c"]
        orders=con.execute("SELECT COUNT(*) c FROM orders WHERE status='DELIVERED'").fetchone()["c"]
        sales=con.execute("SELECT COALESCE(SUM(total),0) s FROM orders WHERE status='DELIVERED'").fetchone()["s"]
        pending=con.execute("SELECT COUNT(*) c FROM orders WHERE status IN ('PENDING','WAITING_PAYMENT')").fetchone()["c"]
        stock=con.execute("SELECT COUNT(*) c FROM inventory WHERE status='AVAILABLE'").fetchone()["c"]
        low=int(setting("LOW_STOCK_THRESHOLD","5"))
        lowc=con.execute("SELECT COUNT(*) c FROM (SELECT product_id,COUNT(*) c FROM inventory WHERE status='AVAILABLE' GROUP BY product_id HAVING c BETWEEN 1 AND ?)",(low,)).fetchone()["c"]
        out=con.execute("SELECT COUNT(*) c FROM products WHERE active=1 AND coming_soon=0 AND NOT EXISTS(SELECT 1 FROM inventory WHERE inventory.product_id=products.product_id AND status='AVAILABLE')").fetchone()["c"]
        return {"users":users,"orders":orders,"sales":float(sales or 0),"pending":pending,"stock":stock,"low":lowc,"out":out}

def sales_24h():
    with conn() as con:
        rows=con.execute("""SELECT o.payment_method,COUNT(*) orders,COALESCE(SUM(o.total),0) sales,
            COALESCE(SUM(o.quantity),0) qty FROM orders o
            WHERE o.status='DELIVERED' AND datetime(o.created_at)>=datetime('now','-24 hours')
            GROUP BY o.payment_method""").fetchall()
        products=con.execute("""SELECT p.name,COUNT(*) orders,SUM(o.quantity) qty,SUM(o.total) sales
            FROM orders o JOIN products p ON p.product_id=o.product_id
            WHERE o.status='DELIVERED' AND datetime(o.created_at)>=datetime('now','-24 hours')
            GROUP BY o.product_id ORDER BY sales DESC""").fetchall()
        total=con.execute("SELECT COALESCE(SUM(total),0) s FROM orders WHERE status='DELIVERED' AND datetime(created_at)>=datetime('now','-24 hours')").fetchone()["s"]
        return rows,products,float(total or 0)

def pending_orders():
    with conn() as con:return con.execute("""SELECT o.*,p.name product_name FROM orders o LEFT JOIN products p ON p.product_id=o.product_id
        WHERE o.status IN ('PENDING','WAITING_PAYMENT') ORDER BY o.order_id DESC LIMIT 50""").fetchall()

def pending_balances():
    with conn() as con:return con.execute("SELECT b.*,u.name,u.username FROM balance_requests b LEFT JOIN users u ON u.user_id=b.user_id WHERE b.status IN ('PENDING','WAITING_PAYMENT') ORDER BY b.request_id DESC LIMIT 50").fetchall()

def search_users(q):
    with conn() as con:
        q=f"%{q}%"
        return con.execute("SELECT * FROM users WHERE CAST(user_id AS TEXT) LIKE ? OR name LIKE ? OR username LIKE ? ORDER BY user_id DESC LIMIT 30",(q,q,q)).fetchall()

def all_user_ids():
    with conn() as con:return [r["user_id"] for r in con.execute("SELECT user_id FROM users WHERE disabled=0 AND blocked=0").fetchall()]

def set_user_state(uid,blocked=None,disabled=None,reason=None):
    parts=[];vals=[]
    if blocked is not None:parts.append("blocked=?");vals.append(int(blocked))
    if disabled is not None:parts.append("disabled=?");vals.append(int(disabled))
    if reason is not None:parts.append("block_reason=?");vals.append(reason)
    if not parts:return False
    vals.append(uid)
    with conn() as con:return con.execute(f"UPDATE users SET {','.join(parts)} WHERE user_id=?",vals).rowcount==1

def get_button_settings():
    with conn() as con:return con.execute("SELECT * FROM button_settings WHERE enabled=1 ORDER BY row_no,col_no").fetchall()

def set_button(key,text,row,col,enabled=1):
    with conn() as con:
        con.execute("""INSERT INTO button_settings(key,text,row_no,col_no,enabled) VALUES(?,?,?,?,?)
            ON CONFLICT(key) DO UPDATE SET text=excluded.text,row_no=excluded.row_no,col_no=excluded.col_no,enabled=excluded.enabled""",
            (key,text,int(row),int(col),int(enabled)))

def log_action(admin,action,target="",details=""):
    with conn() as con:con.execute("INSERT INTO admin_actions(admin_id,action,target,details) VALUES(?,?,?,?)",(admin,action,target,details))
