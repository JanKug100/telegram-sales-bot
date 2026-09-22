from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from io import BytesIO
import csv
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters

from config import (
    BOT_TOKEN, SUPPORT_USERNAME, STORE_NAME,
    DEFAULT_REFERRAL_COMMISSION, DEFAULT_REFERRAL_DEPOSIT_LIMIT,
    ADMIN_IDS,
)

from db import (
    init_db, get_user, create_user, update_user, get_balance, get_setting,
    get_product_by_key, get_available_stock_count, create_purchase_intent,
    complete_purchase, create_payment, get_payment, submit_payment_reference,
    confirm_payment, cancel_payment, get_recent_orders, get_order_items,
    admin_dashboard_stats, admin_list_products, admin_get_product,
    admin_create_product, admin_update_product, admin_delete_product,
    admin_list_categories, admin_log,
    admin_stock_summary, admin_stock_items, admin_add_stock, admin_remove_stock,
)

BOT_USERNAME = None


def ensure_user(update: Update):
    user = update.effective_user
    if not user:
        return None
    existing = get_user(user.id)
    if not existing:
        create_user(user.id, user.username, user.first_name, user.last_name)
    else:
        update_user(user.id, user.username, user.first_name, user.last_name)
    return get_user(user.id)


def main_menu_keyboard(user_id=None):
    rows = [
        [InlineKeyboardButton("📱 Communication Apps", callback_data="communication_apps"), InlineKeyboardButton("🔐 BUY VPN", callback_data="buy_vpn")],
        [InlineKeyboardButton("🧑‍💻 Verification Services", callback_data="verification_service"), InlineKeyboardButton("🌐 BUY Proxy", callback_data="buy_proxy")],
        [InlineKeyboardButton("🧑‍💼 My Profile", callback_data="my_profile"), InlineKeyboardButton("🛍️ Buy More Products", callback_data="buy_more_products")],
        [InlineKeyboardButton("💰 Add Balance", callback_data="add_balance"), InlineKeyboardButton("📦 My Orders", callback_data="my_orders")],
        [InlineKeyboardButton("👥 Refer", callback_data="refer"), InlineKeyboardButton("🎧 Support", callback_data="support")],
    ]
    if user_id in ADMIN_IDS:
        rows.append([InlineKeyboardButton("🔐 Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(rows)


def back_main_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]])


def product_key_from_callback(data: str) -> str:
    if data.startswith("product_"):
        return data[len("product_"):]
    if data.startswith("vpn_product_"):
        return data[len("vpn_product_"):]
    return data


def product_purchase_keyboard(product_key: str, stock_count: int):
    # Preset quantities are convenient, while Custom Quantity lets the
    # customer enter any positive whole number up to the available stock.
    rows = [
        [InlineKeyboardButton("1", callback_data=f"buyqty:{product_key}:1"),
         InlineKeyboardButton("2", callback_data=f"buyqty:{product_key}:2"),
         InlineKeyboardButton("3", callback_data=f"buyqty:{product_key}:3")],
        [InlineKeyboardButton("5", callback_data=f"buyqty:{product_key}:5"),
         InlineKeyboardButton("10", callback_data=f"buyqty:{product_key}:10")],
        [InlineKeyboardButton("✏️ Custom Quantity", callback_data=f"customqty:{product_key}")],
        [InlineKeyboardButton("🔙 Back", callback_data="communication_apps" if product_key in {"gv_old","gv_new","tn_web","tn_phone","tf_web","tf_phone","sl_web","sl_phone","talkatone","textplus"} else "buy_vpn")],
    ]
    return InlineKeyboardMarkup(rows)


def format_delivery(contents):
    if not contents:
        return "No delivery content was found. Please contact support."
    lines = ["📦 DELIVERY", "━━━━━━━━━━━━━━━━"]
    for i, content in enumerate(contents, 1):
        lines.append(f"\n#{i}\n{content}")
    return "\n".join(lines)


def is_communication_product(purchase: dict) -> bool:
    category = str(purchase.get("category_name") or "").lower()
    product_type = str(purchase.get("product_type") or "").lower()
    return category == "communication apps" or product_type == "communication"


def build_csv_bytes(contents):
    output = BytesIO()
    text_buffer = []
    # Build CSV as UTF-8 with BOM so common spreadsheet apps open it cleanly.
    import io
    string_io = io.StringIO()
    writer = csv.writer(string_io, lineterminator="\n")
    parsed_rows = []
    max_fields = 1
    for content in contents:
        raw = str(content or "").strip()
        if not raw:
            parsed = [""]
        elif "\t" in raw:
            parsed = [x.strip() for x in raw.split("\t")]
        elif "," in raw:
            parsed = [x.strip() for x in raw.split(",")]
        elif "|" in raw:
            parsed = [x.strip() for x in raw.split("|")]
        else:
            parsed = [raw]
        parsed_rows.append(parsed)
        max_fields = max(max_fields, len(parsed))
    headers = ["Email / Username", "Password"] if max_fields == 2 else [f"Field {i}" for i in range(1, max_fields + 1)]
    writer.writerow(headers)
    for row in parsed_rows:
        writer.writerow(row + [""] * (max_fields - len(row)))
    data = string_io.getvalue().encode("utf-8-sig")
    output.write(data)
    output.seek(0)
    return output


async def send_purchase_delivery(bot, purchase):
    contents = purchase.get("delivered") or []
    if not contents:
        return
    chat_id = purchase["telegram_id"]
    if is_communication_product(purchase):
        document = build_csv_bytes(contents)
        filename = f"JanKug_{purchase['product_name'].replace(' ', '_')}_Order_{purchase['order_id']}.csv"
        caption = (
            "📦 COMMUNICATION APPS DELIVERY\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"🧾 Order: #{purchase['order_id']}\n"
            f"📱 Product: {purchase['product_name']}\n"
            f"🔢 Quantity: {purchase['quantity']}\n"
            f"💰 Total: ${purchase['total']:.2f}\n\n"
            "📄 Your stock is attached as a CSV file."
        )
        await bot.send_document(chat_id=chat_id, document=InputFile(document, filename=filename), caption=caption)
    else:
        text = (
            "📦 VPN DELIVERY\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"🧾 Order: #{purchase['order_id']}\n"
            f"🔐 Product: {purchase['product_name']}\n"
            f"🔢 Quantity: {purchase['quantity']}\n"
            f"💰 Total: ${purchase['total']:.2f}\n\n"
            f"{format_delivery(contents)}"
        )
        await bot.send_message(chat_id=chat_id, text=text)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return
    referred_by = None
    if context.args and context.args[0].startswith("ref_"):
        raw = context.args[0][4:]
        if raw.isdigit():
            ref_user = get_user(int(raw))
            if ref_user and ref_user["telegram_id"] != user.id:
                referred_by = ref_user["id"]

    existing = get_user(user.id)
    if not existing:
        create_user(user.id, user.username, user.first_name, user.last_name, referred_by)
    else:
        update_user(user.id, user.username, user.first_name, user.last_name)

    await update.message.reply_text(
        f"🏠 {STORE_NAME}\n━━━━━━━━━━━━━━━━\n\nWelcome to the store!\n\nChoose an option below.",
        reply_markup=main_menu_keyboard()
    )


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    await q.edit_message_text(f"🏠 {STORE_NAME}\n━━━━━━━━━━━━━━━━\n\nChoose an option below.", reply_markup=main_menu_keyboard())


