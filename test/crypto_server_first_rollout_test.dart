import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:bitcoin_checker/core/services/server_alert_service.dart';
import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';
import 'package:bitcoin_checker/features/alert_engine/repositories/json_alert_rule_repository.dart';
import 'package:bitcoin_checker/features/alert_engine/scheduler/scheduler_service.dart';
import 'package:bitcoin_checker/features/exchanges/base/currency_pair.dart';
import 'package:bitcoin_checker/features/exchanges/base/exchange.dart';
import 'package:bitcoin_checker/features/exchanges/base/exchange_category.dart';
import 'package:bitcoin_checker/features/exchanges/base/server_price_gateway.dart';
import 'package:bitcoin_checker/features/exchanges/base/standard_rest_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/binance/binance_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/bingx/bingx_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/bitget/bitget_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/bybit/bybit_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/coinbase/coinbase_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/gateio/gateio_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/kifpool/kifpool_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/kraken/kraken_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/kucoin/kucoin_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/lbank/lbank_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/mexc/mexc_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/okx/okx_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/registry/exchange_catalog.dart';
import 'package:bitcoin_checker/features/exchanges/registry/exchange_registry.dart';
import 'package:bitcoin_checker/features/exchanges/tabdeal/tabdeal_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/toobit/toobit_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/xt/xt_exchange.dart';
import 'package:bitcoin_checker/features/notifications/models/alert_dispatch_result.dart';
import 'package:bitcoin_checker/features/notifications/services/notification_service_interface.dart';

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

class _NoopNotificationService implements NotificationServiceInterface {
  @override
  Future<void> initialize({void Function(String? payload)? onNotificationTap}) async {}

  @override
  Future<bool> requestPermissions() async => true;

  @override
  Future<bool> showCriticalAlert({
    required int id,
    required String title,
    required String body,
    String? payload,
    String soundName = 'alarm_siren',
    double volume = 1.0,
    bool soundEnabled = true,
    bool vibrationEnabled = true,
    bool flashEnabled = false,
  }) async =>
      true;

  @override
  Future<AlertDispatchResult> enqueueCriticalAlert({
    required int id,
    required String title,
    required String body,
    String? payload,
    String soundName = 'alarm_siren',
    double volume = 1.0,
    bool soundEnabled = true,
    bool vibrationEnabled = true,
    bool flashEnabled = false,
    bool ttsEnabled = false,
    String? speechText,
  }) async =>
      AlertDispatchResult.shown;

  @override
  Future<void> stopActiveAlarm() async {}
}

class _AdapterTestSpec {
  final String id;
  final CurrencyPair pair;
  final Object directJsonPayload;
  final double expectedDirectPrice;
  final Exchange Function(Dio dio, {bool? serverFirst}) builder;

  const _AdapterTestSpec({
    required this.id,
    required this.pair,
    required this.directJsonPayload,
    required this.expectedDirectPrice,
    required this.builder,
  });
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  void resetAllOverrides() {
    ServerAlertService.resetSyncStateForTesting();
    ServerAlertService.setBaseUrlForTesting('https://test.aisocialfeed.com');
    ServerPriceGateway.enabledOverrideForTesting = null;
    BinanceExchange.serverFirstOverrideForTesting = null;
    MEXCExchange.serverFirstOverrideForTesting = null;
    KuCoinExchange.serverFirstOverrideForTesting = null;
    GateioExchange.serverFirstOverrideForTesting = null;
    LBankExchange.serverFirstOverrideForTesting = null;
    OKXExchange.serverFirstOverrideForTesting = null;
    KrakenExchange.serverFirstOverrideForTesting = null;
    BybitExchange.serverFirstOverrideForTesting = null;
    BitgetExchange.serverFirstOverrideForTesting = null;
    BingXExchange.serverFirstOverrideForTesting = null;
    XTExchange.serverFirstOverrideForTesting = null;
    ToobitExchange.serverFirstOverrideForTesting = null;
    CoinbaseExchange.serverFirstOverrideForTesting = null;
    StandardRestExchange.serverFirstOverrideForTesting = null;
    TabdealExchange.serverFirstOverrideForTesting = null;
    KifpoolExchange.serverFirstOverrideForTesting = null;
  }

