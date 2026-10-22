# فهرست کامل پرامپت‌های باقی‌مانده (Phase 2 تا Phase 5)

مخزن: Mehran-Amp/AlertG — آخرین کامیت بازبینی‌شده: `2c1bda7` (۲۴۵ تست سبز با `pytest tests`).
وضعیت: 1A تا 1C، 2A-1 و 2A-1b قبول شده‌اند.

## قوانین مشترک (بالای هر پرامپت اضافه شود)

```
قوانین ثابت این پروژه:
1. فقط فایل‌هایی را که در پرامپت نام برده شده تغییر بده. هر چیز دیگر ممنوع است.
2. یک دغدغه، حداکثر ۳ تست، یک کامیت، بعد push و STOP.
3. بعد از STOP هیچ کاری نکن و منتظر بازبینی بمان.
4. چیزی خارج از دستور عوض نکردی (مثلاً timeout، نام‌ها، فرمت). اگر لازم شد، در پیام خبر بده، ننویس.
5. سرور: `pytest tests` (نه pytest خالی) باید کاملاً سبز باشد. کلاینت: `flutter test` باید سبز باشد.
6. فایل داده، `.pytest_cache`، `__pycache__` و کلیدها را commit نکن.
7. در پایان فقط گزارش کن: فایل‌های تغییرکرده، تعداد تست، نتیجه اجرا، شناسه کامیت.
8. اگر چیزی مبهم بود یا با کد فعلی نمی‌خواند، متوقف شو و بپرس؛ حدس نزن.
```

ترتیب پیشنهادی کل کار:
Phase 2A (ack و escalation) → 2B (رویدادها) → 2C (Telegram و ادمین) → 2D (race اسکجولر) → Phase 3 (سلامت دستگاه) → Phase 4 (WebSocket) → Phase 5 (آزمون آشوب و گیت انتشار).

**اصل مهم rollout:** سرور فقط وقتی ack انتظار دارد که کلاینت خودش اعلام کند `ack_supported=true`. پس نسخه‌های قدیمی اپ هرگز پوش تکراری یا Telegram اضافه نمی‌گیرند. کلاینت این پرچم را **آخر از همه** روشن می‌کند (2A-4d).

---

# PHASE 2A — Delivery Ack و Escalation

## 2A-2: endpoint ack (سرور)
فایل‌ها: `app/routes/deliveries.py` (جدید)، `server.py` (فقط ثبت router)، یک فایل تست جدید.

۱. `POST /api/deliveries/{delivery_id}/ack` با بدنه اختیاری `{"shown": true, "received_at_ms": 123}`.
۲. احراز هویت دقیقاً مثل `/api/alerts/sync` (`API_DEP` از `app/security.py`).
۳. `journal.record_acked(delivery_id)` را صدا بزن. پاسخ همیشه ۲۰۰ با `{"status":"acked"}` یا `{"status":"unknown"}` است (ack تکراری بی‌خطر).
۴. فقط در پاسخ `acked` اولین‌بار، `METRICS["fcm_acked"]` یک واحد زیاد شود. بدون ack دوباره شمرده نشود.
تست (حداکثر ۳): ack معتبر وضعیت ژورنال را `acked` می‌کند؛ id ناشناخته ۲۰۰ با `unknown`؛ بدون کلید API رد می‌شود (مثل بقیه endpointها).
کامیت: `feat(delivery): add ack endpoint`

## 2A-2b: پرچم `ack_supported` روی آلارم (سرور)
فایل‌ها: `app/models.py`، `app/routes/alerts.py` + تست.

۱. فیلد `ack_supported: bool = False` به مدل آلارم اضافه کن.
۲. در endpoint sync، اگر بدنه‌ی sync فیلد سطح بالای `ack_supported` داشت، آن را روی همه‌ی آلارم‌های آن sync بگذار؛ اگر نبود، False.
۳. این فیلد باید در ذخیره/بارگذاری آلارم‌ها (فایل JSON) حفظ شود و منطق `_trigger_signature` و Edge-Guard را تغییر ندهد.
تست (حداکثر ۳): sync با پرچم true → آلارم‌ها `ack_supported=True`؛ بدون پرچم → False؛ ذخیره و بارگذاری فایل پرچم را نگه می‌دارد.
کامیت: `feat(sync): accept ack_supported flag per synced alert`

