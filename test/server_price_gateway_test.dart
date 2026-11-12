import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:bitcoin_checker/core/services/server_alert_service.dart';
import 'package:bitcoin_checker/features/exchanges/base/currency_pair.dart';
import 'package:bitcoin_checker/features/exchanges/base/server_price_gateway.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ServerPriceGateway.fetch Unit Tests', () {
    const pairBtc = CurrencyPair(
      baseCurrency: 'BTC',
      counterCurrency: 'USDT',
      marketSymbol: 'BTCUSDT',
    );

    setUp(() {
      ServerAlertService.setBaseUrlForTesting('https://test.aisocialfeed.com');
      ServerAlertService.httpClientForTesting = null;
    });

    tearDown(() {
      ServerAlertService.httpClientForTesting = null;
    });

    test('1. success returns PriceSnapshot with price, asOf, state, source, and null volume', () async {
      final mockClient = MockClient((request) async {
        expect(request.method, equals('GET'));
        expect(request.url.path, equals('/api/price/binance/BTCUSDT'));
        return http.Response(
          jsonEncode({
            'status': 'ok',
            'exchange': 'binance',
            'symbol': 'BTCUSDT',
            'price': 68500.50,
            'source': 'binance',
            'asOf': 1731320000,
            'state': 'LIVE',
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      });

      final snapshot = await ServerPriceGateway.fetch(
        'binance',
        pairBtc,
        client: mockClient,
      );

      expect(snapshot, isNotNull);
      expect(snapshot!.price, equals(68500.50));
      expect(snapshot.volume, isNull);
      expect(
        snapshot.asOf,
        equals(DateTime.fromMillisecondsSinceEpoch(1731320000 * 1000, isUtc: true)),
      );
      expect(snapshot.state, equals('LIVE'));
      expect(snapshot.source, equals('binance'));
      expect(snapshot.fetchedAt, isNotNull);
    });

    test('2. 502 server error returns null without throwing', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          jsonEncode({'detail': 'Unable to fetch live price'}),
          502,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      });

      final snapshot = await ServerPriceGateway.fetch(
        'binance',
        pairBtc,
        client: mockClient,
      );

      expect(snapshot, isNull);
    });

    test('3. timeout returns null without throwing', () async {
      final mockClient = MockClient((request) async {
        throw TimeoutException('Simulated timeout after 8s');
      });

      final snapshot = await ServerPriceGateway.fetch(
        'binance',
        pairBtc,
        client: mockClient,
      );

      expect(snapshot, isNull);
    });

    test('4. bad body returns null without throwing', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          '<html>Bad Gateway</html>',
          200,
          headers: {'content-type': 'text/html'},
        );
      });

      final snapshot = await ServerPriceGateway.fetch(
        'binance',
        pairBtc,
        client: mockClient,
      );

      expect(snapshot, isNull);
    });

    test('5. price <= 0 returns null without throwing', () async {
      final mockClientZero = MockClient((request) async {
        return http.Response(
          jsonEncode({'status': 'ok', 'price': 0.0}),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final snapshotZero = await ServerPriceGateway.fetch(
        'binance',
        pairBtc,
        client: mockClientZero,
      );
      expect(snapshotZero, isNull);

      final mockClientNegative = MockClient((request) async {
        return http.Response(
          jsonEncode({'status': 'ok', 'price': -12.5}),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final snapshotNeg = await ServerPriceGateway.fetch(
        'binance',
        pairBtc,
        client: mockClientNegative,
      );
      expect(snapshotNeg, isNull);
    });

    test('6. empty marketSymbol fallback uses baseCurrency + counterCurrency', () async {
      String? requestedPath;
      final mockClient = MockClient((request) async {
        requestedPath = request.url.path;
        return http.Response(
          jsonEncode({'status': 'ok', 'price': 3450.75}),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      const pairEmptySymbol = CurrencyPair(
        baseCurrency: 'ETH',
        counterCurrency: 'USDT',
        marketSymbol: '',
      );

      final snapshot = await ServerPriceGateway.fetch(
        'binance',
        pairEmptySymbol,
        client: mockClient,
      );

      expect(requestedPath, equals('/api/price/binance/ETHUSDT'));
      expect(snapshot, isNotNull);
      expect(snapshot!.price, equals(3450.75));
    });

    test("7. marketSymbol 'ALEPH_USDT' sent unchanged with underscore", () async {
      String? requestedPath;
      final mockClient = MockClient((request) async {
        requestedPath = request.url.path;
        return http.Response(
          jsonEncode({'status': 'ok', 'price': 0.285}),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      const pairAleph = CurrencyPair(
        baseCurrency: 'ALEPH',
        counterCurrency: 'USDT',
        marketSymbol: 'ALEPH_USDT',
      );

      final snapshot = await ServerPriceGateway.fetch(
        'mexc',
        pairAleph,
        client: mockClient,
      );

      expect(requestedPath, equals('/api/price/mexc/ALEPH_USDT'));
      expect(snapshot, isNotNull);
      expect(snapshot!.price, equals(0.285));
    });

    test('8. log format matches [CryptoPrice] ex=<id> sym=<s> source=server http=<code|none> ms=<n> reason=<r|none>', () async {
      final logs = <String>[];
      final oldDebugPrint = debugPrint;
      debugPrint = (String? message, {int? wrapWidth}) {
        if (message != null) logs.add(message);
      };

      try {
        // Case A: Success 200
        final clientSuccess = MockClient((request) async {
          return http.Response(
            jsonEncode({'price': 100.0}),
            200,
            headers: {'content-type': 'application/json'},
          );
        });
        await ServerPriceGateway.fetch('bybit', pairBtc, client: clientSuccess);

        expect(logs.length, equals(1));
        expect(
          logs.last,
          matches(r'^\[CryptoPrice\] ex=bybit sym=BTCUSDT source=server http=200 ms=\d+ reason=none$'),
        );

        // Case B: 502 Failure
        final client502 = MockClient((request) async {
          return http.Response('error', 502);
        });
        await ServerPriceGateway.fetch('okx', pairBtc, client: client502);

        expect(logs.length, equals(2));
        expect(
          logs.last,
          matches(r'^\[CryptoPrice\] ex=okx sym=BTCUSDT source=server http=502 ms=\d+ reason=http_502$'),
        );

        // Case C: Timeout
        final clientTimeout = MockClient((request) async {
          throw TimeoutException('timeout');
        });
        await ServerPriceGateway.fetch('kraken', pairBtc, client: clientTimeout);

        expect(logs.length, equals(3));
        expect(
          logs.last,
          matches(r'^\[CryptoPrice\] ex=kraken sym=BTCUSDT source=server http=none ms=\d+ reason=timeout$'),
        );
      } finally {
        debugPrint = oldDebugPrint;
      }
    });
  });
}