  setUp(resetAllOverrides);
  tearDown(resetAllOverrides);

  final specs = <_AdapterTestSpec>[
    _AdapterTestSpec(
      id: 'binance',
      pair: const CurrencyPair(baseCurrency: 'BTC', counterCurrency: 'USDT', marketSymbol: 'BTCUSDT'),
      directJsonPayload: {'lastPrice': '68100.25', 'quoteVolume': '1200.0', 'highPrice': '69000.0', 'lowPrice': '67000.0'},
      expectedDirectPrice: 68100.25,
      builder: (dio, {serverFirst}) => BinanceExchange(dio: dio, visionDio: dio, serverFirst: serverFirst),
    ),
    _AdapterTestSpec(
      id: 'mexc',
      pair: const CurrencyPair(baseCurrency: 'BTC', counterCurrency: 'USDT', marketSymbol: 'BTCUSDT'),
      directJsonPayload: {'lastPrice': '68200.50', 'quoteVolume': '950.0'},
      expectedDirectPrice: 68200.50,
      builder: (dio, {serverFirst}) => MEXCExchange(dio: dio, serverFirst: serverFirst),
    ),
    _AdapterTestSpec(
      id: 'kucoin',
      pair: const CurrencyPair(baseCurrency: 'BTC', counterCurrency: 'USDT', marketSymbol: 'BTC-USDT'),
      directJsonPayload: {
        'data': {'price': '68300.75', 'size': '410.0'}
      },
      expectedDirectPrice: 68300.75,
      builder: (dio, {serverFirst}) => KuCoinExchange(dio: dio, serverFirst: serverFirst),
    ),
    _AdapterTestSpec(
      id: 'gateio',
      pair: const CurrencyPair(baseCurrency: 'BTC', counterCurrency: 'USDT', marketSymbol: 'BTC_USDT'),
      directJsonPayload: [
        {'last': '68400.10', 'quote_volume': '500.0'}
      ],
      expectedDirectPrice: 68400.10,
      builder: (dio, {serverFirst}) => GateioExchange(dio: dio, serverFirst: serverFirst),
    ),
    _AdapterTestSpec(
      id: 'lbank',
      pair: const CurrencyPair(baseCurrency: 'BTC', counterCurrency: 'USDT', marketSymbol: 'btc_usdt'),
      directJsonPayload: {
        'data': [
          {
            'ticker': {'latest': '68500.20', 'vol': '300.0'}
          }
        ]
      },
      expectedDirectPrice: 68500.20,
      builder: (dio, {serverFirst}) => LBankExchange(dio: dio, serverFirst: serverFirst),
    ),
    _AdapterTestSpec(
      id: 'okx',
      pair: const CurrencyPair(baseCurrency: 'BTC', counterCurrency: 'USDT', marketSymbol: 'BTC-USDT'),
      directJsonPayload: {
        'data': [
          {'last': '68600.30', 'vol24h': '1500.0'}
        ]
      },
      expectedDirectPrice: 68600.30,
      builder: (dio, {serverFirst}) => OKXExchange(dio: dio, serverFirst: serverFirst),
    ),
    _AdapterTestSpec(
      id: 'kraken',
      pair: const CurrencyPair(baseCurrency: 'BTC', counterCurrency: 'USDT', marketSymbol: 'XBTUSDT'),
      directJsonPayload: {
        'result': {
          'XBTUSDT': {
            'c': ['68700.40', '1.0'],
            'v': ['100.0', '200.0'],
          }
        }
      },
      expectedDirectPrice: 68700.40,
      builder: (dio, {serverFirst}) => KrakenExchange(dio: dio, serverFirst: serverFirst),
    ),
    _AdapterTestSpec(
      id: 'bybit',
      pair: const CurrencyPair(baseCurrency: 'BTC', counterCurrency: 'USDT', marketSymbol: 'BTCUSDT'),
      directJsonPayload: {
        'result': {
          'list': [
            {'symbol': 'BTCUSDT', 'lastPrice': '68800.50', 'volume24h': '800.0'}
          ]
        }
      },
      expectedDirectPrice: 68800.50,
      builder: (dio, {serverFirst}) => BybitExchange(dio: dio, serverFirst: serverFirst),
    ),
    _AdapterTestSpec(
      id: 'bitget',
      pair: const CurrencyPair(baseCurrency: 'BTC', counterCurrency: 'USDT', marketSymbol: 'BTCUSDT'),
      directJsonPayload: {
        'data': [
          {'lastPr': '68900.60', 'usdtVolume': '920.0'}
        ]
      },
      expectedDirectPrice: 68900.60,
      builder: (dio, {serverFirst}) => BitgetExchange(dio: dio, serverFirst: serverFirst),
    ),
    _AdapterTestSpec(
      id: 'bingx',
      pair: const CurrencyPair(baseCurrency: 'BTC', counterCurrency: 'USDT', marketSymbol: 'BTC-USDT'),
      directJsonPayload: {
        'data': [
          {'lastPrice': '69000.70', 'volume': '610.0'}
        ]
      },
      expectedDirectPrice: 69000.70,
      builder: (dio, {serverFirst}) => BingXExchange(dio: dio, serverFirst: serverFirst),
    ),
    _AdapterTestSpec(
      id: 'xt',
      pair: const CurrencyPair(baseCurrency: 'BTC', counterCurrency: 'USDT', marketSymbol: 'btc_usdt'),
      directJsonPayload: {
        'result': [
          {'s': 'btc_usdt', 'p': '69100.80'}
        ]
      },
      expectedDirectPrice: 69100.80,
      builder: (dio, {serverFirst}) => XTExchange(dio: dio, serverFirst: serverFirst),
    ),
    _AdapterTestSpec(
      id: 'toobit',
      pair: const CurrencyPair(baseCurrency: 'BTC', counterCurrency: 'USDT', marketSymbol: 'BTCUSDT'),
      directJsonPayload: [
        {'s': 'BTCUSDT', 'p': '69200.90'}
      ],
      expectedDirectPrice: 69200.90,
      builder: (dio, {serverFirst}) => ToobitExchange(dio: dio, serverFirst: serverFirst),
    ),
    _AdapterTestSpec(
      id: 'coinbase',
      pair: const CurrencyPair(baseCurrency: 'BTC', counterCurrency: 'USDT', marketSymbol: 'BTC-USDT'),
      directJsonPayload: {'price': '69300.15', 'volume': '450.0'},
      expectedDirectPrice: 69300.15,
      builder: (dio, {serverFirst}) => CoinbaseExchange(dio: dio, serverFirst: serverFirst),
    ),
    _AdapterTestSpec(
      id: 'htx',
      pair: const CurrencyPair(baseCurrency: 'BTC', counterCurrency: 'USDT', marketSymbol: 'btcusdt'),
      directJsonPayload: {
        'tick': {'close': 69400.25, 'vol': 1100.0}
      },
      expectedDirectPrice: 69400.25,
      builder: (dio, {serverFirst}) => StandardRestExchange(
        id: 'htx',
        name: 'HTX / Huobi',
        category: ExchangeCategory.tier1,
        countryBadge: 'Global',
        defaultCounterCurrency: 'USDT',
        tickerUrlTemplate: 'https://api.huobi.pro/market/detail/merged?symbol={BASE}{QUOTE}',
        dio: dio,
        serverFirst: serverFirst,
      ),
    ),
    _AdapterTestSpec(
      id: 'poloniex',
      pair: const CurrencyPair(baseCurrency: 'BTC', counterCurrency: 'USDT', marketSymbol: 'BTC_USDT'),
      directJsonPayload: {'close': '69500.35', 'amount': '520.0'},
      expectedDirectPrice: 69500.35,
      builder: (dio, {serverFirst}) => StandardRestExchange(
        id: 'poloniex',
        name: 'Poloniex',
        category: ExchangeCategory.tier1,
        countryBadge: 'Global',
        defaultCounterCurrency: 'USDT',
        tickerUrlTemplate: 'https://api.poloniex.com/markets/{BASE_UPPER}_{QUOTE_UPPER}/ticker24h',
        dio: dio,
        serverFirst: serverFirst,
      ),
    ),
    _AdapterTestSpec(
      id: 'bitfinex',
      pair: const CurrencyPair(baseCurrency: 'BTC', counterCurrency: 'USDT', marketSymbol: 'tBTCUST'),
      directJsonPayload: [69590.0, 10.0, 69610.0, 12.0, 100.0, 0.01, 69600.45, 780.0, 70000.0, 68000.0],
      expectedDirectPrice: 69600.45,
      builder: (dio, {serverFirst}) => StandardRestExchange(
        id: 'bitfinex',
        name: 'Bitfinex',
        category: ExchangeCategory.tier1,
        countryBadge: 'Global',
        defaultCounterCurrency: 'USDT',
        tickerUrlTemplate: 'https://api-pub.bitfinex.com/v2/ticker/t{BASE_UPPER}UST',
        dio: dio,
        serverFirst: serverFirst,
      ),
    ),
    _AdapterTestSpec(
      id: 'tabdeal',
      pair: const CurrencyPair(baseCurrency: 'BTC', counterCurrency: 'USDT', marketSymbol: 'BTCUSDT'),
      directJsonPayload: [
        {'symbol': 'BTC_USDT', 'price': '69700.55', 'volume': '125.0'}
      ],
      expectedDirectPrice: 69700.55,
      builder: (dio, {serverFirst}) => TabdealExchange(dio: dio, serverFirst: serverFirst),
    ),
    _AdapterTestSpec(
      id: 'kifpool',
      pair: const CurrencyPair(baseCurrency: 'BTC', counterCurrency: 'USDT', marketSymbol: 'BTCUSDT'),
      directJsonPayload: [
        {'symbol': 'BTC', 'price': '69800.65', 'volume': '95.0'}
      ],
      expectedDirectPrice: 69800.65,
      builder: (dio, {serverFirst}) => KifpoolExchange(dio: dio, serverFirst: serverFirst),
    ),
  ];

