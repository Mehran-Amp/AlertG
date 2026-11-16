import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:bitcoin_checker/core/services/server_alert_service.dart';
import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_draft.dart';
import 'package:bitcoin_checker/features/iran_bourse/localization/bourse_strings.dart';
import 'package:bitcoin_checker/features/iran_bourse/models/bourse_quote.dart';

/// IB-11d-1: the alert draft, the rule it builds, and proof that the app's normal sync sends
/// exactly what the server's Bourse validation expects. Values: real Ayar capture.
const String ayarId = '34144395039913458';

BourseAlertDraft draft({
  BourseAlertKind kind = BourseAlertKind.price,
  AlertDirection direction = AlertDirection.above,
  double? amount = 700000,
  num? prevClose = 668554,
  num? lastPrice = 668761,
  num? upperLimit = 735409,
  num? lowerLimit = 601699,
  String? note,
  bool recurring = false,
  String instrumentId = ayarId,
  String ticker = 'عیار',
}) {
  return BourseAlertDraft(
    instrumentId: instrumentId,
    ticker: ticker,
    name: 'صندوق طلای عیار مفید',
    kind: kind,
    direction: direction,
    amount: amount,
    prevClose: prevClose,
    lastPrice: lastPrice,
    upperLimit: upperLimit,
    lowerLimit: lowerLimit,
    note: note,
    recurring: recurring,
  );
}

class _CapturingClient extends http.BaseClient {
  String? lastRequestBody;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    lastRequestBody = await request.finalize().bytesToString();
    return http.StreamedResponse(Stream.value(http.Response('{}', 200).bodyBytes), 200);
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('validate', () {
    test('a good draft is valid', () {
      expect(draft().validate(), isNull);
    });

    test('the instrument id must be 12-20 digits, as a String', () {
      for (final bad in ['', '123', 'abc', '1' * 21, '3414439503991345x']) {
        expect(draft(instrumentId: bad).validate(), BourseAlertProblem.invalidInstrument, reason: bad);
      }
    });

    test('both-sides is not offered in v1', () {
      expect(draft(direction: AlertDirection.bothSides).validate(), BourseAlertProblem.directionNotSupported);
    });

    test('the amount must be a positive, finite number', () {
      expect(draft(amount: null).validate(), BourseAlertProblem.amountMissing);
      expect(draft(amount: double.nan).validate(), BourseAlertProblem.amountMissing);
      expect(draft(amount: double.infinity).validate(), BourseAlertProblem.amountMissing);
      expect(draft(amount: 0).validate(), BourseAlertProblem.amountNotPositive);
      expect(draft(amount: -5).validate(), BourseAlertProblem.amountNotPositive);
    });

    test('change alerts need yesterday\'s close, price alerts do not', () {
      for (final kind in [BourseAlertKind.percentChange, BourseAlertKind.absoluteChange]) {
        expect(draft(kind: kind, amount: 3, prevClose: null).validate(), BourseAlertProblem.noPreviousClose);
        expect(draft(kind: kind, amount: 3, prevClose: 0).validate(), BourseAlertProblem.noPreviousClose);
        expect(draft(kind: kind, amount: 3).validate(), isNull);
      }
      expect(draft(prevClose: null).validate(), isNull);
    });
  });

  group('triggerPrice and warning', () {
    test('price level', () {
      expect(draft(amount: 700000).triggerPrice, 700000);
      expect(draft(amount: 700000).warning(), isNull);
    });

    test('percent and Rial change are measured from yesterday\'s close', () {
      final up = draft(kind: BourseAlertKind.percentChange, amount: 3).triggerPrice!;
      expect(up, closeTo(668554 * 1.03, 0.01));
      final down = draft(kind: BourseAlertKind.percentChange, amount: 3, direction: AlertDirection.below).triggerPrice!;
      expect(down, closeTo(668554 * 0.97, 0.01));
      expect(draft(kind: BourseAlertKind.absoluteChange, amount: 10000).triggerPrice, 678554);
      expect(
        draft(kind: BourseAlertKind.absoluteChange, amount: 10000, direction: AlertDirection.below).triggerPrice,
        658554,
      );
    });

    test('a target above today\'s upper limit is unreachable', () {
      expect(draft(amount: 800000).warning(), BourseAlertWarning.unreachableToday);
      expect(draft(kind: BourseAlertKind.percentChange, amount: 20).warning(), BourseAlertWarning.unreachableToday);
      expect(draft(kind: BourseAlertKind.absoluteChange, amount: 100000).warning(), BourseAlertWarning.unreachableToday);
    });

    test('a target below today\'s lower limit is unreachable', () {
      expect(draft(amount: 600000, direction: AlertDirection.below).warning(), BourseAlertWarning.unreachableToday);
      expect(
        draft(kind: BourseAlertKind.percentChange, amount: 20, direction: AlertDirection.below).warning(),
        BourseAlertWarning.unreachableToday,
      );
    });

    test('a condition that is already true is flagged', () {
      expect(draft(amount: 668000).warning(), BourseAlertWarning.alreadyReached); // last 668761 >= 668000
      expect(draft(amount: 700000, direction: AlertDirection.below).warning(), BourseAlertWarning.alreadyReached);
    });

    test('a reachable change alert has no warning', () {
      expect(draft(kind: BourseAlertKind.percentChange, amount: 3).warning(), isNull);
      expect(draft(kind: BourseAlertKind.percentChange, amount: 3, direction: AlertDirection.below).warning(), isNull);
      expect(draft(kind: BourseAlertKind.absoluteChange, amount: 10000).warning(), isNull);
    });

    test('unknown limits or last price give no warning, and nothing throws', () {
      expect(draft(amount: 800000, upperLimit: null).warning(), isNull);
      expect(draft(amount: 668000, lastPrice: null).warning(), isNull);
      expect(draft(amount: null).warning(), isNull);
      expect(draft(amount: 5, kind: BourseAlertKind.percentChange, prevClose: null).warning(), isNull);
      expect(draft(direction: AlertDirection.bothSides).warning(), isNull);
    });
  });

