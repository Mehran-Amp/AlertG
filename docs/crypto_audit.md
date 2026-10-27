# AlertG — سند ممیزی وضعیت پایه کریپتو (Phase 0 Audit)
**تاریخ ممیزی:** ۲۷ اکتبر ۲۰۲۶  
**موقعیت در طرح:** فاز ۰ (صرفاً ممیزی و ثبت وضعیت موجود، بدون تغییر کد محصول)

---

## ۱. جدول کامل صرافی‌های اپلیکیشن (برگرفته از `lib/features/exchanges/registry/exchange_catalog.dart`)

در اپلیکیشن فلاتر در مجموع **۳۹ صرافی** (شامل صرافی‌های داخلی، بین‌المللی و تجمیع‌کننده‌ها) در کلاس `ExchangeCatalog` ثبت شده‌اند:

| ردیف | شناسه (`id`) | نام نمایشی (`name`) | دسته (`category`) | کلاس آداپتور (`class`) | ارز کوت پیش‌فرض | وضعیت در بک‌اند پایتون |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| ۱ | `binance` | Binance | Tier 1 Global | `BinanceExchange` | USDT | ✅ دارد (`fetch_crypto`) |
| ۲ | `kucoin` | KuCoin | Tier 1 Global | `KuCoinExchange` | USDT | ✅ دارد (`fetch_crypto`) |
| ۳ | `mexc` | MEXC | Tier 1 Global | `MEXCExchange` | USDT | ✅ دارد (`fetch_crypto`) |
| ۴ | `gateio` | Gate.io | Tier 1 Global | `GateioExchange` | USDT | ✅ دارد (`fetch_crypto`) |
| ۵ | `coinex` | CoinEx | Tier 1 Global | `CoinExExchange` | USDT | ✅ دارد (در حال بسته شدن) |
| ۶ | `lbank` | LBank | Asia / Tier 1 | `LBankExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۷ | `okx` | OKX | Tier 1 Global | `OKXExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۸ | `bybit` | Bybit | Tier 1 Global | `BybitExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۹ | `bitget` | Bitget | Tier 1 Global | `BitgetExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۱۰ | `bingx` | BingX | Tier 1 Global | `BingXExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۱۱ | `kraken` | Kraken | Tier 1 Global | `KrakenExchange` | USD | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۱۲ | `coinbase` | Coinbase | Tier 1 Global | `CoinbaseExchange` | USD | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۱۳ | `kcex` | KCEX | Tier 1 Global | `KCEXExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۱۴ | `ourbit` | Ourbit | Tier 1 Global | `OurbitExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۱۵ | `xt` | XT.com | Tier 1 Global | `XTExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۱۶ | `toobit` | Toobit | Tier 1 Global | `ToobitExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۱۷ | `htx` | HTX / Huobi | Tier 1 Global | `StandardRestExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۱۸ | `bitfinex` | Bitfinex | Tier 1 Global | `StandardRestExchange` | USD | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۱۹ | `bitstamp` | Bitstamp | Europe / Tier 1 | `StandardRestExchange` | USD | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۲۰ | `gemini` | Gemini | US / Tier 1 | `StandardRestExchange` | USD | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۲۱ | `poloniex` | Poloniex | Tier 1 Global | `StandardRestExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۲۲ | `bitmart` | BitMart | Tier 1 Global | `StandardRestExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۲۳ | `cryptocom` | Crypto.com | Tier 1 Global | `StandardRestExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۲۴ | `upbit` | Upbit | Asia | `StandardRestExchange` | KRW | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۲۵ | `bithumb` | Bithumb | Asia | `StandardRestExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۲۶ | `bitflyer` | bitFlyer | Asia | `StandardRestExchange` | USD | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۲۷ | `phemex` | Phemex | Tier 1 Global | `StandardRestExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۲۸ | `woox` | WOO X | Tier 1 Global | `StandardRestExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۲۹ | `deribit` | Deribit | Derivatives | `StandardRestExchange` | USD | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۳۰ | `bitmex` | BitMEX | Derivatives | `StandardRestExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۳۱ | `probit` | ProBit | Tier 1 Global | `StandardRestExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۳۲ | `ascendex` | AscendEX | Tier 1 Global | `StandardRestExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۳۳ | `bitrue` | Bitrue | Tier 1 Global | `StandardRestExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۳۴ | `hitbtc` | HitBTC | Tier 1 Global | `StandardRestExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۳۵ | `bitso` | Bitso | Americas | `StandardRestExchange` | USD | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۳۶ | `indodax` | Indodax | Asia | `StandardRestExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۳۷ | `paribu` | Paribu | Europe | `StandardRestExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۳۸ | `btcturk` | BtcTurk | Europe | `StandardRestExchange` | USDT | ❌ ندارد (به بایننس fallback می‌خورد) |
| ۳۹ | `bitvavo` | Bitvavo | Europe | `StandardRestExchange` | EUR | ❌ ندارد (به بایننس fallback می‌خورد) |

### صرافی‌های داخلی ایران (در اپ و سرور):
* `nobitex`: نوبیتکس (TMN / USDT) — آداپتور اختصاصی در اپ و سرور
* `wallex`: والکس (TMN / USDT) — آداپتور اختصاصی در اپ و سرور
* `ramzinex`: رمزنکس (TMN / USDT) — آداپتور اختصاصی در اپ و سرور
* `tabdeal`: تبدیل (TMN / USDT) — آداپتور اختصاصی در اپ و سرور
* `tetherland`: تترلند (TMN) — آداپتور اختصاصی در اپ و سرور
* `bitbarg`: بیت‌برگ (TMN) — آداپتور اختصاصی در اپ و سرور
* `abantether`: آبان‌تتر (TMN) — آداپتور جنریک
* `sarmayex`: سرمایکس (TMN) — آداپتور جنریک
* `exir`: اکسیر (TMN) — آداپتور جنریک

### تجمیع‌کننده‌ها:
* `coingecko`: CoinGecko (`CoinGeckoExchange` در اپ، در سرور با `UniversalPriceAggregator` شبیه‌سازی می‌شود)
* `coinmarketcap`: CoinMarketCap (`CoinMarketCapExchange` در اپ)

---

## ۲. وضعیت فعلی قیمت‌گیری در بک‌اند (`app/markets/crypto.py`)

تابع `fetch_crypto(client, exchange, symbol, _try_fetch, traces, collect_all_traces)` در فایل `app/markets/crypto.py`:
1. **صرافی‌های شناخته‌شده در کد سرور:**
   - بایننس: `https://api.binance.com/api/v3/ticker/price?symbol={crypto_sym}`
   - مکسی: `https://api.mexc.com/api/v3/ticker/price?symbol={crypto_sym}`
   - کوکوین: `https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={kucoin_sym}`
   - گیت: `https://api.gateio.ws/api/v4/spot/tickers?currency_pair={gate_sym}`
   - کوینکس: `https://api.coinex.com/v1/market/ticker?market={crypto_sym}`
   - آنچین (DEX): `DexScreener` و `GeckoTerminal`

