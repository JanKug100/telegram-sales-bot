# JanKug Store V3 — Production Baseline

Back up `sales_bot.db` before deployment. Existing data is preserved by `CREATE TABLE IF NOT EXISTS`.

Railway variables:
- BOT_TOKEN
- ADMIN_IDS
- SUPPORT_USERNAME
- BINANCE_PAY_ID
- Optional: BINANCE_PAY_API_KEY, BINANCE_PAY_SECRET, BINANCE_PAY_CURRENCY

Use `/admin` for the admin panel.

Starter payment methods:
- Binance Pay (ON)
- bKash (OFF)
- Nagad (OFF)
- USDT TRC20 (OFF)

Payment methods are database-driven. Enabling a method does not by itself create automatic provider verification; official API/webhook integration is required for that provider.

The package uses inline keyboards only. Do not upload `__pycache__`.