async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); user=update.effective_user; ensure_user(update)
    balance=get_balance(user.id); username=f"@{user.username}" if user.username else "@N/A"
    referral_link=f"https://t.me/{context.bot.username}?start=ref_{user.id}" if context.bot.username else "Referral link unavailable"
    db_user=get_user(user.id); total_refs=int(db_user["total_referrals"]) if db_user else 0; ref_income=float(db_user["referral_income"]) if db_user else 0
    commission=get_setting("referral_commission", str(DEFAULT_REFERRAL_COMMISSION)); limit=get_setting("referral_deposit_limit", str(DEFAULT_REFERRAL_DEPOSIT_LIMIT))
    text=(f"👤 ACCOUNT DASHBOARD\n━━━━━━━━━━━━━━━━\n🏷 Name: {user.full_name}\n🔰 Username: {username}\n🆔 User ID: {user.id}\n━━━━━━━━━━━━━━━━\n💳 Balance: ${balance:.2f}\n🎯 Referral Link:\n{referral_link}\n\n💰 Refer {commission}% commission\n📌 First {limit} deposits\n\n📊 Total Refs: {total_refs}\n🎁 Ref Income: ${ref_income:.2f}")
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Refer", callback_data="refer")],[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]))


async def communication_apps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    kb=[[InlineKeyboardButton("Google Voice",callback_data="google_voice"),InlineKeyboardButton("TextNow",callback_data="textnow")],[InlineKeyboardButton("TextFree",callback_data="textfree"),InlineKeyboardButton("Sideline",callback_data="sideline")],[InlineKeyboardButton("Talkatone",callback_data="talkatone"),InlineKeyboardButton("TextPlus",callback_data="textplus")],[InlineKeyboardButton("🏠 Main Menu",callback_data="main_menu")]]
    await q.edit_message_text("💬 COMMUNICATION APPS\n━━━━━━━━━━━━━━━━\n\nSelect a product:",reply_markup=InlineKeyboardMarkup(kb))


def simple_two_product_screen(title, products, back="communication_apps"):
    # products is a flat list of (button_text, callback_data) pairs.
    # Keep the two products on one row.
    kb=[]
    for i in range(0, len(products), 2):
        row=[]
        for label, callback in products[i:i+2]:
            row.append(InlineKeyboardButton(label, callback_data=callback))
        kb.append(row)
    kb.append([InlineKeyboardButton("🔙 Back", callback_data=back)])
    return InlineKeyboardMarkup(kb)


async def google_voice(update, context):
    q=update.callback_query; await q.answer(); await q.edit_message_text("📱 GOOGLE VOICE\n━━━━━━━━━━━━━━━━\n\nChoose product:",reply_markup=simple_two_product_screen("",[("Old GV","product_gv_old"),("New GV","product_gv_new")]))

async def textnow(update, context):
    q=update.callback_query; await q.answer(); await q.edit_message_text("📱 TEXTNOW\n━━━━━━━━━━━━━━━━\n\nChoose product:",reply_markup=simple_two_product_screen("",[("Web TN","product_tn_web"),("Phone TN","product_tn_phone")]))

async def textfree(update, context):
    q=update.callback_query; await q.answer(); await q.edit_message_text("📱 TEXTFREE\n━━━━━━━━━━━━━━━━\n\nChoose product:",reply_markup=simple_two_product_screen("",[("Web TF","product_tf_web"),("Phone TF","product_tf_phone")]))

async def sideline(update, context):
    q=update.callback_query; await q.answer(); await q.edit_message_text("📱 SIDELINE\n━━━━━━━━━━━━━━━━\n\nChoose product:",reply_markup=simple_two_product_screen("",[("Web SL","product_sl_web"),("Phone SL","product_sl_phone")]))


async def show_product_for_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE, product_key: str):
    q=update.callback_query
    product=get_product_by_key(product_key)
    if not product:
        await q.answer("Product is not configured.", show_alert=True); return
    if not int(product["is_active"]):
        await q.answer("This product is currently unavailable.", show_alert=True); return
    stock=get_available_stock_count(product["id"])
    if stock < 1:
        await q.answer("Out of stock.", show_alert=True)
        await q.edit_message_text(f"🛍️ {product['name']}\n━━━━━━━━━━━━━━━━\n\n❌ Out of stock.\n\nPlease contact {SUPPORT_USERNAME} to ask about stock.", reply_markup=product_purchase_keyboard(product_key,0))
        return
    await q.answer()
    await q.edit_message_text(f"🛍️ {product['name']}\n━━━━━━━━━━━━━━━━\n\n💰 Price: ${float(product['price']):.2f}\n📦 Available: {stock}\n\nSelect quantity:", reply_markup=product_purchase_keyboard(product_key,stock))


async def talkatone(update, context): await show_product_for_purchase(update,context,"talkatone")
async def textplus(update, context): await show_product_for_purchase(update,context,"textplus")
async def communication_product(update, context): await show_product_for_purchase(update,context,product_key_from_callback(update.callback_query.data))
async def vpn_product(update, context): await show_product_for_purchase(update,context,product_key_from_callback(update.callback_query.data))


async def custom_quantity_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    product_key = q.data.split(":", 1)[1]
    product = get_product_by_key(product_key)
    if not product or not int(product["is_active"]):
        await q.answer("This product is unavailable.", show_alert=True)
        return

    stock = get_available_stock_count(product["id"])
    if stock < 1:
        await q.answer("Out of stock.", show_alert=True)
        return

    # Store only the current customer's pending custom-quantity request.
    context.user_data["awaiting_custom_quantity"] = product_key
    await q.answer()
    await q.edit_message_text(
        f"✏️ CUSTOM QUANTITY\n━━━━━━━━━━━━━━━━\n\n"
        f"Product: {product['name']}\n"
        f"Price: ${float(product['price']):.2f} each\n"
        f"Available stock: {stock}\n\n"
        f"Please type the quantity you want to buy.\n"
        f"Example: 25\n\n"
        f"Enter a whole number from 1 to {stock}.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"cancelcustomqty:{product_key}")]])
    )


async def cancel_custom_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    product_key = q.data.split(":", 1)[1]
    context.user_data.pop("awaiting_custom_quantity", None)
    await q.answer("Cancelled.")
    await show_product_for_purchase(update, context, product_key)


async def process_custom_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    product_key = context.user_data.get("awaiting_custom_quantity")
    if not product_key or not update.message or not update.message.text:
        return False

    raw = update.message.text.strip()
    if not raw.isdigit():
        await update.message.reply_text(
            "❌ Invalid quantity.\n\nPlease enter a whole number only, for example: 25.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"cancelcustomqty:{product_key}")]])
        )
        return True

    quantity = int(raw)
    if quantity < 1:
        await update.message.reply_text("❌ Quantity must be at least 1.")
        return True

    product = get_product_by_key(product_key)
    if not product or not int(product["is_active"]):
        context.user_data.pop("awaiting_custom_quantity", None)
        await update.message.reply_text("❌ This product is no longer available.", reply_markup=main_menu_keyboard())
        return True

    stock = get_available_stock_count(product["id"])
    if quantity > stock:
        await update.message.reply_text(
            f"❌ Not enough stock.\n\nAvailable: {stock}\nYou requested: {quantity}\n\nPlease enter a quantity from 1 to {stock}.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"cancelcustomqty:{product_key}")]])
        )
        return True

    context.user_data.pop("awaiting_custom_quantity", None)
    total = round(float(product["price"]) * quantity, 2)
    balance = get_balance(update.effective_user.id)

    if balance + 1e-9 >= total:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"✅ Buy {quantity} for ${total:.2f}", callback_data=f"confirmbuy:{product_key}:{quantity}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"product_{product_key}")]
        ])
        await update.message.reply_text(
            f"🛒 ORDER SUMMARY\n━━━━━━━━━━━━━━━━\n\n"
            f"Product: {product['name']}\n"
            f"Quantity: {quantity}\n"
            f"Unit price: ${float(product['price']):.2f}\n"
            f"Total: ${total:.2f}\n\n"
            f"💳 Your balance: ${balance:.2f}\n\n"
            f"Your balance is sufficient.",
            reply_markup=kb
        )
    else:
        required = round(total - balance, 2)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💰 Pay ${required:.2f} & Continue", callback_data=f"paypurchase:{product_key}:{quantity}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"product_{product_key}")]
        ])
        await update.message.reply_text(
            f"🛒 ORDER SUMMARY\n━━━━━━━━━━━━━━━━\n\n"
            f"Product: {product['name']}\n"
            f"Quantity: {quantity}\n"
            f"Total: ${total:.2f}\n\n"
            f"💳 Current balance: ${balance:.2f}\n"
            f"❗ Additional payment required: ${required:.2f}\n\n"
            f"After payment is confirmed, the purchase will continue automatically.",
            reply_markup=kb
        )
    return True


