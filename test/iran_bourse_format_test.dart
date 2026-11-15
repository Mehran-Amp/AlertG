import 'package:flutter_test/flutter_test.dart';

import 'package:bitcoin_checker/features/iran_bourse/localization/bourse_strings.dart';
import 'package:bitcoin_checker/features/iran_bourse/models/bourse_quote.dart';
import 'package:bitcoin_checker/features/iran_bourse/services/iran_bourse_service.dart';
import 'package:bitcoin_checker/features/iran_bourse/utils/bourse_format.dart';

/// IB-11b: Rial formatting and Persian texts.
void main() {
  group('BourseFormat.rial', () {
    test('matches the server notification text style', () {
      expect(BourseFormat.rial(693731), '693,731 ریال');
      expect(BourseFormat.rial(668761), '668,761 ریال');
      expect(BourseFormat.rial(65135046), '65,135,046 ریال');
    });

    test('small and zero values', () {
      expect(BourseFormat.rial(0), '0 ریال');
      expect(BourseFormat.rial(7), '7 ریال');
      expect(BourseFormat.rial(999), '999 ریال');
      expect(BourseFormat.rial(1000), '1,000 ریال');
    });

    test('decimals are rounded, never converted to Toman', () {
      expect(BourseFormat.rial(668761.4), '668,761 ریال');
      expect(BourseFormat.rial(668761.5), '668,762 ریال');
      expect(BourseFormat.rial(10), '10 ریال'); // not 1 Toman
    });

    test('missing or non-finite values give a dash', () {
      expect(BourseFormat.rial(null), BourseFormat.dash);
      expect(BourseFormat.rial(double.nan), BourseFormat.dash);
      expect(BourseFormat.rial(double.infinity), BourseFormat.dash);
      expect(BourseFormat.rial(double.negativeInfinity), BourseFormat.dash);
    });

    test('very large amounts keep full precision as integers', () {
      expect(BourseFormat.rial(34144395039913), '34,144,395,039,913 ریال');
    });

    test('Persian digits are optional', () {
      expect(BourseFormat.rial(693731, persianDigits: true), '۶۹۳٬۷۳۱ ریال');
      expect(BourseFormat.rial(null, persianDigits: true), BourseFormat.dash);
    });
  });

  group('BourseFormat.number / range / percent', () {
    test('number groups thousands', () {
      expect(BourseFormat.number(65135046), '65,135,046');
      expect(BourseFormat.number(null), BourseFormat.dash);
    });

    test('range needs both ends', () {
      expect(BourseFormat.range(668545, 677950), '668,545 تا 677,950');
      expect(BourseFormat.range(null, 677950), BourseFormat.dash);
      expect(BourseFormat.range(668545, null), BourseFormat.dash);
    });

    test('signed percent', () {
      expect(BourseFormat.signedPercent(0.46), '+0.46%');
      expect(BourseFormat.signedPercent(-1.2), '-1.20%');
      expect(BourseFormat.signedPercent(0), '0.00%');
      expect(BourseFormat.signedPercent(0.001), '0.00%'); // rounds to zero: no sign
      expect(BourseFormat.signedPercent(-0.004), '0.00%');
      expect(BourseFormat.signedPercent(null), BourseFormat.dash);
      expect(BourseFormat.signedPercent(double.nan), BourseFormat.dash);
    });

    test('percent in Persian digits', () {
      expect(BourseFormat.signedPercent(0.46, persianDigits: true), '+۰٫۴۶٪');
    });

    test('toPersianDigits converts digits and separators only', () {
      expect(BourseFormat.toPersianDigits('1,234.5'), '۱٬۲۳۴٫۵');
      expect(BourseFormat.toPersianDigits('abc ریال 09'), 'abc ریال ۰۹');
      expect(BourseFormat.toPersianDigits(''), '');
    });
  });

  group('BourseStrings', () {
    final persianLetters = RegExp(r'[؀-ۿ]');

    test('every failure has a distinct Persian message', () {
      final seen = <String>{};
      for (final f in BourseFailure.values) {
        final m = BourseStrings.failureMessage(f);
        expect(m.trim(), isNotEmpty, reason: '$f');
        expect(persianLetters.hasMatch(m), isTrue, reason: '$f has no Persian text');
        expect(seen.add(m), isTrue, reason: '$f duplicates another message');
      }
      expect(seen.length, BourseFailure.values.length);
    });

    test('every state has a label and a description in Persian', () {
      for (final s in BourseState.values) {
        final label = BourseStrings.stateLabel(s);
        final desc = BourseStrings.stateDescription(s);
        expect(persianLetters.hasMatch(label), isTrue, reason: '$s label');
        expect(persianLetters.hasMatch(desc), isTrue, reason: '$s description');
      }
      expect(BourseStrings.stateLabel(BourseState.live), isNot(BourseStrings.stateLabel(BourseState.closed)));
    });

    test('disabled message tells the user the market is not enabled for them', () {
      expect(BourseStrings.failureMessage(BourseFailure.disabled), contains('فعال نشده'));
    });

    test('unit note and the Rial word agree', () {
      expect(BourseStrings.unitNote, contains(BourseFormat.rialWord));
    });
  });
}
