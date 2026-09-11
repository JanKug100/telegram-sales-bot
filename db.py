
import os, sqlite3, time
DB_PATH=os.getenv("DB_PATH","sales_bot.db")

def conn():
    c=sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory=sqlite3.Row
    return c

def init_db():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,first_name TEXT,username TEXT,balance REAL DEFAULT 0,referrer_id INTEGER,created_at INTEGER DEFAULT (strftime('%s','now')));
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,category TEXT NOT NULL,group_name TEXT NOT NULL,name TEXT NOT NULL,price REAL DEFAULT 0,active INTEGER DEFAULT 1,coming_soon INTEGER DEFAULT 0,sort_order INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS inventory(id INTEGER PRIMARY KEY,product_id INTEGER NOT NULL,credential TEXT NOT NULL,status TEXT DEFAULT 'AVAILABLE',created_at INTEGER DEFAULT (strftime('%s','now')),sold_at INTEGER);
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,user_id INTEGER,product_id INTEGER,product_name TEXT,quantity INTEGER,total REAL,status TEXT,paid_at INTEGER,delivered_at INTEGER,created_at INTEGER DEFAULT (strftime('%s','now')));
        CREATE TABLE IF NOT EXISTS order_items(id INTEGER PRIMARY KEY,order_id INTEGER,inventory_id INTEGER,credential TEXT);
        CREATE TABLE IF NOT EXISTS payment_methods(method_id TEXT PRIMARY KEY,name TEXT NOT NULL,emoji TEXT DEFAULT '💳',currency TEXT DEFAULT 'USD',instructions TEXT DEFAULT '',active INTEGER DEFAULT 1,automatic INTEGER DEFAULT 0,sort_order INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS payment_requests(id INTEGER PRIMARY KEY,user_id INTEGER,product_id INTEGER,quantity INTEGER,method_id TEXT,amount REAL,status TEXT DEFAULT 'PENDING',created_at INTEGER DEFAULT (strftime('%s','now')));
        CREATE TABLE IF NOT EXISTS balance_requests(id INTEGER PRIMARY KEY,user_id INTEGER,amount REAL,usd_amount REAL,rate REAL,method_id TEXT,currency TEXT,status TEXT DEFAULT 'PENDING',created_at INTEGER DEFAULT (strftime('%s','now')));
        CREATE TABLE IF NOT EXISTS referral_deposits(id INTEGER PRIMARY KEY,user_id INTEGER,referrer_id INTEGER,deposit_id INTEGER,amount REAL,commission REAL,created_at INTEGER DEFAULT (strftime('%s','now')));
        """)
        defaults={"REFERRAL_RATE":"0.05","REFERRAL_DEPOSIT_LIMIT":"10","USD_BDT_RATE":"127","LOW_STOCK_THRESHOLD":"5"}
        for k,v in defaults.items(): c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",(k,v))
        defaults_pm=[
            ("binance","Binance Pay","🟡","USD","Pay using Binance Pay. Admin can verify manually.",1,0,1),
            ("bkash","bKash","🟢","BDT","Send BDT to the bKash merchant/account shown by Admin.",0,0,2),
            ("nagad","Nagad","🔵","BDT","Send BDT to the Nagad merchant/account shown by Admin.",0,0,3),
            ("usdt_trc20","USDT TRC20","🪙","USDT","Send USDT on TRC20. Enable after configuring wallet and verification.",0,0,4)
        ]
        c.executemany("""INSERT OR IGNORE INTO payment_methods(method_id,name,emoji,currency,instructions,active,automatic,sort_order)
                         VALUES(?,?,?,?,?,?,?,?)""",defaults_pm)
        seed=[
        ("Communication Apps","Google Voice","New Google Voice",3.50),("Communication Apps","Google Voice","Old Google Voice",5.00),
        ("Communication Apps","TextNow","Web TextNow",3.00),("Communication Apps","TextNow","Phone TextNow",1.70),
        ("Communication Apps","TextFree","Web TextFree",0),("Communication Apps","TextFree","Phone TextFree",0),
        ("Communication Apps","Other","Talkatone",2.00),("Communication Apps","Other","TextPlus",2.00),
        ("VPN & Proxy","03 Days","Express VPN",0),("VPN & Proxy","03 Days","CyberGhost VPN",0),("VPN & Proxy","03 Days","Vypr VPN",0),("VPN & Proxy","03 Days","Panda VPN",0),
        ("VPN & Proxy","07 Days","Nord VPN",0),("VPN & Proxy","07 Days","Surfshark VPN",0),("VPN & Proxy","07 Days","PIA VPN",1.50),("VPN & Proxy","07 Days","IPVanish VPN",0),("VPN & Proxy","07 Days","HotspotShield VPN",0),("VPN & Proxy","07 Days","Avast VPN",0),("VPN & Proxy","07 Days","HMA VPN",0),("VPN & Proxy","07 Days","Pure VPN",0),("VPN & Proxy","07 Days","Turbo VPN",0),("VPN & Proxy","07 Days","Bitdefender VPN",0),("VPN & Proxy","07 Days","AdGuard VPN",0),("VPN & Proxy","07 Days","Norton VPN",0),("VPN & Proxy","07 Days","AVG VPN",0),("VPN & Proxy","07 Days","X-VPN",0),("VPN & Proxy","07 Days","Sky VPN",0),("VPN & Proxy","07 Days","Potato VPN",0),("VPN & Proxy","07 Days","Express VPN",1.50),
        ("VPN & Proxy","14 Days","Octohide",0),
        ("VPN & Proxy","30 Days","Express VPN - 1 Device",0),("VPN & Proxy","30 Days","NordVPN",0),("VPN & Proxy","30 Days","Proton VPN",0),("VPN & Proxy","30 Days","Avast VPN",0),("VPN & Proxy","30 Days","Bitdefender VPN",0),("VPN & Proxy","30 Days","HMA VPN",0),("VPN & Proxy","30 Days","Mysterium VPN",0),("VPN & Proxy","30 Days","MYSTERIUM DARK",0),("VPN & Proxy","30 Days","Windscribe VPN",0),("VPN & Proxy","30 Days","PIA VPN - 1 device",0),
        ("Verification Service","Coming Soon","WhatsApp",2),("Verification Service","Coming Soon","Telegram",2),("Verification Service","Coming Soon","Signal",1),("Verification Service","Coming Soon","Viber",1)]
        for i,(cat,g,n,p) in enumerate(seed):
            active=1 if p>0 and cat!="Verification Service" else 0
            r=c.execute("SELECT id FROM products WHERE category=? AND group_name=? AND name=?",(cat,g,n)).fetchone()
            if not r: c.execute("INSERT INTO products(category,group_name,name,price,active,coming_soon,sort_order) VALUES(?,?,?,?,?,?,?)",(cat,g,n,p,active,0 if active else 1,i))

def setting(key,default=None):
    init_db()
    with conn() as c:
        r=c.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone()
        if not r: return default
        try:
            return float(r["value"]) if "." in r["value"] else int(r["value"])
        except: return r["value"]

def set_setting(key,value):
    init_db()
    with conn() as c: c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,str(value)))

def upsert_user(uid,first_name,username):
    with conn() as c:
        c.execute("INSERT INTO users(id,first_name,username) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET first_name=excluded.first_name,username=excluded.username",(uid,first_name,username))

def get_user(uid):
    with conn() as c:
        r=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
        if r:return r
    upsert_user(uid,"","")
    with conn() as c:return c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()

def categories():
    with conn() as c:return [r["category"] for r in c.execute("SELECT DISTINCT category FROM products WHERE active=1 AND coming_soon=0 ORDER BY category")]
def groups(category):
    with conn() as c:return [r["group_name"] for r in c.execute("SELECT DISTINCT group_name FROM products WHERE category=? AND active=1 AND coming_soon=0 ORDER BY sort_order,group_name",(category,))]
def products(category,group):
    with conn() as c:return c.execute("SELECT * FROM products WHERE category=? AND group_name=? AND active=1 AND coming_soon=0 ORDER BY sort_order,id",(category,group)).fetchall()
def product(pid):
    with conn() as c:return c.execute("SELECT * FROM products WHERE id=?",(pid,)).fetchone()
def all_products():
    with conn() as c:return c.execute("SELECT * FROM products ORDER BY category,sort_order,id").fetchall()
def available_stock(pid):
    with conn() as c:return c.execute("SELECT COUNT(*) n FROM inventory WHERE product_id=? AND status='AVAILABLE'",(pid,)).fetchone()["n"]

def purchase_with_balance(uid,pid,qty):
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        p=c.execute("SELECT * FROM products WHERE id=? AND active=1",(pid,)).fetchone()
        u=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
        if not p or not u:return False,"❌ Product unavailable."
        total=round(float(p["price"])*qty,2)
        if u["balance"]<total:return False,f"❌ Insufficient balance.\nRequired: ${total:.2f}\nBalance: ${u['balance']:.2f}"
        inv=c.execute("SELECT * FROM inventory WHERE product_id=? AND status='AVAILABLE' ORDER BY id LIMIT ?",(pid,qty)).fetchall()
        if len(inv)<qty:return False,f"❌ Not enough stock.\nRequested: {qty}\nAvailable: {len(inv)}"
        c.execute("UPDATE users SET balance=balance-? WHERE id=?",(total,uid))
        oid=c.execute("INSERT INTO orders(user_id,product_id,product_name,quantity,total,status,paid_at,delivered_at) VALUES(?,?,?,?,?,'DELIVERED',strftime('%s','now'),strftime('%s','now'))",(uid,pid,p["name"],qty,total)).lastrowid
        creds=[]
        for x in inv:
            c.execute("UPDATE inventory SET status='SOLD',sold_at=strftime('%s','now') WHERE id=?",(x["id"],))
            c.execute("INSERT INTO order_items(order_id,inventory_id,credential) VALUES(?,?,?)",(oid,x["id"],x["credential"]))
            creds.append(x["credential"])
        text=f"✅ DELIVERY SUCCESSFUL!\n\nProduct: {p['name']}\nQuantity: {qty}\nTotal: ${total:.2f}\n\n"
        for i,v in enumerate(creds,1): text+=f"{i}. 📧 Email / Username: {v}\n"
        text+=f"\n💳 Remaining Balance: ${u['balance']-total:.2f}"
        return True,text

def payment_methods():
    with conn() as c:return c.execute("SELECT * FROM payment_methods WHERE active=1 ORDER BY sort_order,id").fetchall()
def all_payment_methods():
    with conn() as c:return c.execute("SELECT * FROM payment_methods ORDER BY sort_order,id").fetchall()
def payment_method(mid):
    with conn() as c:return c.execute("SELECT * FROM payment_methods WHERE method_id=?",(mid,)).fetchone()

def create_payment_request(uid,pid,qty,mid):
    p=product(pid); total=round(p["price"]*qty,2)
    with conn() as c:return c.execute("INSERT INTO payment_requests(user_id,product_id,quantity,method_id,amount) VALUES(?,?,?,?,?)",(uid,pid,qty,mid,total)).lastrowid
def create_balance_request(uid,amount,usd,rate,mid,currency):
    with conn() as c:return c.execute("INSERT INTO balance_requests(user_id,amount,usd_amount,rate,method_id,currency) VALUES(?,?,?,?,?,?)",(uid,amount,usd,rate,mid,currency)).lastrowid

def recent_orders(uid):
    with conn() as c:return c.execute("SELECT * FROM orders WHERE user_id=? AND created_at>=strftime('%s','now')-86400 ORDER BY id DESC",(uid,)).fetchall()
def ref_count(uid):
    with conn() as c:return c.execute("SELECT COUNT(*) n FROM users WHERE referrer_id=?",(uid,)).fetchone()["n"]
def ref_income(uid):
    with conn() as c:return c.execute("SELECT COALESCE(SUM(commission),0) n FROM referral_deposits WHERE referrer_id=?",(uid,)).fetchone()["n"]
def dashboard():
    with conn() as c:
        users=c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
        orders=c.execute("SELECT COUNT(*) n FROM orders WHERE status='DELIVERED'").fetchone()["n"]
        sales=c.execute("SELECT COALESCE(SUM(total),0) n FROM orders WHERE status='DELIVERED'").fetchone()["n"]
        pending=c.execute("SELECT COUNT(*) n FROM payment_requests WHERE status='PENDING'").fetchone()["n"]
        stock=c.execute("SELECT COUNT(*) n FROM inventory WHERE status='AVAILABLE'").fetchone()["n"]
        low=int(setting("LOW_STOCK_THRESHOLD",5))
        lowcount=c.execute("SELECT COUNT(*) n FROM (SELECT product_id,COUNT(*) n FROM inventory WHERE status='AVAILABLE' GROUP BY product_id HAVING n<=?)",(low,)).fetchone()["n"]
        out=c.execute("SELECT COUNT(*) FROM products WHERE active=1 AND coming_soon=0 AND id NOT IN (SELECT product_id FROM inventory WHERE status='AVAILABLE')").fetchone()[0]
        return dict(users=users,orders=orders,sales=sales,pending=pending,stock=stock,low=lowcount,out=out)