  group('toRule', () {
    test('price alert', () {
      final r = draft(amount: 700000, note: '  هدف اول  ').toRule();
      expect(r.exchangeId, 'tsetmc');
      expect(r.marketSymbol, ayarId);
      expect(r.marketSymbol, isA<String>());
      expect(r.baseCurrency, 'عیار');
      expect(r.counterCurrency, 'IRR');
      expect(r.conditionType, AlertConditionType.priceThreshold);
      expect(r.direction, AlertDirection.above);
      expect(r.targetPrice, 700000.0);
      expect(r.percent, isNull);
      expect(r.deltaAbsolute, isNull);
      expect(r.basePrice, 668761.0); // price alert starts from the last price
      expect(r.customNote, 'هدف اول'); // trimmed
      expect(r.preferServerProxy, isTrue);
      expect(r.isActive, isTrue);
      expect(r.isTriggered, isFalse);
      expect(r.language, 'fa');
      expect(r.triggerMode, TriggerMode.oneShot);
      expect(r.uuid, isNotEmpty);
    });

    test('percent alert uses yesterday\'s close as base', () {
      final r = draft(kind: BourseAlertKind.percentChange, amount: 3, direction: AlertDirection.below).toRule();
      expect(r.conditionType, AlertConditionType.percentChange);
      expect(r.direction, AlertDirection.below);
      expect(r.percent, 3.0);
      expect(r.targetPrice, isNull);
      expect(r.basePrice, 668554.0);
    });

    test('Rial-change alert uses yesterday\'s close as base and fires once by default', () {
      final r = draft(kind: BourseAlertKind.absoluteChange, amount: 10000).toRule();
      expect(r.conditionType, AlertConditionType.absolutePriceChange);
      expect(r.deltaAbsolute, 10000.0);
      expect(r.targetPrice, isNull);
      expect(r.basePrice, 668554.0);
      expect(r.triggerMode, TriggerMode.oneShot); // AlertRule.create alone would make it recurring
    });

    test('recurring is opt-in', () {
      expect(draft(recurring: true).toRule().triggerMode, TriggerMode.recurring);
      expect(draft(kind: BourseAlertKind.absoluteChange, amount: 1, recurring: true).toRule().triggerMode,
          TriggerMode.recurring);
    });

    test('an empty or blank note becomes null', () {
      expect(draft(note: '   ').toRule().customNote, isNull);
      expect(draft(note: null).toRule().customNote, isNull);
    });

    test('a missing ticker falls back to the name, then the id', () {
      expect(draft(ticker: '').toRule().baseCurrency, 'صندوق طلای عیار مفید');
      final noNames = BourseAlertDraft(
        instrumentId: ayarId,
        ticker: '',
        name: '',
        kind: BourseAlertKind.price,
        direction: AlertDirection.above,
        amount: 1,
      );
      expect(noNames.toRule().baseCurrency, ayarId);
    });

    test('an invalid draft is refused', () {
      expect(() => draft(amount: null).toRule(), throwsArgumentError);
      expect(() => draft(instrumentId: '12').toRule(), throwsArgumentError);
      expect(() => draft(direction: AlertDirection.bothSides).toRule(), throwsArgumentError);
    });

    test('the rule survives the local save and load (toJson / fromJson)', () {
      final r = draft(amount: 700000).toRule();
      final back = AlertRule.fromJson(jsonDecode(jsonEncode(r.toJson())) as Map<String, dynamic>);
      expect(back.marketSymbol, ayarId);
      expect(back.exchangeId, 'tsetmc');
      expect(back.baseCurrency, 'عیار');
      expect(back.counterCurrency, 'IRR');
      expect(back.targetPrice, 700000.0);
      expect(back.triggerMode, TriggerMode.oneShot);
    });

    test('fromQuote copies the instrument, base price and limits', () {
      final quote = BourseQuote(
        symbol: ayarId,
        ticker: 'عیار',
        name: 'صندوق طلای عیار مفید',
        state: BourseState.closed,
        price: 668761,
        prevClose: 668554,
        upperLimit: 735409,
        lowerLimit: 601699,
      );
      final d = BourseAlertDraft.fromQuote(
        quote,
        kind: BourseAlertKind.percentChange,
        direction: AlertDirection.above,
        amount: 3,
        note: 'n',
      );
      expect(d.instrumentId, ayarId);
      expect(d.ticker, 'عیار');
      expect(d.prevClose, 668554);
      expect(d.lastPrice, 668761);
      expect(d.upperLimit, 735409);
      expect(d.lowerLimit, 601699);
      expect(d.note, 'n');
      expect(d.validate(), isNull);
    });
  });