async def quantity_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    try:
        _, product_key, qty_raw=q.data.split(":",2); quantity=int(qty_raw)
    except Exception:
        await q.answer("Invalid quantity.",show_alert=True); return
    product=get_product_by_key(product_key)
    if not product: await q.answer("Product not found.",show_alert=True); return
    stock=get_available_stock_count(product["id"])
    if stock < quantity:
        await q.answer(f"Only {stock} in stock.",show_alert=True); return
    total=round(float(product["price"])*quantity,2); balance=get_balance(update.effective_user.id)
    if balance+1e-9 >= total:
        kb=InlineKeyboardMarkup([[InlineKeyboardButton(f"✅ Buy {quantity} for ${total:.2f}",callback_data=f"confirmbuy:{product_key}:{quantity}")],[InlineKeyboardButton("🔙 Back",callback_data=f"product_{product_key}")]])
        await q.answer(); await q.edit_message_text(f"🛒 ORDER SUMMARY\n━━━━━━━━━━━━━━━━\n\nProduct: {product['name']}\nQuantity: {quantity}\nUnit price: ${float(product['price']):.2f}\nTotal: ${total:.2f}\n\n💳 Your balance: ${balance:.2f}\n\nYour balance is sufficient.",reply_markup=kb)
    else:
        required=round(total-balance,2)
        kb=InlineKeyboardMarkup([[InlineKeyboardButton(f"💰 Pay ${required:.2f} & Continue",callback_data=f"paypurchase:{product_key}:{quantity}")],[InlineKeyboardButton("🔙 Back",callback_data=f"product_{product_key}")]])
        await q.answer(); await q.edit_message_text(f"🛒 ORDER SUMMARY\n━━━━━━━━━━━━━━━━\n\nProduct: {product['name']}\nQuantity: {quantity}\nTotal: ${total:.2f}\n\n💳 Current balance: ${balance:.2f}\n❗ Additional payment required: ${required:.2f}\n\nAfter payment is confirmed, the purchase will continue automatically.",reply_markup=kb)


async def confirm_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    try: _,product_key,qty_raw=q.data.split(":",2); quantity=int(qty_raw)
    except Exception: await q.answer("Invalid order.",show_alert=True); return
    product=get_product_by_key(product_key)
    if not product: await q.answer("Product not found.",show_alert=True); return
    total=round(float(product["price"])*quantity,2); balance=get_balance(update.effective_user.id)
    if balance+1e-9<total: await q.answer("Your balance is no longer sufficient.",show_alert=True); return
    try:
        intent=create_purchase_intent(update.effective_user.id,product["id"],quantity,0)
        result=complete_purchase(intent)
        await q.answer("Purchase completed!")
        await q.edit_message_text(f"✅ PURCHASE COMPLETE\n━━━━━━━━━━━━━━━━\n\nOrder #{result['order_id']}\nProduct: {result['product_name']}\nQuantity: {result['quantity']}\nTotal: ${result['total']:.2f}\n\n💳 Remaining balance: ${result['balance_after']:.2f}\n\n📦 Delivery is being sent...",reply_markup=back_main_keyboard())
        await send_purchase_delivery(context.bot, result)
    except Exception as e:
        await q.answer(str(e),show_alert=True)


async def pay_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    try: _,product_key,qty_raw=q.data.split(":",2); quantity=int(qty_raw)
    except Exception: await q.answer("Invalid order.",show_alert=True); return
    product=get_product_by_key(product_key)
    if not product: await q.answer("Product not found.",show_alert=True); return
    total=round(float(product["price"])*quantity,2); balance=get_balance(update.effective_user.id); required=max(0,round(total-balance,2))
    if required<=0: await q.answer("No payment is needed now.",show_alert=True); return
    stock=get_available_stock_count(product["id"])
    if stock<quantity: await q.answer("Stock is no longer sufficient.",show_alert=True); return
    intent=create_purchase_intent(update.effective_user.id,product["id"],quantity,required)
    payment_id=create_payment(update.effective_user.id,required,"binance_pay",intent,"USD")
    pay_id=get_setting("binance_pay_id","Not configured yet")
    context.user_data["awaiting_payment_tx"] = payment_id
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Enter Binance Order ID",callback_data=f"enterpay:{payment_id}")],[InlineKeyboardButton("❌ Cancel",callback_data=f"cancel_user_payment:{payment_id}")]])
    await q.answer(); await q.edit_message_text(f"💳 PAYMENT REQUIRED\n━━━━━━━━━━━━━━━━\n\nProduct: {product['name']}\nQuantity: {quantity}\nPurchase total: ${total:.2f}\nCurrent balance: ${balance:.2f}\nPayment required: ${required:.2f}\n\n🔶 Method: Binance Pay\n🆔 Payment Request: #{payment_id}\n💳 Binance Pay ID: {pay_id}\n\nSend the payment through Binance Pay, then submit your Binance Order ID.\n\nAfter admin confirmation, your balance will be credited and this purchase will be completed automatically.",reply_markup=kb)
    for admin_id in ADMIN_IDS:
        try: await context.bot.send_message(admin_id,f"🔔 NEW PURCHASE PAYMENT\nPayment #{payment_id}\nUser: {update.effective_user.id}\nProduct: {product['name']} x{quantity}\nRequired: ${required:.2f}\n\nUser must submit Binance Order ID before approval.")
        except Exception: pass


async def enter_payment(update, context):
    q=update.callback_query
    payment_id=int(q.data.split(":",1)[1]); payment=get_payment(payment_id)
    if not payment or payment["telegram_id"]!=update.effective_user.id or payment["status"]!="pending": await q.answer("Payment is not available.",show_alert=True); return
    context.user_data["awaiting_payment_tx"]=payment_id
    await q.answer(); await q.edit_message_text(f"✍️ PAYMENT #{payment_id}\n\nPlease send your Binance Order ID as a text message.\n\nExample: 1234567890",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data=f"cancel_user_payment:{payment_id}")]]))


async def cancel_user_payment(update, context):
    q=update.callback_query; payment_id=int(q.data.split(":",1)[1]); payment=get_payment(payment_id)
    if not payment or payment["telegram_id"]!=update.effective_user.id: await q.answer("Invalid payment.",show_alert=True); return
    # User cancellation is handled directly as pending -> cancelled.
    from db import cancel_payment as db_cancel_payment
    try:
        db_cancel_payment(payment_id, update.effective_user.id, "Cancelled by customer")
        context.user_data.pop("awaiting_payment_tx",None)
        await q.answer("Payment cancelled."); await q.edit_message_text("❌ Payment cancelled.",reply_markup=back_main_keyboard())
    except Exception as e: await q.answer(str(e),show_alert=True)


