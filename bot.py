
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("jankug")

TOKEN = os.getenv("BOT_TOKEN", "")
SUPPORT = os.getenv("SUPPORT_USERNAME", "@JanKug")
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}

def kb(rows):
    return InlineKeyboardMarkup([[InlineKeyboardButton(t, callback_data=d) for t,d in row] for row in rows])

def main_menu():
    return kb([
        [("🧑‍💼 My Profile","profile"),("🛍️ BUY PRODUCTS","cats")],
        [("📦 MY ORDERS","orders"),("💳 ADD BALANCE","addbal")],
        [("👥 REFER","refer"),("🎧 SUPPORT","support")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u=update.effective_user
    db.init_db()
    db.upsert_user(u.id, u.first_name or "", u.username or "")
    await update.message.reply_text("👋 Welcome to JanKug Store", reply_markup=main_menu())

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not authorized.")
        return
    db.init_db()
    await update.message.reply_text("🛠️ ADMIN PANEL", reply_markup=kb([
        [("📊 Dashboard","ad_dash"),("🛍️ Products","ad_products")],
        [("📦 Inventory","ad_inventory"),("💳 Payment Methods","ad_paymethods")],
        [("💰 Payments","ad_payments"),("💵 Balance Requests","ad_balance")],
        [("🧾 Orders","ad_orders"),("👥 Users","ad_users")],
        [("🎁 Referrals","ad_refs"),("⚙️ Settings","ad_settings")],
        [("🎛️ Button Manager","ad_buttons"),("📢 Broadcast","ad_broadcast")],
        [("📈 Reports","ad_reports"),("🎧 Support","support")],
    ]))

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    await q.answer()
    data=q.data
    u=q.from_user
    db.init_db()
    db.upsert_user(u.id, u.first_name or "", u.username or "")

    if data=="profile":
        x=db.get_user(u.id)
        await q.edit_message_text(
            f"👤 ACCOUNT DASHBOARD\n━━━━━━━━━━━━━━━━\n"
            f"Name: {x['first_name'] or '-'}\nUsername: @{x['username'] or 'N/A'}\nUser ID: {u.id}\n\n"
            f"💳 Balance: ${x['balance']:.2f}\n"
            f"👥 Total Refs: {db.ref_count(u.id)}\n💰 Ref Income: ${db.ref_income(u.id):.2f}",
            reply_markup=kb([[("⬅️ Back","home")]])
        )
    elif data=="home":
        await q.edit_message_text("🏠 MAIN MENU", reply_markup=main_menu())
    elif data=="cats":
        cats=db.categories()
        rows=[[(c,f"📁 {c}",) for c in []]]
        buttons=[]
        for c in cats:
            buttons.append([(f"📁 {c}",f"cat:{c}")])
        buttons.append([("⬅️ Back","home")])
        await q.edit_message_text("🛍️ BUY PRODUCTS", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t,callback_data=d) for t,d in r] for r in buttons]))
    elif data.startswith("cat:"):
        c=data[4:]
        groups=db.groups(c)
        rows=[[ (g,f"grp:{c}|{g}") ] for g in groups]
        rows.append([("⬅️ Back","cats")])
        await q.edit_message_text(f"📁 {c}", reply_markup=kb(rows))
    elif data.startswith("grp:"):
        _,rest=data.split(":",1); c,g=rest.split("|",1)
        ps=db.products(c,g)
        rows=[[(f"{p['name']} — ${p['price']:.2f}",f"prod:{p['id']}")] for p in ps]
        rows.append([("⬅️ Back",f"cat:{c}")])
        await q.edit_message_text(f"🛍️ {g}", reply_markup=kb(rows))
    elif data.startswith("prod:"):
        pid=int(data.split(":")[1]); p=db.product(pid); stock=db.available_stock(pid)
        if not p or not p["active"]:
            await q.edit_message_text("❌ Product unavailable.", reply_markup=kb([[("⬅️ Back","cats")]])); return
        if stock<=0:
            await q.edit_message_text(f"❌ OUT OF STOCK\n\n{p['name']}\nPlease contact Admin: {SUPPORT}",
                                      reply_markup=kb([[("⬅️ Back",f"grp:{p['category']}|{p['group_name']}")]])); return
        rows=[[("1","qty:%d|1"%pid),("2","qty:%d|2"%pid)],
              [("5","qty:%d|5"%pid),("10","qty:%d|10"%pid)],
              [("Custom Quantity",f"custom:{pid}")],
              [("⬅️ Back",f"grp:{p['category']}|{p['group_name']}")]]
        await q.edit_message_text(f"{p['name']}\nPrice: ${p['price']:.2f}\nAvailable: {stock}\n\nSelect quantity:",reply_markup=kb(rows))
    elif data.startswith("qty:"):
        pid,qty=map(int,data.split(":")[1].split("|")); p=db.product(pid); stock=db.available_stock(pid)
        if qty>stock:
            await q.edit_message_text(f"❌ Not Enough Stock\nRequested: {qty}\nAvailable: {stock}\n\nContact Admin: {SUPPORT}",
                                      reply_markup=kb([[("⬅️ Back",f"prod:{pid}")]])); return
        total=round(p["price"]*qty,2)
        bal=db.get_user(u.id)["balance"]
        rows=[]
        if bal>=total: rows.append([("💳 Pay with Balance",f"buybal:{pid}|{qty}")])
        rows.append([("💰 Payment Methods",f"pay:{pid}|{qty}")])
        rows.append([("⬅️ Back",f"prod:{pid}")])
        await q.edit_message_text(f"🧾 ORDER SUMMARY\n\n{p['name']}\nQuantity: {qty}\nUnit Price: ${p['price']:.2f}\nTotal: ${total:.2f}\nBalance: ${bal:.2f}",
                                  reply_markup=kb(rows))
    elif data.startswith("buybal:"):
        pid,qty=map(int,data.split(":")[1].split("|")); ok,msg=db.purchase_with_balance(u.id,pid,qty)
        await q.edit_message_text(msg, reply_markup=kb([[("⬅️ Back","cats")]]))
    elif data.startswith("pay:"):
        pid,qty=map(int,data.split(":")[1].split("|"))
        methods=db.payment_methods()
        rows=[]
        for m in methods:
            rows.append([(f"{m['emoji']} {m['name']}",f"paymethod:{pid}|{qty}|{m['method_id']}")])
        rows.append([("⬅️ Back",f"prod:{pid}")])
        await q.edit_message_text("💳 SELECT PAYMENT METHOD", reply_markup=kb(rows))
    elif data.startswith("paymethod:"):
        _,rest=data.split(":",1); pid,qty,mid=rest.split("|"); p=db.product(int(pid)); total=round(p["price"]*int(qty),2)
        m=db.payment_method(mid)
        await q.edit_message_text(
            f"💳 {m['name']}\n\nAmount: ${total:.2f}\n\n{m['instructions']}\n\n"
            f"After payment, contact Admin for verification if this method is manual.",
            reply_markup=kb([[("✅ I Have Paid",f"paid:{pid}|{qty}|{mid}")],[("⬅️ Back",f"pay:{pid}|{qty}")]])
        )
    elif data.startswith("paid:"):
        _,rest=data.split(":",1); pid,qty,mid=rest.split("|")
        db.create_payment_request(u.id,int(pid),int(qty),mid)
        await q.edit_message_text("✅ Payment request submitted.\n\nAdmin will verify your payment.", reply_markup=kb([[("⬅️ Back","home")]]))
    elif data=="orders":
        orders=db.recent_orders(u.id)
        if not orders: text="📦 MY ORDERS\n\nNo orders in the last 24 hours."
        else:
            parts=["📦 MY ORDERS — LAST 24 HOURS"]
            for o in orders:
                parts.append(f"\n🧾 #{o['id']} — {o['product_name']}\nQuantity: {o['quantity']}\nTotal: ${o['total']:.2f}\nStatus: {o['status']}")
            text="\n".join(parts)
        await q.edit_message_text(text,reply_markup=kb([[("⬅️ Back","home")]]))
    elif data=="addbal":
        methods=db.payment_methods()
        rows=[[(f"{m['emoji']} {m['name']}",f"balmethod:{m['method_id']}")] for m in methods]
        rows.append([("⬅️ Back","home")])
        await q.edit_message_text("💳 ADD BALANCE\n\nChoose a payment method:",reply_markup=kb(rows))
    elif data.startswith("balmethod:"):
        mid=data.split(":",1)[1]; m=db.payment_method(mid)
        context.user_data["balance_method"]=mid
        await q.edit_message_text(f"{m['emoji']} {m['name']}\n\nSend the amount you want to add as a message.\nFor BDT methods, USD credit = BDT / current rate.")
    elif data=="refer":
        ref=f"https://t.me/{context.bot.username}?start={u.id}"
        await q.edit_message_text(f"🎁 REFER\n\n🔗 {ref}\n\n👥 Total Refs: {db.ref_count(u.id)}\n💰 Ref Income: ${db.ref_income(u.id):.2f}\n\nCommission is configurable from Admin Panel.",
                                  reply_markup=kb([[("⬅️ Back","home")]]))
    elif data=="support":
        await q.edit_message_text(f"🎧 SUPPORT\n\nContact: {SUPPORT}",reply_markup=kb([[("⬅️ Back","home")]]))
    elif data.startswith("ad_"):
        if u.id not in ADMIN_IDS:
            await q.edit_message_text("❌ Unauthorized."); return
        if data=="ad_dash":
            s=db.dashboard()
            await q.edit_message_text(
                f"📊 DASHBOARD\n\nUsers: {s['users']}\nOrders: {s['orders']}\nSales: ${s['sales']:.2f}\n"
                f"Pending payments: {s['pending']}\nAvailable stock: {s['stock']}\nLow stock: {s['low']}\nOut of stock: {s['out']}",
                reply_markup=kb([[("⬅️ Back","adminhome")]]))
        elif data=="ad_products":
            ps=db.all_products()
            text="🛍️ PRODUCTS\n\n" + "\n".join(f"{p['id']}. {p['category']} / {p['group_name']} / {p['name']} — ${p['price']:.2f} [{'ON' if p['active'] else 'OFF'}]" for p in ps[:80])
            await q.edit_message_text(text or "No products.",reply_markup=kb([[("⬅️ Back","adminhome")]]))
        elif data=="ad_inventory":
            rows=[]
            for p in db.all_products()[:50]:
                rows.append([(f"{p['name']} ({db.available_stock(p['id'])})",f"prod:{p['id']}")])
            rows.append([("⬅️ Back","adminhome")])
            await q.edit_message_text("📦 INVENTORY",reply_markup=kb(rows))
        elif data=="ad_paymethods":
            ms=db.all_payment_methods()
            text="💳 PAYMENT METHODS\n\n"+"\n".join(f"{m['emoji']} {m['name']} — {'ON' if m['active'] else 'OFF'}" for m in ms)
            await q.edit_message_text(text+"\n\nUse admin commands in README to add/edit/toggle methods.",reply_markup=kb([[("⬅️ Back","adminhome")]]))
        elif data=="ad_refs":
            await q.edit_message_text(f"🎁 REFERRALS\n\nCommission: {db.setting('REFERRAL_RATE',0.05)*100:.2f}%\nDeposit limit: {db.setting('REFERRAL_DEPOSIT_LIMIT',10)}",
                                      reply_markup=kb([[("⬅️ Back","adminhome")]]))
        elif data=="ad_settings":
            await q.edit_message_text(f"⚙️ SETTINGS\n\nUSD/BDT: {db.setting('USD_BDT_RATE',127)}\nLow stock: {db.setting('LOW_STOCK_THRESHOLD',5)}\nReferral: {db.setting('REFERRAL_RATE',0.05)*100:.2f}%",
                                      reply_markup=kb([[("⬅️ Back","adminhome")]]))
        else:
            await q.edit_message_text("This module is ready for extension. Use README admin commands where applicable.",reply_markup=kb([[("⬅️ Back","adminhome")]]))
    elif data=="adminhome":
        await admin_from_callback(q)
    elif data=="custom":
        pass