## 2A-3a: نگه‌داشتن entry تا ack (سرور)
فایل‌ها: `app/notifier/outbox.py`، `app/notifier/journal.py` + تست.

۱. بعد از موفقیت FCM، اگر آلارمِ این entry در `storage.ALERTS_DB` پیدا شود و `ack_supported` داشته باشد، entry را حذف نکن: `entry["phase"]="awaiting_ack"`، `entry["ack_due_at"]=now+ACK_WAIT_SECONDS` (پیش‌فرض ۴۵، از env `ACK_WAIT_SECONDS`)، `entry["resend_count"]=0`، و `next_attempt_at=ack_due_at`. در غیر این صورت رفتار قبلی (حذف).
۲. تابع `on_delivery_acked(delivery_id)` در outbox: entry را حذف و ذخیره کند. اگر در حال ارسال همان entry است، بعد از برگشتن نباید دوباره اضافه شود.
۳. وقتی `ack_due_at` رسید (فعلاً بدون ارسال دوباره): entry حذف شود، `journal.mark_unacked(delivery_id)` و `METRICS["fcm_unacked"]` یک واحد زیاد شود. (ارسال دوباره در 2A-3b می‌آید.)
۴. worker نباید entryهای `awaiting_ack` را قبل از موعدشان بردارد.
تست (حداکثر ۳): آلارم `ack_supported` → entry بعد از موفقیت می‌ماند؛ آلارم بدون پرچم → حذف می‌شود؛ `on_delivery_acked` entry را حذف می‌کند.
کامیت: `feat(outbox): keep entry until ack for ack-capable alerts`

## 2A-3b: ارسال دوباره بعد از موعد ack (سرور)
فایل‌ها: `app/notifier/outbox.py` + تست.

۱. فاصله‌ها: `ACK_WAITS = (45, 90, 180)` ثانیه (قابل تنظیم با env).
۲. وقتی `ack_due_at` رسید و `resend_count < 2`: همان `delivery_id` را دوباره با FCM بفرست (همان payload)، `resend_count += 1` و موعد بعدی را از `ACK_WAITS` بگذار. شکست موقت FCM با همان منطق backoff قبلی مدیریت شود.
۳. وقتی `resend_count == 2` و موعد سوم هم گذشت: مثل 2A-3a به `unacked` ببر (Telegram در 2A-3e).
۴. اگر ack در حین یک ارسال دوباره برسد، entry دوباره زنده نشود.
تست (حداکثر ۳): بدون ack، بعد از موعد اول دقیقاً یک ارسال دوباره با همان `delivery_id`؛ بعد از ack دیگر ارسالی نمی‌شود؛ بعد از دو ارسال دوباره و موعد سوم، `unacked`.
(زمان را با mock کن؛ تست نباید واقعاً منتظر بماند.)
کامیت: `feat(outbox): resend until acked with bounded schedule`

## 2A-3c: ذخیره‌ی `fallback_chat_id` روی entry (سرور)
فایل: `app/notifier/outbox.py` + تست.
۱. `enqueue_alert_push(alert, title, body, data_payload, fallback_chat_id=None)`؛ مقدار روی entry ذخیره شود. بدون این آرگومان رفتار فعلی.
تست (حداکثر ۲): با و بدون آرگومان.
کامیت: `feat(outbox): store optional telegram fallback chat id`