async def text_message_handler(update, context):
    if not update.message: return
    payment_id=context.user_data.get("awaiting_payment_tx")
    if payment_id:
        raw=update.message.text.strip()
        if len(raw)<3 or len(raw)>100:
            await update.message.reply_text("❌ Invalid Binance Order ID. Please send the Order ID as text."); return
        payment=get_payment(payment_id)
        if not payment or payment["telegram_id"]!=update.effective_user.id or payment["status"]!="pending":
            context.user_data.pop("awaiting_payment_tx",None)
            await update.message.reply_text("This payment is no longer pending.",reply_markup=main_menu_keyboard()); return
        try:
            submit_payment_reference(payment_id,raw); context.user_data.pop("awaiting_payment_tx",None)
            await update.message.reply_text(f"✅ Payment reference submitted.\n\nPayment #{payment_id} is waiting for admin confirmation.\nYou do not need to restart your purchase.",reply_markup=main_menu_keyboard())
            for admin_id in ADMIN_IDS:
                try: await context.bot.send_message(admin_id,f"💳 PAYMENT REFERENCE SUBMITTED\nPayment #{payment_id}\nUser: {update.effective_user.id}\nBinance Order ID: {raw}\n\nApprove with /approve_payment {payment_id}")
                except Exception: pass
        except Exception as e: await update.message.reply_text(f"❌ {e}")
        return
    await update.message.reply_text(f"🏠 {STORE_NAME}\n━━━━━━━━━━━━━━━━\n\nChoose an option below.",reply_markup=main_menu_keyboard())


async def buy_vpn(update, context):
    q=update.callback_query; await q.answer(); kb=[[InlineKeyboardButton("03 Days",callback_data="vpn_03_days"),InlineKeyboardButton("07 Days",callback_data="vpn_07_days")],[InlineKeyboardButton("14 Days",callback_data="vpn_14_days"),InlineKeyboardButton("30 Days",callback_data="vpn_30_days")],[InlineKeyboardButton("🏠 Main Menu",callback_data="main_menu")]]; await q.edit_message_text("🔐 BUY VPN\n━━━━━━━━━━━━━━━━\n\n📅 Select validity:",reply_markup=InlineKeyboardMarkup(kb))

async def vpn_03_days(update,context):
    q=update.callback_query; await q.answer(); kb=[[InlineKeyboardButton("Express VPN",callback_data="vpn_product_express_3"),InlineKeyboardButton("CyberGhost VPN",callback_data="vpn_product_cyberghost_3")],[InlineKeyboardButton("Vypr VPN",callback_data="vpn_product_vypr_3"),InlineKeyboardButton("Panda VPN",callback_data="vpn_product_panda_3")],[InlineKeyboardButton("🔙 Back",callback_data="buy_vpn")]]; await q.edit_message_text("🔐 VPN — 03 DAYS\n━━━━━━━━━━━━━━━━\n\nSelect a VPN:",reply_markup=InlineKeyboardMarkup(kb))

async def vpn_07_days(update,context):
    q=update.callback_query; await q.answer(); kb=[[InlineKeyboardButton("Express VPN",callback_data="vpn_product_express_7"),InlineKeyboardButton("Nord VPN",callback_data="vpn_product_nord_7")],[InlineKeyboardButton("PIA VPN",callback_data="vpn_product_pia_7"),InlineKeyboardButton("IPVanish VPN",callback_data="vpn_product_ipvanish_7")],[InlineKeyboardButton("Surfshark VPN",callback_data="vpn_product_surfshark_7"),InlineKeyboardButton("HotspotShield VPN",callback_data="vpn_product_hotspotshield_7")],[InlineKeyboardButton("HMA VPN",callback_data="vpn_product_hma_7"),InlineKeyboardButton("Pure VPN",callback_data="vpn_product_pure_7")],[InlineKeyboardButton("🔙 Back",callback_data="buy_vpn"),InlineKeyboardButton("Next ➡️",callback_data="vpn_07_page_2")]]; await q.edit_message_text("🔐 VPN — 07 DAYS\n━━━━━━━━━━━━━━━━\n\nPage 1",reply_markup=InlineKeyboardMarkup(kb))

async def vpn_07_page_2(update,context):
    q=update.callback_query; await q.answer(); kb=[[InlineKeyboardButton("Turbo VPN",callback_data="vpn_product_turbo_7"),InlineKeyboardButton("Avast VPN",callback_data="vpn_product_avast_7")],[InlineKeyboardButton("AdGuard VPN",callback_data="vpn_product_adguard_7"),InlineKeyboardButton("Norton VPN",callback_data="vpn_product_norton_7")],[InlineKeyboardButton("AVG VPN",callback_data="vpn_product_avg_7"),InlineKeyboardButton("X-VPN",callback_data="vpn_product_x_7")],[InlineKeyboardButton("Sky VPN",callback_data="vpn_product_sky_7"),InlineKeyboardButton("Potato VPN",callback_data="vpn_product_potato_7")],[InlineKeyboardButton("🔙 Back",callback_data="vpn_07_days"),InlineKeyboardButton("Next ➡️",callback_data="vpn_07_page_3")]]; await q.edit_message_text("🔐 VPN — 07 DAYS\n━━━━━━━━━━━━━━━━\n\nPage 2",reply_markup=InlineKeyboardMarkup(kb))

async def vpn_07_page_3(update,context):
    q=update.callback_query; await q.answer(); kb=[[InlineKeyboardButton("Bitdefender VPN",callback_data="vpn_product_bitdefender_7")],[InlineKeyboardButton("🔙 Back",callback_data="vpn_07_page_2")]]; await q.edit_message_text("🔐 VPN — 07 DAYS\n━━━━━━━━━━━━━━━━\n\nPage 3",reply_markup=InlineKeyboardMarkup(kb))

async def vpn_14_days(update,context):
    q=update.callback_query; await q.answer(); kb=[[InlineKeyboardButton("Octohide",callback_data="vpn_product_octohide_14")],[InlineKeyboardButton("🔙 Back",callback_data="buy_vpn")]]; await q.edit_message_text("🔐 VPN — 14 DAYS\n━━━━━━━━━━━━━━━━\n\nSelect a VPN:",reply_markup=InlineKeyboardMarkup(kb))

async def vpn_30_days(update,context):
    q=update.callback_query; await q.answer(); kb=[[InlineKeyboardButton("Express VPN (1 Device)",callback_data="vpn_product_express_30"),InlineKeyboardButton("Nord VPN",callback_data="vpn_product_nord_30")],[InlineKeyboardButton("PIA VPN (1 Device)",callback_data="vpn_product_pia_30"),InlineKeyboardButton("Avast VPN",callback_data="vpn_product_avast_30")],[InlineKeyboardButton("Bitdefender VPN",callback_data="vpn_product_bitdefender_30"),InlineKeyboardButton("HMA VPN",callback_data="vpn_product_hma_30")],[InlineKeyboardButton("Mysterium VPN",callback_data="vpn_product_mysterium_30"),InlineKeyboardButton("MYSTERIUM DARK",callback_data="vpn_product_mysterium_dark_30")],[InlineKeyboardButton("Windscribe VPN",callback_data="vpn_product_windscribe_30"),InlineKeyboardButton("Proton VPN",callback_data="vpn_product_proton_30")],[InlineKeyboardButton("🔙 Back",callback_data="buy_vpn")]]; await q.edit_message_text("🔐 VPN — 30 DAYS\n━━━━━━━━━━━━━━━━\n\nSelect a VPN:",reply_markup=InlineKeyboardMarkup(kb))


async def coming_soon(update,context):
    q=update.callback_query; await q.answer(); await q.edit_message_text("🚧 COMING SOON\n\nThis category will be available soon.",reply_markup=back_main_keyboard())

async def buy_proxy(update,context):
    q=update.callback_query; await q.answer(); await q.edit_message_text("🌐 BUY PROXY\n━━━━━━━━━━━━━━━━\n\n🚧 Coming soon.",reply_markup=back_main_keyboard())
async def verification_service(update,context):
    q=update.callback_query; await q.answer(); await q.edit_message_text("🧑‍💻 VERIFICATION SERVICES\n━━━━━━━━━━━━━━━━\n\n🚧 Coming soon.",reply_markup=back_main_keyboard())

