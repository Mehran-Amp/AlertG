import 'package:flutter_test/flutter_test.dart';
import 'package:bitcoin_checker/features/notifications/background/persistent_notification_text.dart';

/// Expected values below were cross-checked with the Python libraries
/// `jdatetime` (Jalali, 1950-2100 day by day), `convertdate` (astronomical
/// Persian calendar, Nowruz boundaries) and `hijri-converter` (Umm al-Qura).
void main() {
  // 2026-11-06 is a Friday.
  final DateTime friday = DateTime(2026, 11, 6, 12, 0);

  group('Jalali title', () {
    test('2026-11-06 is 15 Aban 1405 (English and Persian digits/names)', () {
      expect(
        PersistentNotificationText.title(friday,
            calendar: NotificationCalendar.jalali, lang: 'en'),
        'Friday \u00b7 15 Aban 1405',
      );
      expect(
        PersistentNotificationText.title(friday,
            calendar: NotificationCalendar.jalali, lang: 'fa'),
        'جمعه \u00b7 ۱۵ آبان ۱۴۰۵',
      );
    });

    test('leap year boundary: 1403 has 30 Esfand, Nowruz 1404 and 1405', () {
      String en(DateTime d) => PersistentNotificationText.title(d,
          calendar: NotificationCalendar.jalali, lang: 'en');
      expect(en(DateTime(2025, 3, 20)), 'Thursday \u00b7 30 Esfand 1403');
      expect(en(DateTime(2025, 3, 21)), 'Friday \u00b7 1 Farvardin 1404');
      expect(en(DateTime(2026, 3, 21)), 'Saturday \u00b7 1 Farvardin 1405');
    });
  });

  group('Gregorian title', () {
    test('English and Persian', () {
      expect(
        PersistentNotificationText.title(friday,
            calendar: NotificationCalendar.gregorian, lang: 'en'),
        'Friday \u00b7 6 Nov 2026',
      );
      expect(
        PersistentNotificationText.title(friday,
            calendar: NotificationCalendar.gregorian, lang: 'fa'),
        'جمعه \u00b7 ۶ نوامبر ۲۰۲۶',
      );
    });

    test('languages other than fa use English names', () {
      expect(
        PersistentNotificationText.title(friday,
            calendar: NotificationCalendar.gregorian, lang: 'ar'),
        'Friday \u00b7 6 Nov 2026',
      );
    });
  });

  group('Hijri title', () {
    test('2026-11-06 is 26 Jumada I 1448; offset moves one day', () {
      String en(int off) => PersistentNotificationText.title(friday,
          calendar: NotificationCalendar.hijri, lang: 'en', hijriOffsetDays: off);
      expect(en(0), 'Friday \u00b7 26 Jumada I 1448');
      expect(en(1), 'Friday \u00b7 27 Jumada I 1448');
      expect(en(-1), 'Friday \u00b7 25 Jumada I 1448');
      // Offsets beyond +-1 are clamped.
      expect(en(5), 'Friday \u00b7 27 Jumada I 1448');
    });

    test('Persian names and digits', () {
      expect(
        PersistentNotificationText.title(friday,
            calendar: NotificationCalendar.hijri, lang: 'fa'),
        'جمعه \u00b7 ۲۶ جمادی\u200cالاول ۱۴۴۸',
      );
    });

    test('date outside the built-in table falls back to Gregorian', () {
      expect(
        PersistentNotificationText.title(DateTime(2100, 6, 1),
            calendar: NotificationCalendar.hijri, lang: 'en'),
        'Tuesday \u00b7 1 Jun 2100',
      );
    });
  });

  group('preferences and status line', () {
    test("'auto' follows language; explicit choice always wins", () {
      expect(PersistentNotificationText.resolveCalendar('auto', 'fa'),
          NotificationCalendar.jalali);
      expect(PersistentNotificationText.resolveCalendar('auto', 'en'),
          NotificationCalendar.gregorian);
      // English app language with the Jalali calendar chosen by the user.
      expect(PersistentNotificationText.resolveCalendar('jalali', 'en'),
          NotificationCalendar.jalali);
      expect(PersistentNotificationText.resolveCalendar('hijri', 'fa'),
          NotificationCalendar.hijri);
      expect(PersistentNotificationText.sanitizePref('nonsense'), 'auto');
      expect(PersistentNotificationText.sanitizePref(null), 'auto');
      expect(PersistentNotificationText.sanitizePref('jalali'), 'jalali');
    });

    test('status line is honest about the server', () {
      expect(
          PersistentNotificationText.statusLine(isFromServer: true, lang: 'en'),
          'server 24/7 online');
      expect(
          PersistentNotificationText.statusLine(isFromServer: false, lang: 'en'),
          'server offline \u00b7 local monitoring');
      expect(
          PersistentNotificationText.statusLine(isFromServer: true, lang: 'fa'),
          'سرور ۲۴/۷ آنلاین');
      expect(
          PersistentNotificationText.statusLine(isFromServer: false, lang: 'fa'),
          'سرور قطع است \u00b7 پایش محلی');
    });
  });
}
