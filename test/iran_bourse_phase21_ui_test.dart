import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_api.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_draft.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_form_page.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_text.dart';
import 'package:bitcoin_checker/features/iran_bourse/localization/bourse_strings.dart';
import 'package:bitcoin_checker/features/iran_bourse/models/bourse_quote.dart';
import 'package:bitcoin_checker/features/settings/models/app_settings.dart';

const String _torilId = '37389789764168256';

BourseQuote _quote({num? volume = 37782645}) => BourseQuote.tryParse({
      'price': 4210,
      'state': 'LIVE',
      'alert_eligible': true,
      'asOf': 1795000000,
      'symbol': _torilId,
      'ticker': 'توریل',
      'name': 'توکاریل',
      'prev_close': 4090,
      'upper_limit': 4210,
      'lower_limit': 3970,
      'volume': volume,
      'traded_today': true,
      'unit': 'IRR',
    })!;

http.Response _ok() => http.Response.bytes(
      utf8.encode(jsonEncode({'status': 'ok'})),
      200,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );

class _Harness {
  final List<http.Request> requests = [];
  final List<AlertRule> saved = [];

  BourseAlertApi get api => BourseAlertApi(
        client: MockClient((r) async {
          requests.add(r);
          return _ok();
        }),
        baseUrl: () => 'https://srv.test',
        apiKey: () => 'k',
        userId: () async => 'u1',
        fcmToken: () async => 'tok',
      );

  Widget page({AppThemePalette palette = AppThemePalette.darkSapphire}) => MaterialApp(
        theme: AppSettings(themePalette: palette).buildThemeData(),
        home: BourseAlertFormPage(
          quote: _quote(),
          api: api,
          onCreated: (rule) async => saved.add(rule),
        ),
      );

  Map<String, dynamic> get lastBody => jsonDecode(utf8.decode(requests.last.bodyBytes)) as Map<String, dynamic>;
}

Future<void> _tapVisible(WidgetTester t, Finder finder) async {
  await t.ensureVisible(finder);
  await t.tap(finder);
  await t.pumpAndSettle();
}

void main() {
  group('Phase 21d — Iranian Bourse queueBuy, queueSell & volumeAbove UI', () {
    testWidgets('queueBuy hides direction/price basis and submits without min_queue_volume', (t) async {
      final h = _Harness();
      await t.pumpWidget(h.page());

      await _tapVisible(t, find.byKey(const Key('bourse_kind_queueBuy')));
      expect(find.byKey(const Key('bourse_form_direction')), findsNothing);
      expect(find.byKey(const Key('bourse_form_price_field')), findsNothing);
      expect(find.byKey(const Key('bourse_form_queue_note')), findsOneWidget);
      expect(find.byKey(const Key('bourse_form_min_queue_volume')), findsOneWidget);

      await _tapVisible(t, find.byKey(const Key('bourse_form_submit')));

      expect(h.requests, hasLength(1));
      expect(h.lastBody['condition_type'], 'queueBuy');
      expect(h.lastBody['target_price'], 0.0);
      final raw = h.lastBody['raw_rule'] as Map<String, dynamic>;
      expect(raw.containsKey('min_queue_volume'), isFalse);
      expect(h.saved.single.conditionType, AlertConditionType.queueBuy);
      expect(h.saved.single.minQueueVolume, isNull);
    });

    testWidgets('queueSell submits optional min_queue_volume and round-trips through JSON', (t) async {
      final h = _Harness();
      await t.pumpWidget(h.page(palette: AppThemePalette.lightSapphire));

      await _tapVisible(t, find.byKey(const Key('bourse_kind_queueSell')));
      await t.ensureVisible(find.byKey(const Key('bourse_form_min_queue_volume')));
      await t.enterText(find.byKey(const Key('bourse_form_min_queue_volume')), '2500000');
      await t.pumpAndSettle();

      expect(find.byKey(const Key('bourse_form_queue_vol_preview')), findsOneWidget);
      expect(find.text('2,500,000 سهم'), findsOneWidget);

      await _tapVisible(t, find.byKey(const Key('bourse_form_submit')));

      expect(h.requests, hasLength(1));
      expect(h.lastBody['condition_type'], 'queueSell');
      final raw = h.lastBody['raw_rule'] as Map<String, dynamic>;
      expect(raw['min_queue_volume'], 2500000.0);

      final roundTripped = AlertRule.fromJson(h.saved.single.toJson());
      expect(roundTripped.conditionType, AlertConditionType.queueSell);
      expect(roundTripped.minQueueVolume, 2500000.0);
    });

    testWidgets('volumeAbove shows today volume hint and submits share threshold in target_price', (t) async {
      final h = _Harness();
      await t.pumpWidget(h.page());

      await _tapVisible(t, find.byKey(const Key('bourse_kind_volumeAbove')));
      expect(find.byKey(const Key('bourse_form_direction')), findsNothing);
      expect(find.byKey(const Key('bourse_form_today_volume')), findsOneWidget);

      await t.ensureVisible(find.byKey(const Key('bourse_form_amount')));
      await t.enterText(find.byKey(const Key('bourse_form_amount')), '15000000');
      await t.pumpAndSettle();

      expect(find.text('15,000,000 سهم'), findsOneWidget);
      await _tapVisible(t, find.byKey(const Key('bourse_form_submit')));

      expect(h.requests, hasLength(1));
      expect(h.lastBody['condition_type'], 'volumeAbove');
      expect(h.lastBody['target_price'], 15000000.0);
      expect(h.saved.single.conditionType, AlertConditionType.volumeAbove);
      expect(h.saved.single.targetPrice, 15000000.0);
    });

    testWidgets('volumeAbove blocks empty or zero share count with validation message', (t) async {
      final h = _Harness();
      await t.pumpWidget(h.page());

      await _tapVisible(t, find.byKey(const Key('bourse_kind_volumeAbove')));
      await _tapVisible(t, find.byKey(const Key('bourse_form_submit')));

      expect(find.text(BourseStrings.alertProblem(BourseAlertProblem.amountMissing)), findsOneWidget);
      expect(h.requests, isEmpty);
    });

    test('bourseAlertDescription formats queueBuy, queueSell, and volumeAbove in Persian', () {
      final buyPlain = BourseAlertDraft(
        instrumentId: _torilId,
        ticker: 'توریل',
        name: 'توکاریل',
        kind: BourseAlertKind.queueBuy,
        direction: AlertDirection.above,
        amount: null,
      ).toRule();
      expect(bourseAlertDescription(buyPlain, persianDigits: false), 'ورود به صف خرید');

      final sellMin = BourseAlertDraft(
        instrumentId: _torilId,
        ticker: 'توریل',
        name: 'توکاریل',
        kind: BourseAlertKind.queueSell,
        direction: AlertDirection.below,
        amount: null,
        minQueueVolume: 1000000,
      ).toRule();
      expect(bourseAlertDescription(sellMin, persianDigits: false), 'ورود به صف فروش (حداقل 1,000,000 سهم)');

      final volRule = BourseAlertDraft(
        instrumentId: _torilId,
        ticker: 'توریل',
        name: 'توکاریل',
        kind: BourseAlertKind.volumeAbove,
        direction: AlertDirection.above,
        amount: 20000000,
      ).toRule();
      expect(bourseAlertDescription(volRule, persianDigits: false), 'حجم معاملات امروز ≥ 20,000,000 سهم');
    });
  });
}