async def buy_more_products(update,context):
    q=update.callback_query; await q.answer(); kb=[[InlineKeyboardButton("📧 Email Accounts",callback_data="coming_soon_email"),InlineKeyboardButton("⭐ Premium Apps",callback_data="coming_soon_premium")],[InlineKeyboardButton("💻 Software & Tools",callback_data="coming_soon_software"),InlineKeyboardButton("🎮 Gaming Products",callback_data="coming_soon_gaming")],[InlineKeyboardButton("🏠 Main Menu",callback_data="main_menu")]]; await q.edit_message_text("🛍️ BUY MORE PRODUCTS\n━━━━━━━━━━━━━━━━\n\nSelect a category:",reply_markup=InlineKeyboardMarkup(kb))


async def add_balance(update,context):
    q=update.callback_query; await q.answer(); context.user_data["awaiting_balance_amount"]=True
    await q.edit_message_text("💰 ADD BALANCE\n━━━━━━━━━━━━━━━━\n\nEnter the USD amount you want to add.\nMinimum: $0.10\n\nExample: 10",reply_markup=back_main_keyboard())

async def create_balance_payment_from_text(update,context,amount):
    if amount<0.10: await update.message.reply_text("❌ Minimum amount is $0.10."); return
    payment_id=create_payment(update.effective_user.id,round(amount,2),"binance_pay",None,"USD")
    context.user_data["awaiting_balance_tx"]=payment_id; context.user_data.pop("awaiting_balance_amount",None)
    pay_id=get_setting("binance_pay_id","Not configured yet")
    await update.message.reply_text(f"💳 BINANCE PAY\n━━━━━━━━━━━━━━━━\n\nPayment #{payment_id}\nAmount: ${amount:.2f}\nBinance Pay ID: {pay_id}\n\nSend the payment, then send your Binance Order ID here.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data=f"cancel_user_payment:{payment_id}")]]))
    for admin_id in ADMIN_IDS:
        try: await context.bot.send_message(admin_id,f"🔔 NEW BALANCE PAYMENT\nPayment #{payment_id}\nUser: {update.effective_user.id}\nAmount: ${amount:.2f}\nWaiting for Binance Order ID.")
        except Exception: pass


async def add_balance_text_handler(update,context):
    if not update.message: return False
    if context.user_data.get("awaiting_balance_amount"):
        raw=update.message.text.strip()
        try: amount=float(raw)
        except ValueError: await update.message.reply_text("❌ Please enter a valid USD amount, for example 10."); return True
        await create_balance_payment_from_text(update,context,amount); return True
    return False


async def my_orders(update,context):
    q=update.callback_query; await q.answer(); rows=get_recent_orders(update.effective_user.id,24,20)
    if not rows:
        await q.edit_message_text("📦 MY ORDERS\n━━━━━━━━━━━━━━━━\n\nNo completed orders in the last 24 hours.",reply_markup=back_main_keyboard()); return
    parts=["📦 MY ORDERS — LAST 24 HOURS","━━━━━━━━━━━━━━━━"]
    for order in rows:
        parts.append(f"\n🧾 Order #{order['id']}\nProduct: {order['name']}\nQty: {order['quantity']}\nTotal: ${float(order['total_amount']):.2f}\nStatus: {order['status']}")
        items=get_order_items(order["id"])
        for i,item in enumerate(items,1):
            content=item["delivered_content"] or ""
            # Mask likely password-looking fields in the display without modifying stored delivery.
            masked=content
            if "password:" in masked.lower():
                import re
                masked=re.sub(r"(?i)(password\s*:\s*)([^\s\n]+)",r"\1••••••",masked)
            parts.append(f"  #{i}: {masked}")
    await q.edit_message_text("\n".join(parts),reply_markup=back_main_keyboard())

async def refer(update,context):
    q=update.callback_query; await q.answer(); user=update.effective_user; ensure_user(update); bot_username=context.bot.username; link=f"https://t.me/{bot_username}?start=ref_{user.id}" if bot_username else "Referral link unavailable"; u=get_user(user.id); commission=get_setting("referral_commission",str(DEFAULT_REFERRAL_COMMISSION)); limit=get_setting("referral_deposit_limit",str(DEFAULT_REFERRAL_DEPOSIT_LIMIT)); await q.edit_message_text(f"👥 REFERRAL PROGRAM\n━━━━━━━━━━━━━━━━\n\n🎯 Your Referral Link:\n{link}\n\n💰 Commission: {commission}%\n📌 Commission applies to the first {limit} deposits.\n\n📊 Total Referrals: {u['total_referrals']}\n🎁 Referral Income: ${float(u['referral_income']):.2f}",reply_markup=back_main_keyboard())

async def support(update,context):
    q=update.callback_query; await q.answer(); await q.edit_message_text(f"🎧 SUPPORT\n━━━━━━━━━━━━━━━━\n\nFor support, please contact:\n{SUPPORT_USERNAME}",reply_markup=back_main_keyboard())


async def admin_only(update):
    return update.effective_user and update.effective_user.id in ADMIN_IDS

async def pending_payments(update,context):
    if not await admin_only(update): return
    # This command intentionally gives a concise queue; approval is still explicit.
    from db import get_connection
    con=get_connection(); cur=con.cursor(); cur.execute("""SELECT p.id,p.amount,p.transaction_id,p.created_at,u.telegram_id,pi.product_id,pi.quantity,pr.name
        FROM payments p JOIN users u ON u.id=p.user_id LEFT JOIN purchase_intents pi ON pi.id=p.purchase_intent_id LEFT JOIN products pr ON pr.id=pi.product_id
        WHERE p.status='pending' ORDER BY p.id ASC LIMIT 50"""); rows=cur.fetchall(); con.close()
    if not rows: await update.message.reply_text("No pending payments."); return
    lines=["💳 PENDING PAYMENTS"]
    for r in rows: lines.append(f"\n#{r['id']} — ${float(r['amount']):.2f}\nUser: {r['telegram_id']}\nProduct: {r['name'] or 'Balance top-up'} x{r['quantity'] or '-'}\nTX: {r['transaction_id'] or 'not submitted'}\nApprove: /approve_payment {r['id']}")
    await update.message.reply_text("\n".join(lines))

async def approve_payment_cmd(update,context):
    if not await admin_only(update): return
    if not context.args or not context.args[0].isdigit(): await update.message.reply_text("Usage: /approve_payment PAYMENT_ID"); return
    payment_id=int(context.args[0]); payment=get_payment(payment_id)
    if not payment: await update.message.reply_text("Payment not found."); return
    if not payment["transaction_id"]: await update.message.reply_text("This payment has no Binance Order ID yet."); return
    try:
        result=confirm_payment(payment_id,update.effective_user.id)
        purchase=result.get("purchase")
        await update.message.reply_text(f"✅ Payment #{payment_id} confirmed." + (f"\nOrder #{purchase['order_id']} completed and delivered." if purchase else "\nBalance credited."))
        if purchase and not purchase.get("already_completed"):
            await context.bot.send_message(purchase["telegram_id"],f"✅ PAYMENT CONFIRMED & ORDER COMPLETED\n━━━━━━━━━━━━━━━━\nPayment #{payment_id}\nOrder #{purchase['order_id']}\nProduct: {purchase['product_name']}\nQuantity: {purchase['quantity']}\nTotal: ${purchase['total']:.2f}\nRemaining balance: ${purchase['balance_after']:.2f}\n\n📦 Delivery is being sent...",reply_markup=back_main_keyboard())
            await send_purchase_delivery(context.bot, purchase)
        else:
            p=get_payment(payment_id); await context.bot.send_message(p["telegram_id"],f"✅ Payment #{payment_id} confirmed. Your balance has been credited.",reply_markup=main_menu_keyboard())
    except Exception as e: await update.message.reply_text(f"❌ Could not approve: {e}")

async def cancel_payment_cmd(update,context):
    if not await admin_only(update): return
    if not context.args or not context.args[0].isdigit(): await update.message.reply_text("Usage: /cancel_payment PAYMENT_ID"); return
    try:
        cancel_payment(int(context.args[0]),update.effective_user.id,"Cancelled by admin")
        await update.message.reply_text("✅ Payment cancelled.")
    except Exception as e: await update.message.reply_text(f"❌ {e}")


# =========================
# STAGE 5A — ADMIN PANEL
# Dashboard + Product Management
# =========================

def admin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard")],
        [InlineKeyboardButton("🛍️ Products", callback_data="admin_products")],
        [InlineKeyboardButton("📦 Stock Management", callback_data="admin_stock_menu")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")],
    ])


