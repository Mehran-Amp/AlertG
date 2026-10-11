# سند معماری و طراحی فنی سیستم (design.md)
## نام پروژه: BitcoinChecker (معماری تولیدی بر پایه Flutter و Dart)

---

## ۱. نمای کلی معماری سیستم (System Architecture Overview)

معماری برنامه بر پایه اصول **Clean Architecture** به همراه الگوی مدیریت وضعیت **BLoC (Business Logic Component)** و الگوی ماژولار **Multi-Exchange Adapter Pattern** طراحی شده است (الهام‌گرفته از معماری موفق `BitcoinChecker` اندروید).

```
+-----------------------------------------------------------------------------------+
|                                FLUTTER APPLICATION                                |
|                                                                                   |
|  [ PRESENTATION LAYER ]                                                           |
|    - Market Ticker Page (Real-Time Sparklines, Pair Search)                       |
|    - Alert Rule Builder (Thresholds, % Window, Volume, AND/OR logic)              |
|    - Notification Center & Audio Alert Player                                     |
|    - MarketDataBloc / AlertRulesBloc / NotificationBloc                           |
|                                     |                                             |
|                                     v                                             |
|  [ DOMAIN LAYER ]                                                                 |
|    - AlertRuleEvaluator (Dedicated Background Dart Isolate)                       |
|    - RollingRingBuffer (Zero-Allocation Circular Buffer for Secs/Mins/Hours)      |
|    - CooldownManager (3-Minute Re-arm State Machine)                             |
|    - Multi-Exchange Adapter Interface (Abstract Exchange, CurrencyPair)           |
|                                     |                                             |
|                                     v                                             |
|  [ DATA & INFRASTRUCTURE LAYER ]                                                  |
|    - Exchange Implementations (Binance, Coinbase, Kraken, KuCoin, OKX, Bybit...)  |
|    - Isar Database (Local-First NoSQL, Sub-millisecond reads)                    |
|    - Audio & Haptic Service (Custom Alert Chimes)                                 |
|                                     |                                             |
|                                     v                                             |
|  [ BACKGROUND & GUARANTEED NOTIFICATION LAYER ]                                   |
|    - Android Foreground Service (Sticky Persistent Notification, Wakelock)        |
|    - Exact Alarm Manager (Periodic Fallback & Wake-up)                            |
|    - iOS Background Tasks & APNs Critical Alerts                                  |
+-----------------------------------------------------------------------------------+
```

---

## ۲. موتور آداپتور صرافی‌ها (Multi-Exchange Adapter Engine)

### ۲.۱ ساختار کلاس‌ها و قرارداد ماژولار (الهام از BitcoinChecker)
هر صرافی به عنوان یک ماژول مستقل پیاده‌سازی می‌شود و قرارداد انتزاعی `Exchange` را پیاده‌سازی می‌کند. با این روش افزودن یک صرافی جدید نیاز به هیچ تغییری در موتور ارزیابی یا UI ندارد:

```dart
abstract class Exchange {
  String get id;
  String get name;
  String get defaultCurrency;
  bool get supportsWebSocket;
  
  // واکشی لیست تمامی جفت‌ارزهای فعال صرافی
  Future<List<CurrencyPair>> fetchCurrencyPairs();
  
  // واکشی آخرین نرخ و حجم به صورت REST (پشتیبان یا پیش‌فرض)
  Future<MarketTicker> fetchTicker(CurrencyPair pair);
  
  // استریم بلادرنگ برای صرافی‌های دارای وب‌سوکت
  Stream<MarketTicker>? getTickerStream(CurrencyPair pair);
}

class CurrencyPair {
  final String baseCurrency;   // مثال: BTC
  final String counterCurrency;// مثال: USDT
  final String marketSymbol;   // مثال در بایننس: BTCUSDT
  
  const CurrencyPair(this.baseCurrency, this.counterCurrency, this.marketSymbol);
}

class MarketTicker {
  final double lastPrice;
  final double volume24h;
  final double high24h;
  final double low24h;
  final double? bid;
  final double? ask;
  final DateTime timestamp;

  MarketTicker({
    required this.lastPrice,
    required this.volume24h,
    required this.high24h,
    required this.low24h,
    this.bid,
    this.ask,
    required this.timestamp,
  });
}
```

