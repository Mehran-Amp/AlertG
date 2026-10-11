# طرح مکتوب بازگشت به نسخه قبل (Rollback Plan & Runbook)
## سامانه Enterprise SignalAlert / BitcoinChecker (نسخه v3.0.0)

---

### ۱. هدف و دامنه کاربرد (Purpose & Scope)
این سند دستورالعمل جامع و گام‌به‌گام برای بازگرداندن سیستم به وضعیت پایدار قبلی در صورت بروز هرگونه اختلال بحرانی، کرش غیرمنتظره، افزایش غیرمجاز نرخ خطا، یا ناهماهنگی در کاتالوگ نمادها در محیط Production ارائه می‌دهد.

---

### ۲. معیارهای ماشه‌ای رول‌بک (Rollback Trigger Criteria)
در صورت احراز هر یک از شرایط زیر، فرآیند رول‌بک باید فوراً فعال شود:
1. **افزایش نرخ خطای شبکه یا کرش**: رسیدن نرخ خطای پاسخ‌ها به بیش از **۵٪** کل درخواست‌ها در بازه ۵ دقیقه‌ای.
2. **قطعی سرویس‌دهنده‌های کلیدی**: قطع پیوسته و عدم دریافت قیمت از صرافی‌های اصلی (Yahoo Finance, Nobitex, Binance) به مدت بیش از ۱۵ دقیقه بدون جایگزینی.
3. **ناهماهنگی کاتالوگ نمادها**: نقض سقف ایمنی کاتالوگ، حذف اشتباهی بیش از ۵٪ نمادها، یا گزارش خطای Delta Sync در اپلیکیشن موبایل.
4. **نشتی حافظه یا مصرف نامتعارف منابع**: افزایش مداوم مصرف RAM (بیش از ۸۰٪ ظرفیت کانتینر) یا ری‌استارت مکرر پاد (CrashLoopBackOff).
5. **شکست در تحویل نوتیفیکیشن‌ها**: نرخ شکست FCM یا Telegram به بالای ۱۰٪ برسد.

---

### ۳. سناریوهای سه‌گانه رول‌بک و دستورات اجرایی

#### سناریوی الف: رول‌بک کاتالوگ نمادها (Catalog Rollback)
اگر در همگام‌سازی هفتگی کاتالوگ، نمادهای نامعتبر اضافه یا نمادهای فعال به اشتباه غیرفعال شده باشند:
- **روش اول (از طریق API ادمین)**:
  ```bash
  curl -X POST "https://api.yourdomain.com/api/admin/catalog/rollback" \
       -H "X-Admin-Key: $ADMIN_KEY" \
       -d "version=1"
  ```
- **روش دوم (از طریق پایتون / سرور مستقیم)**:
  ```bash
  python3 -c "from app.engine.sync import rollback_catalog; rollback_catalog(target_version=1)"
  ```
- **نتیجه**:
  - کاتالوگ به فایل اسنپ‌شات قبلی (`catalog_snapshots/snapshot_v1_*.json`) برمی‌گردد.
  - کش کلاینت‌ها با درخواست نسخه جدید، دلتای بازگشتی را دریافت و همگام می‌کنند.

---

#### سناریوی ب: قطع فوری سرویس‌دهنده مشکل‌دار از طریق Kill Switch (بدون نیاز به ری‌استارت)
اگر فقط یک Provider (مثلاً Yahoo Finance یا Nobitex) دچار قطعی، بلاک IP یا رفتار غیرعادی شده باشد:
- **تنظیم متغیر محیطی در کانتینر**:
  ```bash
  KILL_SWITCH_PROVIDERS="yahoo"
  # یا برای یک دسته خاص:
  KILL_SWITCH_CATEGORIES="macro"
  ```
- سیستم بلافاصله و با تأخیر صفر میلی‌ثانیه، درخواست‌های مربوط به آن منبع را بای‌پس کرده و سایر بخش‌ها بدون وقفه به کار خود ادامه می‌دهند.

---

#### سناریوی ج: رول‌بک کامل نسخه سرور و کانتینر (Full Release Rollback)
اگر نسخه جدید سرور دارای باگ عمیق در منطق یا کتابخانه‌ها باشد:
1. **بازگشت به ایمیج / برچسب پایدار قبلی**:
   ```bash
   # در Google Cloud Run:
   gcloud run services update-traffic signalalert-engine \
       --to-revisions=signalalert-engine-v2-10-0=100 \
       --region=europe-west1

   # در Docker / Kubernetes:
   docker stop signalalert-app && docker run -d --name signalalert-app signalalert:v2.10.0
   # یا
   kubectl rollout undo deployment/signalalert-engine
   ```
2. **بررسی سلامت دیتابیس هشدارها (`alerts.json`)**:
   در صورت آسیب به فایل هشدارها، بازیابی از نسخه پشتیبان اخیر:
   ```bash
   cp data/alerts.json.bak data/alerts.json
   ```

---

#### سناریوی د: رول‌بک فیچر فلگ و کنترل کلاینت‌ها (Feature Flag Demotion)
اگر قابلیت جدیدی مانند Delta Sync یا هشدارهای ماکرو در سمت کاربر اشکال ایجاد کرده باشد:
- **غیرفعال‌سازی آنی از طریق Feature Flag**:
  ```bash
  curl -X POST "https://api.yourdomain.com/api/admin/features?flag=v3_mobile_delta_sync&enabled=false" \
       -H "X-Admin-Key: $ADMIN_KEY"
  ```
  یا برگرداندن قابلیت فقط به گروه بتا:
  ```bash
  FEATURE_FLAG_V3_MOBILE_DELTA_SYNC="beta"
  ```

---

### ۴. چک‌لیست اعتبارسنجی پس از رول‌بک (Verification Checklist)
پس از انجام رول‌بک، گام‌های زیر باید توسط مدیر سیستم بررسی و تایید شوند:
- [ ] فراخوانی اندپوینت `/status` و اطمینان از سلامت کلی (`HEALTHY`)، عدم وجود خطای سیستمی و تطابق تعداد هشدارهای فعال.
- [ ] فراخوانی اندپوینت `/api/admin/probe` و بررسی وضعیت منابع بازار.
- [ ] بررسی لاگ‌های سرور برای اطمینان از رفع خطاهای ۴۲۹ یا ۵۰۰.
- [ ] تست ارسال اعلان تست از طریق `POST /api/test/push` جهت تایید اتصال لایو به FCM و تلگرام.
- [ ] اجرای تست‌های یکپارچگی خودکار:
  ```bash
  python3 -m unittest discover -s tests -p "test_*.py"
  ```
- [ ] ثبت گزارش علت حادثه (Post-Mortem Report) در مستندات عملیاتی.