async def admin_command(update, context):
    if not await admin_only(update):
        return
    await update.message.reply_text(
        "🔐 ADMIN PANEL\n━━━━━━━━━━━━━━━━\n\nChoose an option:",
        reply_markup=admin_kb()
    )


async def admin_dashboard(update, context):
    q = update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True)
        return
    await q.answer()
    s = admin_dashboard_stats()
    text = (
        "📊 ADMIN DASHBOARD\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"👥 Total Users: {s['total_users']}\n"
        f"📦 Total Products: {s['total_products']}\n"
        f"📊 Available Stock: {s['available_stock']}\n\n"
        f"💰 Total Sales: ${s['total_sales']:.2f}\n"
        f"💵 Last 24 Hours: ${s['sales_24h']:.2f}\n"
        f"💵 Last 7 Days: ${s['sales_7d']:.2f}\n"
        f"💵 Last 1 Month: ${s['sales_30d']:.2f}\n"
    )
    await q.edit_message_text(text, reply_markup=admin_kb())


def admin_products_kb(products, page=0, per_page=8):
    start = page * per_page
    current = products[start:start + per_page]
    rows = []
    for p in current:
        status = "🟢" if int(p["is_active"]) else "🔴"
        rows.append([InlineKeyboardButton(
            f"{status} {p['name']} — ${float(p['price']):.2f}",
            callback_data=f"admin_product:{p['id']}"
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"admin_products_page:{page-1}"))
    if start + per_page < len(products):
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin_products_page:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("➕ Add Product", callback_data="admin_add_product")])
    rows.append([InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(rows)


async def admin_products(update, context, page=0):
    q = update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True)
        return
    await q.answer()
    products = admin_list_products()
    if not products:
        text = "🛍️ PRODUCTS\n━━━━━━━━━━━━━━━━\n\nNo products found."
    else:
        text = f"🛍️ PRODUCTS\n━━━━━━━━━━━━━━━━\n\nTotal products: {len(products)}\nSelect a product:"
    await q.edit_message_text(text, reply_markup=admin_products_kb(products, page))


async def admin_products_callback(update, context):
    await admin_products(update, context, 0)


async def admin_products_page(update, context):
    q = update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True)
        return
    try:
        page = int(q.data.split(":", 1)[1])
    except Exception:
        page = 0
    await admin_products(update, context, page)


async def admin_product_detail(update, context):
    q = update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True)
        return
    product_id = int(q.data.split(":", 1)[1])
    p = admin_get_product(product_id)
    if not p:
        await q.answer("Product not found.", show_alert=True)
        return
    await q.answer()
    stock = int(p["available_stock"])
    sold = int(p["sold_stock"])
    status = "🟢 Active" if int(p["is_active"]) else "🔴 Inactive"
    category = p["category_name"] or "Uncategorized"
    text = (
        "🛍️ PRODUCT DETAILS\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"ID: {p['id']}\n"
        f"Name: {p['name']}\n"
        f"Key: {p['product_key']}\n"
        f"Category: {category}\n"
        f"Price: ${float(p['price']):.2f}\n"
        f"Status: {status}\n"
        f"📦 Available Stock: {stock}\n"
        f"📤 Sold Stock: {sold}\n"
    )
    toggle = "🔴 Deactivate" if int(p["is_active"]) else "🟢 Activate"
    kb = [
        [InlineKeyboardButton("💵 Change Price", callback_data=f"admin_price:{product_id}")],
        [InlineKeyboardButton(toggle, callback_data=f"admin_toggle:{product_id}")],
        [InlineKeyboardButton("✏️ Edit Name", callback_data=f"admin_name:{product_id}")],
        [InlineKeyboardButton("🗑️ Remove Product", callback_data=f"admin_delete:{product_id}")],
        [InlineKeyboardButton("🔙 Products", callback_data="admin_products")],
    ]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def admin_prompt(update, context, kind, product_id, prompt):
    q = update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True)
        return
    if not admin_get_product(product_id):
        await q.answer("Product not found.", show_alert=True)
        return
    context.user_data["admin_input"] = {"kind": kind, "product_id": product_id}
    await q.answer()
    await q.edit_message_text(
        prompt,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data=f"admin_product:{product_id}")]
        ])
    )


async def admin_change_price(update, context):
    product_id = int(update.callback_query.data.split(":", 1)[1])
    await admin_prompt(
        update, context, "price", product_id,
        "💵 CHANGE PRICE\n━━━━━━━━━━━━━━━━\n\n"
        "Send the new USD price.\n\nExample: 3.50"
    )


async def admin_change_name(update, context):
    product_id = int(update.callback_query.data.split(":", 1)[1])
    await admin_prompt(
        update, context, "name", product_id,
        "✏️ CHANGE PRODUCT NAME\n━━━━━━━━━━━━━━━━\n\n"
        "Send the new product name."
    )


async def admin_toggle_product(update, context):
    q = update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True)
        return
    product_id = int(q.data.split(":", 1)[1])
    p = admin_get_product(product_id)
    if not p:
        await q.answer("Product not found.", show_alert=True)
        return
    new_status = 0 if int(p["is_active"]) else 1
    admin_update_product(product_id, is_active=new_status)
    admin_log(update.effective_user.id, "toggle_product", "product", product_id, f"is_active={new_status}")
    await q.answer("Product status updated.")
    await admin_product_detail(update, context)


async def admin_delete_product_prompt(update, context):
    q = update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True)
        return
    product_id = int(q.data.split(":", 1)[1])
    p = admin_get_product(product_id)
    if not p:
        await q.answer("Product not found.", show_alert=True)
        return
    await q.answer()
    await q.edit_message_text(
        f"⚠️ REMOVE PRODUCT\n━━━━━━━━━━━━━━━━\n\n"
        f"Product: {p['name']}\n\n"
        "This action will remove the product if it has no stock or order history.\n"
        "If it has existing data, it will be safely deactivated instead.\n\n"
        "Are you sure?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, Remove", callback_data=f"admin_delete_confirm:{product_id}")],
            [InlineKeyboardButton("❌ Cancel", callback_data=f"admin_product:{product_id}")]
        ])
    )


async def admin_delete_product_confirm(update, context):
    q = update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True)
        return
    product_id = int(q.data.split(":", 1)[1])
    result = admin_delete_product(product_id)
    admin_log(update.effective_user.id, "remove_product", "product", product_id, result)
    await q.answer(result, show_alert=True)
    await admin_products(update, context)


async def admin_add_product_prompt(update, context):
    q = update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True)
        return
    cats = admin_list_categories()
    cat_lines = "\n".join([f"{c['id']} = {c['name']}" for c in cats])
    context.user_data["admin_input"] = {"kind": "add_product"}
    await q.answer()
    await q.edit_message_text(
        "➕ ADD PRODUCT\n━━━━━━━━━━━━━━━━\n\n"
        "Send the product details in ONE message using:\n\n"
        "category_id | product_key | product_name | price\n\n"
        "Example:\n"
        "1 | gv_new2 | Google Voice New 2 | 3.50\n\n"
        "Available categories:\n" + cat_lines +
        "\n\nProduct will be created as Active.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin_products")]
        ])
    )


