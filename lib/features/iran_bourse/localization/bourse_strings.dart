import '../alerts/bourse_alert_draft.dart';
import '../models/bourse_quote.dart';
import '../services/iran_bourse_service.dart';

/// Persian texts of the Iranian Bourse flow (pure Persian, RTL, like the existing Iran flow).
///
/// Kept in its own file so the 10-language dictionary in `app_strings.dart` stays untouched.
class BourseStrings {
  static const String title = 'بورس ایران';
  static const String searchHint = 'جستجوی نماد یا نام شرکت (مثلاً فولاد، وبملت)';
  static const String searchEmptyPrompt = 'نام یا نماد را بنویسید تا جستجو شود.';
  static const String searchNoResults = 'نمادی پیدا نشد. املای دیگری را امتحان کنید.';
  static const String searchStaleNote = 'فهرست نمادها ممکن است کمی قدیمی باشد.';
  static const String retry = 'تلاش دوباره';

  // ---- filters ----------------------------------------------------------------------
  static const String filterMarket = 'بازار';
  static const String filterType = 'نوع ابزار';
  static const String filterOnlyTraded = 'فقط نمادهای معامله‌شده امروز';
  static const String filterAll = 'همه';

  // ---- detail card labels -----------------------------------------------------------
  static const String lastPrice = 'آخرین قیمت';
  static const String closePrice = 'قیمت پایانی';
  static const String prevClose = 'قیمت دیروز';
  static const String change = 'تغییر';
  static const String dayRange = 'محدوده امروز';
  static const String upperLimit = 'سقف مجاز قیمت';
  static const String lowerLimit = 'کف مجاز قیمت';
  static const String volume = 'حجم معاملات';
  static const String nav = 'ارزش خالص دارایی (NAV)';
  static const String queue = 'صف';
  static const String lastTradeTime = 'زمان آخرین معامله';
  static const String updatedAt = 'آخرین بروزرسانی';
  static const String market = 'بازار';
  static const String type = 'نوع';
  static const String sector = 'گروه صنعت';
  static const String unitNote = 'همه قیمت‌ها به ریال است.';

  // ---- alert ------------------------------------------------------------------------
  static const String createAlert = 'ساخت هشدار';
  static const String alertPriceLabel = 'قیمت هدف (ریال)';
  static const String alertOnlyLiveNote =
      'هشدار فقط وقتی بازار باز و قیمت زنده است بررسی می‌شود.';
  static const String alertDailyBaseNote =
      'درصد تغییر نسبت به قیمت دیروز همین نماد حساب می‌شود.';

  /// Why the alert form cannot be submitted yet.
  static String alertProblem(BourseAlertProblem problem) {
    switch (problem) {
      case BourseAlertProblem.invalidInstrument:
        return 'شناسه نماد معتبر نیست. نماد را دوباره انتخاب کنید.';
      case BourseAlertProblem.directionNotSupported:
        return 'برای بورس فقط «بالاتر از» و «پایین‌تر از» پشتیبانی می‌شود.';
      case BourseAlertProblem.amountMissing:
        return 'مقدار را وارد کنید.';
      case BourseAlertProblem.amountNotPositive:
        return 'مقدار باید بزرگ‌تر از صفر باشد.';
      case BourseAlertProblem.noPreviousClose:
        return 'قیمت دیروز این نماد هنوز مشخص نیست؛ هشدار قیمت هدف بسازید.';
    }
  }

  /// A hint shown under the amount field; never blocks creating the alert.
  static String alertWarning(BourseAlertWarning warning) {
    switch (warning) {
      case BourseAlertWarning.unreachableToday:
        return 'این مقدار خارج از محدوده مجاز نوسان امروز است و امروز فعال نمی‌شود.';
      case BourseAlertWarning.alreadyReached:
        return 'شرط هم‌اکنون برقرار است؛ هشدار بلافاصله فعال می‌شود.';
    }
  }