2. **باگ نقض قانون R1 در کد فعلی (Fallback ناخواسته به بایننس):**
   در خطوط ۱۰۱ تا ۱۱۶ فایل `app/markets/crypto.py`:
   اگر صرافی ارسالی مثلاً `okx` یا `lbank` یا `bybit` باشد، چون در شرط `if ex in ['mexc', 'kucoin', ...]` وجود ندارد، لیست `providers` با اولویت پیش‌فرض اجرا می‌شود:
   ابتدا `binance`، سپس `mexc`، سپس `kucoin`، سپس `gateio`، سپس `coinex`!
   **نتیجه باگ:** هشدار ثبت‌شده روی OKX مستقیماً با قیمت بایننس ارزیابی می‌شود! این دقیقاً باگی است که در فاز ۳ باید کاملاً مسدود شود.

---

## ۳. نقاط اعتبارسنجی، دسته‌بندی و نمایش شناسه صرافی و نماد

| موقعیت در کد | فایل و خط | وظیفه و رفتار فعلی |
| :--- | :--- | :--- |
| **شناسه صرافی (`EXCHANGE_RE`)** | `app/config.py:63` | ریجکس `^[A-Za-z0-9_.\-&öäüéèáà][A-Za-z0-9_.\-&öäüéèáà ]{0,38}[A-Za-z0-9_.\-&öäüéèáà]$` (۲ الی ۴۰ کاراکتر). همه صرافی‌های جدید (LBank, OKX, Bybit, ...) بدون تغییر در این الگو معتبر هستند. |
| **نماد ارز (`SYMBOL_RE`)** | `app/config.py:60` | ریجکس ۱ الی ۳۲ کاراکتری که نمادهای با ارقام، خط تیره، اسلش و دات را می‌پذیرد (مانند `1000SATS`, `1INCH`, `BTC-USDT`, `BTC/USDT`). |
| **دسته‌بندی بازار (`resolve_symbol_category`)** | `app/engine/categories.py:78` | اگر صرافی ایرانی یا جفت ریالی نباشد، و در دسته‌های سهام/فارکس/ماکرو مچ نشود، در خط ۱۳۶ به عنوان پیش‌فرض `return 'crypto'` بازمی‌گرداند. |
| **سقف و نرخ خزش (`CATEGORY_CACHE_TTL`)** | `app/engine/categories.py:17` | کش کریپتو برابر با ۲.۰ ثانیه (`2.0s`) و آستانه جهش نامتعارف برابر با ۵۰٪ (`0.50`) تنظیم شده است. |
| **نام نمایشی در تلگرام (`get_exchange_display_name`)** | `app/notifier/telegram.py:23` | صرافی‌های `nobitex, wallex, binance, kucoin, mexc, gateio, coinex, okx, bybit` نقشه اختصاصی دارند؛ بقیه با `capitalize()` نمایش داده می‌شوند. در فاز ۲ نام‌های اختصاصی (مثل `LBank`) اضافه خواهد شد. |
| **تقویم بازار کریپتو (`is_crypto_market_open`)** | `app/engine/calendar.py:210` | همیشه `True, 'OPEN'` (کریپتو ۲۴/۷ فعال است). |

