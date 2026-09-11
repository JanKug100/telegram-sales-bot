import os, asyncio, logging
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log=logging.getLogger("jankug-v3")

TOKEN=os.getenv("BOT_TOKEN","").strip()
ADMIN_IDS={int(x) for x in os.getenv("ADMIN_IDS","").replace(","," ").split() if x.strip().isdigit()}

# Initialize/migrate SQLite BEFORE reading settings. This is required when Railway
# already has an older sales_bot.db that does not yet contain the settings table.
db.init_db()
SUPPORT=os.getenv("SUPPORT_USERNAME",db.setting("SUPPORT_USERNAME","@JanKug")).strip()
BINANCE_PAY_ID=os.getenv("BINANCE_PAY_ID","").strip()

def admins():
    global ADMIN_IDS
    ADMIN_IDS={int(x) for x in os.getenv("ADMIN_IDS","").replace(","," ").split() if x.strip().isdigit()}
    return ADMIN_IDS

def is_admin(uid): return uid in admins()
def money(x): return f"${float(x):.2f}"

def main_kb():
    rows={}
    for b in db.get_button_settings():
        rows.setdefault(b["row_no"],[]).append(InlineKeyboardButton(b["text"],callback_data={
            "profile":"profile","products":"products","orders":"orders","balance":"balance","refer":"refer","support":"support"
        }.get(b["key"],"home")))
    return InlineKeyboardMarkup([rows[k] for k in sorted(rows)])

def back(data="home"): return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back",callback_data=data)]])

def admin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Dashboard",callback_data="ad:dashboard"),InlineKeyboardButton("💰 24h Sales",callback_data="ad:sales24")],
        [InlineKeyboardButton("🛍️ Products",callback_data="ad:products"),InlineKeyboardButton("📦 Inventory",callback_data="ad:inventory")],
        [InlineKeyboardButton("💰 Payments",callback_data="ad:payments"),InlineKeyboardButton("💳 Payment Methods",callback_data="ad:paymethods")],
        [InlineKeyboardButton("💵 Balance Requests",callback_data="ad:balances"),InlineKeyboardButton("🧾 Orders",callback_data="ad:orders")],
        [InlineKeyboardButton("👥 Users",callback_data="ad:users"),InlineKeyboardButton("🎁 Referrals",callback_data="ad:refs")],
        [InlineKeyboardButton("⚙️ Settings",callback_data="ad:settings"),InlineKeyboardButton("🎛️ Button Manager",callback_data="ad:buttons")],
        [InlineKeyboardButton("📢 Broadcast",callback_data="ad:broadcast"),InlineKeyboardButton("🎧 Support",callback_data="ad:support")],
        [InlineKeyboardButton("🏠 Main Menu",callback_data="home")]
    ])

async def start(update,context):
    u=update.effective_user
    ref=None
    if context.args and context.args[0].startswith("ref_"):
        try: ref=int(context.args[0][4:])
        except: ref=None
        if ref==u.id: ref=None
    db.upsert_user(u.id,u.full_name,u.username,ref)
    user=db.get_user(u.id)
    if user["blocked"] or user["disabled"]:
        return await update.message.reply_text("⛔ Your account is currently unavailable. Contact Support.")
    await update.message.reply_text("🏠 <b>MAIN MENU</b>\n━━━━━━━━━━━━━━━━\nWelcome to the store!\n\nChoose an option below.",parse_mode="HTML",reply_markup=main_kb())

async def myid(update,context):
    await update.message.reply_text(f"🆔 <b>Your Telegram ID</b>\n<code>{update.effective_user.id}</code>\n\nAdmin: {'✅ YES' if is_admin(update.effective_user.id) else '❌ NO'}",parse_mode="HTML")

async def admin_cmd(update,context):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text(f"⛔ Admin access denied.\n\nYour ID: <code>{update.effective_user.id}</code>\nCurrent ADMIN_IDS: <code>{', '.join(map(str,sorted(admins()))) or 'EMPTY'}</code>",parse_mode="HTML")
    await update.message.reply_text("🛠️ <b>ADMIN PANEL V3</b>\n\nChoose an admin action:",parse_mode="HTML",reply_markup=admin_kb())

async def home(update,context):
    q=update.callback_query; await q.answer()
    await q.edit_message_text("🏠 <b>MAIN MENU</b>\n━━━━━━━━━━━━━━━━\nWelcome to the store!\n\nChoose an option below.",parse_mode="HTML",reply_markup=main_kb())