  group('what the app\'s sync sends to the server', () {
    late _CapturingClient client;

    setUp(() {
      ServerAlertService.registerLoadFailedProvider(() => false);
      ServerAlertService.setBaseUrlForTesting('https://example.invalid');
      client = _CapturingClient();
      ServerAlertService.httpClientForTesting = client;
    });

    tearDown(() {
      ServerAlertService.registerLoadFailedProvider(() => false);
      ServerAlertService.setBaseUrlForTesting('https://example.invalid');
      ServerAlertService.httpClientForTesting = null;
    });

    Future<Map<String, dynamic>> syncedAlert(AlertRule rule) async {
      final ok = await ServerAlertService.syncAllRulesToServer([rule]);
      expect(ok, isTrue);
      final body = jsonDecode(client.lastRequestBody!) as Map<String, dynamic>;
      final alerts = body['alerts'] as List;
      expect(alerts, hasLength(1));
      return Map<String, dynamic>.from(alerts.single as Map);
    }

    test('price alert', () async {
      final rule = draft(amount: 700000).toRule();
      final a = await syncedAlert(rule);
      expect(a['id'], rule.uuid);
      expect(a['exchange'], 'tsetmc');
      expect(a['symbol'], ayarId); // the id, as a String
      expect(a['symbol'], isA<String>());
      expect(a['target_price'], 700000);
      expect(a['condition'], 'ABOVE');
      expect(a['condition_type'], 'priceThreshold');
      expect(a['base_currency'], 'عیار');
      expect(a['counter_currency'], 'IRR');
      expect(a['market_symbol'], ayarId); // the server replaces it with the ticker
      expect(a['trigger_mode'], 'oneShot');
      expect(a['prefer_server_proxy'], isTrue);
      expect(a['is_active'], isTrue);
      final raw = Map<String, dynamic>.from(a['raw_rule'] as Map);
      expect(raw['marketSymbol'], ayarId);
      expect(raw['marketSymbol'], isA<String>());
      expect(raw['exchangeId'], 'tsetmc');
      expect(raw.containsKey('price_field'), isFalse); // the server's default is "last"
    });

    test('a below alert says BELOW', () async {
      final a = await syncedAlert(draft(amount: 650000, direction: AlertDirection.below).toRule());
      expect(a['condition'], 'BELOW');
    });

    test('percent alert carries percent and the daily base', () async {
      final a = await syncedAlert(
          draft(kind: BourseAlertKind.percentChange, amount: 3, direction: AlertDirection.below).toRule());
      expect(a['condition_type'], 'percentChange');
      expect(a['percent'], 3.0);
      expect(a['base_price'], 668554.0);
      expect(a['condition'], 'BELOW');
    });

    test('Rial-change alert carries delta_absolute', () async {
      final a = await syncedAlert(draft(kind: BourseAlertKind.absoluteChange, amount: 10000).toRule());
      expect(a['condition_type'], 'absolutePriceChange');
      expect(a['delta_absolute'], 10000.0);
      expect(a['base_price'], 668554.0);
      expect(a['trigger_mode'], 'oneShot');
    });

    test('note is sent when present', () async {
      final a = await syncedAlert(draft(note: 'هدف اول').toRule());
      expect(a['note'], 'هدف اول');
    });

    test('the id string is never turned into a number on the wire', () async {
      await syncedAlert(draft().toRule());
      expect(client.lastRequestBody, contains('"symbol":"$ayarId"'));
      expect(client.lastRequestBody, isNot(contains('"symbol":$ayarId')));
    });
  });

  group('texts', () {
    final persian = RegExp(r'[؀-ۿ]');

    test('every problem, warning and kind has Persian text', () {
      for (final p in BourseAlertProblem.values) {
        expect(persian.hasMatch(BourseStrings.alertProblem(p)), isTrue, reason: '$p');
      }
      for (final w in BourseAlertWarning.values) {
        expect(persian.hasMatch(BourseStrings.alertWarning(w)), isTrue, reason: '$w');
      }
      for (final k in BourseAlertKind.values) {
        expect(persian.hasMatch(BourseStrings.alertKindLabel(k)), isTrue, reason: '$k');
      }
    });
  });
}
