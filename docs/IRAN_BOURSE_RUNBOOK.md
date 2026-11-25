# راهنمای عملیات بورس ایران (Runbook)

برای وقتی که «بورس کار نمی‌کند» یا می‌خواهید وضعیت سرویس را بررسی کنید.
هر دستور با برچسب محیط اجرا مشخص شده است: **(server360)** روی سرور AlertG، **(aegkala)** روی هاست پل ایرانی، و **(PC)** فقط برای حالت پشتیبان قدیمی (پیوست الف).
کلیدها و توکن‌ها هرگز در دستورها، چت، لاگ یا گیت نوشته نمی‌شوند؛ روی سرور همیشه از فایل‌های `.env` خوانده می‌شوند.

## ۰. ساختار فعلی در پنج خط (معماری خودکار از ۱۴۰۵/۰۸/۳۰)

1. اپ موبایل فقط با سرور **server360** (پورت `8000`) حرف می‌زند؛ هرگز مستقیم با بورس یا پل.
2. سرور AlertG فقط وقتی کاربری لیست یا هشدار فعال بورس داشته باشد از گیت‌وی می‌پرسد (demand-driven).
3. گیت‌وی (`tsetmc-gateway v0.2.2`) به‌صورت **خودکار روی خود server360** روی `http://127.0.0.1:8099` اجرا می‌شود و با اسکریپت `~/AlertG1/AlertG/scripts/bourse/run_gateway.sh` (تنظیمات در `~/tsetmc-gateway/gateway.env`) و ۲ خط cron (`@reboot` و نگهبان هر دقیقه‌ای `* * * * *`) زنده نگه داشته می‌شود (نیازی به روشن بودن PC یا تونل SSH نیست).
4. گیت‌وی برای دسترسی به `cdn.tsetmc.com` با IP ایران، درخواست‌های خود را از طریق پل HTTPS روی هاست ایرانی (`aegkala.com/tse-forward.php` نسخه ۱.۱ با احراز هویت هدر و محدودیت IP سرور) ارسال می‌کند.
5. همهٔ قیمت‌ها به **ریال** هستند (بدون تبدیل به تومان). ساعت بازار: شنبه تا چهارشنبه، ۰۸:۳۰ تا ۱۹:۰۰ به وقت تهران.

## ۱. بررسی سریع (۳ دستور، به همین ترتیب)

**الف) وضعیت کلی بورس در AlertG** `(server360)`
```bash
cd ~/AlertG1/AlertG
A=$(grep '^ADMIN_KEY=' .env | cut -d= -f2-)
curl -s -H "X-Admin-Key: $A" "http://127.0.0.1:8000/api/iran-bourse/status?probe=true" | python3 -m json.tool
```
- `enabled` باید `true` باشد. اگر `false` است، `IRAN_BOURSE_ENABLED` در `.env` خاموش است.
- `poller.running` باید `true` و `poller.stale` باید `false` باشد.
- `poller.failures` اگر بزرگ و در حال رشد است ← گیت‌وی یا پل مشکل دارد (برو سراغ ب).
- بخش `gateway` (به‌خاطر `probe=true`) باید `status: "ok"` و `ready: true` نشان دهد؛ اگر `error` دارد، جدول بخش ۲ را ببین.

**ب) وضعیت گیت‌وی محلی روی server360** `(server360)`
```bash
~/AlertG1/AlertG/scripts/bourse/run_gateway.sh status
K=$(grep '^IRAN_BOURSE_GATEWAY_KEY=' ~/AlertG1/AlertG/.env | cut -d= -f2-)
curl -s -m 8 -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $K" http://127.0.0.1:8099/health
```
- اگر `run_gateway.sh status` گفت `status=stopped` ← با `~/AlertG1/AlertG/scripts/bourse/run_gateway.sh restart` بالا بیاور (بخش ۳).
- کد `200` ← گیت‌وی سالم و آماده است.
- کد `401` ← `IRAN_BOURSE_GATEWAY_KEY` در `~/AlertG1/AlertG/.env` با `TSETMC_API_KEY` در `~/tsetmc-gateway/gateway.env` یکی نیست.
- کد `503` ← گیت‌وی تازه بالا آمده و هنوز اولین Init را تمام نکرده (۱–۲ دقیقه صبر کن؛ اگر ماند برو سراغ پ).
- کد `000` یا خالی ← گیت‌وی روی پورت `8099` گوش نمی‌دهد.

