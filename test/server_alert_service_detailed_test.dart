import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:bitcoin_checker/core/services/server_alert_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ServerAlertService.fetchPriceViaServerDetailed Unit Tests', () {
    setUp(() {
      ServerAlertService.setBaseUrlForTesting('https://test.aisocialfeed.com');
      ServerAlertService.httpClientForTesting = null;
    });

    tearDown(() {
      ServerAlertService.httpClientForTesting = null;
    });

    test('1. HTTP 200 with positive price returns price, asOf, state, source, and null reason', () async {
      final mockClient = MockClient((request) async {
        expect(request.method, equals('GET'));
        expect(request.url.path, equals('/api/price/binance/BTCUSDT'));
        return http.Response(
          jsonEncode({
            'status': 'ok',
            'exchange': 'binance',
            'symbol': 'BTCUSDT',
            'price': 68542.50,
            'source': 'binance',
            'asOf': 1731320000,
            'state': 'LIVE',
            'currency': 'USD',
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      });

      final result = await ServerAlertService.fetchPriceViaServerDetailed(
        'binance',
        'BTC/USDT',
        client: mockClient,
      );

      expect(result['price'], equals(68542.50));
      expect(result['httpStatus'], equals(200));
      expect(result['reason'], isNull);
      expect(result['ms'], isA<int>());
      expect(result['ms'] as int, greaterThanOrEqualTo(0));
      expect(result['asOf'], equals(1731320000));
      expect(result['state'], equals('LIVE'));
      expect(result['source'], equals('binance'));
    });

    test('2. HTTP 502 returns null price and http_502 reason', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          jsonEncode({'detail': 'Unable to fetch live price from market sources.'}),
          502,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      });

      final result = await ServerAlertService.fetchPriceViaServerDetailed(
        'binance',
        'BTCUSDT',
        client: mockClient,
      );

      expect(result['price'], isNull);
      expect(result['httpStatus'], equals(502));
      expect(result['reason'], equals('http_502'));
      expect(result['ms'], isA<int>());
      expect(result['ms'] as int, greaterThanOrEqualTo(0));
      expect(result['asOf'], isNull);
      expect(result['state'], isNull);
      expect(result['source'], isNull);
    });

    test('3. Timeout returns null price and timeout reason', () async {
      final mockClient = MockClient((request) async {
        throw TimeoutException('Request timed out after 8s');
      });

      final result = await ServerAlertService.fetchPriceViaServerDetailed(
        'binance',
        'BTCUSDT',
        client: mockClient,
      );

      expect(result['price'], isNull);
      expect(result['httpStatus'], isNull);
      expect(result['reason'], equals('timeout'));
      expect(result['ms'], isA<int>());
      expect(result['ms'] as int, greaterThanOrEqualTo(0));
      expect(result['asOf'], isNull);
      expect(result['state'], isNull);
      expect(result['source'], isNull);
    });

    test('4a. Malformed body (non-JSON text) returns bad_body reason', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          '<html><head><title>502 Bad Gateway</title></head><body>502 Bad Gateway</body></html>',
          200,
          headers: {'content-type': 'text/html'},
        );
      });

      final result = await ServerAlertService.fetchPriceViaServerDetailed(
        'binance',
        'BTCUSDT',
        client: mockClient,
      );

      expect(result['price'], isNull);
      expect(result['httpStatus'], equals(200));
      expect(result['reason'], equals('bad_body'));
      expect(result['ms'], isA<int>());
      expect(result['asOf'], isNull);
    });

    test('4b. Malformed body (JSON array instead of map) returns bad_body reason', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          jsonEncode([1, 2, 3]),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final result = await ServerAlertService.fetchPriceViaServerDetailed(
        'binance',
        'BTCUSDT',
        client: mockClient,
      );

      expect(result['price'], isNull);
      expect(result['httpStatus'], equals(200));
      expect(result['reason'], equals('bad_body'));
    });

    test('4c. Malformed body (missing price field) returns bad_body reason', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'status': 'ok',
            'exchange': 'binance',
            'symbol': 'BTCUSDT',
            'asOf': 1731320000,
            'state': 'LIVE',
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final result = await ServerAlertService.fetchPriceViaServerDetailed(
        'binance',
        'BTCUSDT',
        client: mockClient,
      );

      expect(result['price'], isNull);
      expect(result['httpStatus'], equals(200));
      expect(result['reason'], equals('bad_body'));
      expect(result['asOf'], equals(1731320000));
      expect(result['state'], equals('LIVE'));
    });

    test('4d. Malformed body (non-numeric price field) returns bad_body reason', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'status': 'ok',
            'price': 'not_a_number',
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final result = await ServerAlertService.fetchPriceViaServerDetailed(
        'binance',
        'BTCUSDT',
        client: mockClient,
      );

      expect(result['price'], isNull);
      expect(result['httpStatus'], equals(200));
      expect(result['reason'], equals('bad_body'));
    });

    test('5a. Zero price (price == 0.0) returns nonpositive reason', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'status': 'ok',
            'exchange': 'binance',
            'symbol': 'BTCUSDT',
            'price': 0.0,
            'asOf': 1731320000,
            'state': 'LIVE',
            'source': 'binance',
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final result = await ServerAlertService.fetchPriceViaServerDetailed(
        'binance',
        'BTCUSDT',
        client: mockClient,
      );

      expect(result['price'], isNull);
      expect(result['httpStatus'], equals(200));
      expect(result['reason'], equals('nonpositive'));
      expect(result['asOf'], equals(1731320000));
      expect(result['state'], equals('LIVE'));
      expect(result['source'], equals('binance'));
    });

    test('5b. Negative price (price < 0.0) returns nonpositive reason', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'status': 'ok',
            'exchange': 'binance',
            'symbol': 'BTCUSDT',
            'price': -12.34,
            'asOf': 1731320000,
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final result = await ServerAlertService.fetchPriceViaServerDetailed(
        'binance',
        'BTCUSDT',
        client: mockClient,
      );

      expect(result['price'], isNull);
      expect(result['httpStatus'], equals(200));
      expect(result['reason'], equals('nonpositive'));
      expect(result['asOf'], equals(1731320000));
    });

    test('6. Network exception returns null price and network reason', () async {
      final mockClient = MockClient((request) async {
        throw http.ClientException('Connection refused');
      });

      final result = await ServerAlertService.fetchPriceViaServerDetailed(
        'binance',
        'BTCUSDT',
        client: mockClient,
      );

      expect(result['price'], isNull);
      expect(result['httpStatus'], isNull);
      expect(result['reason'], equals('network'));
      expect(result['ms'], isA<int>());
    });

    test('7. Uses injected httpClientForTesting when client parameter is omitted', () async {
      ServerAlertService.httpClientForTesting = MockClient((request) async {
        return http.Response(
          jsonEncode({'price': 1234.56}),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final result = await ServerAlertService.fetchPriceViaServerDetailed(
        'binance',
        'ETHUSDT',
      );

      expect(result['price'], equals(1234.56));
      expect(result['httpStatus'], equals(200));
      expect(result['reason'], isNull);
    });
  });
}
