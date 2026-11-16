import 'package:flutter_test/flutter_test.dart';

import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_draft.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_text.dart';

/// IB-11f: wording of Bourse alerts in the alert list.
const String ayarId = '34144395039913458';

AlertRule rule(BourseAlertKind kind, AlertDirection dir, double amount) => BourseAlertDraft(
      instrumentId: ayarId,
      ticker: 'عیار',
      name: 'x',
      kind: kind,
      direction: dir,
      amount: amount,
      prevClose: 668554,
      lastPrice: 668761,
    ).toRule();

void main() {
  test('price level: Rial with grouping, both directions', () {
    expect(bourseAlertDescription(rule(BourseAlertKind.price, AlertDirection.above, 700000), persianDigits: false),
        'عبور قیمت به بالاتر از 700,000 ریال');
    expect(bourseAlertDescription(rule(BourseAlertKind.price, AlertDirection.below, 650000), persianDigits: false),
        'عبور قیمت به پایین‌تر از 650,000 ریال');
  });

  test('percent change is versus yesterday, with no time window', () {
    final up = bourseAlertDescription(rule(BourseAlertKind.percentChange, AlertDirection.above, 3), persianDigits: false);
    expect(up, 'تغییر قیمت +3٪ نسبت به قیمت دیروز');
    final down = bourseAlertDescription(rule(BourseAlertKind.percentChange, AlertDirection.below, 2.5), persianDigits: false);
    expect(down, 'تغییر قیمت -2.5٪ نسبت به قیمت دیروز');
    expect(up, isNot(contains('1m')));
  });

  test('Rial change is in Rial, never dollars', () {
    final text = bourseAlertDescription(rule(BourseAlertKind.absoluteChange, AlertDirection.above, 5000), persianDigits: false);
    expect(text, 'تغییر قیمت +5,000 ریال نسبت به قیمت دیروز');
    expect(text, isNot(contains(r'$')));
    expect(text, isNot(contains('دلاری')));
  });

  test('Persian digits when asked', () {
    expect(bourseAlertDescription(rule(BourseAlertKind.percentChange, AlertDirection.above, 3)),
        'تغییر قیمت +۳٪ نسبت به قیمت دیروز');
    expect(bourseAlertDescription(rule(BourseAlertKind.price, AlertDirection.above, 700000)),
        'عبور قیمت به بالاتر از ۷۰۰٬۰۰۰ ریال');
  });
}
