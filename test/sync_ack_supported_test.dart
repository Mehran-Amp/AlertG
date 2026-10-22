import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:bitcoin_checker/core/services/server_alert_service.dart';
import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';

class _CapturingClient extends http.BaseClient {
  String? lastRequestBody;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    lastRequestBody = await request.finalize().bytesToString();
    return http.StreamedResponse(
      Stream.value(http.Response('{}', 200).bodyBytes),
      200,
    );
  }
}

AlertRule _createDummyRule({required String uuid}) {
  return AlertRule(
    uuid: uuid,
    baseCurrency: 'BTC',
    counterCurrency: 'USDT',
    marketSymbol: 'BTCUSDT',
    exchangeId: 'binance',
    checkIntervalSeconds: 60,
    conditionType: AlertConditionType.priceThreshold,
    direction: AlertDirection.above,
    triggerMode: TriggerMode.oneShot,
    targetPrice: 50000,
    isActive: true,
    isTriggered: false,
    createdAt: DateTime.now(),
  );
}

void main() {
  group('ServerAlertService 2A-4d ack_supported flag', () {
    tearDown(() {
      ServerAlertService.registerLoadFailedProvider(() => false);
      ServerAlertService.setBaseUrlForTesting('https://example.invalid');
      ServerAlertService.httpClientForTesting = null;
    });

    test('sync request body includes ack_supported: true at top level', () async {
      ServerAlertService.registerLoadFailedProvider(() => false);
      ServerAlertService.setBaseUrlForTesting('https://example.invalid');

      final client = _CapturingClient();
      ServerAlertService.httpClientForTesting = client;

      final rule = _createDummyRule(uuid: 'rule-ack-test-1');
      final result = await ServerAlertService.syncAllRulesToServer([rule]);

      expect(result, isTrue);
      expect(client.lastRequestBody, isNotNull);

      final Map<String, dynamic> bodyJson = jsonDecode(client.lastRequestBody!) as Map<String, dynamic>;
      expect(bodyJson['ack_supported'], isTrue);
    });
  });
}
