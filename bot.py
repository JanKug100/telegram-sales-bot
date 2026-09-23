from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from io import BytesIO
import io
import csv
import asyncio
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters, ApplicationHandlerStop

from config import (
    BOT_TOKEN, SUPPORT_USERNAME, STORE_NAME,
    DEFAULT_REFERRAL_COMMISSION, DEFAULT_REFERRAL_DEPOSIT_LIMIT,
    ADMIN_IDS,
)

from db import (
    init_db, get_user, create_user, update_user, get_balance, get_setting, set_setting,
    get_product_by_key, get_available_stock_count, create_purchase_intent,
    complete_purchase, create_payment, get_payment, submit_payment_reference,
    confirm_payment, cancel_payment, get_recent_orders, get_order_items,
    admin_dashboard_stats, admin_list_products, admin_get_product,
    admin_create_product, admin_update_product, admin_delete_product,
    admin_list_categories, admin_log, admin_create_communication_app,
    get_communication_products, get_communication_children,
    admin_stock_summary, admin_stock_items, admin_add_stock, admin_remove_stock,
    admin_recent_orders, admin_get_order, admin_order_items, admin_list_users, admin_get_user_by_db_id,
    admin_set_user_blocked, admin_remove_user,
    admin_get_stock_fields, admin_add_stock_field, admin_rename_stock_field, admin_remove_stock_field,
    admin_get_settings, admin_list_payment_methods, admin_get_payment_method, admin_broadcast_recipients,
    admin_create_payment_method, admin_update_payment_method,
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


def is_blocked_customer(user_id: int) -> bool:
    """Return True only for blocked non-admin customers."""
    if not user_id or user_id in ADMIN_IDS:
        return False
    user = get_user(user_id)
    return bool(user and int(user["is_blocked"] or 0) == 1)


async def blocked_customer_callback_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop blocked customers from using old or newly rendered inline buttons."""
    user = update.effective_user
    q = update.callback_query
    if not user or not q:
        return
    if not is_blocked_customer(user.id):
        return

    context.user_data.clear()
    try:
        await q.answer("🚫 Your account is blocked. Please contact support.", show_alert=True)
    except Exception:
        pass
    try:
        await q.edit_message_text(
            "🚫 ACCOUNT BLOCKED\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "Your account has been blocked by the administrator.\n\n"
            f"Please contact {SUPPORT_USERNAME} for assistance."
        )
    except Exception:
        pass


async def blocked_customer_message_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop blocked customers from continuing text-based customer flows."""
    user = update.effective_user
    if not user or not is_blocked_customer(user.id):
        return

    context.user_data.clear()
    if update.message:
        await update.message.reply_text(
            "🚫 ACCOUNT BLOCKED\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "Your account has been blocked by the administrator.\n\n"
            f"Please contact {SUPPORT_USERNAME} for assistance."
        )
    raise ApplicationHandlerStop


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
    product=get_product_by_key(product_key)
    back="communication_apps" if product and str(product["category_name"] or "").lower()=="communication apps" else "buy_vpn"
    rows = [
        [InlineKeyboardButton("1", callback_data=f"buyqty:{product_key}:1"),
         InlineKeyboardButton("2", callback_data=f"buyqty:{product_key}:2"),
         InlineKeyboardButton("3", callback_data=f"buyqty:{product_key}:3")],
        [InlineKeyboardButton("5", callback_data=f"buyqty:{product_key}:5"),
         InlineKeyboardButton("10", callback_data=f"buyqty:{product_key}:10")],
        [InlineKeyboardButton("✏️ Custom Quantity", callback_data=f"customqty:{product_key}")],
        [InlineKeyboardButton("🔙 Back", callback_data=back)],
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


def _parse_communication_stock_row(content):
    raw = str(content or "").strip()
    if not raw:
        return [""]
    # Support the three separators commonly used when pasting stock.
    # Tab is preferred, then |, then comma.
    if "\t" in raw:
        return [x.strip() for x in raw.split("\t")]
    if "|" in raw:
        return [x.strip() for x in raw.split("|")]
    if "," in raw:
        return [x.strip() for x in raw.split(",")]
    return [raw]


def _clean_stock_field_names(field_names):
    """Return human-readable field names from sqlite3.Row objects or strings."""
    names=[]
    for item in (field_names or []):
        if isinstance(item, dict):
            value=item.get("field_name") or item.get("name") or ""
        else:
            try:
                keys=item.keys()
                if "field_name" in keys:
                    value=item["field_name"]
                else:
                    value=str(item)
            except Exception:
                value=str(item)
        value=str(value or "").strip()
        if value:
            names.append(value)
    return names


def _stock_field_example_value(field_name, index):
    """Generate an example value based on the configured field name."""
    name=str(field_name or "").strip().lower()
    if "password" in name or "pass" in name:
        return "password1"
    if "2fa" in name or "otp" in name or "auth" in name:
        return "2FA-CODE"
    if "recovery" in name and "email" in name:
        return "recovery@example.com"
    if "email" in name or "mail" in name:
        return "user1@example.com"
    if "phone" in name or "number" in name or "mobile" in name:
        return "+1234567890"
    if "link" in name or "url" in name:
        return "https://example.com/recovery"
    if "name" in name:
        return "Account Name"
    if "username" in name or "user" in name:
        return "username123"
    if "code" in name:
        return "CODE123"
    return f"value{index + 1}"


def build_csv_bytes(contents, field_names=None):
    rows = [_parse_communication_stock_row(x) for x in (contents or [])] or [[""]]
    configured = _clean_stock_field_names(field_names)

    # If the product has custom fields, use those exact names as CSV headers.
    # If a stock row contains more values than configured fields, preserve them
    # by adding generic Field N columns instead of silently dropping data.
    if configured:
        max_fields = max(len(x) for x in rows)
        headers = configured[:]
        if max_fields > len(headers):
            headers.extend([f"Field {i}" for i in range(len(headers) + 1, max_fields + 1)])
        max_fields = max(len(headers), max_fields)
    else:
        max_fields = max(len(x) for x in rows)
        if max_fields == 1:
            headers = ["Stock"]
        elif max_fields == 2:
            headers = ["Email / Username", "Password"]
        else:
            headers = ["Field 1", "Field 2"] + [f"Field {i}" for i in range(3, max_fields + 1)]

    string_io = io.StringIO()
    writer = csv.writer(string_io, lineterminator="\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row + [""] * (len(headers) - len(row)))
    return BytesIO(string_io.getvalue().encode("utf-8-sig"))


async def send_purchase_delivery(bot, purchase):
    contents = purchase.get("delivered") or []
    if not contents:
        return
    chat_id = purchase["telegram_id"]
    if is_communication_product(purchase):
        field_names = admin_get_stock_fields(int(purchase.get("product_id") or 0))
        document = build_csv_bytes(contents, field_names)
        filename = f"JanKug_{purchase['product_name'].replace(' ', '_')}_Order_{purchase['order_id']}.csv"
        caption = (
            "📦 COMMUNICATION APPS DELIVERY\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"🧾 Order: #{purchase['order_id']}\n"
            f"📱 Product: {purchase['product_name']}\n"
            f"🔢 Quantity: {purchase['quantity']}\n"
            f"💰 Total: ${purchase['total']:.2f}\n\n"
            "📄 All purchased stock is included in this ONE CSV file."
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

    # Blocked customers must not regain access through /start.
    if is_blocked_customer(user.id):
        await update.message.reply_text(
            "🚫 ACCOUNT BLOCKED\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "Your account has been blocked by the administrator.\n\n"
            f"Please contact {SUPPORT_USERNAME} for assistance."
        )
        return

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
    products=get_communication_products()
    kb=[]
    for i in range(0,len(products),2):
        row=[]
        for p in products[i:i+2]:
            if str(p["product_type"]).lower()=="group":
                label=f"{p['name']}"
                callback=f"comm_group:{p['id']}"
            else:
                label=f"{p['name']} — ${float(p['price']):.2f}"
                callback=f"product_{p['product_key']}"
            row.append(InlineKeyboardButton(label,callback_data=callback))
        kb.append(row)
    kb.append([InlineKeyboardButton("🏠 Main Menu",callback_data="main_menu")])
    await q.edit_message_text("💬 COMMUNICATION APPS\n━━━━━━━━━━━━━━━━\n\nSelect an app:",reply_markup=InlineKeyboardMarkup(kb))


async def communication_group(update, context):
    q=update.callback_query
    if not q.data.startswith("comm_group:"): return
    parent_id=int(q.data.split(":",1)[1])
    parent=admin_get_product(parent_id)
    if not parent or str(parent["product_type"]).lower()!="group":
        await q.answer("App not found.",show_alert=True); return
    children=get_communication_children(parent_id)
    if not children:
        await q.answer("No subcategories available.",show_alert=True); return
    await q.answer()
    kb=[]
    for i in range(0,len(children),2):
        row=[]
        for p in children[i:i+2]:
            row.append(InlineKeyboardButton(f"{p['name']} — ${float(p['price']):.2f}",callback_data=f"product_{p['product_key']}"))
        kb.append(row)
    kb.append([InlineKeyboardButton("🔙 Communication Apps",callback_data="communication_apps")])
    await q.edit_message_text(f"📱 {parent['name'].upper()}\n━━━━━━━━━━━━━━━━\n\nChoose product:",reply_markup=InlineKeyboardMarkup(kb))


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


async def _payment_methods_keyboard(prefix="balance_method"):
    methods=admin_list_payment_methods(False)
    rows=[]
    for m in methods:
        currency=str(m["currency"] or "USD").upper()
        rows.append([InlineKeyboardButton(f"💳 {m['name']} — {currency}",callback_data=f"{prefix}:{m['id']}")])
    rows.append([InlineKeyboardButton("❌ Cancel",callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)


async def pay_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    try: _,product_key,qty_raw=q.data.split(":",2); quantity=int(qty_raw)
    except Exception: await q.answer("Invalid order.",show_alert=True); return
    product=get_product_by_key(product_key)
    if not product: await q.answer("Product not found.",show_alert=True); return
    total=round(float(product["price"])*quantity,2); balance=get_balance(update.effective_user.id); required=max(0,round(total-balance,2))
    if required<=0: await q.answer("No payment is needed now.",show_alert=True); return
    if get_available_stock_count(product["id"])<quantity: await q.answer("Stock is no longer sufficient.",show_alert=True); return
    context.user_data["purchase_payment_selection"]={"product_id":int(product["id"]),"product_key":product_key,"quantity":quantity,"required":required,"total":total,"product_name":product["name"],"balance":balance}
    await q.answer(); await q.edit_message_text(f"💳 PAYMENT REQUIRED\n━━━━━━━━━━━━━━━━\n\nProduct: {product['name']}\nQuantity: {quantity}\nPurchase total: ${total:.2f}\nCurrent balance: ${balance:.2f}\nPayment required: ${required:.2f}\n\nChoose a payment method.\nAfter admin confirmation, the purchase will continue automatically.",reply_markup=await _payment_methods_keyboard("purchase_method"))


async def purchase_method_selected(update,context):
    q=update.callback_query; state=context.user_data.get("purchase_payment_selection")
    if not state: await q.answer("Purchase payment session expired.",show_alert=True); return
    try: method_id=int(q.data.split(":",1)[1])
    except Exception: await q.answer("Invalid payment method.",show_alert=True); return
    method=admin_get_payment_method(method_id)
    if not method or not int(method["is_active"]): await q.answer("Payment method is unavailable.",show_alert=True); return
    intent=create_purchase_intent(update.effective_user.id,state["product_id"],state["quantity"],state["required"])
    rate=float(method["exchange_rate"] or 1); currency=str(method["currency"] or "USD").upper(); local_amount=round(float(state["required"])*rate,2) if currency!="USD" else round(float(state["required"]),2)
    payment_id=create_payment(update.effective_user.id,state["required"],method["method_type"],intent,currency,rate,local_amount)
    context.user_data["awaiting_payment_tx"]=payment_id; context.user_data.pop("purchase_payment_selection",None)
    pay_amount=f"${state['required']:.2f}" if currency=="USD" else f"{local_amount:.2f} {currency} (USD value ${state['required']:.2f})"
    details=str(method["details"] or "Not configured yet")
    await q.answer(); await q.edit_message_text(f"💳 PAYMENT REQUEST\n━━━━━━━━━━━━━━━━\n\nPayment #{payment_id}\nProduct: {state['product_name']} x{state['quantity']}\nPurchase total: ${state['total']:.2f}\nCurrent balance: ${state['balance']:.2f}\nPayment required: ${state['required']:.2f}\n\nMethod: {method['name']}\nPay: {pay_amount}\n\n📌 Payment Details:\n{details}\n\nSend payment, then send the transaction/order ID here.\nAfter admin confirmation, your purchase will complete automatically.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data=f"cancel_user_payment:{payment_id}")]]))
    for admin_id in ADMIN_IDS:
        try: await context.bot.send_message(admin_id,f"🔔 NEW PURCHASE PAYMENT\nPayment #{payment_id}\nUser: {update.effective_user.id}\nProduct: {state['product_name']} x{state['quantity']}\nRequired: ${state['required']:.2f}\nMethod: {method['name']}\nLocal amount: {local_amount:.2f} {currency}\nWaiting for transaction ID.")
        except Exception: pass


async def enter_payment(update, context):
    q=update.callback_query; payment_id=int(q.data.split(":",1)[1]); payment=get_payment(payment_id)
    if not payment or payment["telegram_id"]!=update.effective_user.id or payment["status"]!="pending": await q.answer("Payment is not available.",show_alert=True); return
    context.user_data["awaiting_payment_tx"]=payment_id
    await q.answer(); await q.edit_message_text(f"✍️ PAYMENT #{payment_id}\n\nPlease send your transaction/order ID as a text message.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data=f"cancel_user_payment:{payment_id}")]]))


async def cancel_user_payment(update, context):
    q=update.callback_query; payment_id=int(q.data.split(":",1)[1]); payment=get_payment(payment_id)
    if not payment or payment["telegram_id"]!=update.effective_user.id: await q.answer("Invalid payment.",show_alert=True); return
    from db import cancel_payment as db_cancel_payment
    try:
        db_cancel_payment(payment_id, update.effective_user.id, "Cancelled by customer")
        context.user_data.pop("awaiting_payment_tx",None); context.user_data.pop("balance_payment_amount",None); context.user_data.pop("purchase_payment_selection",None)
        await q.answer("Payment cancelled."); await q.edit_message_text("❌ Payment cancelled.",reply_markup=back_main_keyboard())
    except Exception as e: await q.answer(str(e),show_alert=True)


async def text_message_handler(update, context):
    if not update.message: return
    payment_id=context.user_data.get("awaiting_payment_tx")
    if payment_id:
        raw=update.message.text.strip()
        if len(raw)<3 or len(raw)>150:
            await update.message.reply_text("❌ Invalid transaction/order ID. Please send the correct reference."); return
        payment=get_payment(payment_id)
        if not payment or payment["telegram_id"]!=update.effective_user.id or payment["status"]!="pending":
            context.user_data.pop("awaiting_payment_tx",None); await update.message.reply_text("This payment is no longer pending.",reply_markup=main_menu_keyboard()); return
        try:
            submit_payment_reference(payment_id,raw); context.user_data.pop("awaiting_payment_tx",None)
            await update.message.reply_text(f"✅ Payment reference submitted.\n\nPayment #{payment_id} is waiting for admin confirmation.\nYou do not need to restart your purchase.",reply_markup=main_menu_keyboard())
            for admin_id in ADMIN_IDS:
                try:
                    admin_kb = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("✅ Accept Payment", callback_data=f"admin_payment_accept:{payment_id}"),
                            InlineKeyboardButton("❌ Cancel Payment", callback_data=f"admin_payment_cancel:{payment_id}"),
                        ]
                    ])
                    await context.bot.send_message(
                        admin_id,
                        f"💳 PAYMENT REFERENCE SUBMITTED\n━━━━━━━━━━━━━━━━\n\n"
                        f"Payment #{payment_id}\n"
                        f"User: {update.effective_user.id}\n"
                        f"Transaction ID: {raw}\n\n"
                        "Choose an action below:",
                        reply_markup=admin_kb,
                    )
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


async def show_balance_payment_methods(update,context,amount):
    methods=admin_list_payment_methods(False)
    if not methods:
        await update.message.reply_text("❌ No payment method is currently available. Please contact support.",reply_markup=back_main_keyboard()); return
    context.user_data["balance_payment_amount"]=round(float(amount),2); context.user_data.pop("awaiting_balance_amount",None)
    await update.message.reply_text(f"💳 SELECT PAYMENT METHOD\n━━━━━━━━━━━━━━━━\n\nAmount to add: ${float(amount):.2f}\n\nChoose a payment method:",reply_markup=await _payment_methods_keyboard("balance_method"))


async def balance_method_selected(update,context):
    q=update.callback_query; amount=context.user_data.get("balance_payment_amount")
    if not amount: await q.answer("Payment amount expired. Start again.",show_alert=True); return
    try: method_id=int(q.data.split(":",1)[1])
    except Exception: await q.answer("Invalid payment method.",show_alert=True); return
    method=admin_get_payment_method(method_id)
    if not method or not int(method["is_active"]): await q.answer("Payment method is unavailable.",show_alert=True); return
    rate=float(method["exchange_rate"] or 1); currency=str(method["currency"] or "USD").upper(); local_amount=round(float(amount)*rate,2) if currency!="USD" else round(float(amount),2)
    payment_id=create_payment(update.effective_user.id,float(amount),method["method_type"],None,currency,rate,local_amount)
    context.user_data["awaiting_payment_tx"]=payment_id; context.user_data.pop("balance_payment_amount",None)
    details=str(method["details"] or "Not configured yet"); pay_amount=f"${amount:.2f}" if currency=="USD" else f"{local_amount:.2f} {currency} (USD value ${amount:.2f})"
    await q.answer(); await q.edit_message_text(f"💳 {method['name'].upper()}\n━━━━━━━━━━━━━━━━\n\nPayment #{payment_id}\nPay: {pay_amount}\n\n📌 Payment Details:\n{details}\n\nAfter sending payment, send your transaction/order ID here.\nAdmin will verify and credit your USD balance.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data=f"cancel_user_payment:{payment_id}")]]))
    for admin_id in ADMIN_IDS:
        try: await context.bot.send_message(admin_id,f"🔔 NEW BALANCE PAYMENT\nPayment #{payment_id}\nUser: {update.effective_user.id}\nAmount: ${amount:.2f}\nMethod: {method['name']}\nLocal amount: {local_amount:.2f} {currency}\nWaiting for transaction ID.")
        except Exception: pass


async def create_balance_payment_from_text(update,context,amount):
    await show_balance_payment_methods(update,context,amount)


async def add_balance_text_handler(update,context):
    if not update.message: return False
    if context.user_data.get("awaiting_balance_amount"):
        raw=update.message.text.strip()
        try: amount=float(raw)
        except ValueError: await update.message.reply_text("❌ Please enter a valid USD amount, e.g. 10"); return True
        if amount<0.10: await update.message.reply_text("❌ Minimum amount is $0.10."); return True
        await show_balance_payment_methods(update,context,amount); return True
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
        commission=float(result.get("referral_commission",0) or 0)
        await update.message.reply_text(f"✅ Payment #{payment_id} confirmed." + (f"\nOrder #{purchase['order_id']} completed and delivered." if purchase else "\nBalance credited.") + (f"\nReferral commission: ${commission:.2f}" if commission>0 else ""))
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


async def admin_payment_accept_callback(update, context):
    q = update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True)
        return
    try:
        payment_id = int(q.data.split(":", 1)[1])
    except Exception:
        await q.answer("Invalid payment.", show_alert=True)
        return

    payment = get_payment(payment_id)
    if not payment:
        await q.answer("Payment not found.", show_alert=True)
        return
    if not payment["transaction_id"]:
        await q.answer("This payment has no transaction/order ID yet.", show_alert=True)
        return

    try:
        result = confirm_payment(payment_id, update.effective_user.id)
        purchase = result.get("purchase")
        commission = float(result.get("referral_commission", 0) or 0)

        if purchase and not purchase.get("already_completed"):
            await q.answer("Payment accepted.")
            await q.edit_message_text(
                f"✅ PAYMENT ACCEPTED\n━━━━━━━━━━━━━━━━\n\n"
                f"Payment #{payment_id}\n"
                f"User: {payment['telegram_id']}\n"
                f"Transaction ID: {payment['transaction_id']}\n\n"
                f"Order #{purchase['order_id']} completed and delivered."
                + (f"\nReferral commission: ${commission:.2f}" if commission > 0 else "")
            )
            await context.bot.send_message(
                purchase["telegram_id"],
                f"✅ PAYMENT CONFIRMED & ORDER COMPLETED\n━━━━━━━━━━━━━━━━\n\n"
                f"Payment #{payment_id}\n"
                f"Order #{purchase['order_id']}\n"
                f"Product: {purchase['product_name']}\n"
                f"Quantity: {purchase['quantity']}\n"
                f"Total: ${purchase['total']:.2f}\n"
                f"Remaining balance: ${purchase['balance_after']:.2f}\n\n"
                "📦 Delivery is being sent...",
                reply_markup=back_main_keyboard(),
            )
            await send_purchase_delivery(context.bot, purchase)
        else:
            await q.answer("Payment accepted.")
            await q.edit_message_text(
                f"✅ PAYMENT ACCEPTED\n━━━━━━━━━━━━━━━━\n\n"
                f"Payment #{payment_id}\n"
                f"User: {payment['telegram_id']}\n"
                f"Transaction ID: {payment['transaction_id']}\n\n"
                "Balance has been credited."
                + (f"\nReferral commission: ${commission:.2f}" if commission > 0 else "")
            )
            await context.bot.send_message(
                payment["telegram_id"],
                f"✅ PAYMENT CONFIRMED\n━━━━━━━━━━━━━━━━\n\n"
                f"Payment #{payment_id} confirmed.\n"
                "Your balance has been credited successfully.",
                reply_markup=main_menu_keyboard(),
            )
    except Exception as e:
        await q.answer(f"Could not accept: {e}", show_alert=True)


async def admin_payment_cancel_callback(update, context):
    q = update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True)
        return
    try:
        payment_id = int(q.data.split(":", 1)[1])
    except Exception:
        await q.answer("Invalid payment.", show_alert=True)
        return

    payment = get_payment(payment_id)
    if not payment:
        await q.answer("Payment not found.", show_alert=True)
        return
    if payment["status"] != "pending":
        await q.answer(f"Payment is already {payment['status']}.", show_alert=True)
        return

    try:
        cancel_payment(payment_id, update.effective_user.id, "Cancelled by admin")
        await q.answer("Payment cancelled.")
        await q.edit_message_text(
            f"❌ PAYMENT CANCELLED\n━━━━━━━━━━━━━━━━\n\n"
            f"Payment #{payment_id}\n"
            f"User: {payment['telegram_id']}\n"
            f"Transaction ID: {payment['transaction_id'] or 'Not submitted'}\n\n"
            "The payment was cancelled by admin."
        )
        await context.bot.send_message(
            payment["telegram_id"],
            f"❌ PAYMENT CANCELLED\n━━━━━━━━━━━━━━━━\n\n"
            f"Payment #{payment_id} has been cancelled by admin.\n"
            "No balance was credited and the pending purchase was cancelled.",
            reply_markup=main_menu_keyboard(),
        )
    except Exception as e:
        await q.answer(f"Could not cancel: {e}", show_alert=True)


# =========================
# STAGE 5A — ADMIN PANEL
# Dashboard + Product Management
# =========================

def admin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Dashboard", callback_data="admin_dashboard")],
        [InlineKeyboardButton("🛍️ Products", callback_data="admin_products")],
        [InlineKeyboardButton("📦 Stock Management", callback_data="admin_stock_menu")],
        [InlineKeyboardButton("📦 Orders", callback_data="admin_orders")],
        [InlineKeyboardButton("👥 Customers", callback_data="admin_customers")],
        [InlineKeyboardButton("👥 Referrals", callback_data="admin_referrals")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings")],
        [InlineKeyboardButton("💳 Payment Methods", callback_data="admin_payment_methods")],
        [InlineKeyboardButton("📢 Broadcast / Notice", callback_data="admin_broadcast")],
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
    await q.answer()
    cats=admin_list_categories()
    rows=[]
    for c in cats:
        rows.append([InlineKeyboardButton(f"{c['emoji'] or ''} {c['name']}",callback_data=f"admin_add_category:{c['id']}")])
    rows.append([InlineKeyboardButton("❌ Cancel",callback_data="admin_products")])
    context.user_data.pop("admin_input",None)
    context.user_data.pop("comm_wizard",None)
    await q.edit_message_text("➕ ADD PRODUCT\n━━━━━━━━━━━━━━━━\n\nSelect a category:",reply_markup=InlineKeyboardMarkup(rows))


async def admin_add_category(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.",show_alert=True); return
    category_id=int(q.data.split(":",1)[1])
    cats=admin_list_categories(); cat=next((c for c in cats if int(c["id"])==category_id),None)
    if not cat:
        await q.answer("Category not found.",show_alert=True); return
    await q.answer()
    if str(cat["name"]).lower()=="communication apps":
        context.user_data["comm_wizard"]={"category_id":category_id,"step":"app_name","subcategories":[]}
        context.user_data.pop("admin_input",None)
        await q.edit_message_text("➕ ADD COMMUNICATION APP\n━━━━━━━━━━━━━━━━\n\nSend the App Name.\n\nExample: Google Voice",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data="admin_comm_cancel")]]))
        return
    # Keep the existing simple one-message creator for categories not being redesigned yet.
    context.user_data["admin_input"]={"kind":"add_product","category_id":category_id}
    await q.edit_message_text(
        "➕ ADD PRODUCT\n━━━━━━━━━━━━━━━━\n\n"
        "Send: product_key | product_name | price\n\n"
        "Example: new_vpn | New VPN | 2.00",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data="admin_products")]])
    )