  // ---- alert kinds ------------------------------------------------------------------
  static const String kindPrice = 'رسیدن به قیمت';
  static const String kindPercent = 'درصد تغییر نسبت به دیروز';
  static const String kindAbsolute = 'مقدار تغییر (ریال) نسبت به دیروز';
  static const String directionAbove = 'بالاتر از';
  static const String directionBelow = 'پایین‌تر از';
  static const String alertAmountPercent = 'درصد تغییر';
  static const String alertAmountAbsolute = 'مقدار تغییر (ریال)';
  static const String alertNoteLabel = 'یادداشت (اختیاری)';
  static const String alertSubmit = 'ثبت هشدار';
  static const String alertRecurring = 'پس از هر بار فعال شدن دوباره فعال بماند';
  static const String alertCreated = 'هشدار ساخته شد.';
  static const String alertSaveFailed =
      'هشدار ساخته نشد چون ذخیره آن روی دستگاه ناموفق بود. دوباره تلاش کنید.';
  static const String alertAmountHintRial = 'مثلاً ۷۰۰٬۰۰۰';

  static String alertKindLabel(BourseAlertKind kind) {
    switch (kind) {
      case BourseAlertKind.price:
        return kindPrice;
      case BourseAlertKind.percentChange:
        return kindPercent;
      case BourseAlertKind.absoluteChange:
        return kindAbsolute;
    }
  }

  /// Short title for a quote state (badge text).
  static String stateLabel(BourseState state) {
    switch (state) {
      case BourseState.live:
        return 'زنده';
      case BourseState.closed:
        return 'بازار بسته';
      case BourseState.noTradeToday:
        return 'امروز معامله نشده';
      case BourseState.stale:
        return 'داده قدیمی';
      case BourseState.unknown:
        return 'وضعیت نامشخص';
    }
  }

  /// One-sentence explanation of a quote state.
  static String stateDescription(BourseState state) {
    switch (state) {
      case BourseState.live:
        return 'بازار باز است و قیمت به‌روز است.';
      case BourseState.closed:
        return 'بازار بسته است؛ آخرین قیمت معامله نمایش داده می‌شود.';
      case BourseState.noTradeToday:
        return 'این نماد امروز هنوز معامله نشده است.';
      case BourseState.stale:
        return 'اتصال به منبع داده قطع یا کند است؛ به این قیمت اعتماد نکنید.';
      case BourseState.unknown:
        return 'وضعیت این قیمت مشخص نیست.';
    }
  }

  /// User-facing message for a failed call.
  static String failureMessage(BourseFailure failure) {
    switch (failure) {
      case BourseFailure.disabled:
        return 'بازار بورس ایران هنوز برای شما فعال نشده است.';
      case BourseFailure.unavailable:
        return 'منبع داده بورس موقتاً در دسترس نیست؛ کمی بعد دوباره تلاش کنید.';
      case BourseFailure.notFound:
        return 'نمادی با این شناسه پیدا نشد.';
      case BourseFailure.badRequest:
        return 'درخواست نامعتبر بود. ورودی را بررسی کنید.';
      case BourseFailure.unauthorized:
        return 'دسترسی به سرور مجاز نیست؛ تنظیمات اتصال برنامه را بررسی کنید.';
      case BourseFailure.network:
        return 'اتصال به اینترنت یا سرور برقرار نشد.';
      case BourseFailure.badResponse:
        return 'پاسخ سرور قابل فهم نبود؛ برنامه را به‌روزرسانی کنید.';
      case BourseFailure.notAllowed:
        return 'ساخت هشدار بورس هنوز برای حساب شما فعال نشده است.';
      case BourseFailure.noPreviousClose:
        return 'قیمت دیروز این نماد هنوز مشخص نیست؛ هشدار قیمت هدف بسازید.';
      case BourseFailure.rejected:
        return 'سرور این هشدار را نپذیرفت. مقادیر را بررسی کنید.';
    }
  }
}