## 2A-3d: فراخواننده‌ها chat id را بدهند (سرور)
فایل‌ها: `app/engine/checker.py`، `app/engine/sync.py` (فقط سه نقطه‌ی فراخوانی `enqueue_alert_push`: checker.py خط‌های حدود ۳۸۱ و ۵۸۷، sync.py حدود ۹۸۵).
۱. `effective_chat_id` را (همان که برای Telegram استفاده می‌شود) به‌صورت `fallback_chat_id=` پاس بده.
۲. هیچ منطق دیگری را عوض نکن.
تست (حداکثر ۱): مسیر ساده‌ای که ثابت می‌کند entry ساخته‌شده `fallback_chat_id` درست دارد.
کامیت: `feat(checker): pass telegram chat id to outbox for fallback`

## 2A-3e: fallback به Telegram بعد از شکست ack (سرور)
فایل: `app/notifier/outbox.py` + تست.
۱. وقتی entry به `unacked` می‌رسد و `fallback_chat_id` دارد: یک پیام Telegram بفرست (از `send_telegram_alert` و کلاینت `state.http_client`) با همان متن، به‌اضافه‌ی یک خط «(تأیید دریافت پوش نرسید)».
۲. فقط یک بار برای هر `delivery_id`؛ در ژورنال علامت `telegram_fallback_sent` گذاشته شود.
۳. شکست Telegram نباید exception به worker برساند؛ فقط لاگ و `METRICS["telegram_fallback_failed"]`.
تست (حداکثر ۳): با `fallback_chat_id` یک ارسال؛ بدون آن هیچ ارسال؛ فراخوانی دوباره ارسال تکراری نمی‌سازد.
کامیت: `feat(outbox): telegram fallback when push is never acked`

## 2A-4a: سرویس ack در کلاینت (Dart)
فایل‌ها: `lib/core/services/delivery_ack_service.dart` (جدید) + `test/delivery_ack_service_test.dart`.
نکته: دو isolate (FCM و سرویس) می‌نویسند؛ برای جلوگیری از lost update، **هر ack یک فایل جدا** است.
۱. `DeliveryAckService.enqueueAck(String deliveryId, {bool shown = true})`: فایل `acks/<deliveryId>.json` را به‌صورت اتمی (tmp + rename) در پوشه‌ی documents بساز. اگر وجود داشت، دست نزن.
۲. `flush()`: پوشه‌ی `acks/` را بخوان؛ برای هر فایل `POST /api/deliveries/{id}/ack` (با `ServerAlertService.post` یا همان هدرها/کلید API)؛ در پاسخ ۲۰۰ فایل را پاک کن؛ در شکست نگه دار. single-flight باشد (دو flush هم‌زمان در یک isolate یکی را اجرا کند).
۳. فایل‌های قدیمی‌تر از ۲۴ ساعت حذف شوند.
۴. client و مسیر پوشه قابل تزریق برای تست باشد (`@visibleForTesting`).
تست (حداکثر ۳): enqueue فایل می‌سازد؛ flush موفق فایل را پاک می‌کند؛ flush ناموفق فایل را نگه می‌دارد.
کامیت: `feat(ack): add DeliveryAckService with per-ack files`

## 2A-4b: ارسال ack بعد از نمایش (Dart)
فایل: `lib/core/services/fcm_notification_service.dart`.
۱. در `_handleIncomingAlert`، اگر `d['delivery_id']` غیرخالی بود و `enqueueCriticalAlert` مقدار `shown` یا `duplicate` برگرداند: `enqueueAck(deliveryId)` و بعد `flush()` با timeout پنج‌ثانیه‌ای (اگر در isolate پس‌زمینه است، await شود تا پروسه زودتر کشته نشود).
۲. اگر `failed` برگشت، ack نفرست.
۳. هر استثنا فقط لاگ شود؛ هرگز handler را نشکند.
تست خودکار: لازم نیست؛ معیار دستی: بعد از `/api/test/push`، ژورنال سرور وضعیت `acked` را نشان بدهد (فقط بعد از 2A-2 و وقتی پوش `delivery_id` دارد).
کامیت: `feat(fcm): ack delivery after banner shown`

