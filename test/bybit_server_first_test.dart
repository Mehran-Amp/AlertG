import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:bitcoin_checker/core/services/server_alert_service.dart';
import 'package:bitcoin_checker/features/exchanges/base/currency_pair.dart';
import 'package:bitcoin_checker/features/exchanges/bybit/bybit_exchange.dart';

class _MockDioAdapter implements HttpClientAdapter {
  final ResponseBody Function(RequestOptions options) onFetch;
  _MockDioAdapter(this.onFetch);

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    return onFetch(options);
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('BybitExchange Server-First Pricing Unit Tests (PHASE F2)', () {
    const pairBtc = CurrencyPair(
      baseCurrency: 'BTC',
      counterCurrency: 'USDT',
      marketSymbol: 'BTCUSDT',
    );

    setUp(() {
      ServerAlertService.setBaseUrlForTesting('https://test.aisocialfeed.com');
      ServerAlertService.httpClientForTesting = null;
      BybitExchange.serverFirstOverrideForTesting = null;
    });

    tearDown(() {
      ServerAlertService.httpClientForTesting = null;
      BybitExchange.serverFirstOverrideForTesting = null;
    });

    test('1. server wins: when server returns price, it builds ticker without direct fetch', () async {
      ServerAlertService.httpClientForTesting = MockClient((request) async {
        expect(request.url.path, equals('/api/price/bybit/BTCUSDT'));
        return http.Response(
          jsonEncode({
            'status': 'ok',
            'exchange': 'bybit',
            'symbol': 'BTCUSDT',
            'price': 76543.21,
            'source': 'bybit',
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      bool directDioCalled = false;
      final dio = Dio()
        ..httpClientAdapter = _MockDioAdapter((options) {
          directDioCalled = true;
          return ResponseBody.fromString('{"result":{"list":[]}}', 200);
        });

      final exchange = BybitExchange(dio: dio);
      final ticker = await exchange.fetchTicker(pairBtc);

      expect(ticker.lastPrice, equals(76543.21));
      expect(ticker.volume24h, equals(0.0));
      expect(ticker.exchangeId, equals('bybit'));
      expect(directDioCalled, isFalse);
    });

    test('2. server null falls back to direct: when server fails, it runs existing direct Dio code', () async {
      ServerAlertService.httpClientForTesting = MockClient((request) async {
        return http.Response('{"detail": "Gateway Error"}', 502);
      });

      bool directDioCalled = false;
      final dio = Dio()
        ..httpClientAdapter = _MockDioAdapter((options) {
          directDioCalled = true;
          expect(options.path, equals('/v5/market/tickers'));
          expect(options.queryParameters['symbol'], equals('BTCUSDT'));
          return ResponseBody.fromString(
            jsonEncode({
              'result': {
                'list': [
                  {
                    'symbol': 'BTCUSDT',
                    'lastPrice': '69800.50',
                    'volume24h': '1420.75',
                    'highPrice24h': '70500.00',
                    'lowPrice24h': '68900.00',
                  }
                ]
              }
            }),
            200,
            headers: {
              Headers.contentTypeHeader: [Headers.jsonContentType],
            },
          );
        });

      final exchange = BybitExchange(dio: dio);
      final ticker = await exchange.fetchTicker(pairBtc);

      expect(directDioCalled, isTrue);
      expect(ticker.lastPrice, equals(69800.50));
      expect(ticker.volume24h, equals(1420.75));
      expect(ticker.high24h, equals(70500.00));
      expect(ticker.low24h, equals(68900.00));
    });

    test('3. switch off = old behavior: when serverFirst is false, server is bypassed and direct Dio is used', () async {
      bool serverClientCalled = false;
      ServerAlertService.httpClientForTesting = MockClient((request) async {
        serverClientCalled = true;
        return http.Response(jsonEncode({'price': 99999.0}), 200);
      });

      bool directDioCalled = false;
      final dio = Dio()
        ..httpClientAdapter = _MockDioAdapter((options) {
          directDioCalled = true;
          return ResponseBody.fromString(
            jsonEncode({
              'result': {
                'list': [
                  {
                    'symbol': 'BTCUSDT',
                    'lastPrice': '65400.00',
                    'volume24h': '850.00',
                  }
                ]
              }
            }),
            200,
            headers: {
              Headers.contentTypeHeader: [Headers.jsonContentType],
            },
          );
        });

      final exchange = BybitExchange(dio: dio, serverFirst: false);
      final ticker = await exchange.fetchTicker(pairBtc);

      expect(serverClientCalled, isFalse);
      expect(directDioCalled, isTrue);
      expect(ticker.lastPrice, equals(65400.00));
      expect(ticker.volume24h, equals(850.00));
    });

    test('4. fetchSnapshot calls fetchTicker and preserves price and volume', () async {
      ServerAlertService.httpClientForTesting = MockClient((request) async {
        return http.Response(
          jsonEncode({'price': 72100.0}),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final exchange = BybitExchange();
      final snapshot = await exchange.fetchSnapshot(pairBtc);

      expect(snapshot.price, equals(72100.0));
      expect(snapshot.volume, equals(0.0));
    });
  });
}