### ۲.۲ ثبت خودکار صرافی‌ها (Exchange Registry)
یک رجیستری مرکزی تمامی صرافی‌ها را شناسایی کرده و به کاربر اجازه می‌دهد بین ده‌ها صرافی و هزاران جفت‌ارز جستجو کند:
- `BinanceExchange` (WebSocket + REST)
- `CoinbaseExchange` (WebSocket + REST)
- `KrakenExchange` (REST / WS)
- `KuCoinExchange` (REST / WS)
- `OKXExchange` (REST / WS)
- `BybitExchange` (REST / WS)
- `CoinGeckoExchange` (REST پایش جامع ده‌ها هزار ارز متفرقه)

---

## ۳. موتور ارزیابی شروط در Dart Isolate و بهینه‌سازی رم

### ۳.۱ بافر حلقوی چرخشی (Circular Ring Buffer)
برای اینکه پنجره‌های زمانی انتخابی کاربر (از ۱۰ ثانیه تا ۴۸ ساعت) رم دستگاه را پر نکنند، از ساختار داده **RingBuffer** با ظرفیت مشخص استفاده می‌شود. این بافر حافظه ثابتی را تخصیص می‌دهد و تیک‌های جدید جایگزین قدیمی‌ترین تیک‌ها می‌شوند:

```dart
class TickDataPoint {
  final double price;
  final double volume;
  final int timestampMs;

  const TickDataPoint(this.price, this.volume, this.timestampMs);
}

class CircularTickBuffer {
  final int maxCapacity;
  final List<TickDataPoint?> _buffer;
  int _head = 0;
  int _size = 0;

  CircularTickBuffer({this.maxCapacity = 720})
      : _buffer = List<TickDataPoint?>.filled(maxCapacity, null);

  void add(double price, double volume, int timestampMs) {
    _buffer[_head] = TickDataPoint(price, volume, timestampMs);
    _head = (_head + 1) % maxCapacity;
    if (_size < maxCapacity) _size++;
  }

  // محاسبه دقیق تغییر درصدی نسبت به پنجره زمانی مشخص
  double? calculatePercentChange(Duration window) {
    if (_size < 2) return null;
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    final targetWindowMs = nowMs - window.inMilliseconds;

    TickDataPoint? oldestPoint;
    TickDataPoint? latestPoint;

    for (int i = 0; i < _size; i++) {
      int idx = (_head - 1 - i + maxCapacity) % maxCapacity;
      final point = _buffer[idx];
      if (point == null) continue;
      
      latestPoint ??= point;
      if (point.timestampMs <= targetWindowMs) {
        oldestPoint = point;
        break;
      }
      oldestPoint = point; // نزدیک‌ترین نقطه در دسترس
    }

    if (oldestPoint == null || latestPoint == null || oldestPoint.price == 0) {
      return null;
    }

    return ((latestPoint.price - oldestPoint.price) / oldestPoint.price) * 100.0;
  }
}
```

### ۳.۲ ماشین وضعیت زمان خنک‌سازی ۳ دقیقه‌ای (3-Minute Cooldown State Machine)
هنگامی که یک شرط هشدار برقرار می‌شود:
1. وضعیت هشدار به `Triggered` تغییر می‌یابد.
2. زنگ هشدار بحرانی و نوتیفیکیشن صادر می‌شود.
3. یک تایمر خنک‌سازی دقیق ۳ دقیقه‌ای (`180,000 میلی‌ثانیه`) فعال می‌شود.
4. در طول این ۳ دقیقه، حتی در صورت نوسان مکرر قیمت حول مرز شرط، هیچ پیام جدیدی صادر نمی‌شود.
5. پس از سپری شدن ۳ دقیقه، وضعیت هشدار خودکار به `Armed (مسلح)` بازمی‌گردد.

---

## ۴. معماری تضمین تحویل نوتیفیکیشن (Guaranteed Notification Pipeline)

برای رعایت نیازمندی حیاتی «ارسال نوتیفیکیشن تحت هر شرایطی» و انتشار موفق در Google Play و App Store:

