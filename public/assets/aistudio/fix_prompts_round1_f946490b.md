# پرامپت‌های اصلاحی دور اول (بعد از بازبینی 24 اکتبر، تا کامیت `c7f8df7`)

قوانین مشترک (همان بلوک بالای فایل قبلی) بالای هر پرامپت اضافه شود.
ترتیب اجرا: FIX-1 ← FIX-2 ← FIX-3 ← FIX-4a ← FIX-4b ← FIX-5a ← FIX-5b. هر کدام یک کامیت، بعد push و STOP.
قبل از FIX-1: تمام کار جدید (از جمله 3A-2) متوقف شود تا این دور تمام شود.

---

## FIX-1: پاک‌سازی مخزن (فایل‌هایی که نباید عوض می‌شدند)
فایل‌ها: `pubspec.lock`، `vite.config.ts`، `public/assets/aistudio/prompts_full_list_fee5328f.md`.

در کامیت `45770ad` سه تغییر بی‌ربط وارد شد:
۱. `pubspec.lock` به‌طور کامل حذف شد (۱۰۰۱ خط). این قفل در کامیت `5dbc94e` عمداً اضافه شده بود تا بیلدها تکرارپذیر باشند.
۲. `vite.config.ts` (فایل وب، نه اپ) ۴۱۹ خط تغییر کرد و شامل قیمت‌های ثابت ساختگی برای صرافی‌هاست.
۳. فایل `prompts_full_list_fee5328f.md` به `public/` اضافه شد (پوشه‌ی عمومی).

کار:
- `git checkout 61ee008 -- pubspec.lock vite.config.ts` و `git rm public/assets/aistudio/prompts_full_list_fee5328f.md`.
- بعد از آن `flutter pub get` را اجرا کن و اگر `pubspec.lock` تغییر کرد، توضیح بده چرا (نباید تغییر کند مگر pubspec.yaml عوض شده باشد).
معیار پذیرش: `git diff 61ee008 HEAD --stat -- pubspec.lock vite.config.ts` خالی است.
کامیت: `chore: restore pubspec.lock and revert unrelated vite/prompt files`

---

## FIX-2: برگرداندن fallback متن ساده در Telegram (رگرسیون)
فایل‌ها: `app/notifier/telegram.py` + `tests/test_telegram_retry.py`.

مشکل: در `send_telegram_alert` قدیمی، اگر ارسال با `parse_mode=HTML` شکست می‌خورد (مثلاً متن شامل `<` یا `&`)، یک بار دیگر بدون HTML و با تگ‌های حذف‌شده ارسال می‌شد. نسخه‌ی جدید برای هر ۴xx غیر از ۴۲۹ فقط `False` برمی‌گرداند؛ یعنی آلارمی که متنش HTML را می‌شکند دیگر هیچ‌وقت به Telegram نمی‌رسد.

کار:
۱. وقتی پاسخ `400` است و `parse_mode` هنوز HTML بود: یک بار با `parse_mode=None` و متن بدون تگ (`re.sub(r'<[^>]+>', '', message)`) دوباره بفرست.
۲. بقیه‌ی منطق (۴۲۹ و ۵xx و timeout) بدون تغییر بماند.
تست (حداکثر ۲): ۴۰۰ و بعد ۲۰۰ برای متن ساده → `True`؛ ۴۰۰ برای متن ساده هم → `False` (فقط یک بار تلاش دوم).
کامیت: `fix(telegram): restore plain-text retry on HTML parse failure`

---

## FIX-3: dedup دوکلیدی در کلاینت (رگرسیون: اعلان دوبل)
فایل‌ها: `lib/features/notifications/services/notification_service.dart` + `test/alert_dedup_test.dart`.

مشکل: وقتی پوش FCM `delivery_id` دارد، کلید dedup فقط `delivery_id` می‌شود. اسکجولر محلی برای همان آلارم با کلید `rule.uuid` ثبت می‌کند. این دو کلید یکی نیستند، پس اگر هم گوشی و هم سرور همان آلارم را در چند ثانیه ببینند، **دو بنر و دو بار صدا/TTS** می‌آید. قبل از 2A-4c این حالت با کلید `alert_id` در پنجره‌ی ۲۰ثانیه جلوگیری می‌شد.

کار: در `enqueueCriticalAlert` وقتی `dedupeKey` (شناسه‌ی تحویل) داده شده:
۱. ابتدا کلید `dedupeKey` را با پنجره‌ی ده‌دقیقه‌ای claim کن (همان رفتار فعلی).
۲. سپس اگر `payload` (alert_id) غیرخالی است، کلید `payload` را با پنجره‌ی ۲۰ثانیه claim کن.
۳. اگر هر کدام شکست خورد: نتیجه `duplicate` (claim اول را نگه دار، رها نکن).
۴. اگر نمایش بنر شکست خورد: هر دو claim رها شوند.
تست (حداکثر ۳): آلارم محلی با کلید alert_id، بعد FCM با همان alert_id و delivery_id جدید در ۲۰ ثانیه → `duplicate`؛ ارسال دوباره با همان delivery_id بعد از ۳۰ ثانیه → `duplicate`؛ delivery_id جدید برای همان alert_id بعد از ۳۰ ثانیه → `shown`.
کامیت: `fix(notif): dedupe by both delivery_id and alert_id`

---

