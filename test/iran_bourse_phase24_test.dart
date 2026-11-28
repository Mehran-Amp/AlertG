import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:bitcoin_checker/core/services/fcm_notification_service.dart';
import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_api.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_draft.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_form_page.dart';
import 'package:bitcoin_checker/features/iran_bourse/localization/bourse_strings.dart';
import 'package:bitcoin_checker/features/iran_bourse/models/bourse_quote.dart';
import 'package:bitcoin_checker/features/settings/models/app_settings.dart';

void main() {
  const String fooladId = '46348559193224090';

  group('Phase 24d — sound, flags, and TTS for queueBuy, queueSell, volumeAbove', () {
    test('BourseAlertDraft.toRule and BourseAlertApi.create preserve custom sound and channel flags', () async {
      final capturedPayloads = <Map<String, dynamic>>[];

      final api = BourseAlertApi(
        client: MockClient((req) async {
          capturedPayloads.add(jsonDecode(req.body) as Map<String, dynamic>);
          return http.Response('{"ok":true}', 200);
        }),
        baseUrl: () => 'https://srv.test',
        apiKey: () => 'k',
        userId: () async => 'u1',
        fcmToken: () async => 'tok1',
      );

      final drafts = <BourseAlertDraft>[
        const BourseAlertDraft(
          instrumentId: fooladId,
          ticker: 'فولاد',
          name: 'فولاد مبارکه اصفهان',
          kind: BourseAlertKind.queueBuy,
          direction: AlertDirection.above,
          amount: null,
          minQueueVolume: 500000,
          lastPrice: 4100,
        ),
        const BourseAlertDraft(
          instrumentId: fooladId,
          ticker: 'فولاد',
          name: 'فولاد مبارکه اصفهان',
          kind: BourseAlertKind.queueSell,
          direction: AlertDirection.below,
          amount: null,
          lastPrice: 3900,
        ),
        const BourseAlertDraft(
          instrumentId: fooladId,
          ticker: 'فولاد',
          name: 'فولاد مبارکه اصفهان',
          kind: BourseAlertKind.volumeAbove,
          direction: AlertDirection.above,
          amount: 25000000,
          lastPrice: 4050,
        ),
      ];

      final expectedConditionTypes = ['queueBuy', 'queueSell', 'volumeAbove'];
      final customSounds = ['digital_alarm', 'sonar_ping', 'bell_ring'];

      for (int i = 0; i < drafts.length; i++) {
        final rule = drafts[i].toRule(
          customSound: customSounds[i],
          soundEnabled: i != 1, // test sound off on queueSell
          vibrationEnabled: i != 2, // test vibration off on volumeAbove
          flashEnabled: i == 0, // test flash on for queueBuy
          ttsEnabled: true,
        );
        final res = await api.create(rule);
        expect(res.isOk, isTrue);

        final payload = capturedPayloads[i];
        expect(payload['exchange'], 'tsetmc');
        expect(payload['condition_type'], expectedConditionTypes[i]);
        expect(payload['sound'], customSounds[i]);
        expect(payload['sound_enabled'], i != 1);
        expect(payload['vibration_enabled'], i != 2);
        expect(payload['flash_enabled'], i == 0);
        expect(payload['tts_enabled'], isTrue);
      }
    });

    test('buildBourseAlertSpeech formats Persian queue, volume, and price speech without instrument ID or dollars', () {
      final queueBuySpeech = buildBourseAlertSpeech({
        'exchange': 'tsetmc',
        'symbol': fooladId,
        'ticker': 'فولاد',
        'name': 'فولاد مبارکه اصفهان',
        'condition_type': 'queueBuy',
        'alert_category': 'queue',
        'price': '4200',
        'note': 'بررسی سفارش',
      });
      expect(queueBuySpeech, contains('صف خرید'));
      expect(queueBuySpeech, contains('فولاد مبارکه اصفهان'));
      expect(queueBuySpeech, contains('4200 ریال'));
      expect(queueBuySpeech, contains('بررسی سفارش'));
      expect(queueBuySpeech, isNot(contains(fooladId)));
      expect(queueBuySpeech.toLowerCase(), isNot(contains('dollar')));

      final queueSellSpeech = buildBourseAlertSpeech({
        'exchange': 'tsetmc',
        'symbol': fooladId,
        'ticker': 'فولاد',
        'name': 'فولاد مبارکه اصفهان',
        'condition_type': 'queueSell',
        'alert_category': 'queue',
        'price': '3800',
      });
      expect(queueSellSpeech, contains('صف فروش'));
      expect(queueSellSpeech, contains('3800 ریال'));
      expect(queueSellSpeech, isNot(contains(fooladId)));

      final volumeSpeech = buildBourseAlertSpeech({
        'exchange': 'tsetmc',
        'symbol': fooladId,
        'ticker': 'فولاد',
        'name': 'فولاد مبارکه اصفهان',
        'condition_type': 'volumeAbove',
        'alert_category': 'volume',
        'volume': '25000000',
      });
      expect(volumeSpeech, contains('حجم معاملات'));
      expect(volumeSpeech, contains('25000000 سهم'));
      expect(volumeSpeech, isNot(contains(fooladId)));

      final priceSpeech = buildBourseAlertSpeech({
        'exchange': 'tsetmc',
        'symbol': fooladId,
        'ticker': 'فولاد',
        'price': '4100',
      });
      expect(priceSpeech, contains('فولاد'));
      expect(priceSpeech, contains('4100 ریال'));
      expect(priceSpeech, isNot(contains(fooladId)));
    });
  });

  group('Phase 24c — Option A immediate-fire warning when symbol is already in buy/sell queue', () {
    BourseQuote makeQueueQuote({
      String state = 'LIVE',
      bool alertEligible = true,
      bool tradedToday = true,
      String? queue,
      num price = 4210,
      num upperLimit = 4210,
      num lowerLimit = 3970,
      Map<String, dynamic>? bestBid,
      Map<String, dynamic>? bestAsk,
    }) =>
        BourseQuote.tryParse({
          'symbol': fooladId,
          'ticker': 'توریل',
          'name': 'توکاریل',
          'state': state,
          'alert_eligible': alertEligible,
          'traded_today': tradedToday,
          'price': price,
          'prev_close': 4090,
          'upper_limit': upperLimit,
          'lower_limit': lowerLimit,
          'volume': 12000000,
          'queue': queue,
          'best_bid': bestBid,
          'best_ask': bestAsk,
          'unit': 'IRR',
        })!;

    BourseAlertApi okApi(List<http.Request> log) => BourseAlertApi(
          client: MockClient((r) async {
            log.add(r);
            return http.Response('{"status":"ok"}', 200);
          }),
          baseUrl: () => 'https://srv.test',
          apiKey: () => 'k',
          userId: () async => 'u1',
          fcmToken: () async => 'tok1',
        );

    Future<void> tapVisible(WidgetTester t, Finder finder) async {
      await t.ensureVisible(finder);
      await t.tap(finder);
      await t.pumpAndSettle();
    }

    testWidgets('shows immediate-fire warning for live buy queue, allows submit, and respects minQueueVolume', (t) async {
      final requests = <http.Request>[];
      final saved = <AlertRule>[];
      final quote = makeQueueQuote(
        queue: 'buy',
        bestBid: {'price': 4210, 'volume': 3000000, 'orders': 24},
        bestAsk: {'price': 4250, 'volume': 1000, 'orders': 2}, // out-of-band ask above upperLimit
      );

      await t.pumpWidget(MaterialApp(
        theme: const AppSettings(themePalette: AppThemePalette.darkSapphire).buildThemeData(),
        home: BourseAlertFormPage(
          quote: quote,
          api: okApi(requests),
          onCreated: (rule) async => saved.add(rule),
        ),
      ));

      await tapVisible(t, find.byKey(const Key('bourse_kind_queueBuy')));
      expect(find.byKey(const Key('bourse_form_warning')), findsOneWidget);
      expect(
        find.text('این نماد همین الان در صف خرید است. با ثبت، فوراً اعلان می‌گیرید.'),
        findsOneWidget,
      );

      // Switching to queueSell hides the buy-queue warning
      await tapVisible(t, find.byKey(const Key('bourse_kind_queueSell')));
      expect(find.byKey(const Key('bourse_form_warning')), findsNothing);

      // Back to queueBuy: minQueueVolume above current bid (5,000,000 > 3,000,000) clears warning
      await tapVisible(t, find.byKey(const Key('bourse_kind_queueBuy')));
      await t.ensureVisible(find.byKey(const Key('bourse_form_min_queue_volume')));
      await t.enterText(find.byKey(const Key('bourse_form_min_queue_volume')), '5000000');
      await t.pumpAndSettle();
      expect(find.byKey(const Key('bourse_form_warning')), findsNothing);

      // Clearing minQueueVolume restores the warning and submission still succeeds (warning never blocks)
      await t.enterText(find.byKey(const Key('bourse_form_min_queue_volume')), '');
      await t.pumpAndSettle();
      expect(find.byKey(const Key('bourse_form_warning')), findsOneWidget);

      await tapVisible(t, find.byKey(const Key('bourse_form_submit')));
      expect(requests, hasLength(1));
      expect(saved.single.conditionType, AlertConditionType.queueBuy);
    });

    testWidgets('shows immediate-fire warning for live sell queue and allows submit', (t) async {
      final requests = <http.Request>[];
      final saved = <AlertRule>[];
      final quote = makeQueueQuote(
        queue: 'sell',
        price: 3970,
        bestBid: null,
        bestAsk: {'price': 3970, 'volume': 4900000, 'orders': 15},
      );

      await t.pumpWidget(MaterialApp(
        theme: const AppSettings(themePalette: AppThemePalette.lightSapphire).buildThemeData(),
        home: BourseAlertFormPage(
          quote: quote,
          api: okApi(requests),
          onCreated: (rule) async => saved.add(rule),
        ),
      ));

      await tapVisible(t, find.byKey(const Key('bourse_kind_queueSell')));
      expect(find.byKey(const Key('bourse_form_warning')), findsOneWidget);
      expect(
        find.text('این نماد همین الان در صف فروش است. با ثبت، فوراً اعلان می‌گیرید.'),
        findsOneWidget,
      );

      await tapVisible(t, find.byKey(const Key('bourse_form_submit')));
      expect(requests, hasLength(1));
      expect(saved.single.conditionType, AlertConditionType.queueSell);
    });

    testWidgets('does not show immediate-fire queue warning when market is CLOSED', (t) async {
      final quote = makeQueueQuote(
        state: 'CLOSED',
        alertEligible: false,
        queue: 'buy',
        bestBid: {'price': 4210, 'volume': 3000000, 'orders': 24},
      );

      await t.pumpWidget(MaterialApp(
        home: BourseAlertFormPage(
          quote: quote,
          api: okApi([]),
          onCreated: (_) async {},
        ),
      ));

      await tapVisible(t, find.byKey(const Key('bourse_kind_queueBuy')));
      expect(find.byKey(const Key('bourse_form_warning')), findsNothing);
    });

    test('quote queue detection rejects false positive when fillable opposite order exists at limit', () {
      final notAQueue = makeQueueQuote(
        queue: null,
        price: 2590,
        upperLimit: 2590,
        lowerLimit: 2440,
        bestBid: {'price': 2589, 'volume': 15000, 'orders': 1},
        bestAsk: {'price': 2590, 'volume': 1620401, 'orders': 8},
      );
      expect(notAQueue.isCurrentlyInBuyQueue, isFalse);

      final draft = BourseAlertDraft.fromQuote(
        notAQueue,
        kind: BourseAlertKind.queueBuy,
        direction: AlertDirection.above,
        amount: null,
      );
      expect(draft.warning(), isNull);
      expect(BourseStrings.alertWarning(BourseAlertWarning.alreadyInBuyQueue), contains('صف خرید'));
      expect(BourseStrings.alertWarning(BourseAlertWarning.alreadyInSellQueue), contains('صف فروش'));
    });
  });
}