async def admin_from_callback(q):
    await q.edit_message_text("🛠️ ADMIN PANEL",reply_markup=kb([
        [("📊 Dashboard","ad_dash"),("🛍️ Products","ad_products")],
        [("📦 Inventory","ad_inventory"),("💳 Payment Methods","ad_paymethods")],
        [("💰 Payments","ad_payments"),("💵 Balance Requests","ad_balance")],
        [("🧾 Orders","ad_orders"),("👥 Users","ad_users")],
        [("🎁 Referrals","ad_refs"),("⚙️ Settings","ad_settings")],
        [("🎛️ Button Manager","ad_buttons"),("📢 Broadcast","ad_broadcast")],
        [("📈 Reports","ad_reports"),("🎧 Support","support")],
    ]))

async def text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mid=context.user_data.get("balance_method")
    if mid:
        try: amount=float(update.message.text.strip())
        except:
            await update.message.reply_text("❌ Please enter a valid number."); return
        rate=float(db.setting("USD_BDT_RATE",127))
        m=db.payment_method(mid)
        currency=m["currency"].upper()
        usd=round(amount/rate,2) if currency=="BDT" else round(amount,2)
        rid=db.create_balance_request(update.effective_user.id,amount,usd,rate,mid,currency)
        await update.message.reply_text(f"🧾 Balance Request #{rid}\n\nPaid amount: {amount:.2f} {currency}\nUSD credit: ${usd:.2f}\n\nPlease complete payment and contact Admin if manual verification is required.")
        context.user_data.pop("balance_method",None)
    else:
        await update.message.reply_text("Please use the menu buttons.",reply_markup=main_menu())

def run():
    db.init_db()
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is missing.")
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("admin",admin))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,text_input))
    app.run_polling()

if __name__=="__main__":
    run()