## 2A-4c: dedup با `delivery_id` (Dart)
فایل‌ها: `lib/features/notifications/services/notification_service.dart`، `lib/core/services/fcm_notification_service.dart` + تست.
مشکل: dedup فعلی ۲۰ ثانیه است و با کلید `alert_id`؛ ارسال دوباره‌ی سرور بعد از ۴۵ ثانیه صدا/TTS را دوباره پخش می‌کند.
۱. به `enqueueCriticalAlert` پارامتر اختیاری `dedupeKey` اضافه کن؛ اگر داده شد جای `payload` را می‌گیرد.
۲. `_handleIncomingAlert` اگر `delivery_id` داشت آن را به‌عنوان `dedupeKey` بدهد.
۳. برای کلیدهای `delivery_id` پنجره‌ی dedup ده دقیقه باشد (برای کلیدهای قبلی ۲۰ ثانیه بماند).
تست (حداکثر ۲): `AlertDedup.claim` برای یک کلید در پنجره دوم بار false می‌دهد؛ بعد از `release` دوباره true.
کامیت: `fix(notif): dedupe by delivery_id with a 10 minute window`

## 2A-4d: روشن‌کردن پرچم (Dart) — آخرین مرحله‌ی 2A کلاینت
فایل‌ها: `lib/core/services/server_alert_service.dart` + تست.
۱. در payload‌ی sync، فیلد سطح بالای `'ack_supported': true` اضافه شود.
تست (حداکثر ۱): با `httpClientForTesting` بدنه‌ی درخواست sync شامل `ack_supported: true` باشد.
کامیت: `feat(sync): announce ack_supported to the server`

## 2A-4e: flush دوره‌ای و هنگام resume (Dart)
فایل‌ها: `lib/features/notifications/background/background_service_manager.dart`، `lib/app/navigation/app_shell.dart`.
۱. در تایمر ۶۰ثانیه‌ای service isolate که از قبل هست، `DeliveryAckService.flush()` را هم صدا بزن (جدا از شرط flag sync).
۲. در resume اپ هم `flush()` صدا زده شود.
۳. شکست‌ها با `ServiceLogger` ثبت شوند.
کامیت: `feat(ack): flush pending acks periodically and on resume`

## 2A-5: متریک `ack_latency_ms` (سرور)
فایل: `app/notifier/journal.py` + `app/routes/admin.py` (یا جایی که `/api/status` است) + تست.
۱. در `record_acked`، فاصله‌ی `acked_at - sent_at` را به میلی‌ثانیه محاسبه و در یک پنجره‌ی ۵۰۰تایی نگه دار.
۲. در پاسخ `/api/status` میانگین، p95 و تعداد `unacked` را بگذار.
تست (حداکثر ۲).
کامیت: `feat(metrics): expose ack latency and unacked count`

## 2A-6: آزمون پذیرش روی دستگاه (دستی؛ نتیجه را با مدرک بفرست)
برای هر ردیف: اسکرین‌شات، ۱۰ خط logcat، و وضعیت ژورنال سرور.

| # | سناریو | قبول اگر |
|---|---|---|
| 1 | اپ باز، پوش آزمایشی | ژورنال `acked` در کمتر از ۵ ثانیه |
| 2 | اپ از recents پاک، صفحه قفل | بنر+صدا+TTS؛ ژورنال `acked` |
| 3 | حالت هواپیما ۲ دقیقه، بعد روشن | بنر دقیقاً یک بار (بدون صدای تکراری)؛ ژورنال `acked` |
| 4 | اپ حذف‌شده یا توکن مرده | بعد از ~۵ دقیقه ژورنال `unacked` و پیام Telegram رسیده |
| 5 | سرور restart وسط انتظار ack | بعد از بالا آمدن، منطق ادامه پیدا کند و پوش گم نشود |

---

# PHASE 2B — رویدادها (Market Events)

