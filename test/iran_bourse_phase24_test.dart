import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:bitcoin_checker/core/services/fcm_notification_service.dart';
import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_api.dart';
import 'package:bitcoin_checker/features/iran_bourse/alerts/bourse_alert_draft.dart';

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
}
