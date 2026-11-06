/// Pure text builder for the permanent (foreground-service) notification (ID 777).
///
/// No plugins, no Flutter imports and no I/O, so it is safe to call from the
/// background-service isolate (FIX-6b: nothing here may touch the disk).
///
/// Title format: `<weekday> · <one date in the selected calendar>`, e.g.
///   Gregorian/en  `Friday · 6 Nov 2026`
///   Jalali/fa     `جمعه · ۱۵ آبان ۱۴۰۵`
///   Jalali/en     `Friday · 15 Aban 1405`
///   Hijri/en      `Friday · 26 Jumada I 1448`
/// Weekday and month names come from fixed tables below (not from `intl`), so
/// no locale initialisation is needed. Persian ("fa") uses Persian names and
/// digits; every other language uses English names.
enum NotificationCalendar { jalali, gregorian, hijri }

class PersistentNotificationText {
  PersistentNotificationText._();

  /// Stored preference values. 'auto' = follow the app language until the user
  /// chooses explicitly (fa -> Jalali, everything else -> Gregorian).
  static const String prefAuto = 'auto';
  static const String prefJalali = 'jalali';
  static const String prefGregorian = 'gregorian';
  static const String prefHijri = 'hijri';

  static NotificationCalendar resolveCalendar(String pref, String lang) {
    switch (pref) {
      case prefJalali:
        return NotificationCalendar.jalali;
      case prefGregorian:
        return NotificationCalendar.gregorian;
      case prefHijri:
        return NotificationCalendar.hijri;
      default:
        return lang == 'fa' ? NotificationCalendar.jalali : NotificationCalendar.gregorian;
    }
  }

  /// Normalises any stored value to one of the four known preference strings.
  static String sanitizePref(String? pref) {
    if (pref == prefJalali || pref == prefGregorian || pref == prefHijri) {
      return pref!;
    }
    return prefAuto;
  }

  /// Title line of the permanent notification.
  /// [hijriOffsetDays] (-1, 0, +1) only affects the Hijri calendar (moon-sighting
  /// differences). A Hijri date outside the built-in table falls back to Gregorian.
  static String title(
    DateTime now, {
    required NotificationCalendar calendar,
    required String lang,
    int hijriOffsetDays = 0,
  }) {
    final bool fa = lang == 'fa';
    final String weekday = (fa ? _weekdaysFa : _weekdaysEn)[now.weekday - 1];
    final int epochDay = _epochDay(now);

    String? date;
    if (calendar == NotificationCalendar.jalali) {
      final j = _jalaliFromEpochDay(epochDay);
      date = '${j[2]} ${(fa ? _jalaliMonthsFa : _jalaliMonthsEn)[j[1] - 1]} ${j[0]}';
    } else if (calendar == NotificationCalendar.hijri) {
      final int off = hijriOffsetDays < -1 ? -1 : (hijriOffsetDays > 1 ? 1 : hijriOffsetDays);
      final h = _hijriFromEpochDay(epochDay + off);
      if (h != null) {
        date = '${h[2]} ${(fa ? _hijriMonthsFa : _hijriMonthsEn)[h[1] - 1]} ${h[0]}';
      }
    }
    date ??= '${now.day} ${(fa ? _gregorianMonthsFa : _gregorianMonthsEn)[now.month - 1]} ${now.year}';

    final String line = '$weekday \u00b7 $date';
    return fa ? _toPersianDigits(line) : line;
  }

  /// Second line. Honest by design: "online" is shown only while prices come
  /// from the server; otherwise the app says it is monitoring locally.
  static String statusLine({required bool isFromServer, required String lang}) {
    if (lang == 'fa') {
      return isFromServer ? 'سرور ۲۴/۷ آنلاین' : 'سرور قطع است \u00b7 پایش محلی';
    }
    return isFromServer ? 'server 24/7 online' : 'server offline \u00b7 local monitoring';
  }

  // ---------------------------------------------------------------- tables

  static const List<String> _weekdaysEn = [
    'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
  ];
  static const List<String> _weekdaysFa = [
    'دوشنبه', 'سه\u200cشنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه', 'شنبه', 'یکشنبه',
  ];