async def customer_cb(update,context):
    q=update.callback_query; await q.answer(); d=q.data
    if d=="profile":
        u=db.get_user(q.from_user.id); link=f"https://t.me/{context.bot.username}?start=ref_{u['user_id']}"
        return await q.edit_message_text(f"👤 <b>ACCOUNT DASHBOARD</b>\n━━━━━━━━━━━━━━━━\nName: {u['name']}\nUsername: @{u['username'] or 'N/A'}\nUser ID: <code>{u['user_id']}</code>\nBalance: <b>{money(u['balance'])}</b>\nRef Link: <code>{link}</code>\nTotal Refs: {db.ref_count(u['user_id'])}\nRef Income: {money(u['ref_income'])}",parse_mode="HTML",reply_markup=back())
    if d=="products":
        cs=db.categories(); kb=[[InlineKeyboardButton(c,callback_data=f"cat:{c}")] for c in cs]+[[InlineKeyboardButton("⬅️ Main Menu",callback_data="home")]]
        return await q.edit_message_text("🛍️ <b>BUY PRODUCTS</b>\n\nSelect a category:",parse_mode="HTML",reply_markup=InlineKeyboardMarkup(kb))
    if d=="orders":
        return await show_orders(q)
    if d=="balance":
        u=db.get_user(q.from_user.id)
        methods=db.payment_methods(True)
        kb=[[InlineKeyboardButton(f"{m['emoji']} {m['name']}",callback_data=f"balmethod:{m['code']}")] for m in methods]
        kb += [[InlineKeyboardButton("💳 My Balance",callback_data="showbal")],[InlineKeyboardButton("⬅️ Main Menu",callback_data="home")]]
        return await q.edit_message_text(f"💳 <b>ADD BALANCE</b>\nCurrent Balance: <b>{money(u['balance'])}</b>\n\nChoose payment method:",parse_mode="HTML",reply_markup=InlineKeyboardMarkup(kb))
    if d=="refer":
        u=db.get_user(q.from_user.id); rate=float(db.setting("REFERRAL_RATE","0.05"))*100; lim=int(db.setting("REFERRAL_DEPOSIT_LIMIT","10"))
        link=f"https://t.me/{context.bot.username}?start=ref_{u['user_id']}"
        return await q.edit_message_text(f"👥 <b>REFER & EARN</b>\n━━━━━━━━━━━━━━━━\nCommission: <b>{rate:.2f}%</b>\nFirst approved deposits: <b>{lim}</b>\n\nYour link:\n<code>{link}</code>\n\nTotal Refs: {db.ref_count(u['user_id'])}\nRef Income: {money(u['ref_income'])}",parse_mode="HTML",reply_markup=back())
    if d=="support":
        return await q.edit_message_text(f"🎧 <b>SUPPORT</b>\n\n{SUPPORT}",parse_mode="HTML",reply_markup=back())

async def show_orders(q):
    rows=db.recent_orders(q.from_user.id,24)
    if not rows:return await q.edit_message_text("📦 <b>MY ORDERS — LAST 24 HOURS</b>\n\nNo orders.",parse_mode="HTML",reply_markup=back())
    lines=["📦 <b>MY ORDERS — LAST 24 HOURS</b>","━━━━━━━━━━━━━━━━"]
    for o in rows:
        lines += [f"\n<b>#{o['order_id']}</b> — {o['product_name']}",f"Quantity: {o['quantity']} | Total: {money(o['total'])}",f"Status: {o['status']}"]
        if o["status"]=="DELIVERED":
            for i,it in enumerate(db.order_items(o["order_id"]),1):
                lines += [f"{i}.📧 Email / Username: {it['email']}",f"🔑 Password: {it['password']}"]
    await q.edit_message_text("\n".join(lines),parse_mode="HTML",reply_markup=back())

async def category_cb(update,context):
    q=update.callback_query; await q.answer(); cat=q.data[4:]; gs=db.groups(cat)
    if gs:
        kb=[[InlineKeyboardButton(g,callback_data=f"grp:{cat}|{g}")] for g in gs]
    else:
        kb=[[InlineKeyboardButton(p["name"],callback_data=f"prd:{p['product_id']}")] for p in db.products(cat)]
    kb.append([InlineKeyboardButton("⬅️ Back",callback_data="products")])
    await q.edit_message_text(f"🛍️ <b>{cat}</b>\n\nSelect:",parse_mode="HTML",reply_markup=InlineKeyboardMarkup(kb))

async def group_cb(update,context):
    q=update.callback_query; await q.answer(); cat,grp=q.data[4:].split("|",1)
    ps=db.products(cat,grp); kb=[]
    for p in ps:
        st=db.stock_count(p["product_id"])
        label="Coming Soon" if p["coming_soon"] else f"{money(p['price'])} | Stock {st}"
        kb.append([InlineKeyboardButton(f"{p['name']} — {label}",callback_data=f"prd:{p['product_id']}")])
    kb.append([InlineKeyboardButton("⬅️ Back",callback_data=f"cat:{cat}")])
    await q.edit_message_text(f"🛍️ <b>{grp}</b>",parse_mode="HTML",reply_markup=InlineKeyboardMarkup(kb))