**پ) بررسی سلامت پل ایرانی (aegkala) و لاگ گیت‌وی** `(server360)`
```bash
grep -c "blocked\|timed out" ~/tsetmc-gateway/gateway.log
tail -n 30 ~/tsetmc-gateway/gateway.log
```
و برای بررسی بدون چاپ کلید (وضعیت متغیرها در `~/tsetmc-gateway/gateway.env` با سطح دسترسی `600` ذخیره شده‌اند؛ کلیدها را هرگز چاپ نکن).

## ۲. علامت ← علت ← کار

| علامت / کد | علت محتمل | کار |
|---|---|---|
| لیست بورس در اپ خطا یا «در دسترس نیست» | گیت‌وی روی `server360` متوقف شده (`BourseConnectionError` / `BourseTimeout`) | بررسی ب؛ اجرای `~/AlertG1/AlertG/scripts/bourse/run_gateway.sh restart` |
| `gateway rejected the API key` (`401` / `BourseUnauthorized`) | ناهماهنگی `IRAN_BOURSE_GATEWAY_KEY` در AlertG و `TSETMC_API_KEY` در گیت‌وی | هر دو فایل `.env` و `gateway.env` را با کلید یکسان هماهنگ کن و هر دو سرویس را restart کن |
| `gateway has not loaded market data yet` (`503` / `BourseNotReady`) | گیت‌وی تازه استارت شده یا پل پاسخ نمی‌دهد | ۱–۲ دقیقه صبر کن؛ سپس `tail -n 40 ~/tsetmc-gateway/gateway.log` را ببین |
| خطای نسخه (`BourseBadVersion`) | نسخهٔ گیت‌وی در `IRAN_BOURSE_ALLOWED_VERSIONS` نیست | `IRAN_BOURSE_ALLOWED_VERSIONS` را در `.env` با نسخهٔ تأییدشده (`0.2.2`) هماهنگ کن |
| **کد `401` از پل (`aegkala`)** | توکن پل در `~/tsetmc-gateway/gateway.env` با فایل تنظیمات پل یکی نیست | توکن جدید را در هر دو طرف هماهنگ کن و گیت‌وی را restart کن |
| **کد `403` از پل (`aegkala`)** | IP خروجی `server360` در لیست مجاز (`ALLOW_IPS`) پل نیست یا فایروال هاست بلاک کرده | IP فعلی `server360` را بررسی و در تنظیمات پل تأیید کن |
| **کد `404` از پل (`aegkala`)** | فایل `tse-forward.php` حذف یا جابه‌جا شده یا مسیر URL اشتباه است | وجود `tse-forward.php` روی هاست `aegkala` و URL پل در `gateway.env` را بررسی کن |
| **کد `400` از پل (`aegkala`)** | پارامتر مسیر یا مقصد در لیست سفید پل نیست | نسخهٔ گیت‌وی و `tse-forward.php` v1.1 را بررسی کن |
| **کد `502` از پل (`aegkala`)** | خود `cdn.tsetmc.com` موقتاً خطا داده یا تایم‌اوت شده (در لاگ عادی است اگر تکرارش کم باشد) | اگر دائمی شد، بررسی کن آیا TSETMC در کل ایران از دسترس خارج شده یا نه |
| قیمت‌ها قدیمی با برچسب «بازار بسته» | خارج از ساعات معاملات یا روز تعطیل رسمی (طبیعی) | فقط ساعت و تقویم تهران را بررسی کن |
| قیمت‌ها قدیمی در زمان باز بودن بازار (`session: STALE`) | گیت‌وی به پل وصل نیست یا TSETMC دادهٔ جدید نمی‌دهد | بررسی ب و پ؛ لاگ گیت‌وی و حافظه (`ps -o pid,etime,rss -p $(cat ~/tsetmc-gateway/gateway.pid)`) |
| هشدار فعال نمی‌شود | بازار بسته، کاربر در `IRAN_BOURSE_ALLOWED_USER_IDS` نیست، یا داده `STALE` است | `status?probe=true` و `grep -a "\[IranBourse\]" ~/AlertG1/AlertG/server.log \| tail -30` را ببین |
| `seq went backwards` در لاگ AlertG | گیت‌وی restart شده است | کاملاً عادی است؛ سرور یک‌بار کل بازار را دوباره می‌گیرد |