async def admin_comm_sub_choice(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.",show_alert=True); return
    state=context.user_data.get("comm_wizard")
    if not state:
        await q.answer("Wizard expired. Start again.",show_alert=True); return
    yes=q.data=="admin_comm_sub_yes"
    await q.answer()
    if not yes:
        state["step"]="direct_price"
        await q.edit_message_text(f"📱 {state['app_name']}\n━━━━━━━━━━━━━━━━\n\nNo Sub Categories selected.\n\nSend the USD price.\nExample: 2.00",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data="admin_comm_cancel")]]))
        return
    state["step"]="sub_name"
    await q.edit_message_text("➕ ADD SUB CATEGORY\n━━━━━━━━━━━━━━━━\n\nSend the Sub Category Name.\n\nExample: Old GV",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data="admin_comm_cancel")]]))


async def admin_comm_cancel(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.",show_alert=True); return
    context.user_data.pop("comm_wizard",None); context.user_data.pop("admin_input",None)
    await q.answer("Cancelled.")
    await admin_products(update,context)


async def admin_comm_add_more(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.",show_alert=True); return
    state=context.user_data.get("comm_wizard")
    if not state:
        await q.answer("Wizard expired.",show_alert=True); return
    state["step"]="sub_name"
    await q.answer()
    await q.edit_message_text("➕ ADD SUB CATEGORY\n━━━━━━━━━━━━━━━━\n\nSend the next Sub Category Name.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data="admin_comm_cancel")]]))


async def admin_comm_done(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.",show_alert=True); return
    state=context.user_data.get("comm_wizard")
    if not state or not state.get("subcategories"):
        await q.answer("Add at least one subcategory first.",show_alert=True); return
    try:
        result=admin_create_communication_app(state["category_id"],state["app_name"],state["subcategories"])
        admin_log(update.effective_user.id,"add_communication_app_group","product",result["parent_id"],state["app_name"])
        lines=[f"• {x['name']} — ${x['price']:.2f}" for x in state["subcategories"]]
        context.user_data.pop("comm_wizard",None)
        await q.answer("Created.")
        await q.edit_message_text(f"✅ Communication App created\n━━━━━━━━━━━━━━━━\n\n📱 {state['app_name']}\n\n"+"\n".join(lines)+"\n\nYou can now add stock to each subcategory.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛍️ Products",callback_data="admin_products")],[InlineKeyboardButton("🔐 Admin Panel",callback_data="admin_panel")]]))
    except Exception as e:
        await q.answer("Could not create app.",show_alert=True)
        await q.edit_message_text(f"❌ {e}",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Add Product",callback_data="admin_add_product")]]))


async def admin_input_handler(update, context) -> bool:
    state = context.user_data.get("admin_input")
    if not state or not update.message or not update.message.text:
        return False
    if not await admin_only(update):
        context.user_data.pop("admin_input", None)
        return False

    raw = update.message.text.strip()
    kind = state.get("kind")

    # Communication Apps uses its own step-by-step wizard.
    comm=context.user_data.get("comm_wizard")
    if comm:
        try:
            step=comm.get("step")
            if step=="app_name":
                if not raw or len(raw)>100: raise ValueError("App name must be 1-100 characters.")
                comm["app_name"]=raw
                comm["step"]="sub_choice"
                await update.message.reply_text("📱 APP NAME: " + raw + "\n\nDoes this app have Sub Categories?",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes",callback_data="admin_comm_sub_yes"),InlineKeyboardButton("❌ No",callback_data="admin_comm_sub_no")],[InlineKeyboardButton("❌ Cancel",callback_data="admin_comm_cancel")]]))
                return True
            if step=="direct_price":
                price=float(raw)
                if price<0: raise ValueError("Price cannot be negative.")
                result=admin_create_communication_app(comm["category_id"],comm["app_name"],[],direct_price=price)
                admin_log(update.effective_user.id,"add_communication_app","product",result["product_id"],f"{comm['app_name']} / ${price:.2f}")
                name=comm["app_name"]
                context.user_data.pop("comm_wizard",None)
                await update.message.reply_text(f"✅ Communication App added.\n\n📱 {name} — ${price:.2f}\n\nIt has no Sub Categories.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛍️ Products",callback_data="admin_products")],[InlineKeyboardButton("🔐 Admin Panel",callback_data="admin_panel")]]))
                return True
            if step=="sub_name":
                if not raw or len(raw)>100: raise ValueError("Sub Category name must be 1-100 characters.")
                comm["pending_sub_name"]=raw
                comm["step"]="sub_price"
                await update.message.reply_text(f"💵 Price for {raw}\n\nSend USD price.\nExample: 5.00",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data="admin_comm_cancel")]]))
                return True
            if step=="sub_price":
                price=float(raw)
                if price<0: raise ValueError("Price cannot be negative.")
                comm.setdefault("subcategories",[]).append({"name":comm.pop("pending_sub_name"),"price":round(price,2)})
                comm["step"]="waiting_more"
                lines=[f"• {x['name']} — ${x['price']:.2f}" for x in comm["subcategories"]]
                await update.message.reply_text("📱 " + comm["app_name"] + "\n━━━━━━━━━━━━━━━━\n\n"+"\n".join(lines)+"\n\nAdd another Sub Category?",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Add Another",callback_data="admin_comm_add_more"),InlineKeyboardButton("✅ Done",callback_data="admin_comm_done")],[InlineKeyboardButton("❌ Cancel",callback_data="admin_comm_cancel")]]))
                return True
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}\n\nPlease try again.")
            return True

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
            if "category_id" in state:
                if len(parts) != 3:
                    raise ValueError("Use exactly: product_key | product_name | price")
                category_id = int(state["category_id"])
                key = parts[0]
                name = parts[1]
                price = float(parts[2])
            else:
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

        if kind == "usd_bdt_rate":
            rate=float(raw)
            if rate<=0: raise ValueError("Rate must be greater than 0.")
            set_setting("usd_bdt_rate",rate); context.user_data.pop("admin_input",None)
            await update.message.reply_text(f"✅ USD/BDT rate updated: 1 USD = {rate:g} BDT",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💱 Rate",callback_data="admin_rate")],[InlineKeyboardButton("⚙️ Settings",callback_data="admin_settings")]])); return True

        if kind in {"referral_commission","referral_limit"}:
            value=float(raw) if kind=="referral_commission" else int(raw)
            if kind=="referral_commission" and not 0<=value<=100: raise ValueError("Commission must be between 0 and 100.")
            if kind=="referral_limit" and value<0: raise ValueError("Deposit limit cannot be negative.")
            set_setting("referral_commission" if kind=="referral_commission" else "referral_deposit_limit",value); context.user_data.pop("admin_input",None)
            await update.message.reply_text("✅ Referral setting updated.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👥 Referral Settings",callback_data="admin_referrals")],[InlineKeyboardButton("⚙️ Settings",callback_data="admin_settings")]])); return True

        if kind in {"payment_add","payment_edit"}:
            parts=[x.strip() for x in raw.split("|",4)]
            if len(parts)!=5: raise ValueError("Use: Name | type | currency | exchange_rate | details")
            name,ptype,currency,rate_raw,details=parts; currency=currency.upper(); rate=float(rate_raw)
            if currency not in {"USD","BDT"}: raise ValueError("Currency must be USD or BDT.")
            if rate<=0: raise ValueError("Exchange rate must be greater than 0.")
            if currency=="USD": rate=1.0
            if kind=="payment_add":
                mid=admin_create_payment_method(name,ptype,currency,rate,details); admin_log(update.effective_user.id,"add_payment_method","payment_method",mid,name); message=f"✅ Payment method added: #{mid} {name}"
            else:
                mid=int(state["method_id"]); admin_update_payment_method(mid,name=name,method_type=ptype,currency=currency,exchange_rate=rate,details=details); admin_log(update.effective_user.id,"edit_payment_method","payment_method",mid,name); message=f"✅ Payment method #{mid} updated."
            context.user_data.pop("admin_input",None); await update.message.reply_text(message,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Payment Methods",callback_data="admin_payment_methods")],[InlineKeyboardButton("⚙️ Settings",callback_data="admin_settings")]])); return True

    except Exception as e:
        await update.message.reply_text(f"❌ {e}\n\nPlease try again or press Cancel.")
        return True

    return False




def admin_settings_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("👥 Referral Settings",callback_data="admin_referrals")],[InlineKeyboardButton("💱 USD / BDT Rate",callback_data="admin_rate")],[InlineKeyboardButton("💳 Payment Methods",callback_data="admin_payment_methods")],[InlineKeyboardButton("🔙 Admin Panel",callback_data="admin_panel")]])