## FIX-4a: `start_utc` محاسبه‌ی پویا (یادآوری ۳۰ دقیقه‌ای فقط تا اولین وقوع بعد از بوت کار می‌کرد)
فایل‌ها: `app/engine/market_events.py` + `tests/test_market_events_advance_reminder.py`.

مشکل: `start_utc` رویدادهای دوره‌ای هنگام import یک بار محاسبه و در دیکشنری ثابت ذخیره می‌شود. سرور یک هفته که بالا بماند، مقدار در گذشته می‌ماند و یادآوری دیگر هرگز نمی‌آید. (من با شبیه‌سازی ۸ روز بعد دیدم: زمان باقی‌مانده منفی ۸۶ ساعت می‌شود.) `get_market_events` هم چون کلید از قبل هست دوباره محاسبه نمی‌کند.

کار:
۱. `start_utc` را از `CURATED_HIGH_IMPACT_CATALOG` حذف کن (یا آن را فقط کش اولیه بدان).
۲. در `check_and_dispatch_30m_advance_reminders` و `get_market_events` برای هر رویداد `start_utc` را **در لحظه‌ی بررسی** با `parse_event_start_utc(ev["time_utc"], now)` بساز؛ برای رویدادهایی که `time_utc` قابل‌تجزیه نیست `None` و کنار گذاشته می‌شوند.
۳. کلید dedup همان `...:start_utc` بماند تا یک وقوع دقیقاً یک بار یادآوری بگیرد.
تست (حداکثر ۳، با زمان mock): یک هفته و یک روز بعد از import، رویداد دوره‌ای هنوز در پنجره‌ی ۳۰ دقیقه‌ای پیدا می‌شود؛ هر وقوع فقط یک بار؛ رویداد نامعتبر هرگز.
کامیت: `fix(events): compute start_utc at check time for recurring events`

## FIX-4b: اجرای دقیقه‌ای بررسی یادآورها
فایل‌ها: `server.py` + یک تست.

مشکل: `check_and_dispatch_30m_advance_reminders` فقط از `refresh_market_events` صدا زده می‌شود که هر ۶ ساعت اجرا می‌شود. پنجره‌ی یادآوری ۱۲۰ ثانیه است، یعنی احتمال اجرای درست حدود ۰٫۵۶٪. عملاً هیچ‌وقت نمی‌آید.

کار:
۱. در `setup_scheduler_jobs` یک job جدید با فاصله‌ی ۳۰ ثانیه برای `check_and_dispatch_30m_advance_reminders` ثبت کن (`max_instances=1`، `coalesce=True`، یک `id` یکتا).
۲. فراخوانی از داخل `check_and_dispatch_event_notifications` برداشته شود تا دوبار اجرا نشود.
تست (حداکثر ۲): job ثبت شده و فاصله‌اش ≤ ۶۰ ثانیه است؛ فراخوانی از مسیر ۶ساعته حذف شده.
کامیت: `fix(events): run advance reminder check every 30 seconds`

---

## FIX-5a: پوش رویداد برای کلاینت‌های قدیمی و کاربران بدون opt-in
فایل‌ها: `app/engine/market_events.py` + تست.

مشکل‌ها:
۱. `EventAlertStub.ack_supported = True` برای همه ثابت است. اپ‌های قدیمی ack نمی‌فرستند، پس هر رویداد دو بار دوباره ارسال می‌شود و بعد پیام «پوش تأیید نشد» به Telegram می‌رود.
۲. شرط `prof.get('events_fcm_enabled', True)` پیش‌فرض True است؛ کاربری که فقط Telegram را فعال کرده هم پوش می‌گیرد.

کار:
۱. `ack_supported` استاب را از آلارم‌های همان کاربر در `ALERTS_DB` بخوان (اگر هر آلارمی با `ack_supported=True` داشت True، وگرنه False).
۲. FCM فقط وقتی برود که `events_notification_enabled` برابر True باشد؛ `events_fcm_enabled` را حذف کن یا پیش‌فرضش را False بگذار.
تست (حداکثر ۳): کاربر بدون آلارم ack_supported → استاب False؛ کاربر با آلارم ack_supported → True؛ کاربر فقط Telegram → هیچ پوشی.
کامیت: `fix(events): derive ack_supported per user and require opt-in for push`

## FIX-5b: ذخیره‌ی پایدار `USER_DISPATCHED_EVENTS`
فایل‌ها: `app/engine/market_events.py` + تست.

مشکل: اینکه کدام رویداد قبلاً به کدام کاربر فرستاده شده فقط در حافظه است. بعد از هر restart همه‌ی کاربران opt-in شده دوباره همه‌ی رویدادها را هم در Telegram و هم (حالا) با پوش و صدا می‌گیرند.

کار: همان فایل `market_events_state.json` (اتمی) را گسترش بده تا `dispatched_events` (کلید: `user_id:event_id:start_utc`، مقدار: زمان ارسال) هم ذخیره و هنگام شروع بارگذاری شود؛ ورودی‌های قدیمی‌تر از ۷ روز حذف شوند؛ رفتار فایل خراب مثل قبل (`.bad`).
تست (حداکثر ۲): ذخیره/بارگذاری؛ بعد از بارگذاری دوباره‌ارسال نمی‌شود.
کامیت: `fix(events): persist per-user dispatched events across restarts`