## 2B-1: زمان واقعی رویداد
فایل‌ها: `app/engine/calendar.py` (و در صورت نیاز `app/engine/market_events.py`) + تست.
قدم صفر: ابتدا بخوان که هر رویداد زمانش را چگونه نگه می‌دارد (رشته‌ی نمایشی؟). اگر زمان منبع به‌صورت قابل‌اعتماد به UTC تبدیل نمی‌شود، **متوقف شو و گزارش بده**؛ حدس نزن.
۱. به هر رویداد فیلد `start_utc` (epoch ثانیه، عدد صحیح) اضافه کن، فیلدهای رشته‌ای فعلی دست‌نخورده بمانند.
۲. اگر تبدیل ممکن نبود، `start_utc=None` و رویداد از یادآوری‌ها کنار گذاشته شود، نه این‌که حدس زده شود.
تست (حداکثر ۳): تبدیل منطقه‌ی زمانی درست؛ رویداد بدون زمان معتبر `None`؛ فیلدهای قبلی تغییر نکرده.
کامیت: `feat(events): add start_utc epoch to events`

## 2B-2: ذخیره‌ی پایدار وضعیت رویدادها
فایل: `app/engine/market_events.py` + تست.
۱. مجموعه‌ی «یادآوری‌های فرستاده‌شده» (کلید: `event_id:chat_id:kind`) و «ثبت‌نام‌های یادآوری کاربر» روی `market_events_state.json` با نوشتن اتمی ذخیره و هنگام شروع بارگذاری شود. ورودی‌های قدیمی‌تر از ۷ روز پاک شوند. فایل خراب → `.bad`.
۲. رفتار دیگری عوض نشود.
تست (حداکثر ۲): ذخیره و بارگذاری؛ فایل خراب بدون crash.
کامیت: `feat(events): persist reminder state across restarts`

## 2B-3: یادآوری ۳۰ دقیقه قبل از رویداد
فایل: `app/engine/market_events.py` + تست.
۱. با `start_utc`، برای هر کاربر ثبت‌نام‌شده، در بازه‌ی T-30min (با تلورانس یک دقیقه) دقیقاً یک بار یادآوری (`is_advance_notice=True`) بفرست.
۲. با وضعیت 2B-2 تکرار پس از restart جلوگیری شود.
۳. اگر رویداد لغو شود یا زمانش عوض شود، یادآوری قبلی نباید بعد از تغییر دوباره بیاید (کلید شامل `start_utc`).
تست (حداکثر ۳): ارسال در بازه؛ ارسال تکراری ندارد؛ بعد از restart (بارگذاری وضعیت) دوباره نمی‌فرستد. (زمان را mock کن.)
کامیت: `feat(events): send 30-minute advance reminder once`

## 2B-4: رویداد از مسیر FCM هم برسد
فایل‌ها: `app/engine/market_events.py` + تست.
قدم صفر: بررسی کن توکن FCM هر کاربر کجا ذخیره است. اگر برای کاربر مشخص نگاشتی بین چت/کاربر و توکن نیست، **متوقف شو و گزارش بده**.
۱. اگر کاربر `events_notification_enabled` دارد، رویداد و یادآوری از `enqueue_alert_push` (با همان `delivery_id` و ack) هم برود، نه فقط Telegram.
تست (حداکثر ۲).
کامیت: `feat(events): deliver event notifications through the outbox`

---

# PHASE 2C — استحکام Telegram و هشدار ادمین

## 2C-1: retry برای Telegram
فایل: `app/notifier/telegram.py` + تست.
۱. در `send_telegram_alert`: پاسخ ۴۲۹ → منتظر `retry_after` (حداکثر ۳۰ ثانیه) و دوباره؛ ۵xx یا timeout → تا ۳ تلاش با backoff (1، 3، 7 ثانیه). ۴xx دیگر (غیر از ۴۲۹) بدون retry.
۲. مقدار بازگشتی `True/False` باشد (اگر قبلاً چیز دیگری برمی‌گرداند، سازگار نگه دار).
تست (حداکثر ۳) با client جعلی: ۴۲۹ سپس ۲۰۰ موفق؛ ۵xx سه بار سپس False؛ ۴۰۰ بدون retry.
کامیت: `feat(telegram): retry on 429 and transient errors`