async def admin_input_handler(update, context) -> bool:
    state = context.user_data.get("admin_input")
    if not state or not update.message or not update.message.text:
        return False
    if not await admin_only(update):
        context.user_data.pop("admin_input", None)
        return False

    raw = update.message.text.strip()
    kind = state.get("kind")

    try:
        if kind == "price":
            price = float(raw)
            if price < 0:
                raise ValueError("Price cannot be negative.")
            pid = int(state["product_id"])
            admin_update_product(pid, price=round(price, 2))
            admin_log(update.effective_user.id, "change_price", "product", pid, f"price={price:.2f}")
            context.user_data.pop("admin_input", None)
            await update.message.reply_text(
                f"✅ Product price updated to ${price:.2f}.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛍️ Products", callback_data="admin_products")],
                    [InlineKeyboardButton("🔐 Admin Panel", callback_data="admin_panel")]
                ])
            )
            return True

        if kind == "name":
            if len(raw) < 1 or len(raw) > 100:
                raise ValueError("Name must be 1-100 characters.")
            pid = int(state["product_id"])
            admin_update_product(pid, name=raw)
            admin_log(update.effective_user.id, "change_name", "product", pid, raw)
            context.user_data.pop("admin_input", None)
            await update.message.reply_text(
                "✅ Product name updated.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛍️ Products", callback_data="admin_products")],
                    [InlineKeyboardButton("🔐 Admin Panel", callback_data="admin_panel")]
                ])
            )
            return True

        if kind == "add_product":
            parts = [x.strip() for x in raw.split("|")]
            if len(parts) != 4:
                raise ValueError("Use exactly: category_id | product_key | product_name | price")
            category_id = int(parts[0])
            key = parts[1]
            name = parts[2]
            price = float(parts[3])
            if not key or not name or price < 0:
                raise ValueError("Invalid product data.")
            product_id = admin_create_product(category_id, key, name, price)
            admin_log(update.effective_user.id, "add_product", "product", product_id, f"{key} / {name}")
            context.user_data.pop("admin_input", None)
            await update.message.reply_text(
                f"✅ Product added successfully.\n\n"
                f"Product ID: {product_id}\n"
                f"Name: {name}\n"
                f"Price: ${price:.2f}\n\n"
                "It is Active and currently has 0 stock.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛍️ Products", callback_data="admin_products")],
                    [InlineKeyboardButton("🔐 Admin Panel", callback_data="admin_panel")]
                ])
            )
            return True

    except Exception as e:
        await update.message.reply_text(f"❌ {e}\n\nPlease try again or press Cancel.")
        return True

    return False



async def admin_command_callback(update, context):
    q = update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True)
        return
    await q.answer()
    await q.edit_message_text(
        "🔐 ADMIN PANEL\n━━━━━━━━━━━━━━━━\n\nChoose an option:",
        reply_markup=admin_kb()
    )


# =========================
# STAGE 5B — STOCK MANAGEMENT
# =========================


def admin_stock_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Stock Overview", callback_data="admin_stock")],
        [InlineKeyboardButton("➕ Add Stock", callback_data="admin_stock_add")],
        [InlineKeyboardButton("🗑️ Remove Bad Stock", callback_data="admin_stock_remove")],
        [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")],
    ])


async def admin_stock_menu(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    await q.answer()
    await q.edit_message_text("📦 STOCK MANAGEMENT\n━━━━━━━━━━━━━━━━\n\nChoose an option:", reply_markup=admin_stock_kb())


async def admin_stock_overview(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    await q.answer()
    rows=admin_stock_summary()
    lines=["📦 STOCK OVERVIEW","━━━━━━━━━━━━━━━━"]
    if not rows:
        lines.append("\nNo products found.")
    else:
        for r in rows:
            status="🟢" if int(r["is_active"]) else "🔴"
            lines.append(f"\n{status} {r['name']}\nAvailable: {r['available_stock']} | Sold: {r['sold_stock']}")
    kb=[[InlineKeyboardButton("➕ Add Stock",callback_data="admin_stock_add")],
        [InlineKeyboardButton("🗑️ Remove Bad Stock",callback_data="admin_stock_remove")],
        [InlineKeyboardButton("🔙 Stock Management",callback_data="admin_stock_menu")]]
    await q.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))


def stock_product_keyboard(products, action):
    rows=[]
    for p in products:
        rows.append([InlineKeyboardButton(f"{p['name']} (available: {p['available_stock']})", callback_data=f"stock_{action}_product:{p['id']}")])
    rows.append([InlineKeyboardButton("🔙 Stock Management",callback_data="admin_stock_menu")])
    return InlineKeyboardMarkup(rows)


async def admin_stock_add_menu(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    await q.answer()
    products=admin_list_products()
    await q.edit_message_text("➕ ADD STOCK\n━━━━━━━━━━━━━━━━\n\nSelect the product:", reply_markup=stock_product_keyboard(products,"add"))


async def admin_stock_add_product(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    product_id=int(q.data.split(":",1)[1])
    p=admin_get_product(product_id)
    if not p: await q.answer("Product not found.",show_alert=True); return
    context.user_data["admin_stock_input"]={"action":"add","product_id":product_id}
    await q.answer()
    await q.edit_message_text(
        f"➕ ADD STOCK\n━━━━━━━━━━━━━━━━\n\nProduct: {p['name']}\n\n"
        "Send stock items as separate lines.\n"
        "For account stock, you can use: email,password\n"
        "Example:\n"
        "user1@example.com,password1\n"
        "user2@example.com,password2\n\n"
        "Each line becomes one stock item.\n"
        "You can paste many lines at once.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data="admin_stock_menu")]])
    )


async def admin_stock_remove_menu(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    await q.answer()
    products=admin_list_products()
    await q.edit_message_text("🗑️ REMOVE BAD STOCK\n━━━━━━━━━━━━━━━━\n\nSelect the product:", reply_markup=stock_product_keyboard(products,"remove"))


async def admin_stock_remove_product(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    product_id=int(q.data.split(":",1)[1])
    p=admin_get_product(product_id)
    if not p: await q.answer("Product not found.",show_alert=True); return
    items=admin_stock_items(product_id,"available",50)
    if not items:
        await q.answer("No available stock.",show_alert=True); return
    rows=[]
    for item in items:
        content=str(item["stock_content"])
        preview=content.replace("\n"," ")[:45]
        rows.append([InlineKeyboardButton(f"#{item['id']} {preview}",callback_data=f"admin_stock_remove_item:{item['id']}")])
    rows.append([InlineKeyboardButton("🔙 Back",callback_data="admin_stock_remove")])
    await q.answer()
    await q.edit_message_text(f"🗑️ REMOVE BAD STOCK\n━━━━━━━━━━━━━━━━\n\nProduct: {p['name']}\n\nSelect the stock item to remove:",reply_markup=InlineKeyboardMarkup(rows))


async def admin_stock_remove_item(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.",show_alert=True); return
    stock_id=int(q.data.split(":",1)[1])
    item=admin_stock_items(None,"available",1,stock_id=stock_id)
    if not item:
        await q.answer("Stock item not found.",show_alert=True); return
    row=item[0]
    await q.answer()
    await q.edit_message_text(
        f"⚠️ REMOVE STOCK ITEM\n━━━━━━━━━━━━━━━━\n\nStock ID: #{row['id']}\nProduct: {row['product_name']}\n\n{row['stock_content']}\n\nRemove this item?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, Remove",callback_data=f"admin_stock_remove_confirm:{stock_id}")],
            [InlineKeyboardButton("❌ Cancel",callback_data=f"stock_remove_product:{row['product_id']}")]
        ])
    )


async def admin_stock_remove_confirm(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.",show_alert=True); return
    stock_id=int(q.data.split(":",1)[1])
    result=admin_remove_stock(stock_id,update.effective_user.id)
    await q.answer(result,show_alert=True)
    await admin_stock_menu(update,context)


async def admin_stock_input_handler(update, context):
    state=context.user_data.get("admin_stock_input")
    if not state or not update.message or not update.message.text:
        return False
    if not await admin_only(update):
        context.user_data.pop("admin_stock_input",None); return False
    raw=update.message.text.strip()
    if raw.lower() in {"cancel","/cancel"}:
        context.user_data.pop("admin_stock_input",None)
        await update.message.reply_text("❌ Stock operation cancelled.",reply_markup=admin_kb()); return True
    if state["action"]!="add": return False
    lines=[x.strip() for x in raw.splitlines() if x.strip()]
    if not lines:
        await update.message.reply_text("❌ No stock items found. Paste one stock item per line."); return True
    if len(lines)>500:
        await update.message.reply_text("❌ Maximum 500 stock items per upload. Split the stock into smaller batches."); return True
    try:
        added=admin_add_stock(state["product_id"],lines,update.effective_user.id)
        context.user_data.pop("admin_stock_input",None)
        await update.message.reply_text(f"✅ Stock added successfully.\n\nAdded: {added} item(s).",reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Stock Overview",callback_data="admin_stock")],
            [InlineKeyboardButton("🔐 Admin Panel",callback_data="admin_panel")]
        ]))
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
    return True

