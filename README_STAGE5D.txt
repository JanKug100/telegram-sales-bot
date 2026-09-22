JAN KUG STORE — STAGE 5D

Files in this package:
- bot.py — Stage 5C base + Stage 5D features
- db.py — Stage 5C database + Stage 5D helpers
- requirements.txt — existing requirements

IMPORTANT:
1. Keep your existing config.py. DO NOT replace it with a different config.py.
2. Keep your existing sales_bot.db. DO NOT delete it.
3. In GitHub, replace ONLY bot.py and db.py with the files in this package.
4. Railway will redeploy automatically after GitHub updates.

Stage 5D adds:
- Admin Panel > Referrals
- Admin Panel > Settings
- Referral commission percentage editing
- First-deposit limit editing
- USD/BDT rate editing (default 1 USD = 127 BDT)
- Admin > Payment Methods
- Add payment methods without code changes
- Edit payment method name/type/currency/rate/details
- Enable/disable payment methods
- Binance Pay support
- bKash/Nagad/custom BDT methods
- Customer chooses an active payment method when adding balance
- Customer chooses an active payment method when a purchase needs extra balance
- BDT local amount is calculated from the method's exchange rate
- After admin confirms a purchase top-up, the purchase continues automatically
- Referral commission is credited automatically on confirmed qualifying deposits
- Existing Stage 5A/5B/5C product, stock, CSV delivery, orders and customer features are retained

Payment method input format in Admin:
Name | type | currency | exchange_rate | details

Example:
bKash | bkash | BDT | 127 | Number: 01XXXXXXXXX
Nagad | nagad | BDT | 127 | Number: 01XXXXXXXXX
Binance Pay | binance_pay | USD | 1 | Binance Pay ID: YOUR_ID