## 2C-2: کد خطای مجوز FCM
فایل‌ها: `app/notifier/fcm.py`، `app/notifier/outbox.py` + تست.
۱. `PermissionDeniedError`/`ThirdPartyAuthError` (و معادل متن «PERMISSION_DENIED») کد `FCM_AUTH_ERROR` برگردانند.
۲. outbox آن‌ها را مثل خطای موقت retry کند ولی `METRICS["fcm_auth_error"]` را زیاد کند و `blocked_token` نگذارد (مشکل سرور است نه توکن).
تست (حداکثر ۲).
کامیت: `feat(fcm): classify auth errors separately from token errors`

## 2C-3: هشدار به ادمین
فایل: `app/notifier/outbox.py` + تست.
۱. اگر ۳ خطای `FCM_AUTH_ERROR` پشت‌سرهم رخ داد، با `notify_admin_telegram` یک پیام بفرست؛ حداکثر یک بار در ۳۰ دقیقه. با اولین موفقیت شمارنده صفر شود.
تست (حداکثر ۲): سه خطا → یک پیام؛ خطای چهارم در ۳۰ دقیقه پیام تازه نمی‌سازد.
کامیت: `feat(outbox): alert admin on repeated FCM auth errors`

---

# PHASE 2D — race اسکجولر (Dart)

## 2D-1a: `updateRule` اتمی در repository
فایل‌ها: `lib/features/alert_engine/repositories/json_alert_rule_repository.dart` + تست.
۱. متد `Future<bool> updateRule(String uuid, AlertRule Function(AlertRule current) mutate, {bool syncToServer = false})`: زیر قفل فایل، دیسک را دوباره بخوان، قانون را با uuid پیدا کن، `mutate` را روی نسخه‌ی تازه اجرا کن، ذخیره کن. اگر قانون حذف شده بود، false و بدون ذخیره.
تست (حداکثر ۳): mutate روی نسخه‌ی تازه اجرا می‌شود (ویرایش هم‌زمان کاربر از بین نمی‌رود)؛ قانون حذف‌شده false؛ حالت `_loadFailed` ذخیره نمی‌کند.
کامیت: `feat(repo): atomic updateRule that re-reads under lock`

## 2D-1b: اسکجولر از `updateRule` استفاده کند
فایل‌ها: `lib/features/alert_engine/scheduler/scheduler_service.dart` + تست.
۱. هر `saveRule` فعلی با نسخه‌ی قدیمی را با `updateRule` عوض کن؛ فقط فیلدهای متعلق به اسکجولر (`lastCheckedAt`، `lastCheckedPrice`، `previousPrice`، `isActive`، `isTriggered`، `cooldownUntil`، `lastTriggeredAt`، `triggerCount`، `basePrice`، `baseVolume`) روی نسخه‌ی تازه اعمال شوند.
تست (حداکثر ۲): ویرایش `targetPrice` کاربر در حین ارزیابی از بین نمی‌رود؛ قانون حذف‌شده دوباره ساخته نمی‌شود.
کامیت: `fix(scheduler): commit via updateRule to avoid overwriting user edits`

---

# PHASE 3 — سلامت دستگاه

## 3A-1: heartbeat (سرور)
فایل‌ها: `app/routes/devices.py` (جدید)، `server.py` (ثبت router) + تست.
۱. `POST /api/device/heartbeat` با `API_DEP`. بدنه: `{user_id, fcm_token_tail (۶ کاراکتر آخر)، app_version, notifications_enabled, battery_unrestricted, fgs_running, ts_ms}`.
۲. آخرین heartbeat هر کاربر/دستگاه روی `device_health.json` (اتمی) نگه داشته شود.
۳. `GET /api/device/health/{user_id}` (با `API_DEP`) آخرین وضعیت را برگرداند.
تست (حداکثر ۳).
کامیت: `feat(health): device heartbeat endpoint`