  group('Phase F3 — All 18 Canonical Crypto Exchanges Server-First Rollout', () {
    test('ExchangeCatalog.buildCryptoExchanges() all 18 exchanges resolve via ServerPriceGateway first', () async {
      final requestedPaths = <String>[];
      ServerAlertService.httpClientForTesting = MockClient((request) async {
        requestedPaths.add(request.url.path);
        return http.Response(
          jsonEncode({
            'status': 'ok',
            'price': 77777.77,
            'source': 'server',
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final exchanges = ExchangeCatalog.buildCryptoExchanges();
      expect(exchanges.length, equals(18));

      for (final ex in exchanges) {
        final pair = CurrencyPair(
          baseCurrency: 'BTC',
          counterCurrency: 'USDT',
          marketSymbol: 'BTCUSDT',
        );
        final snapshot = await ex.fetchSnapshot(pair);
        expect(snapshot.price, equals(77777.77), reason: '${ex.id} should return server price');
        expect(snapshot.volume, equals(0.0), reason: '${ex.id} server snapshot volume should be 0.0');
      }

      expect(requestedPaths.length, equals(18));
    });

    for (final spec in specs) {
      test('${spec.id}: (1) server wins without direct call, (2) server null falls back to direct, (3) switch off uses direct', () async {
        // 1. Server wins
        bool directCalled = false;
        final dio1 = Dio()
          ..httpClientAdapter = _MockDioAdapter((_) {
            directCalled = true;
            return ResponseBody.fromString(
              jsonEncode(spec.directJsonPayload),
              200,
              headers: {
                Headers.contentTypeHeader: [Headers.jsonContentType],
              },
            );
          });

        ServerAlertService.httpClientForTesting = MockClient((request) async {
          expect(request.url.path, equals('/api/price/${spec.id}/${spec.pair.marketSymbol}'));
          return http.Response(
            jsonEncode({'status': 'ok', 'price': 81234.56}),
            200,
            headers: {'content-type': 'application/json'},
          );
        });

        final ex1 = spec.builder(dio1);
        final ticker1 = await ex1.fetchTicker(spec.pair);
        expect(ticker1.lastPrice, equals(81234.56));
        expect(ticker1.volume24h, equals(0.0));
        expect(directCalled, isFalse, reason: '${spec.id} must not call direct Dio when server succeeds');

        // 2. Server null -> falls back to direct
        bool directCalled2 = false;
        final dio2 = Dio()
          ..httpClientAdapter = _MockDioAdapter((_) {
            directCalled2 = true;
            return ResponseBody.fromString(
              jsonEncode(spec.directJsonPayload),
              200,
              headers: {
                Headers.contentTypeHeader: [Headers.jsonContentType],
              },
            );
          });

        ServerAlertService.httpClientForTesting = MockClient((_) async {
          return http.Response('{"detail":"upstream down"}', 502);
        });

        final ex2 = spec.builder(dio2);
        final ticker2 = await ex2.fetchTicker(spec.pair);
        expect(directCalled2, isTrue, reason: '${spec.id} must call direct Dio when server returns null');
        expect(ticker2.lastPrice, closeTo(spec.expectedDirectPrice, 1e-6));

        // 3. Switch off -> bypasses server and calls direct
        bool serverCalled3 = false;
        ServerAlertService.httpClientForTesting = MockClient((_) async {
          serverCalled3 = true;
          return http.Response(jsonEncode({'price': 99999.0}), 200);
        });

        bool directCalled3 = false;
        final dio3 = Dio()
          ..httpClientAdapter = _MockDioAdapter((_) {
            directCalled3 = true;
            return ResponseBody.fromString(
              jsonEncode(spec.directJsonPayload),
              200,
              headers: {
                Headers.contentTypeHeader: [Headers.jsonContentType],
              },
            );
          });

        final ex3 = spec.builder(dio3, serverFirst: false);
        final ticker3 = await ex3.fetchTicker(spec.pair);
        expect(serverCalled3, isFalse, reason: '${spec.id} must not call server when serverFirst is false');
        expect(directCalled3, isTrue);
        expect(ticker3.lastPrice, closeTo(spec.expectedDirectPrice, 1e-6));
      });
    }

    test('SchedulerService evaluates crypto rule via adapter server-first without duplicate server calls', () async {
      final tempDir = Directory.systemTemp.createTempSync('scheduler_server_first_');
      try {
        int serverPriceHits = 0;
        ServerAlertService.httpClientForTesting = MockClient((request) async {
          if (request.url.path.startsWith('/api/price/')) {
            serverPriceHits++;
            return http.Response(
              jsonEncode({'status': 'ok', 'price': 71000.0}),
              200,
              headers: {'content-type': 'application/json'},
            );
          }
          return http.Response('{}', 200);
        });

        bool directDioCalled = false;
        final dio = Dio()
          ..httpClientAdapter = _MockDioAdapter((_) {
            directDioCalled = true;
            return ResponseBody.fromString('{}', 500);
          });

        final registry = ExchangeRegistry()..register(BinanceExchange(dio: dio, visionDio: dio));
        final repo = JsonAlertRuleRepository(tempDir.path);
        await repo.load();

        final rule = AlertRule(
          uuid: 'sched-crypto-1',
          baseCurrency: 'BTC',
          counterCurrency: 'USDT',
          marketSymbol: 'BTCUSDT',
          exchangeId: 'binance',
          checkIntervalSeconds: 5,
          conditionType: AlertConditionType.priceThreshold,
          direction: AlertDirection.above,
          triggerMode: TriggerMode.oneShot,
          targetPrice: 70000.0,
          preferServerProxy: true,
          isActive: true,
          createdAt: DateTime.now().subtract(const Duration(minutes: 1)),
        );
        await repo.saveRule(rule, syncToServer: false);

        final scheduler = SchedulerService(
          alertRuleRepository: repo,
          exchangeRegistry: registry,
          notificationService: _NoopNotificationService(),
        );

        final triggered = await scheduler.evaluateSingleRule(rule, DateTime.now());
        expect(triggered, isTrue);
        expect(serverPriceHits, equals(1));
        expect(directDioCalled, isFalse);
      } finally {
        tempDir.deleteSync(recursive: true);
      }
    });
  });
}
