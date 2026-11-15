import 'package:intl/intl.dart';

/// Number and price text for the Iranian Bourse screens.
///
/// All prices are Rial (IRR). Nothing here converts units (rule D1).
/// Digits are Latin by default, like the rest of the app and the server notifications;
/// pass `persianDigits: true` to get ۰-۹ instead.
class BourseFormat {
  static const String dash = '—';
  static const String rialWord = 'ریال';

  static final NumberFormat _grouped = NumberFormat('#,###', 'en_US');

  /// Rial amount as text: `693,731 ریال`. `null`, NaN or infinite values give [dash].
  static String rial(num? value, {bool persianDigits = false}) {
    final n = _fmt(value);
    if (n == null) return dash;
    return _digits('$n $rialWord', persianDigits);
  }

  /// Plain grouped number (volumes, NAV without unit): `65,135,046`.
  static String number(num? value, {bool persianDigits = false}) {
    final n = _fmt(value);
    if (n == null) return dash;
    return _digits(n, persianDigits);
  }

  /// Signed percent with two decimals: `+0.46%`, `-1.20%`, `0.00%`.
  static String signedPercent(double? value, {bool persianDigits = false}) {
    if (value == null || value.isNaN || value.isInfinite) return dash;
    final body = value.abs().toStringAsFixed(2);
    final String text;
    if (body == '0.00') {
      text = '0.00%';
    } else {
      text = '${value > 0 ? '+' : '-'}$body%';
    }
    return _digits(text, persianDigits);
  }

  /// Day range text: `low تا high` in Rial without the unit word, e.g. `668,545 تا 677,950`.
  /// Returns [dash] unless both ends are present.
  static String range(num? low, num? high, {bool persianDigits = false}) {
    final l = _fmt(low);
    final h = _fmt(high);
    if (l == null || h == null) return dash;
    return _digits('$l تا $h', persianDigits);
  }

  /// Time of day in Tehran (UTC+03:30, no daylight saving) as `HH:mm:ss`, from a UTC moment.
  /// Returns [dash] for null.
  static String tehranTime(DateTime? utc, {bool persianDigits = false}) {
    if (utc == null) return dash;
    final t = utc.toUtc().add(const Duration(hours: 3, minutes: 30));
    String two(int v) => v.toString().padLeft(2, '0');
    return _digits('${two(t.hour)}:${two(t.minute)}:${two(t.second)}', persianDigits);
  }

  /// Converts Latin digits and separators to Persian ones: `1,234.5` -> `۱٬۲۳۴٫۵`.
  static String toPersianDigits(String input) {
    const latin = '0123456789';
    const persian = '۰۱۲۳۴۵۶۷۸۹';
    final out = StringBuffer();
    for (final ch in input.split('')) {
      final i = latin.indexOf(ch);
      if (i >= 0) {
        out.write(persian[i]);
      } else if (ch == ',') {
        out.write('٬');
      } else if (ch == '.') {
        out.write('٫');
      } else if (ch == '%') {
        out.write('٪');
      } else {
        out.write(ch);
      }
    }
    return out.toString();
  }

  static String _digits(String s, bool persian) => persian ? toPersianDigits(s) : s;

  /// Rounded, grouped integer text, or null for a missing / non-finite value.
  static String? _fmt(num? v) {
    if (v == null) return null;
    if (v is double && (v.isNaN || v.isInfinite)) return null;
    return _grouped.format(v.round());
  }
}
