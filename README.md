# JanKug Store — Final Production Source

## Railway Variables

Required:
- BOT_TOKEN = your Telegram BotFather token
- ADMIN_IDS = comma-separated Telegram numeric IDs
- SUPPORT_USERNAME = JanKug
- BINANCE_PAY_ID = your manual Binance Pay ID

Optional automatic Binance Pay Merchant API:
- BINANCE_PAY_API_KEY = Binance Pay Certificate SN / API identity key
- BINANCE_PAY_SECRET = Binance Pay API secret
- BINANCE_PAY_CURRENCY = USDT (default)

Optional:
- BKASH_NUMBER
- NAGAD_NUMBER

Never put real secrets in GitHub or in chat.

## What this version includes

- Inline-keyboard customer UI (no Reply Keyboard / Keyboard Toggle feature)
- Profile, orders, referrals, support
- Database-driven categories, groups, products and variants
- Quantity 1 / 2 / 5 / 10 / custom
- Stock validation and atomic balance + stock purchase
- Automatic stock delivery
- Balance wallet
- Binance Pay manual approval flow
- Optional Binance Pay Merchant API order creation + automatic status polling when API credentials are configured
- bKash/Nagad BDT-to-USD conversion with Admin-controlled rate
- Configurable referral commission and qualifying deposit limit
- Admin dashboard
- Product price editing and enable/disable
- Add product from Admin Panel
- Inventory management and invalid-stock protection
- User management
- Balance request approval/rejection
- Orders and last-24-hour sales reports
- Broadcast
- Payment method ON/OFF
- Low-stock threshold
- Admin action logging
- Safe database migrations for older sales_bot.db files
- /addstock and /stock admin commands
- /cancel state reset
- Error handling

## Important payment note

Automatic Binance Pay requires Binance Pay Merchant API credentials. If those variables are absent, the bot safely falls back to the existing manual Binance Pay ID + Admin approval flow.

Binance Pay API signing follows Binance's current HMAC-SHA512 rules. The bot uses the V2 order/query endpoints when automatic mode is enabled.

## Run

```bash
pip install -r requirements.txt
python bot.py
```

Railway can run the same command.

The database file `sales_bot.db` is intentionally NOT included in this source backup. Your live database contains customer/order/stock data and should be backed up separately.