async def error_handler(update,context): print("Bot error:",context.error)


def main():
    if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN is missing. Please add BOT_TOKEN in Railway Variables.")
    init_db()
    application=Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start",start))
    application.add_handler(CommandHandler("pending_payments",pending_payments))
    application.add_handler(CommandHandler("approve_payment",approve_payment_cmd))
    application.add_handler(CommandHandler("cancel_payment",cancel_payment_cmd))
    application.add_handler(CommandHandler("admin",admin_command))

    application.add_handler(CallbackQueryHandler(admin_command_callback,pattern="^admin_panel$"))
    application.add_handler(CallbackQueryHandler(admin_dashboard,pattern="^admin_dashboard$"))
    application.add_handler(CallbackQueryHandler(admin_products_callback,pattern="^admin_products$"))
    application.add_handler(CallbackQueryHandler(admin_products_page,pattern="^admin_products_page:"))
    application.add_handler(CallbackQueryHandler(admin_product_detail,pattern="^admin_product:"))
    application.add_handler(CallbackQueryHandler(admin_change_price,pattern="^admin_price:"))
    application.add_handler(CallbackQueryHandler(admin_change_name,pattern="^admin_name:"))
    application.add_handler(CallbackQueryHandler(admin_toggle_product,pattern="^admin_toggle:"))
    application.add_handler(CallbackQueryHandler(admin_delete_product_prompt,pattern="^admin_delete:"))
    application.add_handler(CallbackQueryHandler(admin_delete_product_confirm,pattern="^admin_delete_confirm:"))
    application.add_handler(CallbackQueryHandler(admin_add_product_prompt,pattern="^admin_add_product$"))
    application.add_handler(CallbackQueryHandler(admin_stock_menu,pattern="^admin_stock_menu$"))
    application.add_handler(CallbackQueryHandler(admin_stock_overview,pattern="^admin_stock$"))
    application.add_handler(CallbackQueryHandler(admin_stock_add_menu,pattern="^admin_stock_add$"))
    application.add_handler(CallbackQueryHandler(admin_stock_add_product,pattern="^stock_add_product:"))
    application.add_handler(CallbackQueryHandler(admin_stock_remove_menu,pattern="^admin_stock_remove$"))
    application.add_handler(CallbackQueryHandler(admin_stock_remove_product,pattern="^stock_remove_product:"))
    application.add_handler(CallbackQueryHandler(admin_stock_remove_item,pattern="^admin_stock_remove_item:"))
    application.add_handler(CallbackQueryHandler(admin_stock_remove_confirm,pattern="^admin_stock_remove_confirm:"))

    application.add_handler(CallbackQueryHandler(show_main_menu,pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(show_profile,pattern="^my_profile$"))
    application.add_handler(CallbackQueryHandler(communication_apps,pattern="^communication_apps$"))
    application.add_handler(CallbackQueryHandler(google_voice,pattern="^google_voice$"))
    application.add_handler(CallbackQueryHandler(textnow,pattern="^textnow$"))
    application.add_handler(CallbackQueryHandler(textfree,pattern="^textfree$"))
    application.add_handler(CallbackQueryHandler(sideline,pattern="^sideline$"))
    application.add_handler(CallbackQueryHandler(talkatone,pattern="^talkatone$"))
    application.add_handler(CallbackQueryHandler(textplus,pattern="^textplus$"))
    application.add_handler(CallbackQueryHandler(custom_quantity_prompt,pattern="^customqty:"))
    application.add_handler(CallbackQueryHandler(cancel_custom_quantity,pattern="^cancelcustomqty:"))
    application.add_handler(CallbackQueryHandler(quantity_selected,pattern="^buyqty:"))
    application.add_handler(CallbackQueryHandler(confirm_buy,pattern="^confirmbuy:"))
    application.add_handler(CallbackQueryHandler(pay_purchase,pattern="^paypurchase:"))
    application.add_handler(CallbackQueryHandler(enter_payment,pattern="^enterpay:"))
    application.add_handler(CallbackQueryHandler(cancel_user_payment,pattern="^cancel_user_payment:"))
    application.add_handler(CallbackQueryHandler(communication_product,pattern="^product_"))
    application.add_handler(CallbackQueryHandler(buy_vpn,pattern="^buy_vpn$"))
    application.add_handler(CallbackQueryHandler(vpn_03_days,pattern="^vpn_03_days$"))
    application.add_handler(CallbackQueryHandler(vpn_07_days,pattern="^vpn_07_days$"))
    application.add_handler(CallbackQueryHandler(vpn_07_page_2,pattern="^vpn_07_page_2$"))
    application.add_handler(CallbackQueryHandler(vpn_07_page_3,pattern="^vpn_07_page_3$"))
    application.add_handler(CallbackQueryHandler(vpn_14_days,pattern="^vpn_14_days$"))
    application.add_handler(CallbackQueryHandler(vpn_30_days,pattern="^vpn_30_days$"))
    application.add_handler(CallbackQueryHandler(vpn_product,pattern="^vpn_product_"))
    application.add_handler(CallbackQueryHandler(buy_proxy,pattern="^buy_proxy$"))
    application.add_handler(CallbackQueryHandler(verification_service,pattern="^verification_service$"))
    application.add_handler(CallbackQueryHandler(buy_more_products,pattern="^buy_more_products$"))
    application.add_handler(CallbackQueryHandler(coming_soon,pattern="^coming_soon_"))
    application.add_handler(CallbackQueryHandler(add_balance,pattern="^add_balance$"))
    application.add_handler(CallbackQueryHandler(my_orders,pattern="^my_orders$"))
    application.add_handler(CallbackQueryHandler(refer,pattern="^refer$"))
    application.add_handler(CallbackQueryHandler(support,pattern="^support$"))

    # Text handler first checks active payment/amount states.
    async def text_router(update,context):
        if await admin_stock_input_handler(update,context): return
        if await admin_input_handler(update,context): return
        if await process_custom_quantity(update,context): return
        if await add_balance_text_handler(update,context): return
        await text_message_handler(update,context)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,text_router))
    application.add_error_handler(error_handler)

    print(f"{STORE_NAME} Stage 5A bot is running...")
    application.run_polling()

if __name__ == "__main__": main()