---

## ۴. جریان کامل یک هشدار کریپتو (از ابتدا تا انتها)

1. **مرحله ۱ — ایجاد هشدار در فلاتر (UI Creation):**
   - فایل: `lib/features/watchlist/pages/create_alert_flow.dart` (متد `_submit`)
   - ورودی‌ها: `exchangeId` (مثلاً `binance`)، `symbol` (مثلاً `BTCUSDT`)، `targetPrice`، `condition` (`ABOVE`/`BELOW`).
   - ساخت مدل: شیء `AlertRule` با مشخصات جفت‌ارز تولید می‌شود.

2. **مرحله ۲ — ذخیره محلی و همگام‌سازی ابری (Local Save & Cloud Sync):**
   - ذخیره در دیسک گوشی: `lib/features/alert_engine/repositories/json_alert_rule_repository.dart` (متد `saveRule`) در فایل `alert_rules.json`.
   - ارسال به بک‌اند: `ServerAlertService.syncAllRulesToServer()` در `lib/core/services/server_alert_service.dart`.
   - دریافت در سرور: اندپوینت `POST /api/alerts/sync` در `app/routes/alerts.py` (متد `sync_user_alerts`).
   - ذخیره در دیسک سرور: در حافظه رم `storage.ALERTS_DB` و فایل `alerts_data.json` از طریق `save_alerts_to_disk_async`.

3. **مرحله ۳ — چرخه ارزیابی در موتور پس‌زمینه (Evaluation Loop):**
   - زمان‌بند سرور: در فایل `app/engine/checker.py` (متد `evaluate_alerts`) هر ۲ الی ۵ ثانیه اجرا می‌شود.
   - بررسی باز بودن بازار: `is_market_open(alert.exchange, alert.symbol)` (برای کریپتو همیشه `True`).
   - واکشی قیمت: فراخوانی `fetch_price_with_trace(client, alert.exchange, alert.symbol)` در `app/markets/base.py`.
   - شاخه کریپتو: خط ۲۴۵ در `app/markets/base.py` تابع `fetch_crypto()` در `app/markets/crypto.py` را صدا می‌زند.
   - ارزیابی شرط: قیمت جدید با `alert.target_price` مقایسه می‌شود. اگر شرط محقق شد و فاصله از آخرین شلیک بیش از ۳ دقیقه بود (Cooldown)، تریگر می‌شود.

4. **مرحله ۴ — صف‌بندی و ارسال اعلان (Notification Dispatch):**
   - صف‌بندی در Outbox: فراخوانی `outbox.enqueue_alert(alert, current_price)`.
   - تلگرام: `app/notifier/telegram.py` (متد `send_telegram_alert`) با نام صرافی از `get_exchange_display_name()`.
   - پوش نوتیفیکیشن: `app/notifier/fcm.py` (متد `send_fcm_notification`) به دستگاه کاربر.
   - ذخیره سابقه: ثبت در `app/notifier/journal.py`.

---

## ۵. خلاصه وضعیت فاز ۰
* **کد محصول:** هیچ تغییری نکرده است (Zero Code Changes).
* **وضعیت تست‌های رگرسیون:** تمامی تست‌های موجود معتبر و سبز باقی می‌مانند.
* **آماده‌سازی Probe:** اسکریپت تست و اعتبارسنجی زنده صرافی‌ها به صورت مستقل در `scripts/probe_crypto_exchanges.py` آماده شده تا توسط مدیر روی سرور اجرا گردد.