## 3A-2: ارسال heartbeat (Dart)
فایل‌ها: `lib/core/services/device_health_service.dart` (جدید)، `lib/features/notifications/background/background_service_manager.dart`.
۱. هر ۱۵ دقیقه از service isolate (و یک بار هنگام شروع) heartbeat بفرست. وضعیت‌ها را (مجوز اعلان، مستثنی‌بودن از بهینه‌سازی باتری، زنده‌بودن سرویس) از APIهای موجود بگیر؛ اگر چیزی در دسترس نیست `null` بفرست، حدس نزن.
۲. شکست‌ها فقط با `ServiceLogger` ثبت شوند.
کامیت: `feat(health): send heartbeat from service isolate`

## 3A-3: تشخیص دستگاه ساکت و escalation سریع (سرور)
فایل: `app/notifier/outbox.py` + تست.
۱. هنگام enqueue، اگر آخرین heartbeat کاربر بیش از ۴۵ دقیقه قدیمی است (و کاربر قبلاً heartbeat داشته)، مهلت‌های ack به `(15, 30)` ثانیه کوتاه شود و Telegram زودتر برود.
تست (حداکثر ۲).
کامیت: `feat(outbox): shorten ack waits for silent devices`

## 3B-1: تشخیص محدودیت Foreground Service در اندروید ۱۵ (Dart/Android، فقط تشخیص)
۱. فقط لاگ: وقتی سیستم‌عامل سرویس `dataSync` را به timeout می‌رساند، چه اتفاقی می‌افتد؟ در `ServiceLogger` شروع/پایان سرویس و دلیل توقف (اگر callback ای وجود دارد) ثبت شود. بدون تغییر رفتار.
۲. گزارش بده: روی اندروید ۱۵ سرویس بعد از چند ساعت می‌میرد؟ (یک گوشی با اندروید ۱۵، ۱۲ ساعت.)
کامیت: `chore(diag): log foreground service lifecycle`

## 3B-2: صفحه‌ی «سلامت اعلان‌ها» (Dart)
فایل‌ها: صفحه‌ی جدید در `lib/features/settings/pages/` + یک ورودی در تنظیمات.
۱. نمایش: مجوز اعلان، بهینه‌سازی باتری، autostart (دکمه‌ی باز کردن تنظیمات موجود)، آخرین sync موفق (`lastSyncOk`)، وضعیت `syncPending`، آخرین heartbeat، آخرین ack.
۲. دکمه‌ی «ارسال پوش آزمایشی» و «کپی لاگ سرویس».
کامیت: `feat(ui): notification health page`

## 3C-1: قفل نسخه‌ی firebase-admin و تست رده‌های خطا (سرور)
فایل‌ها: `requirements.txt` + تست.
۱. نسخه‌ی `firebase-admin` را پین کن (۷.x که تست شده) و تستی که ثابت می‌کند کلاس‌های خطای `UnregisteredError`، `SenderIdMismatchError`، `InvalidArgumentError`، `QuotaExceededError`، `UnavailableError` هنوز وجود دارند (تا ارتقای ناخواسته بی‌صدا نشکند).
کامیت: `chore(deps): pin firebase-admin and test error classes`

## 3C-2: بستن N1 — استراتژی payload (فقط بعد از نتیجه‌ی دستگاه)
اگر لاگ handler نشان داد که در حالت «اپ بسته» سیستم‌عامل به‌تنهایی بنر نشان می‌دهد و handler دارت اجرا نمی‌شود، تصمیم می‌گیریم بلوک `android.notification` از `app/notifier/fcm.py` حذف شود (data-only). پرامپتش بعد از نتیجه نوشته می‌شود.

## 3D: خطای `sendData` / `updatePriceSource` (Dart)
فایل: `lib/features/notifications/background/background_service_manager.dart`.
۱. ابتدا بازتولید کن (لاگ بنویس): متن نوتیفیکیشن ۷۷۷ بعد از `updatePriceSource` درست عوض می‌شود یا نه؟
۲. فقط همان مشکل را رفع کن. اگر ریشه در نسخه‌ی پلاگین است، گزارش بده.
کامیت: `fix(bg): update foreground notification text from price source`