async def product_cb(update,context):
    q=update.callback_query; await q.answer(); pid=q.data[4:]; p=db.get_product(pid)
    if not p or not p["active"] or p["coming_soon"]: return await q.edit_message_text("⏳ This product is currently unavailable.",reply_markup=back())
    st=db.stock_count(pid)
    if st<1:return await q.edit_message_text(f"❌ <b>OUT OF STOCK</b>\n\nContact {SUPPORT}.",parse_mode="HTML",reply_markup=back())
    kb=[[InlineKeyboardButton(str(x),callback_data=f"qty:{pid}:{x}") for x in (1,2,5,10)],[InlineKeyboardButton("✏️ Custom Quantity",callback_data=f"custom:{pid}")],[InlineKeyboardButton("⬅️ Back",callback_data=f"grp:{p['category']}|{p['group_name']}")]]
    await q.edit_message_text(f"🛍️ <b>{p['name']}</b>\n💵 {money(p['price'])} each\n📦 Available: {st}\n\nSelect quantity:",parse_mode="HTML",reply_markup=InlineKeyboardMarkup(kb))

async def quantity_cb(update,context):
    q=update.callback_query; await q.answer(); _,pid,qty=q.data.split(":"); await begin_purchase(q,context,pid,int(qty))

async def custom_cb(update,context):
    q=update.callback_query; await q.answer(); context.user_data["custom_pid"]=q.data[7:]
    await q.edit_message_text("✏️ Send the custom quantity as a number.",reply_markup=back())

async def begin_purchase(q,context,pid,qty):
    p=db.get_product(pid); st=db.stock_count(pid)
    if qty<1:return await q.edit_message_text("❌ Invalid quantity.")
    if qty>st:return await q.edit_message_text(f"❌ Not enough stock.\nRequested: {qty}\nAvailable: {st}\nContact {SUPPORT}.",reply_markup=back())
    total=round(float(p["price"])*qty,2)
    u=db.get_user(q.from_user.id)
    if float(u["balance"])>=total:
        oid=db.create_order(q.from_user.id,pid,qty,total,"Balance")
        items,newbal=db.purchase_balance(q.from_user.id,pid,qty,total)
        if items:
            return await q.edit_message_text(delivery(p,items,total,"Balance"),parse_mode="HTML",reply_markup=back())
    oid=db.create_order(q.from_user.id,pid,qty,total,None)
    methods=db.payment_methods(True)
    kb=[[InlineKeyboardButton(f"{m['emoji']} {m['name']}",callback_data=f"pay:{oid}:{m['code']}")] for m in methods]
    kb.append([InlineKeyboardButton("❌ Cancel",callback_data="home")])
    await q.edit_message_text(f"💳 <b>PAYMENT REQUIRED</b>\nProduct: {p['name']}\nQuantity: {qty}\nTotal: <b>{money(total)}</b>\n\nChoose payment method:",parse_mode="HTML",reply_markup=InlineKeyboardMarkup(kb))

def delivery(p,items,total,method):
    s=[f"🎉 <b>DELIVERY SUCCESSFUL!</b>","━━━━━━━━━━━━━━━━━━",f"Product: {p['name']}",f"Quantity: {len(items)}",f"Total: {money(total)}",f"Payment: {method}",""]
    for i,it in enumerate(items,1):s += [f"{i}.📧 Email / Username: {it['email']}",f"🔑 Password: {it['password']}"]
    return "\n".join(s)

async def pay_method_cb(update,context):
    q=update.callback_query; await q.answer(); _,oid,code=q.data.split(":",2); o=db.get_order(int(oid)); m=db.get_payment(code)
    if not o or o["user_id"]!=q.from_user.id or not m or not m["enabled"]:return await q.answer("Invalid payment method.",show_alert=True)
    db.update_product if False else None
    db.mark_paid_waiting(int(oid))
    text=f"💳 <b>{m['emoji']} {m['name']}</b>\n━━━━━━━━━━━━━━━━\nOrder: <code>#{oid}</code>\nAmount: <b>{money(o['total'])}</b>\nCurrency: {m['currency']}\n\n{m['instructions']}"
    if code=="binance" and BINANCE_PAY_ID:text+=f"\n\nBinance Pay ID:\n<code>{BINANCE_PAY_ID}</code>"
    kb=[[InlineKeyboardButton("✅ I Have Paid",callback_data=f"paid:{oid}")],[InlineKeyboardButton("❌ Cancel",callback_data="home")]]
    await q.edit_message_text(text,parse_mode="HTML",reply_markup=InlineKeyboardMarkup(kb))

