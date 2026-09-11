# JanKug Store — V3

This version is designed as a database-driven Telegram store with a larger Admin Panel.

## Railway Variables
Required:
- BOT_TOKEN
- ADMIN_IDS
- SUPPORT_USERNAME
- BINANCE_PAY_ID

Do not put secrets in GitHub.

## Main customer menu
- My Profile
- BUY PRODUCTS
- MY ORDERS (last 24 hours)
- ADD BALANCE
- REFER
- SUPPORT

## Admin Panel
- Dashboard
- Last 24h Sales
- Products
- Inventory
- Payments
- Balance Requests
- Orders
- Users
- Referrals
- Settings
- Button Manager
- Broadcast
- Support
- Payment Methods

## Dynamic Payment Methods
Payment methods are stored in SQLite, not hard-coded.

Admin commands:
- `/addpayment code|name|emoji|currency|instructions`
- `/paytoggle code`
- `/payedit code|name|emoji|currency|instructions`

Examples:
- `/addpayment bkash|bKash|🟢|BDT|Send BDT to our bKash number and press I Have Paid.`
- `/addpayment nagad|Nagad|🔵|BDT|Send BDT to our Nagad number and press I Have Paid.`
- `/addpayment crypto|USDT TRC20|🪙|USDT|Send the exact USDT amount to the wallet shown by Admin.`

Important: adding a payment method to the menu does NOT create an automatic gateway integration. Automatic bKash/Nagad/etc. requires the provider's official merchant/API/webhook credentials and a dedicated integration.

## Product management
- `/addcategory Category Name`
- `/addproduct id|category|group|name|price|active|coming_soon`
- `/price product_id|new_price`
- `/toggle product_id`
- `/rename product_id|new name`
- `/addstock product_id|email|password`

Prices are database values, so customers see updated prices without editing Python.

## Referral
- `/refrate 7.5`
- `/reflimit 20`

The rate and deposit limit are stored in settings. New approved deposits use the current settings; historical referral income is not recalculated.

## BDT conversion
- `/bdtrate 127`
A BDT payment request credits USD proportionally using the rate saved at request time.

## Notes
- No Reply Keyboard / Keyboard Toggle is used.
- `sales_bot.db` is intentionally not included in this ZIP. Preserve your production DB if it contains customer/order/stock history.
- Some VPN products are seeded as Coming Soon because no final price was supplied. Set price and enable them from Admin.