## 3E-1: `/health/deep` (سرور)
فایل‌ها: `app/routes/admin.py` (یا جدید) + تست.
۱. خروجی: طول outbox، تعداد `blocked_token`، آخرین موفقیت FCM، تعداد `unacked`، تأخیر چرخه‌ی checker. در صورت وضعیت بد (مثلاً آخرین موفقیت FCM بیش از ۱ ساعت با وجود صف پر) کد ۵۰۳.
کامیت: `feat(health): deep health endpoint`

## 3E-2: نظارت و restart خودکار (سرور)
فایل‌ها: `run_server.sh` یا `docker-compose`/systemd (هرکدام که واقعاً استفاده می‌شود؛ ابتدا بپرس).
۱. restart policy، و یک چک دوره‌ای `/health/deep` که در صورت شکست ادمین را با Telegram خبر کند.
کامیت: `chore(ops): restart policy and health alert`

---

# PHASE 4 — کانال WebSocket (جزئیات بعد از نتیجه‌ی Phase 2 نهایی می‌شود)

## 4A-1: endpoint سوکت (سرور)
۱. `/ws` با احراز هویت کلید API، ping/pong هر ۳۰ ثانیه، و ثبت اتصال هر کاربر/دستگاه. تست با `TestClient`.
## 4A-2: ارسال روی سوکت (سرور)
۱. اگر کاربر وصل است، اعلان با همان `delivery_id` روی سوکت هم برود (FCM همچنان ارسال می‌شود). ack روی سوکت هم پذیرفته شود (`journal.record_acked`).
## 4B-1: کلاینت سوکت در service isolate (Dart)
۱. اتصال، reconnect با backoff (۲، ۵، ۱۵، ۶۰ ثانیه)، و لاگ.
## 4B-2: یکپارچه‌سازی (Dart)
۱. پیام سوکت از همان مسیر `_handleIncomingAlert` عبور کند تا dedup با `delivery_id` بین FCM و سوکت کار کند (فقط یک بار صدا).
## 4C: آزمون
۱. سه سناریو: فقط سوکت، فقط FCM، هر دو هم‌زمان (یک بار نمایش). تصمیم قبل از شروع: پشت reverse proxy سوکت چگونه عبور می‌کند؟

---

# PHASE 5 — آزمون آشوب و گیت انتشار

## 5A-1: مجموعه‌ی آشوب سرور
فایل: `tests/test_chaos_delivery.py` (جدید).
سناریوها (هر کدام یک تست با mock): FCM کاملاً down و برگشت؛ توکن مرده و جایگزینی توکن؛ restart (بارگذاری مجدد outbox/journal) وسط انتظار ack؛ ack تکراری و ack زودتر از `sent`؛ فایل ژورنال خراب؛ دیسک پر (ذخیره شکست می‌خورد ولی ارسال ادامه دارد).
کامیت: `test(chaos): delivery chaos suite`

## 5A-2: اسکریپت soak
فایل: `scripts/soak_delivery.py`. ۲۰۰ آلارم ساختگی، ۱۰ دقیقه، گزارش: تعداد ارسال، acked، unacked، میانگین/p95 تأخیر. بدون وابستگی به FCM واقعی (mock).

## 5B: ماتریس دستگاه و چک‌لیست انتشار
فایل: `docs/release_gate.md`. جدول: گوشی/اندروید × سناریو (foreground، swiped، Doze 30 دقیقه، هواپیما، ریبوت، بهینه‌سازی باتری روشن) با ستون «قبول/رد/مدرک».

## 5C: CI
فایل: `.github/workflows/ci.yml`. اجرای `pytest tests`، `flutter analyze`، `flutter test`. شکست هر کدام انتشار را متوقف کند.

## 5D: گیت انتشار
فایل: `scripts/release_gate.py`. قبل از انتشار بررسی کند: تست‌ها سبز، `google-services.json` موجود، `/health/deep` سالم، `unacked` در ۲۴ ساعت اخیر زیر آستانه، و ماتریس 5B کامل پر شده. خروجی: PASS/FAIL با دلیل.