## ۳. مدیریت گیت‌وی و نگهبان خودکار `(server360)`

```bash
# وضعیت، راه‌اندازی مجدد و توقف گیت‌وی
~/AlertG1/AlertG/scripts/bourse/run_gateway.sh status
~/AlertG1/AlertG/scripts/bourse/run_gateway.sh restart
~/AlertG1/AlertG/scripts/bourse/run_gateway.sh stop

# بررسی مصرف حافظه و زمان بالا بودن (باید RSS زیر ۲۰۰ مگابایت باشد)
ps -o pid,etime,rss -p $(cat ~/tsetmc-gateway/gateway.pid)

# بررسی دو خط cron نگهبان (@reboot و * * * * *)
crontab -l | grep run_gateway
```
- فقط **یک نمونه** از گیت‌وی باید در حال اجرا باشد (پورت `8099`).
- `run_gateway.sh` فایل `~/tsetmc-gateway/gateway.pid` و چرخش لاگ `gateway.log` (حداکثر ۵ مگابایت) را مدیریت می‌کند تا دو نمونه هم‌زمان بالا نیایند. خروجی cron در `~/tsetmc-gateway/cron.log` ثبت می‌شود.

## ۴. بررسی پس از هر رفع مشکل

1. دستور بخش `۱-ب` ← کد `200`.
2. دستور بخش `۱-الف` (`status?probe=true`) ← `poller.stale: false`، `gateway.ready: true` و `poller.failures` دیگر افزایش نمی‌یابد.
3. در اپ موبایل لیست بورس را باز کن؛ ردیف‌ها نمایش داده شوند و در ساعات بازار نوار «بازار بسته» دیده نشود.

## ۵. ممنوع‌ها

- کلید، توکن یا رمز را هرگز در چت، لاگ، اسکریپت‌های git-tracked یا کامیت قرار نده.
- گیت‌وی را هم‌زمان در دو نمونه اجرا نکن.
- به پل یا گیت‌وی در حلقهٔ سریع درخواست نزن (حداکثر چند درخواست دستی برای عیب‌یابی).
- قبل از `git pull origin main` مطمئن شو فایل‌های tracked (مثل `reports/soak_test_checkpoint.json`) تغییر ناخواسته ندارند.

## ۶. به‌روزرسانی سرور AlertG `(server360)`

```bash
cd ~/AlertG1/AlertG
git status --short
git pull origin main
./run_server.sh restart
```
اگر فقط فایل گزارش خودکار `reports/soak_test_checkpoint.json` تغییر کرده بود و جلوی `git pull` را گرفت:
```bash
git checkout -- reports/soak_test_checkpoint.json
git pull origin main
./run_server.sh restart
```

---

## پیوست الف: حالت پشتیبان قدیمی (PC ایرانی + تونل SSH معکوس)

از تاریخ `2026-11-20` گیت‌وی به‌طور کامل به `server360` + پل `aegkala` منتقل شد و دیگر به PC ایرانی نیازی نیست.
تنها در صورتی که پل ایرانی برای مدت طولانی از دسترس خارج شود و بخواهید موقتاً به PC ایرانی برگردید:

1. روی `server360` گیت‌وی محلی را متوقف کن تا پورت `8099` آزاد شود: `~/AlertG1/AlertG/scripts/bourse/run_gateway.sh stop` (و دو خط cron مربوط به `run_gateway.sh` را موقتاً کامنت کن).
2. روی PC ایرانی (با **VPN خاموش**، فقط یک نمونه، پورت `8099`) گیت‌وی را اجرا کن و تونل SSH معکوس را روی پورت `8099` سرور برقرار کن.
3. روی `server360` با `ss -ltn | grep 8099` و دستور بخش `۱-ب` تأیید کن پاسخ `200` برمی‌گردد (تنظیم `IRAN_BOURSE_GATEWAY_URL=http://127.0.0.1:8099` بدون تغییر باقی می‌ماند).
