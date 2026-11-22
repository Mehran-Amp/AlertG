import '../alerts/bourse_alert_draft.dart';
import '../models/bourse_board.dart';
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

  // ---- browse list (IB-16c) ----------------------------------------------------------
  static const String browseSearchHint = 'جستجوی نماد یا نام در همین فهرست';
  static const String browseEmpty = 'نمادی در این دسته پیدا نشد.';
  static const String browseLoadMoreFailed = 'دریافت ادامه فهرست ناموفق بود.';
  static const String tagLastPrice = 'آخرین قیمت';
  static const String tagNotTradedToday = 'امروز معامله نشده';
  static const String sortTitle = 'مرتب‌سازی';
  static const String bannerClosed =
      'بازار بسته است؛ قیمت‌ها آخرین قیمت معامله هستند. هشدار را همین حالا هم می‌توانید بسازید؛ '
      'از زمان باز شدن بازار بر اساس قیمت زنده بررسی می‌شود.';
  static const String bannerStale =
      'اتصال به منبع داده قطع یا کند است؛ قیمت‌ها ممکن است قدیمی باشند.';
  static const String bannerUnknown = 'وضعیت بازار مشخص نیست؛ قیمت‌ها ممکن است زنده نباشند.';
  static const String tabAll = 'همه';
  static const String tabTopMovers = 'پرتغییرترین‌ها';
  static const String filterTradedOnly = 'فقط نمادهای معامله‌شده امروز';
  static String rowAlertBadge(String countText) => '$countText هشدار';

  static String groupLabel(BourseGroup group) {
    switch (group) {
      case BourseGroup.stocks:
        return 'سهام';
      case BourseGroup.funds:
        return 'صندوق‌ها';
      case BourseGroup.bonds:
        return 'اوراق';
      case BourseGroup.rights:
        return 'حق تقدم';
      case BourseGroup.derivatives:
        return 'اختیار و آتی';
      case BourseGroup.other:
        return 'سایر';
    }
  }

  static String sortLabel(BourseSort sort) {
    switch (sort) {
      case BourseSort.value:
        return 'بیشترین ارزش معامله';
      case BourseSort.volume:
        return 'بیشترین حجم';
      case BourseSort.change:
        return 'بیشترین تغییر قیمت';
      case BourseSort.price:
        return 'بیشترین قیمت';
      case BourseSort.name:
        return 'نام (الفبا)';
    }
  }

  // ---- market picker card -----------------------------------------------------------
  static const String marketCardTitle = 'بورس و فرابورس ایران';
  static const String marketCardDescription =
      'هشدار قیمت سهام، صندوق‌ها و حق تقدم بازار سرمایه به ریال؛ فقط در ساعات باز بودن بازار بررسی می‌شود.';
  static const String marketCardCta = 'جستجوی نماد';

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
  // ---- alert form when the market is closed (IB-16d) ----
  static String alertClosedNote(String priceText) =>
      'بازار بسته است؛ این هشدار بر اساس آخرین قیمت ($priceText) ساخته می‌شود و '
      'از زمان باز شدن بازار بررسی می‌شود.';
  static String alertDistanceAbove(String pct) => '$pct بالاتر از آخرین قیمت';
  static String alertDistanceBelow(String pct) => '$pct پایین‌تر از آخرین قیمت';

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
        return 'جهت انتخاب‌شده پشتیبانی نمی‌شود.';
      case BourseAlertProblem.amountMissing:
        return 'مقدار را وارد کنید.';
      case BourseAlertProblem.amountNotPositive:
        return 'مقدار باید بزرگ‌تر از صفر باشد.';
      case BourseAlertProblem.noPreviousClose:
        return 'قیمت دیروز این نماد هنوز مشخص نیست؛ هشدار قیمت هدف بسازید.';
      case BourseAlertProblem.bothSidesTargetsMissing:
        return 'برای حالت دوطرفه، هر دو قیمت حد بالا و حد پایین را وارد کنید.';
      case BourseAlertProblem.invalidRange:
        return 'قیمت حد بالا باید بزرگ‌تر از قیمت حد پایین باشد.';
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

  // ---- alert kinds & sections -------------------------------------------------------
  static const String kindPrice = 'رسیدن به قیمت';
  static const String kindPercent = 'درصد تغییر نسبت به دیروز';
  static const String kindAbsolute = 'مقدار تغییر (ریال) نسبت به دیروز';
  static const String directionAbove = 'بالاتر از';
  static const String directionBelow = 'پایین‌تر از';
  static const String directionBothSides = 'هر دو جهت';
  static const String alertAmountPercent = 'درصد تغییر';
  static const String alertAmountAbsolute = 'مقدار تغییر (ریال)';
  static const String alertNoteLabel = 'یادداشت (اختیاری)';
  static const String alertSubmit = 'ثبت هشدار';
  static const String alertRecurring = 'پس از هر بار فعال شدن دوباره فعال بماند';
  static const String alertCreated = 'هشدار ساخته شد.';
  static const String alertSaveFailed =
      'هشدار ساخته نشد چون ذخیره آن روی دستگاه ناموفق بود. دوباره تلاش کنید.';
  static const String alertAmountHintRial = 'مثلاً ۷۰۰٬۰۰۰';

  static const String alertSectionCondition = 'شرط و جهت هشدار';
  static const String alertSectionBehavior = 'رفتار هشدار و یادداشت';
  static const String alertSectionNotification = 'شیوهٔ اطلاع‌رسانی و آلارم';

  static const String dailyBandLabel = 'دامنه مجاز امروز';
  static const String shortcutUpperLimit = 'سقف مجاز امروز';
  static const String shortcutLowerLimit = 'کف مجاز امروز';
  static const String priceFieldLabel = 'مبنای بررسی قیمت';
  static const String priceFieldLast = 'آخرین معامله';
  static const String priceFieldClose = 'قیمت پایانی';

  // ---- two-way price target ---------------------------------------------------------
  static const String bothWayBehaviorLabel = 'رفتار پس از اولین برخورد قیمت';
  static const String bothWayOcoTitle = 'خروج با اولین تارگت';
  static const String bothWayOcoDesc = 'پس از برخورد غیرفعال شود';
  static const String bothWayDualTitle = 'پایش دائمی کانال';
  static const String bothWayDualDesc = 'کانال همچنان فعال بماند';
  static const String upperTargetTitle = 'حد بالا (مقاومت)';
  static const String upperPriceLabel = 'قیمت حد بالا (ریال)';
  static const String upperNoteLabel = 'یادداشت حد بالا (اختیاری)';
  static const String lowerTargetTitle = 'حد پایین (حمایت)';
  static const String lowerPriceLabel = 'قیمت حد پایین (ریال)';
  static const String lowerNoteLabel = 'یادداشت حد پایین (اختیاری)';
  static String bothSidesPreviewUpper(String priceText) => '▲ سقف: $priceText';
  static String bothSidesPreviewLower(String priceText) => '▼ کف: $priceText';

  // ---- notification options ---------------------------------------------------------
  static const String notifPresetStandard = 'صدا و ویبره';
  static const String notifPresetSoundOnly = 'فقط صدا';
  static const String notifPresetVibrateOnly = 'فقط ویبره';
  static const String notifPresetSilent = 'فقط نوتیف';
  static const String notifSoundTitle = 'صدای زنگ آلارم';
  static const String notifSoundMuted = 'پخش صدا خاموش است';
  static const String notifChangeSound = 'تغییر';
  static const String notifSelectSoundTitle = 'انتخاب صدای آلارم';
  static const String notifConfirmSound = 'تأیید صدا';
  static const String notifSoundToggle = 'پخش صدای آلارم';
  static const String notifVibrateToggle = 'لرزش گوشی (ویبره)';
  static const String notifFlashToggle = 'فلاش دوربین (SOS)';
  static const String notifTtsTitle = 'اعلام صوتی (TTS)';
  static const String notifTtsSubtitle = 'خواندن نام نماد و قیمت هنگام فعال شدن هشدار';
  static const String notifTtsTest = 'تست صدا';

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