async def admin_settings(update,context):
    q=update.callback_query
    if not await admin_only(update): await q.answer("Admin access required.",show_alert=True); return
    await q.answer(); settings=admin_get_settings()
    await q.edit_message_text(f"⚙️ SETTINGS\n━━━━━━━━━━━━━━━━\n\nStore: {settings.get('store_name','JanKug Store')}\nSupport: {settings.get('support_username','@JanKug')}\nReferral commission: {settings.get('referral_commission','5')}%\nReferral deposit limit: {settings.get('referral_deposit_limit','10')}\nUSD/BDT rate: 1 USD = {settings.get('usd_bdt_rate','127')} BDT",reply_markup=admin_settings_kb())

async def admin_referrals(update,context):
    q=update.callback_query
    if not await admin_only(update): await q.answer("Admin access required.",show_alert=True); return
    await q.answer(); commission=get_setting("referral_commission","5"); limit=get_setting("referral_deposit_limit","10")
    await q.edit_message_text(f"👥 REFERRAL SETTINGS\n━━━━━━━━━━━━━━━━\n\nCommission: {commission}%\nFirst deposits: {limit}\n\nChoose what to change:",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 Change Commission %",callback_data="admin_referral_commission")],[InlineKeyboardButton("🔢 Change Deposit Limit",callback_data="admin_referral_limit")],[InlineKeyboardButton("🔙 Settings",callback_data="admin_settings")]]))

async def admin_referral_commission_prompt(update,context):
    q=update.callback_query
    if not await admin_only(update): await q.answer("Admin access required.",show_alert=True); return
    context.user_data["admin_input"]={"kind":"referral_commission"}; await q.answer(); await q.edit_message_text("💰 CHANGE REFERRAL COMMISSION\n\nSend a percentage from 0 to 100.\nExample: 5",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data="admin_referrals")]]))