### ۴.۱ در پلتفرم اندروید (Android)
- **Foreground Service با نوتیفیکیشن پین‌شده**:
  - استفاده از پلاگین `flutter_background_service`.
  - یک سرویس پس‌زمینه مداوم با اعلان کم‌مصرف در Notification Drawer ثبت می‌شود که به اندروید اعلام می‌کند این پروسه نباید توسط سیستم‌عامل کشته شود.
  - اعلام نوع `foregroundServiceType="dataSync"` یا `specialUse` در فایل `AndroidManifest.xml` مطابق ضوابط سخت‌گیرانه Android 14+.
- **معافیت از صرفه‌جویی باتری (Doze Mode Exemption)**:
  - درخواست مجوز `android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`.
- **کانال صوتی و لرزش با اولویت بالا**:
  - تعریف کانال اختصاصی `NotificationChannel` با `importance: Importance.max` و فعال بودن لرزش و صدای بحرانی.
  - استفاده از `android.permission.SCHEDULE_EXACT_ALARM` برای تضمین زمان‌بندی بررسی در صورت قطعی لحظه‌ای سرویس.

### ۴.۲ در پلتفرم اپل (iOS)
- **Background Tasks Framework (`BGAppRefreshTask` / `BGProcessingTask`)**:
  - ثبت تسک‌های دوره‌ای پایش در پس‌زمینه.
- **مجوز هشدارهای بحرانی (Critical Alerts Entitlement)**:
  - ارسال درخواست مجوز به کاربر برای قابلیت `criticalAlert: true` که اجازه می‌دهد در صورت فعال بودن دکمه Do Not Disturb یا Silent سوئیچ آیفون، هشدارهای صوتی مالی پخش شوند.

---

## ۵. مدل داده و ذخیره‌سازی محلی (Isar Database Schema)

استفاده از دیتابیس بومی **Isar** که دارای سرعت خیره‌کننده و مصرف فوق‌العاده پایین رم است:

```dart
import 'package:isar/isar.dart';

part 'alert_rule_schema.g.dart';

enum AlertType { priceCross, percentChange, volumeSurge, compound }
enum ConditionType { above, below, percentUp, percentDown, volumeSurge }
enum LogicOperator { and, or }

@collection
class AlertRuleSchema {
  Id id = Isar.autoIncrement;

  late String exchangeId;      // مثال: binance
  late String baseCurrency;    // مثال: BTC
  late String counterCurrency; // مثال: USDT
  late String marketSymbol;    // مثال: BTCUSDT

  @enumerated
  late AlertType alertType;

  @enumerated
  late ConditionType condition;

  late double targetValue;

  int? timeWindowSeconds; // بازه زمانی دلخواه کاربر (از ثانیه تا ساعت)

  @enumerated
  LogicOperator? logicOperator;

  // شرط دوم برای شروط ترکیبی AND / OR
  String? secondaryConditionJson;

  bool isActive = true;
  DateTime createdAt = DateTime.now();
  DateTime? lastTriggeredAt;
  int triggerCount = 0;
  
  // زمان پایان دوره خنک‌سازی ۳ دقیقه‌ای
  DateTime? cooldownUntil;
}

@collection
class NotificationLogSchema {
  Id id = Isar.autoIncrement;
  late int ruleId;
  late String title;
  late String message;
  late double triggeredPrice;
  late DateTime timestamp;
}
```

---

## ۶. انطباق با سیاست‌های گوگل‌پلی و اپ‌استور (Store Compliance Guidelines)

1. **Google Play Store**:
   - درخواست مجوز Foreground Service باید با فایل ویدیویی تست و توضیحات درون برنامه‌ای شفاف باشد که کاربر متوجه شود این سرویس فقط برای مانیتورینگ زنده دارایی‌های انتخابی او اجرا می‌شود.
   - عدم مصرف بی‌رویه باتری با بهینه‌سازی فرکانس درخواست‌های تیک به کمک وب‌سوکت‌های یکپارچه.
2. **Apple App Store**:
   - توضیح صریح در صفحه App Privacy پیرامون عدم جمع‌آوری داده‌های هویتی (اپلیکیشن ۱۰۰٪ محلی‌محور است و داده خصوصی کاربران به هیچ سروری ارسال نمی‌شود).
   - پیاده‌سازی دکمه Mute و قطع صدای هشدار از روی نوتیفیکیشن بنر (Notification Actions).