async def paid_cb(update,context):
    q=update.callback_query; await q.answer("Payment reported.")
    oid=int(q.data.split(":")[1]); o=db.get_order(oid)
    if not o or o["user_id"]!=q.from_user.id:return
    for aid in admins():
        try:
            await context.bot.send_message(aid,f"🔔 <b>PAYMENT REPORT</b>\nOrder: <code>#{oid}</code>\nUser: <code>{q.from_user.id}</code>\nProduct: {o['product_name']}\nQty: {o['quantity']}\nAmount: <b>{money(o['total'])}</b>",parse_mode="HTML",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Approve",callback_data=f"approve:{oid}"),InlineKeyboardButton("❌ Reject",callback_data=f"reject:{oid}")]]))
        except Exception as e:log.warning("admin notify: %s",e)
    await q.edit_message_text("⏳ Payment reported. Admin will verify it.",reply_markup=back())

async def balance_method_cb(update,context):
    q=update.callback_query; await q.answer(); code=q.data.split(":")[1]; m=db.get_payment(code)
    if not m or not m["enabled"]:return await q.answer("Unavailable.",show_alert=True)
    context.user_data["bal_method"]=code
    await q.edit_message_text(f"{m['emoji']} <b>{m['name']}</b>\n\n{m['instructions']}\n\nEnter the amount in <b>{m['currency']}</b>.",parse_mode="HTML",reply_markup=back())

async def showbal(update,context):
    q=update.callback_query; await q.answer(); u=db.get_user(q.from_user.id)
    await q.edit_message_text(f"💳 Current Balance: <b>{money(u['balance'])}</b>",parse_mode="HTML",reply_markup=back())

async def approve_cb(update,context):
    q=update.callback_query
    if not is_admin(q.from_user.id):return await q.answer("⛔ Admin only.",show_alert=True)
    await q.answer(); oid=int(q.data.split(":")[1]); items,status=db.reserve_and_deliver_order(oid)
    if not items:return await q.answer(f"Cannot approve: {status}",show_alert=True)
    o=db.get_order(oid); p=db.get_product(o["product_id"])
    await context.bot.send_message(o["user_id"],delivery(p,items,o["total"],o["payment_method"] or "Payment"),parse_mode="HTML")
    await q.edit_message_text(f"✅ Order #{oid} approved and delivered.",reply_markup=admin_kb())

async def reject_cb(update,context):
    q=update.callback_query
    if not is_admin(q.from_user.id):return await q.answer("⛔ Admin only.",show_alert=True)
    await q.answer(); oid=int(q.data.split(":")[1]); db.reject_order(oid); o=db.get_order(oid)
    try:await context.bot.send_message(o["user_id"],f"❌ Order #{oid} payment was rejected.")
    except:pass
    await q.edit_message_text(f"❌ Order #{oid} rejected.",reply_markup=admin_kb())

async def balpaid_cb(update,context):
    q=update.callback_query; await q.answer("Payment reported.")
    rid=int(q.data.split(":")[1]); r=db.get_balance_request(rid)
    if not r or r["user_id"]!=q.from_user.id:return
    db.mark_balance_waiting(rid)
    for aid in admins():
        try:await context.bot.send_message(aid,f"🔔 <b>BALANCE PAYMENT</b>\nRequest: <code>#{rid}</code>\nUser: <code>{q.from_user.id}</code>\nAmount: <b>{r['amount']} {r['currency']}</b>\nUSD Credit: <b>{money(r['usd_amount'] or r['amount'])}</b>",parse_mode="HTML",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Approve",callback_data=f"bapprove:{rid}"),InlineKeyboardButton("❌ Reject",callback_data=f"breject:{rid}")]]))
        except:pass
    await q.edit_message_text("⏳ Balance payment reported. Admin will verify it.",reply_markup=back())

async def bapprove_cb(update,context):
    q=update.callback_query
    if not is_admin(q.from_user.id):return await q.answer("⛔ Admin only.",show_alert=True)
    await q.answer();rid=int(q.data.split(":")[1]);credit=db.approve_balance(rid)
    if credit is None:return await q.answer("Already processed.",show_alert=True)
    r=db.get_balance_request(rid);u=db.get_user(r["user_id"])
    await context.bot.send_message(r["user_id"],f"✅ Balance request #{rid} approved.\n💵 Added: <b>{money(credit)}</b>\n💳 New Balance: <b>{money(u['balance'])}</b>",parse_mode="HTML")
    await q.edit_message_text(f"✅ Balance request #{rid} approved.",reply_markup=admin_kb())

async def breject_cb(update,context):
    q=update.callback_query
    if not is_admin(q.from_user.id):return await q.answer("⛔ Admin only.",show_alert=True)
    await q.answer();rid=int(q.data.split(":")[1]);db.reject_balance(rid);r=db.get_balance_request(rid)
    try:await context.bot.send_message(r["user_id"],f"❌ Balance request #{rid} was rejected.")
    except:pass
    await q.edit_message_text(f"❌ Balance request #{rid} rejected.",reply_markup=admin_kb())

async def admin_cb(update,context):
    q=update.callback_query
    if not is_admin(q.from_user.id):return await q.answer("⛔ Admin only.",show_alert=True)
    await q.answer(); key=q.data[3:]
    if key=="dashboard":
        s=db.dashboard();text=f"📊 <b>DASHBOARD</b>\n━━━━━━━━━━━━━━━━\n👥 Users: {s['users']}\n🧾 Delivered Orders: {s['orders']}\n💰 Total Sales: {money(s['sales'])}\n⏳ Pending Payments: {s['pending']}\n📦 Available Stock: {s['stock']}\n🟠 Low Stock: {s['low']}\n🔴 Out of Stock: {s['out']}"
    elif key=="sales24":
        rows,prods,total=db.sales_24h(); lines=[f"💰 <b>SALES — LAST 24 HOURS</b>\n━━━━━━━━━━━━━━━━\nTotal Sales: <b>{money(total)}</b>"]
        for r in rows:lines.append(f"\n{r['payment_method'] or 'Unknown'}: {money(r['sales'])} | Orders {r['orders']} | Qty {r['qty']}")
        if prods:
            lines.append("\n📦 <b>Products</b>")
            for p in prods:lines.append(f"• {p['name']}: {p['qty']} sold | {money(p['sales'])}")
        text="\n".join(lines)
    elif key=="products":
        ps=db.stock_summary();lines=["🛍️ <b>PRODUCTS</b>","━━━━━━━━━━━━━━━━"]
        for p in ps[:50]:lines.append(f"#{p['id']} • {p['name']} • {money(p['price'])} • {'ON' if p['active'] else 'OFF'}")
        lines += ["","Commands:","<code>/addcategory Name</code>","<code>/addproduct id|category|group|name|price|active|coming_soon</code>","<code>/price product_id|new_price</code>","<code>/toggle product_id</code>","<code>/rename product_id|new name</code>"]
        text="\n".join(lines)
    elif key=="inventory":
        rows=db.stock_summary();text="📦 <b>INVENTORY</b>\n━━━━━━━━━━━━━━━━\n"+"\n".join(f"#{r['id']} {r['name']} — Available {r['available'] or 0} | Sold {r['sold'] or 0} | Invalid {r['invalid'] or 0}" for r in rows[:50])+"\n\n<code>/addstock product_id|email|password</code>"
    elif key=="payments":
        rows=db.pending_orders();text="💰 <b>PENDING PAYMENTS</b>\n━━━━━━━━━━━━━━━━\n" + ("\n".join(f"#{r['order_id']} {r['product_name']} {money(r['total'])} • {r['status']}" for r in rows) or "None.")
    elif key=="paymethods":
        ms=db.payment_methods(); lines=["💳 <b>PAYMENT METHODS</b>","━━━━━━━━━━━━━━━━"]
        for m in ms:lines.append(f"{m['emoji']} <b>{m['name']}</b> | {m['code']} | {m['currency']} | {'ON' if m['enabled'] else 'OFF'}")
        lines += ["","➕ Add any future method:","<code>/addpayment code|name|emoji|currency|instructions</code>","<code>/paytoggle code</code>","<code>/payedit code|name|emoji|currency|instructions</code>"]
        text="\n".join(lines)
    elif key=="balances":
        rows=db.pending_balances();text="💵 <b>BALANCE REQUESTS</b>\n━━━━━━━━━━━━━━━━\n"+("\n".join(f"#{r['request_id']} User {r['user_id']} • {r['amount']} {r['currency']} → {money(r['usd_amount'] or r['amount'])}" for r in rows) or "None.")
    elif key=="orders":
        rows=db.pending_orders();text="🧾 <b>ORDERS</b>\n━━━━━━━━━━━━━━━━\n"+("\n".join(f"#{r['order_id']} User {r['user_id']} • {r['product_name']} • {money(r['total'])} • {r['status']}" for r in rows) or "No pending orders.")
    elif key=="users":
        text="👥 <b>USERS</b>\n\n<code>/user USER_ID</code>\n<code>/users SEARCH</code>\n<code>/block USER_ID|reason</code>\n<code>/unblock USER_ID</code>\n<code>/disable USER_ID</code>"
    elif key=="refs":
        text=f"🎁 <b>REFERRALS</b>\n\nCommission: {float(db.setting('REFERRAL_RATE','0.05'))*100:.2f}%\nDeposit limit: {db.setting('REFERRAL_DEPOSIT_LIMIT','10')}\n\n<code>/refrate 7.5</code>\n<code>/reflimit 20</code>"
    elif key=="settings":
        text=f"⚙️ <b>SETTINGS</b>\n\nUSD/BDT: {db.setting('USD_BDT_RATE','127')}\nLow stock: {db.setting('LOW_STOCK_THRESHOLD','5')}\nBalance min/max: {db.setting('BALANCE_MIN','0.10')} / {db.setting('BALANCE_MAX','10000')}\nSupport: {db.setting('SUPPORT_USERNAME','@JanKug')}\n\n<code>/bdtrate 127</code>\n<code>/lowstock 5</code>\n<code>/support @JanKug</code>"
    elif key=="buttons":
        text="🎛️ <b>BUTTON MANAGER</b>\n\n<code>/setbutton key|new text|row|column|1</code>\nKeys: profile, products, orders, balance, refer, support"
    elif key=="broadcast":
        text="📢 <b>BROADCAST</b>\n\nUse:\n<code>/broadcast your message</code>"
    elif key=="support":
        text=f"🎧 <b>SUPPORT</b>\nCurrent: {SUPPORT}\n\n<code>/support @username</code>"
    else:text="Admin Panel"
    await q.edit_message_text(text,parse_mode="HTML",reply_markup=admin_kb())

async def addstock_cmd(update,context):
    if not is_admin(update.effective_user.id):return
    raw=" ".join(context.args)
    parts=raw.split("|",2)
    if len(parts)!=3:return await update.message.reply_text("Format: /addstock product_id|email|password")
    pid,email,pw=parts
    if not db.get_product(pid):return await update.message.reply_text("❌ Product not found.")
    db.add_stock(pid,email,pw);await update.message.reply_text("✅ Stock added.")

async def product_cmd(update,context):
    if not is_admin(update.effective_user.id):return
    parts=" ".join(context.args).split("|")
    if len(parts)<5:return await update.message.reply_text("Format: /addproduct id|category|group|name|price|active|coming_soon")
    parts += ["1","0"]
    try:db.add_product(parts[0],parts[1],parts[2],parts[3],float(parts[4]),int(parts[5]),int(parts[6]))
    except Exception as e:return await update.message.reply_text(f"❌ {e}")
    await update.message.reply_text("✅ Product added.")

async def text_admin_cmd(update,context):
    if not is_admin(update.effective_user.id):return False
    t=update.message.text.strip()
    if t.startswith("/price "):
        p=t[7:].split("|",1)
        if len(p)==2:
            ok=db.update_product(p[0],price=float(p[1]));await update.message.reply_text("✅ Price updated." if ok else "❌ Product not found.")
        return True
    if t.startswith("/toggle "):
        pid=t[8:].strip();p=db.get_product(pid)
        if p:db.update_product(pid,active=0 if p["active"] else 1,coming_soon=0 if p["active"] else p["coming_soon"]);await update.message.reply_text("✅ Product toggled.")
        return True
    if t.startswith("/rename "):
        p=t[8:].split("|",1)
        if len(p)==2:await update.message.reply_text("✅ Renamed." if db.update_product(p[0],name=p[1]) else "❌ Product not found.")
        return True
    if t.startswith("/addcategory "):
        name=t[13:].strip()
        pid="cat_"+str(abs(hash(name))%100000000)
        try:db.add_product(pid,name,"",name,0,0,1);await update.message.reply_text("✅ Category created. Add products under it with /addproduct.")
        except:await update.message.reply_text("❌ Category already exists or invalid.")
        return True
    if t.startswith("/addpayment "):
        p=t[12:].split("|",4)
        if len(p)!=5:return await update.message.reply_text("Format: /addpayment code|name|emoji|currency|instructions")
        try:db.add_payment(*p);await update.message.reply_text("✅ Payment method added. It is now available to enable/edit from Payment Methods.")
        except Exception as e:await update.message.reply_text(f"❌ {e}")
        return True
    if t.startswith("/paytoggle "):
        code=t[11:].strip();m=db.get_payment(code)
        if not m:return await update.message.reply_text("❌ Method not found.")
        db.update_payment(code,enabled=0 if m["enabled"] else 1);await update.message.reply_text("✅ Payment method toggled.")
        return True
    if t.startswith("/payedit "):
        p=t[9:].split("|",4)
        if len(p)!=5:return await update.message.reply_text("Format: /payedit code|name|emoji|currency|instructions")
        ok=db.update_payment(p[0],name=p[1],emoji=p[2],currency=p[3],instructions=p[4]);await update.message.reply_text("✅ Updated." if ok else "❌ Method not found.")
        return True
    if t.startswith("/refrate "):
        try:
            v=float(t[9:].strip()); assert 0<=v<=100
            db.set_setting("REFERRAL_RATE",v/100);await update.message.reply_text(f"✅ Referral commission set to {v:.2f}%")
        except:await update.message.reply_text("❌ Use a percentage from 0 to 100.")
        return True
    if t.startswith("/reflimit "):
        try:
            v=int(t[10:].strip()); assert v>=0
            db.set_setting("REFERRAL_DEPOSIT_LIMIT",v);await update.message.reply_text(f"✅ Referral deposit limit set to {v}.")
        except:await update.message.reply_text("❌ Invalid limit.")
        return True
    if t.startswith("/bdtrate "):
        try:
            v=float(t[9:].strip()); assert v>0
            db.set_setting("USD_BDT_RATE",v);await update.message.reply_text(f"✅ $1 = ৳{v:g}")
        except:await update.message.reply_text("❌ Invalid rate.")
        return True
    if t.startswith("/lowstock "):
        try:db.set_setting("LOW_STOCK_THRESHOLD",int(t[10:].strip()));await update.message.reply_text("✅ Low-stock threshold updated.")
        except:await update.message.reply_text("❌ Invalid value.")
        return True
    if t.startswith("/support "):
        global SUPPORT
        SUPPORT=t[9:].strip();db.set_setting("SUPPORT_USERNAME",SUPPORT);await update.message.reply_text("✅ Support updated.")
        return True
    if t.startswith("/setbutton "):
        p=t[11:].split("|",4)
        if len(p)!=5:return await update.message.reply_text("Format: /setbutton key|text|row|column|1")
        db.set_button(p[0],p[1],int(p[2]),int(p[3]),int(p[4]));await update.message.reply_text("✅ Button updated.")
        return True
    if t.startswith("/user "):
        try:
            u=db.get_user(int(t[6:].strip()))
            if not u:return await update.message.reply_text("❌ User not found.")
            return await update.message.reply_text(f"👤 {u['name']}\nID: {u['user_id']}\nUsername: @{u['username'] or 'N/A'}\nBalance: {money(u['balance'])}\nBlocked: {u['blocked']}\nDisabled: {u['disabled']}")
        except:return await update.message.reply_text("❌ Invalid ID.")
    if t.startswith("/users "):
        rows=db.search_users(t[7:].strip());return await update.message.reply_text("\n".join(f"{u['user_id']} | {u['name']} | @{u['username'] or 'N/A'} | {money(u['balance'])}" for u in rows) or "No users.")
    if t.startswith("/block "):
        p=t[7:].split("|",1)
        try:
            uid=int(p[0]);reason=p[1] if len(p)>1 else "Admin action";db.set_user_state(uid,blocked=1,reason=reason);await update.message.reply_text("✅ User blocked.")
        except:await update.message.reply_text("❌ Invalid user.")
        return True
    if t.startswith("/unblock "):
        try:db.set_user_state(int(t[9:].strip()),blocked=0,reason="");await update.message.reply_text("✅ User unblocked.")
        except:await update.message.reply_text("❌ Invalid user.")
        return True
    if t.startswith("/disable "):
        try:db.set_user_state(int(t[9:].strip()),disabled=1);await update.message.reply_text("✅ User disabled.")
        except:await update.message.reply_text("❌ Invalid user.")
        return True
    if t.startswith("/broadcast "):
        msg=t[11:].strip();sent=failed=0
        for uid in db.all_user_ids():
            try:await context.bot.send_message(uid,msg);sent+=1
            except:failed+=1
        await update.message.reply_text(f"📢 Broadcast complete.\n✅ Sent: {sent}\n❌ Failed: {failed}");return True
    return False

async def text_handler(update,context):
    # Admin commands that use ordinary text.
    if update.message.text.startswith("/") and await text_admin_cmd(update,context):return
    if "custom_pid" in context.user_data:
        pid=context.user_data.pop("custom_pid")
        try:qty=int(update.message.text.strip())
        except:return await update.message.reply_text("❌ Enter a whole number.")
        p=db.get_product(pid)
        if not p:return await update.message.reply_text("❌ Product not found.")
        st=db.stock_count(pid)
        if qty>st:return await update.message.reply_text(f"❌ Requested {qty}, available {st}.")
        total=round(float(p["price"])*qty,2);u=db.get_user(update.effective_user.id)
        if float(u["balance"])>=total:
            oid=db.create_order(update.effective_user.id,pid,qty,total,"Balance")
            items,new=db.purchase_balance(update.effective_user.id,pid,qty,total)
            if items:return await update.message.reply_text(delivery(p,items,total,"Balance"),parse_mode="HTML")
        oid=db.create_order(update.effective_user.id,pid,qty,total,None)
        ms=db.payment_methods(True);kb=[[InlineKeyboardButton(f"{m['emoji']} {m['name']}",callback_data=f"pay:{oid}:{m['code']}")] for m in ms]
        return await update.message.reply_text(f"💳 Choose payment method for <b>{p['name']}</b>\nTotal: <b>{money(total)}</b>",parse_mode="HTML",reply_markup=InlineKeyboardMarkup(kb))
    if "bal_method" in context.user_data:
        code=context.user_data.pop("bal_method");m=db.get_payment(code)
        try:amount=float(update.message.text.strip())
        except:return await update.message.reply_text("❌ Enter a valid amount.")
        if amount<=0:return await update.message.reply_text("❌ Amount must be greater than 0.")
        if m["currency"]=="BDT":
            rate=float(db.setting("USD_BDT_RATE","127"));usd=round(amount/rate,2)
        else:rate=1;usd=round(amount,2)
        mn=float(db.setting("BALANCE_MIN","0.10"));mx=float(db.setting("BALANCE_MAX","10000"))
        if usd<mn or usd>mx:return await update.message.reply_text(f"❌ USD credit must be between {money(mn)} and {money(mx)}.")
        rid=db.create_balance_request(update.effective_user.id,amount,m["currency"],usd,rate,code)
        await update.message.reply_text(f"💳 <b>{m['name']}</b>\nAmount: <b>{amount:g} {m['currency']}</b>\nRate: $1 = ৳{rate:g}\nUSD Credit: <b>{money(usd)}</b>\nRequest: <code>#{rid}</code>\n\n{m['instructions']}",parse_mode="HTML",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ I Have Paid",callback_data=f"balpaid:{rid}")],[InlineKeyboardButton("❌ Cancel",callback_data="home")]]))
        return
    await update.message.reply_text("🏠 Use /start to open the menu.")

async def error(update,context):log.exception("Unhandled error",exc_info=context.error)

def main():
    if not TOKEN:raise RuntimeError("BOT_TOKEN is missing in Railway Variables.")
    db.init_db()
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("myid",myid))
    app.add_handler(CommandHandler("admin",admin_cmd))
    app.add_handler(CommandHandler("addstock",addstock_cmd))
    app.add_handler(CommandHandler("addproduct",product_cmd))
    app.add_handler(CallbackQueryHandler(home,pattern=r"^home$"))
    app.add_handler(CallbackQueryHandler(customer_cb,pattern=r"^(profile|products|orders|balance|refer|support)$"))
    app.add_handler(CallbackQueryHandler(category_cb,pattern=r"^cat:"))
    app.add_handler(CallbackQueryHandler(group_cb,pattern=r"^grp:"))
    app.add_handler(CallbackQueryHandler(product_cb,pattern=r"^prd:"))
    app.add_handler(CallbackQueryHandler(quantity_cb,pattern=r"^qty:"))
    app.add_handler(CallbackQueryHandler(custom_cb,pattern=r"^custom:"))
    app.add_handler(CallbackQueryHandler(pay_method_cb,pattern=r"^pay:"))
    app.add_handler(CallbackQueryHandler(paid_cb,pattern=r"^paid:"))
    app.add_handler(CallbackQueryHandler(balance_method_cb,pattern=r"^balmethod:"))
    app.add_handler(CallbackQueryHandler(showbal,pattern=r"^showbal$"))
    app.add_handler(CallbackQueryHandler(balpaid_cb,pattern=r"^balpaid:"))
    app.add_handler(CallbackQueryHandler(approve_cb,pattern=r"^approve:"))
    app.add_handler(CallbackQueryHandler(reject_cb,pattern=r"^reject:"))
    app.add_handler(CallbackQueryHandler(bapprove_cb,pattern=r"^bapprove:"))
    app.add_handler(CallbackQueryHandler(breject_cb,pattern=r"^breject:"))
    app.add_handler(CallbackQueryHandler(admin_cb,pattern=r"^ad:"))
    app.add_handler(MessageHandler(filters.TEXT, text_handler))
    app.add_error_handler(error)
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__":main()