async def admin_referral_limit_prompt(update,context):
    q=update.callback_query
    if not await admin_only(update): await q.answer("Admin access required.",show_alert=True); return
    context.user_data["admin_input"]={"kind":"referral_limit"}; await q.answer(); await q.edit_message_text("🔢 CHANGE DEPOSIT LIMIT\n\nSend how many first deposits qualify.\nExample: 10",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data="admin_referrals")]]))

async def admin_rate(update,context):
    q=update.callback_query
    if not await admin_only(update): await q.answer("Admin access required.",show_alert=True); return
    await q.answer(); rate=get_setting("usd_bdt_rate","127")
    await q.edit_message_text(f"💱 USD / BDT RATE\n━━━━━━━━━━━━━━━━\n\nCurrent: 1 USD = {rate} BDT",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Change Rate",callback_data="admin_rate_change")],[InlineKeyboardButton("🔙 Settings",callback_data="admin_settings")]]))

async def admin_rate_change_prompt(update,context):
    q=update.callback_query
    if not await admin_only(update): await q.answer("Admin access required.",show_alert=True); return
    context.user_data["admin_input"]={"kind":"usd_bdt_rate"}; await q.answer(); await q.edit_message_text("💱 CHANGE USD / BDT RATE\n\nSend the BDT value for 1 USD.\nExample: 127",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data="admin_rate")]]))


