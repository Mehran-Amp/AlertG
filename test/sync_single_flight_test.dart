import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:bitcoin_checker/core/services/server_alert_service.dart';
import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';

class _GatedClient extends http.BaseClient {
  int requestCount = 0;
  final List<Completer<void>> gates = [];
  final List<String> bodies = [];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    requestCount++;
    bodies.add(await request.finalize().bytesToString());

    if (requestCount == 1) {
      final completer = Completer<void>();
      gates.add(completer);
      await completer.future;
    }

    return http.StreamedResponse(
      Stream.value(http.Response('{}', 200).bodyBytes),
      200,
    );
  }
}


/// HTTP client that responds immediately with 200 and counts requests.
class _ImmediateClient extends http.BaseClient {
  int requestCount = 0;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    requestCount++;
    await request.finalize().bytesToString();
    return http.StreamedResponse(
      Stream.value(http.Response('{}', 200).bodyBytes),
      200,
    );
  }
}



AlertRule _makeRule({required String uuid}) {
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
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ServerAlertService single-flight', () {
    tearDown(() {
      ServerAlertService.registerLoadFailedProvider(() => false);
      ServerAlertService.setBaseUrlForTesting('https://example.invalid');
      ServerAlertService.httpClientForTesting = null;
    });

    test('a second call during an in-flight sync runs once more with its own rules', () async {
      ServerAlertService.registerLoadFailedProvider(() => false);
      ServerAlertService.setBaseUrlForTesting('https://example.invalid');
      final client = _GatedClient();
      ServerAlertService.httpClientForTesting = client;

      final ruleA = _makeRule(uuid: 'rule-a');
      final ruleB = _makeRule(uuid: 'rule-b');

      final firstFuture = ServerAlertService.syncAllRulesToServer([ruleA]);

      await Future<void>.delayed(const Duration(milliseconds: 100));
      expect(client.requestCount, 1);

      final secondResult = await ServerAlertService.syncAllRulesToServer([ruleB]);
      expect(secondResult, isFalse);

      client.gates.first.complete();

      final firstResult = await firstFuture;
      expect(firstResult, isTrue);

      expect(client.requestCount, 2);
      expect(client.bodies.last, contains('rule-b'));
      expect(client.bodies.last, isNot(contains('rule-a')));
    });

    test('after a successful 200, retryIndex is reset to 0', () async {
      ServerAlertService.registerLoadFailedProvider(() => false);
      ServerAlertService.setBaseUrlForTesting('https://example.invalid');

      // Use a client that responds immediately (no gate), so the sync
      // succeeds and we can check that retryIndex was reset.
      ServerAlertService.httpClientForTesting = _ImmediateClient();

      await ServerAlertService.syncAllRulesToServer([_makeRule(uuid: 'rule-1')]);

      expect(ServerAlertService.retryIndexForTesting, 0);
    });

        test('circuit breaker keeps syncPending true and returns false', () async {
      ServerAlertService.registerLoadFailedProvider(() => false);
      ServerAlertService.setBaseUrlForTesting('https://example.invalid');

      // Force the breaker open deterministically (no real network needed).
      ServerAlertService.tripCircuitBreakerForTesting();
      expect(ServerAlertService.isServerAvailable, isFalse);

      // Count requests to prove the circuit-breaker path never hits HTTP.
      final client = _ImmediateClient();
      ServerAlertService.httpClientForTesting = client;

      final ok = await ServerAlertService.syncAllRulesToServer(const []);
      expect(ok, isFalse);
      expect(ServerAlertService.syncPending, isTrue);
      expect(client.requestCount, 0);

      // Clean up: close the breaker so other tests are not affected.
      ServerAlertService.resetCircuitBreakerForTesting();
    });
  });
}