  static const List<String> _gregorianMonthsEn = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];
  static const List<String> _gregorianMonthsFa = [
    'ژانویه', 'فوریه', 'مارس', 'آوریل', 'مه', 'ژوئن', 'ژوئیه', 'اوت', 'سپتامبر', 'اکتبر', 'نوامبر', 'دسامبر',
  ];

  static const List<String> _jalaliMonthsEn = [
    'Farvardin', 'Ordibehesht', 'Khordad', 'Tir', 'Mordad', 'Shahrivar',
    'Mehr', 'Aban', 'Azar', 'Dey', 'Bahman', 'Esfand',
  ];
  static const List<String> _jalaliMonthsFa = [
    'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
    'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند',
  ];

  static const List<String> _hijriMonthsEn = [
    'Muharram', 'Safar', 'Rabi I', 'Rabi II', 'Jumada I', 'Jumada II',
    'Rajab', 'Shaban', 'Ramadan', 'Shawwal', 'Dhu al-Qadah', 'Dhu al-Hijjah',
  ];
  static const List<String> _hijriMonthsFa = [
    'محرم', 'صفر', 'ربیع\u200cالاول', 'ربیع\u200cالثانی', 'جمادی\u200cالاول', 'جمادی\u200cالثانی',
    'رجب', 'شعبان', 'رمضان', 'شوال', 'ذی\u200cالقعده', 'ذی\u200cالحجه',
  ];

  static String _toPersianDigits(String s) {
    const String latin = '0123456789';
    const String persian = '۰۱۲۳۴۵۶۷۸۹';
    final StringBuffer out = StringBuffer();
    for (int i = 0; i < s.length; i++) {
      final int idx = latin.indexOf(s[i]);
      out.write(idx >= 0 ? persian[idx] : s[i]);
    }
    return out.toString();
  }

  // ------------------------------------------------------------ day numbers

  /// Days since 1970-01-01 of the *local calendar date* of [d].
  static int _epochDay(DateTime d) =>
      DateTime.utc(d.year, d.month, d.day).millisecondsSinceEpoch ~/ 86400000;

  // ------------------------------------------------- Hijri (Umm al-Qura table)
  // Generated from the Umm al-Qura data of the `hijri-converter` library and
  // verified day-by-day (1980-2075, 0 mismatches). Covers AH 1400..1499.
  // _hijriStarts[i] = epoch day of 1 Muharram of AH (1400 + i); the last entry
  // is the start of AH 1500. _hijriMasks[i] bit m (0 = Muharram) is 1 when
  // that month has 30 days, 0 when it has 29.
  static const int _hijriFirstYear = 1400;
  static const List<int> _hijriStarts = [
    3610, 3965, 4318, 4673, 5027, 5382, 5736, 6091, 6445, 6799, 7153, 7508, 7862, 8217,
    8572, 8926, 9280, 9634, 9988, 10343, 10698, 11053, 11407, 11761, 12115, 12469, 12824,
    13179, 13533, 13888, 14242, 14596, 14950, 15304, 15659, 16013, 16368, 16722, 17076,
    17430, 17785, 18139, 18494, 18848, 19203, 19557, 19911, 20265, 20620, 20975, 21329,
    21683, 22037, 22392, 22746, 23101, 23455, 23810, 24164, 24518, 24872, 25227, 25581,
    25936, 26290, 26645, 26999, 27353, 27707, 28062, 28416, 28771, 29125, 29479, 29833,
    30188, 30542, 30897, 31251, 31606, 31960, 32314, 32668, 33023, 33377, 33732, 34087,
    34441, 34795, 35149, 35503, 35858, 36213, 36567, 36921, 37275, 37629, 37984, 38338,
    38693, 39047,
  ];
  static const List<int> _hijriMasks = [
    3403, 1322, 2647, 1198, 2422, 1388, 2901, 2730, 2645, 1197, 2397, 730, 1497, 3506,
    2980, 2890, 2645, 693, 1397, 2922, 3026, 3012, 2953, 2709, 1325, 1453, 2922, 1748,
    3529, 3474, 2726, 2390, 686, 1389, 874, 2901, 2730, 2381, 1181, 2397, 698, 1461,
    1450, 3413, 2714, 2350, 622, 1373, 2778, 1748, 1701, 1355, 2711, 1358, 2734, 1452,
    2985, 3474, 2853, 1611, 3243, 1370, 2901, 1746, 3749, 3658, 2709, 1325, 2733, 876,
    1881, 1746, 1685, 1325, 2651, 1210, 2490, 948, 2921, 2898, 2726, 1206, 2413, 748,
    1753, 3762, 3412, 3370, 2646, 1198, 2413, 3434, 2900, 2857, 2707, 1323, 2647, 1334,
    2741, 1706,
  ];

  /// Returns [year, month, day] or null when outside the table.
  static List<int>? _hijriFromEpochDay(int d) {
    if (d < _hijriStarts[0] || d >= _hijriStarts[_hijriStarts.length - 1]) {
      return null;
    }
    int yi = 0;
    for (int i = 0; i < _hijriMasks.length; i++) {
      if (_hijriStarts[i] <= d) {
        yi = i;
      } else {
        break;
      }
    }
    int rem = d - _hijriStarts[yi];
    int m = 0;
    while (m < 12) {
      final int len = ((_hijriMasks[yi] >> m) & 1) == 1 ? 30 : 29;
      if (rem < len) break;
      rem -= len;
      m++;
    }
    if (m > 11) return null;
    return [_hijriFirstYear + yi, m + 1, rem + 1];
  }

  // ------------------------------------------- Jalali (port of jalaali-js)
  // Verified against the `jdatetime` library on every day 1950-2100 and
  // against the astronomical `convertdate` implementation on samples and all
  // Nowruz boundaries (0 mismatches). Division/modulo deliberately truncate
  // toward zero, exactly like the JavaScript original.
  static int _div(int a, int b) => a ~/ b;
  static int _mod(int a, int b) => a - (a ~/ b) * b;

  static const List<int> _jBreaks = [
    -61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060, 2097,
    2192, 2262, 2324, 2394, 2456, 3178,
  ];

  /// Returns [leap, gy, march].
  static List<int> _jalCal(int jy) {
    final int bl = _jBreaks.length;
    final int gy = jy + 621;
    int leapJ = -14;
    int jp = _jBreaks[0];
    int jump = 0;
    for (int i = 1; i < bl; i++) {
      final int jm = _jBreaks[i];
      jump = jm - jp;
      if (jy < jm) break;
      leapJ = leapJ + _div(jump, 33) * 8 + _div(_mod(jump, 33), 4);
      jp = jm;
    }
    int n = jy - jp;
    leapJ = leapJ + _div(n, 33) * 8 + _div(_mod(n, 33) + 3, 4);
    if (_mod(jump, 33) == 4 && jump - n == 4) leapJ += 1;
    final int leapG = _div(gy, 4) - _div((_div(gy, 100) + 1) * 3, 4) - 150;
    final int march = 20 + leapJ - leapG;
    if (jump - n < 6) n = n - jump + _div(jump + 4, 33) * 33;
    int leap = _mod(_mod(n + 1, 33) - 1, 4);
    if (leap == -1) leap = 4;
    return [leap, gy, march];
  }

  static int _g2d(int gy, int gm, int gd) {
    int d = _div((gy + _div(gm - 8, 6) + 100100) * 1461, 4) +
        _div(153 * _mod(gm + 9, 12) + 2, 5) +
        gd -
        34840408;
    d = d - _div(_div(gy + 100100 + _div(gm - 8, 6), 100) * 3, 4) + 752;
    return d;
  }

  /// Returns the Gregorian year of a Julian day number.
  static int _d2gYear(int jdn) {
    int j = 4 * jdn + 139361631;
    j = j + _div(_div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908;
    final int i = _div(_mod(j, 1461), 4) * 5 + 308;
    final int gm = _mod(_div(i, 153), 12) + 1;
    return _div(j, 1461) - 100100 + _div(8 - gm, 6);
  }

  /// Returns [year, month, day] of the Jalali date for [epochDay].
  static List<int> _jalaliFromEpochDay(int epochDay) {
    final int jdn = epochDay + 2440588; // JDN of 1970-01-01
    final int gy = _d2gYear(jdn);
    int jy = gy - 621;
    final List<int> r = _jalCal(jy);
    final int jdn1f = _g2d(gy, 3, r[2]);
    int k = jdn - jdn1f;
    if (k >= 0) {
      if (k <= 185) {
        return [jy, 1 + _div(k, 31), _mod(k, 31) + 1];
      }
      k -= 186;
    } else {
      jy -= 1;
      k += 179;
      if (r[0] == 1) k += 1;
    }
    return [jy, 7 + _div(k, 30), _mod(k, 30) + 1];
  }
}