def _payment_methods_admin_kb(methods):
    rows=[]
    for m in methods:
        status="🟢" if int(m["is_active"]) else "🔴"; rows.append([InlineKeyboardButton(f"{status} #{m['id']} {m['name']}",callback_data=f"admin_payment_method:{m['id']}")])
    rows.append([InlineKeyboardButton("➕ Add Payment Method",callback_data="admin_payment_add")]); rows.append([InlineKeyboardButton("🔙 Settings",callback_data="admin_settings")]); return InlineKeyboardMarkup(rows)

async def admin_payment_methods(update,context):
    q=update.callback_query
    if not await admin_only(update): await q.answer("Admin access required.",show_alert=True); return
    await q.answer(); await q.edit_message_text("💳 PAYMENT METHODS\n━━━━━━━━━━━━━━━━\n\nSelect a method to edit/toggle, or add a new one.",reply_markup=_payment_methods_admin_kb(admin_list_payment_methods(True)))

async def admin_payment_method_detail(update,context):
    q=update.callback_query
    if not await admin_only(update): await q.answer("Admin access required.",show_alert=True); return
    mid=int(q.data.split(":",1)[1]); m=admin_get_payment_method(mid)
    if not m: await q.answer("Payment method not found.",show_alert=True); return
    await q.answer(); status="Enabled" if int(m["is_active"]) else "Disabled"; rate=float(m["exchange_rate"] or 1)
    await q.edit_message_text(f"💳 PAYMENT METHOD #{mid}\n━━━━━━━━━━━━━━━━\n\nName: {m['name']}\nType: {m['method_type']}\nCurrency: {m['currency']}\nRate: {rate:g}\nStatus: {status}\n\nDetails:\n{m['details'] or '(empty)'}",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Edit",callback_data=f"admin_payment_edit:{mid}")],[InlineKeyboardButton("🔄 Enable / Disable",callback_data=f"admin_payment_toggle:{mid}")],[InlineKeyboardButton("🔙 Payment Methods",callback_data="admin_payment_methods")]]))

async def admin_payment_add_prompt(update,context):
    q=update.callback_query
    if not await admin_only(update): await q.answer("Admin access required.",show_alert=True); return
    context.user_data["admin_input"]={"kind":"payment_add"}; await q.answer(); await q.edit_message_text("➕ ADD PAYMENT METHOD\n━━━━━━━━━━━━━━━━\n\nSend ONE line:\nName | type | currency | exchange_rate | details\n\nExamples:\nBinance Pay | binance_pay | USD | 1 | Binance Pay ID: 123456\nbKash | bkash | BDT | 127 | Number: 01XXXXXXXXX\nNagad | nagad | BDT | 127 | Number: 01XXXXXXXXX",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data="admin_payment_methods")]]))

async def admin_payment_edit_prompt(update,context):
    q=update.callback_query
    if not await admin_only(update): await q.answer("Admin access required.",show_alert=True); return
    mid=int(q.data.split(":",1)[1]); m=admin_get_payment_method(mid)
    if not m: await q.answer("Payment method not found.",show_alert=True); return
    context.user_data["admin_input"]={"kind":"payment_edit","method_id":mid}; await q.answer(); await q.edit_message_text(f"✏️ EDIT PAYMENT METHOD #{mid}\n━━━━━━━━━━━━━━━━\n\nCurrent:\n{m['name']} | {m['method_type']} | {m['currency']} | {m['exchange_rate'] or 1} | {m['details'] or ''}\n\nSend the complete replacement line:\nName | type | currency | exchange_rate | details",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data=f"admin_payment_method:{mid}")]]))

async def admin_payment_toggle(update,context):
    q=update.callback_query
    if not await admin_only(update): await q.answer("Admin access required.",show_alert=True); return
    mid=int(q.data.split(":",1)[1]); m=admin_get_payment_method(mid)
    if not m: await q.answer("Payment method not found.",show_alert=True); return
    new=0 if int(m["is_active"]) else 1; admin_update_payment_method(mid,is_active=new); admin_log(update.effective_user.id,"toggle_payment_method","payment_method",mid,f"is_active={new}")
    await q.answer("Payment method updated."); await admin_payment_method_detail(update,context)

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
# STAGE 5E — BROADCAST / NOTICE SYSTEM
# =========================

def _broadcast_selected_ids(context):
    raw=context.user_data.get("broadcast_selected", [])
    cleaned=[]
    for value in raw:
        try:
            value=int(value)
        except (TypeError, ValueError):
            continue
        if value not in cleaned:
            cleaned.append(value)
    context.user_data["broadcast_selected"]=cleaned
    return cleaned


def broadcast_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 All Customers", callback_data="broadcast_all")],
        [InlineKeyboardButton("🎯 Select Customers", callback_data="broadcast_select")],
        [InlineKeyboardButton("🔙 Admin Panel", callback_data="admin_panel")],
    ])


async def admin_broadcast(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    context.user_data.pop("broadcast_input", None)
    context.user_data.pop("broadcast_search", None)
    context.user_data["broadcast_selected"]=[]
    await q.answer()
    recipients=len(admin_broadcast_recipients())
    await q.edit_message_text(
        "📢 BROADCAST / NOTICE\n━━━━━━━━━━━━━━━━\n\n"
        f"👥 Active customers: {recipients}\n\n"
        "Choose who should receive the notice:",
        reply_markup=broadcast_menu_kb()
    )


async def broadcast_all_prompt(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    context.user_data.pop("broadcast_search", None)
    context.user_data["broadcast_selected"]=[]
    context.user_data["broadcast_input"]={"mode":"all"}
    await q.answer()
    await q.edit_message_text(
        "📢 SEND TO ALL ACTIVE CUSTOMERS\n━━━━━━━━━━━━━━━━\n\n"
        "Type the notice/message you want to send.\n\n"
        "⚠️ Blocked customers are automatically excluded.\n"
        "You can use normal Telegram text formatting such as *bold* if your client supports it.\n\n"
        "Send your message now:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data="admin_broadcast")]])
    )


def broadcast_select_kb(context, page=0, per_page=8):
    search=str(context.user_data.get("broadcast_search") or "").strip()
    selected=set(_broadcast_selected_ids(context))
    # Search/list uses existing customer helper. We keep the selector small and paginated.
    rows=admin_list_users(100, search)
    start=page*per_page
    current=rows[start:start+per_page]
    kb=[]
    for u in current:
        uid=int(u["id"])
        checked="✅" if uid in selected else "⬜"
        name=f"@{u['username']}" if u["username"] else (u["first_name"] or str(u["telegram_id"]))
        if int(u["is_blocked"]):
            # Blocked users cannot receive broadcasts and are not selectable.
            continue
        kb.append([InlineKeyboardButton(f"{checked} {name} · {u['telegram_id']}", callback_data=f"broadcast_toggle:{uid}:{page}")])
    nav=[]
    if page>0:
        nav.append(InlineKeyboardButton("⬅️ Previous",callback_data=f"broadcast_page:{page-1}"))
    if start+per_page<len(rows):
        nav.append(InlineKeyboardButton("Next ➡️",callback_data=f"broadcast_page:{page+1}"))
    if nav: kb.append(nav)
    kb.append([InlineKeyboardButton("🔍 Search Customer",callback_data="broadcast_search")])
    kb.append([InlineKeyboardButton(f"✉️ Write Notice ({len(selected)} selected)",callback_data="broadcast_selected_write")])
    kb.append([InlineKeyboardButton("🧹 Clear Selection",callback_data=f"broadcast_clear:{page}")])
    kb.append([InlineKeyboardButton("❌ Cancel",callback_data="admin_broadcast")])
    return InlineKeyboardMarkup(kb)


async def broadcast_select(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    context.user_data["broadcast_selected"]=[]
    context.user_data.pop("broadcast_search",None)
    await q.answer()
    await q.edit_message_text(
        "🎯 SELECT CUSTOMERS\n━━━━━━━━━━━━━━━━\n\n"
        "Tap customers to select/deselect them.\n"
        "Only active (unblocked) customers can be selected.\n\n"
        f"Selected: {len(_broadcast_selected_ids(context))}",
        reply_markup=broadcast_select_kb(context,0)
    )


async def broadcast_page(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    page=max(0,int(q.data.split(":",1)[1]))
    await q.answer()
    await q.edit_message_text(
        "🎯 SELECT CUSTOMERS\n━━━━━━━━━━━━━━━━\n\n"
        f"Selected: {len(_broadcast_selected_ids(context))}",
        reply_markup=broadcast_select_kb(context,page)
    )


async def broadcast_toggle(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    _,uid_raw,page_raw=q.data.split(":",2)
    uid=int(uid_raw); page=int(page_raw)
    selected=_broadcast_selected_ids(context)
    if uid in selected:
        selected.remove(uid); msg="Customer deselected."
    else:
        user=admin_get_user_by_db_id(uid)
        if not user or int(user["is_blocked"]):
            await q.answer("This customer cannot receive broadcasts.",show_alert=True); return
        selected.append(uid); msg="Customer selected."
    context.user_data["broadcast_selected"]=selected
    await q.answer(msg)
    await q.edit_message_reply_markup(reply_markup=broadcast_select_kb(context,page))


async def broadcast_clear(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    page=int(q.data.split(":",1)[1])
    context.user_data["broadcast_selected"]=[]
    await q.answer("Selection cleared.")
    await q.edit_message_reply_markup(reply_markup=broadcast_select_kb(context,page))


async def broadcast_search_prompt(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    context.user_data["broadcast_search_input"]=True
    await q.answer()
    await q.edit_message_text(
        "🔍 SEARCH CUSTOMER FOR BROADCAST\n━━━━━━━━━━━━━━━━\n\n"
        "Send Telegram ID, username, or customer name:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data="broadcast_select")]])
    )


async def broadcast_selected_write(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    selected=_broadcast_selected_ids(context)
    active=admin_broadcast_recipients(selected)
    selected=[int(u["id"]) for u in active]
    context.user_data["broadcast_selected"]=selected
    if not selected:
        await q.answer("Select at least one active customer.",show_alert=True); return
    context.user_data["broadcast_input"]={"mode":"selected","user_ids":selected}
    await q.answer()
    await q.edit_message_text(
        "✉️ SEND TO SELECTED CUSTOMERS\n━━━━━━━━━━━━━━━━\n\n"
        f"Selected active customers: {len(selected)}\n\n"
        "Type the notice/message you want to send:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data="broadcast_select")]])
    )


async def broadcast_cancel(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    for key in ("broadcast_input","broadcast_selected","broadcast_search","broadcast_search_input"):
        context.user_data.pop(key,None)
    await q.answer("Cancelled.")
    await q.edit_message_text("🔐 ADMIN PANEL\n━━━━━━━━━━━━━━━━\n\nChoose an option:",reply_markup=admin_kb())


async def send_broadcast_message(update, context, mode_state):
    text=(update.message.text or "").strip()
    if not text:
        await update.message.reply_text("❌ Message cannot be empty."); return
    if len(text)>4096:
        await update.message.reply_text("❌ Message is too long. Maximum is 4096 characters."); return
    recipients=admin_broadcast_recipients(None if mode_state.get("mode")=="all" else mode_state.get("user_ids",[]))
    total=len(recipients); sent=0; failed=0
    await update.message.reply_text(f"📢 Broadcast started.\n\nRecipients: {total}\nPlease wait...")
    for user in recipients:
        try:
            await context.bot.send_message(chat_id=int(user["telegram_id"]),text=text)
            sent+=1
        except Exception:
            failed+=1
        # Keep a safe pace for large broadcasts.
        await asyncio.sleep(0.08)
    admin_log(update.effective_user.id,"broadcast_notice","broadcast",None,f"mode={mode_state.get('mode')}; total={total}; sent={sent}; failed={failed}")
    for key in ("broadcast_input","broadcast_selected","broadcast_search","broadcast_search_input"):
        context.user_data.pop(key,None)
    await update.message.reply_text(
        "📢 BROADCAST COMPLETED\n━━━━━━━━━━━━━━━━\n\n"
        f"👥 Recipients: {total}\n"
        f"✅ Sent: {sent}\n"
        f"❌ Failed: {failed}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 Broadcast / Notice",callback_data="admin_broadcast")],[InlineKeyboardButton("🔐 Admin Panel",callback_data="admin_panel")]])
    )

# STAGE 5C — ORDERS + CUSTOMERS
def admin_orders_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("📦 Recent Orders",callback_data="admin_orders")],[InlineKeyboardButton("👥 Customers",callback_data="admin_customers")],[InlineKeyboardButton("🔙 Admin Panel",callback_data="admin_panel")]])
async def admin_orders(update,context):
    q=update.callback_query
    if not await admin_only(update): await q.answer("Admin access required.",show_alert=True); return
    await q.answer(); rows=admin_recent_orders(30); lines=["📦 ORDERS — RECENT","━━━━━━━━━━━━━━━━"]; kb=[]
    if not rows: lines.append("No orders found.")
    for r in rows:
        status="✅" if r["status"]=="completed" else "⏳"; lines.append(f"#{r['id']} — {r['product_name']} x{r['quantity']} — ${float(r['total_amount']):.2f} — {status}"); kb.append([InlineKeyboardButton(f"🔎 Order #{r['id']}",callback_data=f"admin_order:{r['id']}")])
    kb += [[InlineKeyboardButton("👥 Customers",callback_data="admin_customers")],[InlineKeyboardButton("🔙 Admin Panel",callback_data="admin_panel")]]
    await q.edit_message_text("\n".join(lines),reply_markup=InlineKeyboardMarkup(kb))
async def admin_order_detail(update,context):
    q=update.callback_query
    if not await admin_only(update): await q.answer("Admin access required.",show_alert=True); return
    oid=int(q.data.split(":",1)[1]); o=admin_get_order(oid)
    if not o: await q.answer("Order not found.",show_alert=True); return
    await q.answer(); user=f"@{o['username']}" if o['username'] else str(o['telegram_id'])
    lines=["📦 ORDER DETAILS","━━━━━━━━━━━━━━━━",f"Order: #{o['id']}",f"User: {user}",f"Telegram ID: {o['telegram_id']}",f"Product: {o['product_name']}",f"Quantity: {o['quantity']}",f"Unit Price: ${float(o['unit_price']):.2f}",f"Total: ${float(o['total_amount']):.2f}",f"Status: {o['status']}",f"Delivery: {o['delivery_status']}",f"Created: {o['created_at']}"]
    items=admin_order_items(oid)
    if items:
        lines.append("Delivered items:")
        for i,it in enumerate(items,1): lines.append(f"{i}. {str(it['delivered_content'] or '')[:100]}")
    await q.edit_message_text("\n".join(lines),reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orders",callback_data="admin_orders")],[InlineKeyboardButton("🔐 Admin Panel",callback_data="admin_panel")]]))
def admin_customers_kb(rows):
    kb=[]
    for u in rows:
        name=f"@{u['username']}" if u['username'] else (u['first_name'] or str(u['telegram_id'])); flag="🚫" if int(u['is_blocked']) else "👤"; kb.append([InlineKeyboardButton(f"{flag} {name} · {u['telegram_id']}",callback_data=f"admin_customer:{u['id']}")])
    kb += [[InlineKeyboardButton("🔍 Search Customer",callback_data="admin_customer_search")],[InlineKeyboardButton("📦 Orders",callback_data="admin_orders")],[InlineKeyboardButton("🔙 Admin Panel",callback_data="admin_panel")]]; return InlineKeyboardMarkup(kb)
async def admin_customers(update,context):
    q=update.callback_query
    if not await admin_only(update): await q.answer("Admin access required.",show_alert=True); return
    await q.answer(); rows=admin_list_users(30); await q.edit_message_text("👥 CUSTOMERS\n━━━━━━━━━━━━━━━━\n\nRecent customers: "+str(len(rows)),reply_markup=admin_customers_kb(rows))
async def admin_customer_detail(update,context):
    q=update.callback_query
    if not await admin_only(update): await q.answer("Admin access required.",show_alert=True); return
    uid=int(q.data.split(":",1)[1]); u=admin_get_user_by_db_id(uid)
    if not u: await q.answer("Customer not found.",show_alert=True); return
    await q.answer(); status="🚫 BLOCKED" if int(u['is_blocked']) else "🟢 ACTIVE"; username=f"@{u['username']}" if u['username'] else "N/A"
    lines=["👤 CUSTOMER DETAILS","━━━━━━━━━━━━━━━━",f"Telegram ID: {u['telegram_id']}",f"Username: {username}",f"Name: {(u['first_name'] or '')} {(u['last_name'] or '')}",f"Status: {status}",f"Balance: ${float(u['balance']):.2f}",f"Orders: {u['order_count']}",f"Total spent: ${float(u['total_spent']):.2f}",f"Referrals: {u['total_referrals']}",f"Referral income: ${float(u['referral_income']):.2f}"]
    toggle="🔓 Unblock" if int(u['is_blocked']) else "🚫 Block"; kb=[[InlineKeyboardButton(toggle,callback_data=f"admin_customer_block:{uid}")],[InlineKeyboardButton("🗑️ Remove Customer",callback_data=f"admin_customer_remove:{uid}")],[InlineKeyboardButton("🔙 Customers",callback_data="admin_customers")],[InlineKeyboardButton("🔐 Admin Panel",callback_data="admin_panel")]]
    await q.edit_message_text("\n".join(lines),reply_markup=InlineKeyboardMarkup(kb))
async def admin_customer_block(update,context):
    q=update.callback_query
    if not await admin_only(update): await q.answer("Admin access required.",show_alert=True); return
    uid=int(q.data.split(":",1)[1]); u=admin_get_user_by_db_id(uid)
    if not u: await q.answer("Customer not found.",show_alert=True); return
    blocked=not bool(int(u['is_blocked'])); admin_set_user_blocked(uid,blocked,update.effective_user.id); await q.answer("Customer blocked." if blocked else "Customer unblocked.",show_alert=True); await admin_customer_detail(update,context)
async def admin_customer_remove_prompt(update,context):
    q=update.callback_query
    if not await admin_only(update): await q.answer("Admin access required.",show_alert=True); return
    uid=int(q.data.split(":",1)[1]); u=admin_get_user_by_db_id(uid)
    if not u: await q.answer("Customer not found.",show_alert=True); return
    await q.answer(); await q.edit_message_text("⚠️ REMOVE CUSTOMER\n\nThis permanently removes the customer only when there is no history. Are you sure?",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes, Remove",callback_data=f"admin_customer_remove_confirm:{uid}")],[InlineKeyboardButton("❌ Cancel",callback_data=f"admin_customer:{uid}")]]))
async def admin_customer_remove_confirm(update,context):
    q=update.callback_query
    if not await admin_only(update): await q.answer("Admin access required.",show_alert=True); return
    uid=int(q.data.split(":",1)[1])
    try: admin_remove_user(uid,update.effective_user.id); await q.answer("Customer removed.",show_alert=True); await admin_customers(update,context)
    except Exception as e: await q.answer(str(e)[:190],show_alert=True); await admin_customer_detail(update,context)
async def admin_customer_search_prompt(update,context):
    q=update.callback_query
    if not await admin_only(update): await q.answer("Admin access required.",show_alert=True); return
    context.user_data["admin_customer_search"]=True; await q.answer(); await q.edit_message_text("🔍 SEARCH CUSTOMER\n\nSend Telegram ID, username, or name:",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel",callback_data="admin_customers")]]))

# =========================
# STAGE 5B — STOCK MANAGEMENT
# =========================


def admin_stock_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Stock Overview", callback_data="admin_stock")],
        [InlineKeyboardButton("➕ Add Stock", callback_data="admin_stock_add")],
        [InlineKeyboardButton("⚙️ Stock Fields", callback_data="admin_stock_fields")],
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
    fields = admin_get_stock_fields(product_id)
    field_names = _clean_stock_field_names(fields)
    field_text = "\n".join(f"{i}. {name}" for i, name in enumerate(field_names, 1)) if field_names else "No custom fields configured yet."
    example_values = [_stock_field_example_value(name, i) for i, name in enumerate(field_names)]
    example = ",".join(example_values) if field_names else "email,password,2FA,number,link"
    context.user_data["admin_stock_input"]={"action":"add","product_id":product_id,"field_count":len(fields)}
    await q.answer()
    await q.edit_message_text(
        f"➕ ADD STOCK\n━━━━━━━━━━━━━━━━\n\nProduct: {p['name']}\n\n"
        f"Custom fields:\n{field_text}\n\n"
        "Send one stock item per line.\n"
        f"Use comma, TAB, or | between fields.\n"
        "The number/order of values must match the fields above.\n\n"
        f"Example (same order as the fields above):\n{example}\n\n"
        "📌 Copy this format when adding stock. Each line = 1 stock item.\n"
        "You can paste many lines at once.\n\n"
        "Need different fields? Use ⚙️ Stock Fields first.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Edit Stock Fields",callback_data=f"admin_stock_fields_product:{product_id}")],
            [InlineKeyboardButton("❌ Cancel",callback_data="admin_stock_menu")]
        ])
    )


def _stock_fields_keyboard(product_id, fields):
    rows=[]
    for field in fields:
        rows.append([
            InlineKeyboardButton(f"✏️ {field['field_name']}", callback_data=f"admin_stock_field_rename:{field['id']}"),
            InlineKeyboardButton("🗑️", callback_data=f"admin_stock_field_remove:{field['id']}")
        ])
    rows.append([InlineKeyboardButton("➕ Add Field", callback_data=f"admin_stock_field_add:{product_id}")])
    rows.append([InlineKeyboardButton("🔙 Stock Management", callback_data="admin_stock_menu")])
    return InlineKeyboardMarkup(rows)


async def admin_stock_fields_menu(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    await q.answer()
    products=admin_list_products()
    rows=[[InlineKeyboardButton(f"{p['name']}", callback_data=f"admin_stock_fields_product:{p['id']}")] for p in products]
    rows.append([InlineKeyboardButton("🔙 Stock Management", callback_data="admin_stock_menu")])
    await q.edit_message_text("⚙️ STOCK FIELDS\n━━━━━━━━━━━━━━━━\n\nSelect a product to customize its stock fields:", reply_markup=InlineKeyboardMarkup(rows))


async def admin_stock_fields_product(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    product_id=int(q.data.split(":",1)[1])
    p=admin_get_product(product_id)
    if not p:
        await q.answer("Product not found.", show_alert=True); return
    fields=admin_get_stock_fields(product_id)
    await q.answer()
    if fields:
        field_lines="\n".join(f"{i}. {f['field_name']}" for i,f in enumerate(fields,1))
    else:
        field_lines="No fields configured. Add your first field below."
    await q.edit_message_text(
        f"⚙️ STOCK FIELDS\n━━━━━━━━━━━━━━━━\n\nProduct: {p['name']}\n\n"
        f"{field_lines}\n\n"
        "These names will become the CSV column headers for Communication Apps delivery.\n"
        "You can add, rename, or remove fields anytime.",
        reply_markup=_stock_fields_keyboard(product_id, fields)
    )


async def admin_stock_field_add_prompt(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    product_id=int(q.data.split(":",1)[1])
    if not admin_get_product(product_id):
        await q.answer("Product not found.", show_alert=True); return
    context.user_data["admin_stock_field_input"]={"action":"add","product_id":product_id}
    await q.answer()
    await q.edit_message_text(
        "➕ ADD STOCK FIELD\n━━━━━━━━━━━━━━━━\n\n"
        "Send the field name you want.\n\n"
        "Examples:\n"
        "Email\nPassword\n2FA\nPhone Number\nRecovery Link\nAccount Name",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_stock_fields_product:{product_id}")]])
    )


async def admin_stock_field_rename_prompt(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    field_id=int(q.data.split(":",1)[1])
    field=admin_get_stock_fields(field_id=field_id)
    if not field:
        await q.answer("Field not found.", show_alert=True); return
    row=field[0]
    context.user_data["admin_stock_field_input"]={"action":"rename","field_id":field_id,"product_id":row['product_id']}
    await q.answer()
    await q.edit_message_text(
        f"✏️ RENAME STOCK FIELD\n━━━━━━━━━━━━━━━━\n\nCurrent name: {row['field_name']}\n\nSend the new field name:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_stock_fields_product:{row['product_id']}")]])
    )


async def admin_stock_field_remove_prompt(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    field_id=int(q.data.split(":",1)[1])
    fields=admin_get_stock_fields(field_id=field_id)
    if not fields:
        await q.answer("Field not found.", show_alert=True); return
    row=fields[0]
    await q.answer()
    await q.edit_message_text(
        f"⚠️ REMOVE STOCK FIELD\n━━━━━━━━━━━━━━━━\n\nField: {row['field_name']}\nProduct ID: {row['product_id']}\n\n"
        "Removing the field changes future stock-entry instructions and CSV headers. Existing stock data is not deleted.\n\nAre you sure?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, Remove", callback_data=f"admin_stock_field_remove_confirm:{field_id}")],
            [InlineKeyboardButton("❌ Cancel", callback_data=f"admin_stock_fields_product:{row['product_id']}")]
        ])
    )


async def admin_stock_field_remove_confirm(update, context):
    q=update.callback_query
    if not await admin_only(update):
        await q.answer("Admin access required.", show_alert=True); return
    field_id=int(q.data.split(":",1)[1])
    fields=admin_get_stock_fields(field_id=field_id)
    if not fields:
        await q.answer("Field not found.", show_alert=True); return
    product_id=int(fields[0]['product_id'])
    admin_remove_stock_field(field_id)
    admin_log(update.effective_user.id,"remove_stock_field","stock_field",field_id,"removed stock field")
    await q.answer("Field removed.")
    await admin_stock_fields_product(update, context)


async def admin_stock_field_input_handler(update, context):
    state=context.user_data.get("admin_stock_field_input")
    if not state or not update.message or not update.message.text:
        return False
    if not await admin_only(update):
        context.user_data.pop("admin_stock_field_input",None); return False
    raw=update.message.text.strip()
    if raw.lower() in {"cancel","/cancel"}:
        product_id=state.get("product_id")
        context.user_data.pop("admin_stock_field_input",None)
        await update.message.reply_text("❌ Field operation cancelled.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Stock Fields",callback_data=f"admin_stock_fields_product:{product_id}")]]))
        return True
    if len(raw)<1 or len(raw)>50:
        await update.message.reply_text("❌ Field name must be 1-50 characters.")
        return True
    try:
        if state.get("action")=="add":
            field_id=admin_add_stock_field(int(state["product_id"]),raw,update.effective_user.id)
            message=f"✅ Stock field added: {raw}"
        else:
            admin_rename_stock_field(int(state["field_id"]),raw,update.effective_user.id)
            field_id=int(state["field_id"])
            message=f"✅ Stock field renamed to: {raw}"
        product_id=int(state["product_id"])
        context.user_data.pop("admin_stock_field_input",None)
        await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Stock Fields",callback_data=f"admin_stock_fields_product:{product_id}")],[InlineKeyboardButton("📦 Stock Management",callback_data="admin_stock_menu")]]))
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
    return True


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
    field_count=int(state.get("field_count") or 0)
    if field_count:
        invalid=[]
        for line_no,line in enumerate(lines,1):
            values=_parse_communication_stock_row(line)
            if len(values)!=field_count:
                invalid.append(f"Line {line_no}: expected {field_count} fields, got {len(values)}")
                if len(invalid)>=5: break
        if invalid:
            await update.message.reply_text(
                "❌ Stock format does not match the configured fields.\n\n"
                + "\n".join(invalid)
                + "\n\nUse comma, TAB, or | between values. Open ⚙️ Stock Fields to see the current field order."
            )
            return True
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
    # Group -1 runs before all normal callback/message handlers.
    # Returning without handling lets admins and active customers continue normally.
    application.add_handler(
        CallbackQueryHandler(blocked_customer_callback_guard, pattern=r"^.*$"),
        group=-1,
    )
    application.add_handler(CommandHandler("pending_payments",pending_payments))
    application.add_handler(CommandHandler("approve_payment",approve_payment_cmd))
    application.add_handler(CommandHandler("cancel_payment",cancel_payment_cmd))
    application.add_handler(CommandHandler("admin",admin_command))

    application.add_handler(CallbackQueryHandler(admin_command_callback,pattern="^admin_panel$"))
    application.add_handler(CallbackQueryHandler(admin_broadcast,pattern="^admin_broadcast$"))
    application.add_handler(CallbackQueryHandler(broadcast_all_prompt,pattern="^broadcast_all$"))
    application.add_handler(CallbackQueryHandler(broadcast_select,pattern="^broadcast_select$"))
    application.add_handler(CallbackQueryHandler(broadcast_page,pattern="^broadcast_page:"))
    application.add_handler(CallbackQueryHandler(broadcast_toggle,pattern="^broadcast_toggle:"))
    application.add_handler(CallbackQueryHandler(broadcast_clear,pattern="^broadcast_clear:"))
    application.add_handler(CallbackQueryHandler(broadcast_search_prompt,pattern="^broadcast_search$"))
    application.add_handler(CallbackQueryHandler(broadcast_selected_write,pattern="^broadcast_selected_write$"))
    application.add_handler(CallbackQueryHandler(broadcast_cancel,pattern="^broadcast_cancel$"))
    application.add_handler(CallbackQueryHandler(admin_settings,pattern="^admin_settings$"))
    application.add_handler(CallbackQueryHandler(admin_referrals,pattern="^admin_referrals$"))
    application.add_handler(CallbackQueryHandler(admin_referral_commission_prompt,pattern="^admin_referral_commission$"))
    application.add_handler(CallbackQueryHandler(admin_referral_limit_prompt,pattern="^admin_referral_limit$"))
    application.add_handler(CallbackQueryHandler(admin_rate,pattern="^admin_rate$"))
    application.add_handler(CallbackQueryHandler(admin_rate_change_prompt,pattern="^admin_rate_change$"))
    application.add_handler(CallbackQueryHandler(admin_payment_methods,pattern="^admin_payment_methods$"))
    application.add_handler(CallbackQueryHandler(admin_payment_method_detail,pattern="^admin_payment_method:"))
    application.add_handler(CallbackQueryHandler(admin_payment_add_prompt,pattern="^admin_payment_add$"))
    application.add_handler(CallbackQueryHandler(admin_payment_edit_prompt,pattern="^admin_payment_edit:"))
    application.add_handler(CallbackQueryHandler(admin_payment_toggle,pattern="^admin_payment_toggle:"))
    application.add_handler(CallbackQueryHandler(admin_payment_accept_callback,pattern="^admin_payment_accept:"))
    application.add_handler(CallbackQueryHandler(admin_payment_cancel_callback,pattern="^admin_payment_cancel:"))
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
    application.add_handler(CallbackQueryHandler(admin_add_category,pattern="^admin_add_category:"))
    application.add_handler(CallbackQueryHandler(admin_comm_sub_choice,pattern="^admin_comm_sub_yes$|^admin_comm_sub_no$"))
    application.add_handler(CallbackQueryHandler(admin_comm_add_more,pattern="^admin_comm_add_more$"))
    application.add_handler(CallbackQueryHandler(admin_comm_done,pattern="^admin_comm_done$"))
    application.add_handler(CallbackQueryHandler(admin_comm_cancel,pattern="^admin_comm_cancel$"))
    application.add_handler(CallbackQueryHandler(admin_orders,pattern="^admin_orders$"))
    application.add_handler(CallbackQueryHandler(admin_order_detail,pattern="^admin_order:"))
    application.add_handler(CallbackQueryHandler(admin_customers,pattern="^admin_customers$"))
    application.add_handler(CallbackQueryHandler(admin_customer_detail,pattern="^admin_customer:"))
    application.add_handler(CallbackQueryHandler(admin_customer_block,pattern="^admin_customer_block:"))
    application.add_handler(CallbackQueryHandler(admin_customer_remove_prompt,pattern="^admin_customer_remove:"))
    application.add_handler(CallbackQueryHandler(admin_customer_remove_confirm,pattern="^admin_customer_remove_confirm:"))
    application.add_handler(CallbackQueryHandler(admin_customer_search_prompt,pattern="^admin_customer_search$"))
    application.add_handler(CallbackQueryHandler(admin_stock_menu,pattern="^admin_stock_menu$"))
    application.add_handler(CallbackQueryHandler(admin_stock_overview,pattern="^admin_stock$"))
    application.add_handler(CallbackQueryHandler(admin_stock_add_menu,pattern="^admin_stock_add$"))
    application.add_handler(CallbackQueryHandler(admin_stock_add_product,pattern="^stock_add_product:"))
    application.add_handler(CallbackQueryHandler(admin_stock_fields_menu,pattern="^admin_stock_fields$"))
    application.add_handler(CallbackQueryHandler(admin_stock_fields_product,pattern="^admin_stock_fields_product:"))
    application.add_handler(CallbackQueryHandler(admin_stock_field_add_prompt,pattern="^admin_stock_field_add:"))
    application.add_handler(CallbackQueryHandler(admin_stock_field_rename_prompt,pattern="^admin_stock_field_rename:"))
    application.add_handler(CallbackQueryHandler(admin_stock_field_remove_prompt,pattern="^admin_stock_field_remove:"))
    application.add_handler(CallbackQueryHandler(admin_stock_field_remove_confirm,pattern="^admin_stock_field_remove_confirm:"))
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
    application.add_handler(CallbackQueryHandler(communication_group,pattern="^comm_group:"))
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
    application.add_handler(CallbackQueryHandler(balance_method_selected,pattern="^balance_method:"))
    application.add_handler(CallbackQueryHandler(purchase_method_selected,pattern="^purchase_method:"))
    application.add_handler(CallbackQueryHandler(my_orders,pattern="^my_orders$"))
    application.add_handler(CallbackQueryHandler(refer,pattern="^refer$"))
    application.add_handler(CallbackQueryHandler(support,pattern="^support$"))

    # Text handler first checks active payment/amount states.
    async def text_router(update,context):
        if context.user_data.get("broadcast_search_input") and await admin_only(update):
            raw=(update.message.text or "").strip()
            context.user_data.pop("broadcast_search_input",None)
            context.user_data["broadcast_search"]=raw
            await update.message.reply_text(
                f"🎯 SELECT CUSTOMERS\n━━━━━━━━━━━━━━━━\n\nSearch: {raw}\nSelected: {len(_broadcast_selected_ids(context))}",
                reply_markup=broadcast_select_kb(context,0)
            )
            return
        if context.user_data.get("broadcast_input") and await admin_only(update):
            mode_state=context.user_data.get("broadcast_input")
            await send_broadcast_message(update,context,mode_state)
            return
        if context.user_data.get("admin_customer_search") and await admin_only(update):
            raw=(update.message.text or "").strip(); context.user_data.pop("admin_customer_search",None); rows=admin_list_users(30,raw)
            await update.message.reply_text(f"👥 CUSTOMERS\n━━━━━━━━━━━━━━━━\n\nSearch: {raw}\nTotal shown: {len(rows)}",reply_markup=admin_customers_kb(rows)); return
        if await admin_stock_field_input_handler(update,context): return
        if await admin_stock_input_handler(update,context): return
        if await admin_input_handler(update,context): return
        if await process_custom_quantity(update,context): return
        if await add_balance_text_handler(update,context): return
        await text_message_handler(update,context)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, blocked_customer_message_guard),
        group=-1,
    )
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,text_router))
    application.add_error_handler(error_handler)

    print(f"{STORE_NAME} Stage 5C bot is running...")
    application.run_polling()

if __name__ == "__main__": main()
