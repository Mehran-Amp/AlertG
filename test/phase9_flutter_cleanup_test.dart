import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:bitcoin_checker/core/services/server_alert_service.dart';
import 'package:bitcoin_checker/core/utils/format_utils.dart';
import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';
import 'package:bitcoin_checker/features/alert_engine/repositories/json_alert_rule_repository.dart';
import 'package:bitcoin_checker/features/exchanges/base/crypto_catalog_service.dart';
import 'package:bitcoin_checker/features/exchanges/base/exchange.dart';
import 'package:bitcoin_checker/features/exchanges/base/exchange_category.dart';
import 'package:bitcoin_checker/features/exchanges/base/standard_rest_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/binance/binance_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/coinbase/coinbase_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/gateio/gateio_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/kifpool/kifpool_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/kraken/kraken_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/kucoin/kucoin_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/mexc/mexc_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/registry/exchange_catalog.dart';
import 'package:bitcoin_checker/features/exchanges/registry/exchange_registry.dart';
import 'package:bitcoin_checker/features/exchanges/tabdeal/tabdeal_exchange.dart';
import 'package:bitcoin_checker/features/settings/services/settings_service.dart';
import 'package:bitcoin_checker/features/watchlist/pages/create_alert_flow.dart';

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

Dio _failingDio() {
  return Dio()
    ..httpClientAdapter = _MockDioAdapter((options) {
      throw DioException(
        requestOptions: options,
        type: DioExceptionType.connectionError,
        message: 'Simulated offline network error',
      );
    });
}

Dio _jsonDio(Object payload) {
  return Dio()
    ..httpClientAdapter = _MockDioAdapter((_) {
      return ResponseBody.fromString(
        jsonEncode(payload),
        200,
        headers: {
          Headers.contentTypeHeader: [Headers.jsonContentType],
        },
      );
    });
}

AlertRule _buildRule({
  required String uuid,
  required String exchangeId,
  String base = 'BTC',
  String counter = 'USDT',
  String? symbol,
}) {
  return AlertRule(
    uuid: uuid,
    baseCurrency: base,
    counterCurrency: counter,
    marketSymbol: symbol ?? '$base$counter',
    exchangeId: exchangeId,
    checkIntervalSeconds: 60,
    conditionType: AlertConditionType.priceThreshold,
    direction: AlertDirection.above,
    triggerMode: TriggerMode.oneShot,
    targetPrice: 50000,
    isActive: true,
    createdAt: DateTime.now(),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempTestDir;

  setUpAll(() {
    tempTestDir = Directory.systemTemp.createTempSync('alertg_phase9_test_');
  });

  tearDownAll(() {
    try {
      if (tempTestDir.existsSync()) {
        tempTestDir.deleteSync(recursive: true);
      }
    } catch (_) {}
  });

  setUp(() {
    CryptoCatalogService.instance.testCacheDir = tempTestDir;
    CryptoCatalogService.instance.clearMemoryCache();
    CryptoCatalogService.instance.testClient = null;
    ServerAlertService.resetCircuitBreakerForTesting();
    ServerAlertService.setBaseUrlForTesting('https://example.invalid');
    ServerAlertService.httpClientForTesting = null;
    ServerAlertService.registerLoadFailedProvider(() => false);
  });

  tearDown(() async {
    CryptoCatalogService.instance.clearMemoryCache();
    CryptoCatalogService.instance.testClient = null;
    ServerAlertService.httpClientForTesting = null;
    // Clean up any leftover catalog files between tests
    if (tempTestDir.existsSync()) {
      for (final entity in tempTestDir.listSync()) {
        if (entity is File && entity.path.contains('crypto_catalog_')) {
          try {
            entity.deleteSync();
          } catch (_) {}
        }
      }
    }
  });

  group('Phase 9 — Canonical ExchangeCatalog Cleanup', () {
    test('contains strictly 18 canonical crypto exchanges (2 Iran + 16 global)', () {
      final iran = ExchangeCatalog.buildIranCryptoExchanges();
      final intl = ExchangeCatalog.buildInternationalCryptoExchanges();
      final combined = ExchangeCatalog.buildCryptoExchanges();

      expect(iran.map((e) => e.id).toList(), equals(['tabdeal', 'kifpool']));
      expect(
        intl.map((e) => e.id).toSet(),
        equals({
          'binance',
          'mexc',
          'kucoin',
          'gateio',
          'lbank',
          'okx',
          'kraken',
          'bybit',
          'bitget',
          'htx',
          'bingx',
          'xt',
          'toobit',
          'poloniex',
          'coinbase',
          'bitfinex',
        }),
      );
      expect(combined.length, equals(18));
      expect(combined.map((e) => e.id).toSet().length, equals(18));

      const retiredIds = {
        'coinex',
        'coingecko',
        'coinmarketcap',
        'bitvavo',
        'upbit',
        'bitmex',
        'bitstamp',
        'gemini',
        'kcex',
        'ourbit',
      };
      for (final id in retiredIds) {
        expect(combined.any((e) => e.id == id), isFalse, reason: '$id must not be in canonical catalog');
      }
    });
  });

  group('Phase 9 — Rule R4: Zero Static Catalog Fallbacks', () {
    test('CryptoCatalogService returns empty list (not static pairs) when server, cache, and direct adapter fail', () async {
      CryptoCatalogService.instance.testClient = MockClient((_) async {
        return http.Response('Service Unavailable', 503);
      });

      final failingBinance = BinanceExchange(dio: _failingDio(), visionDio: _failingDio());
      final pairs = await CryptoCatalogService.instance.fetchPairsForExchange(
        'binance',
        fallbackExchange: failingBinance,
        forceRefresh: true,
      );

      expect(pairs, isEmpty);
      final diag = CryptoCatalogService.instance.getDiagnostic('binance');
      expect(diag, isNotNull);
      expect(diag!.source, equals('empty'));
      expect(diag.pairCount, equals(0));
    });

    test('CryptoCatalogService uses disk cache and records disk_cache source when network fails', () async {
      final cacheFile = File('${tempTestDir.path}/crypto_catalog_gateio.json');
      await cacheFile.writeAsString(jsonEncode({
        'status': 'success',
        'exchange': 'gateio',
        'symbols': [
          {'base_currency': 'BTC', 'counter_currency': 'USDT', 'market_symbol': 'BTC_USDT'},
          {'base_currency': 'BTC', 'counter_currency': 'USDC', 'market_symbol': 'BTC_USDC'},
        ],
      }));

      CryptoCatalogService.instance.testClient = MockClient((_) async {
        throw const SocketException('Offline');
      });

      final pairs = await CryptoCatalogService.instance.fetchPairsForExchange(
        'gateio',
        fallbackExchange: GateioExchange(dio: _failingDio()),
        forceRefresh: true,
      );

      expect(pairs.length, equals(1));
      expect(pairs.first.marketSymbol, equals('BTC_USDT'));
      expect(CryptoCatalogService.instance.getDiagnostic('gateio')?.source, equals('disk_cache'));
    });

    test('Direct crypto adapters return empty list on REST failure without static fallback', () async {
      final adapters = <Exchange>[
        BinanceExchange(dio: _failingDio(), visionDio: _failingDio()),
        MEXCExchange(dio: _failingDio()),
        KuCoinExchange(dio: _failingDio()),
        GateioExchange(dio: _failingDio()),
        TabdealExchange(dio: _failingDio()),
        KifpoolExchange(dio: _failingDio()),
        KrakenExchange(dio: _failingDio()),
        CoinbaseExchange(dio: _failingDio()),
        StandardRestExchange(
          id: 'htx',
          name: 'HTX / Huobi',
          category: ExchangeCategory.tier1,
          countryBadge: 'Global',
          defaultCounterCurrency: 'USDT',
          pairsUrl: 'https://api.huobi.pro/v1/common/symbols',
          tickerUrlTemplate: 'https://api.huobi.pro/market/detail/merged?symbol={BASE}{QUOTE}',
          dio: _failingDio(),
        ),
      ];

      for (final adapter in adapters) {
        final pairs = await adapter.fetchCurrencyPairs();
        expect(pairs, isEmpty, reason: '${adapter.id} must return empty list on failure');
      }
    });
  });

  group('Phase 9 — Strict Spot USDT / Iran Quote Enforcement', () {
    test('CryptoCatalogService allows TMN & USDT for tabdeal/kifpool, and strictly USDT for global exchanges', () async {
      CryptoCatalogService.instance.testClient = MockClient((req) async {
        if (req.url.path.contains('/tabdeal/')) {
          return http.Response(
            jsonEncode({
              'status': 'success',
              'symbols': [
                {'base_currency': 'BTC', 'counter_currency': 'IRT', 'market_symbol': 'BTCIRT'},
                {'base_currency': 'ETH', 'counter_currency': 'USDT', 'market_symbol': 'ETHUSDT'},
                {'base_currency': 'SOL', 'counter_currency': 'EUR', 'market_symbol': 'SOLEUR'},
              ],
            }),
            200,
          );
        }
        return http.Response(
          jsonEncode({
            'status': 'success',
            'symbols': [
              {'base_currency': 'BTC', 'counter_currency': 'USDT', 'market_symbol': 'BTC-USDT'},
              {'base_currency': 'BTC', 'counter_currency': 'USD', 'market_symbol': 'BTC-USD'},
              {'base_currency': 'ETH', 'counter_currency': 'EUR', 'market_symbol': 'ETH-EUR'},
            ],
          }),
          200,
        );
      });

      final tabdealPairs = await CryptoCatalogService.instance.fetchPairsForExchange('tabdeal', forceRefresh: true);
      expect(tabdealPairs.map((p) => '${p.baseCurrency}/${p.counterCurrency}').toList(), equals(['BTC/TMN', 'ETH/USDT']));

      final coinbasePairs = await CryptoCatalogService.instance.fetchPairsForExchange('coinbase', forceRefresh: true);
      expect(coinbasePairs.length, equals(1));
      expect(coinbasePairs.first.counterCurrency, equals('USDT'));
    });

    test('Coinbase, Kraken, and StandardRestExchange filter non-USDT pairs cleanly', () async {
      final coinbase = CoinbaseExchange(
        dio: _jsonDio([
          {'id': 'BTC-USD', 'base_currency': 'BTC', 'quote_currency': 'USD', 'status': 'online'},
          {'id': 'BTC-USDT', 'base_currency': 'BTC', 'quote_currency': 'USDT', 'status': 'online'},
          {'id': 'ETH-EUR', 'base_currency': 'ETH', 'quote_currency': 'EUR', 'status': 'online'},
        ]),
      );
      expect(coinbase.defaultCounterCurrency, equals('USDT'));
      final cbPairs = await coinbase.fetchCurrencyPairs();
      expect(cbPairs.length, equals(1));
      expect(cbPairs.first.marketSymbol, equals('BTC-USDT'));

      final kraken = KrakenExchange(
        dio: _jsonDio({
          'result': {
            'XXBTZUSD': {'c': ['67000.0']},
            'XBTUSDT': {'c': ['67005.0']},
            'SOLUSDT': {'c': ['180.0']},
          }
        }),
      );
      final krakenPairs = await kraken.fetchCurrencyPairs();
      expect(krakenPairs.every((p) => p.counterCurrency == 'USDT'), isTrue);
      expect(krakenPairs.map((p) => p.baseCurrency).toList(), equals(['BTC', 'SOL']));

      final htx = StandardRestExchange(
        id: 'htx',
        name: 'HTX / Huobi',
        category: ExchangeCategory.tier1,
        countryBadge: 'Global',
        defaultCounterCurrency: 'USDT',
        pairsUrl: 'https://api.huobi.pro/v1/common/symbols',
        dio: _jsonDio({
          'data': [
            {'base-currency': 'btc', 'quote-currency': 'usdt', 'symbol': 'btcusdt', 'state': 'online'},
            {'base-currency': 'eth', 'quote-currency': 'btc', 'symbol': 'ethbtc', 'state': 'online'},
            {'base-currency': 'sol', 'quote-currency': 'usdc', 'symbol': 'solusdc', 'state': 'online'},
          ]
        }),
      );
      final htxPairs = await htx.fetchCurrencyPairs();
      expect(htxPairs.length, equals(1));
      expect(htxPairs.first.marketSymbol, equals('btcusdt'));
    });
  });

  group('Phase 9 — FormatUtils Micro-Price Precision (< 1e-12)', () {
    test('formatExactDecimal and formatPrice preserve precision below 1e-12 without truncating to 0', () {
      expect(FormatUtils.formatExactDecimal(1e-12), equals('0.000000000001'));
      expect(FormatUtils.formatExactDecimal(1e-13), equals('0.0000000000001'));
      expect(FormatUtils.formatExactDecimal(0.00000000000045), equals('0.00000000000045'));
      expect(FormatUtils.formatExactDecimal(0.000000000000000123), equals('0.000000000000000123'));

      final formatted = FormatUtils.formatPrice(0.00000000000045, currencySymbol: 'USDT')
          .replaceAll(RegExp(r'[\u202A\u202C]'), '');
      expect(formatted, equals(r'$0.00000000000045'));
      expect(formatted, isNot(equals(r'$0')));
    });
  });

  group('Phase 9 — Legacy CoinEx Alert Purge & Sync Exclusion', () {
    test('JsonAlertRuleRepository purges CoinEx rules on load and exposes one-time notice count', () async {
      final dir = tempTestDir.createTempSync('coinex_purge_');
      try {
        final alertsFile = File('${dir.path}/alerts.json');
        await alertsFile.writeAsString(jsonEncode({
          'version': 1,
          'rules': [
            _buildRule(uuid: 'legacy-coinex-1', exchangeId: 'coinex').toJson(),
            _buildRule(uuid: 'legacy-coinex-2', exchangeId: 'CoinEx').toJson(),
            _buildRule(uuid: 'valid-binance-1', exchangeId: 'binance').toJson(),
          ],
        }));

        final repo = JsonAlertRuleRepository(dir.path);
        await repo.load();

        expect(repo.allRules.map((r) => r.uuid).toList(), equals(['valid-binance-1']));
        expect(repo.consumeRemovedCoinExNoticeCount(), equals(2));
        expect(repo.consumeRemovedCoinExNoticeCount(), equals(0));

        // Verify persisted file on disk no longer contains CoinEx
        final onDisk = jsonDecode(await alertsFile.readAsString()) as Map<String, dynamic>;
        final diskRules = (onDisk['rules'] as List).cast<Map<String, dynamic>>();
        expect(diskRules.length, equals(1));
        expect(diskRules.first['uuid'], equals('valid-binance-1'));
      } finally {
        dir.deleteSync(recursive: true);
      }
    });

    test('ServerAlertService.syncAllRulesToServer never uploads CoinEx alerts', () async {
      String? capturedBody;
      ServerAlertService.httpClientForTesting = MockClient((request) async {
        capturedBody = request.body;
        return http.Response(jsonEncode({'status': 'ok'}), 200);
      });

      final rules = [
        _buildRule(uuid: 'c1', exchangeId: 'coinex'),
        _buildRule(uuid: 'b1', exchangeId: 'binance'),
      ];

      final ok = await ServerAlertService.syncAllRulesToServer(rules, userId: 'test_user');
      expect(ok, isTrue);
      expect(capturedBody, isNotNull);

      final decoded = jsonDecode(capturedBody!) as Map<String, dynamic>;
      final uploaded = (decoded['alerts'] as List).cast<Map<String, dynamic>>();
      expect(uploaded.length, equals(1));
      expect(uploaded.first['id'], equals('b1'));
      expect(uploaded.first['exchange'], equals('binance'));
    });
  });

  group('Phase 9 — CreateAlertFlow UI States (Offline & Disk Cache)', () {
    testWidgets('shows disk_cache outdated banner when cached pairs are loaded offline', (WidgetTester tester) async {
      final dir = tempTestDir.createTempSync('widget_cache_');
      try {
        final cacheFile = File('${tempTestDir.path}/crypto_catalog_binance.json');
        await cacheFile.writeAsString(jsonEncode({
          'status': 'success',
          'exchange': 'binance',
          'symbols': [
            {'base_currency': 'BTC', 'counter_currency': 'USDT', 'market_symbol': 'BTCUSDT'},
          ],
        }));

        CryptoCatalogService.instance.testClient = MockClient((_) async {
          throw const SocketException('Offline');
        });

        final registry = ExchangeRegistry()
          ..register(BinanceExchange(dio: _failingDio(), visionDio: _failingDio()));
        final repo = JsonAlertRuleRepository(dir.path);
        final settings = SettingsService(dir.path);
        await settings.setLanguage('en');

        await tester.pumpWidget(
          ChangeNotifierProvider<SettingsService>.value(
            value: settings,
            child: MaterialApp(
              home: CreateAlertFlow(registry: registry, repository: repo),
            ),
          ),
        );
        await tester.pumpAndSettle();

        await tester.tap(find.text('Enter International Crypto Exchanges →'));
        await tester.pumpAndSettle();

        expect(find.text('Binance'), findsOneWidget);
        expect(find.text('Bitvavo'), findsNothing);
        expect(find.text('CoinEx'), findsNothing);

        await tester.tap(find.text('Binance'));
        await tester.pumpAndSettle();

        expect(find.textContaining('may be outdated'), findsOneWidget);
        expect(find.text('BTC / USDT'), findsOneWidget);
      } finally {
        dir.deleteSync(recursive: true);
      }
    });

    testWidgets('shows empty offline catalog UI with Retry button when server and disk cache fail', (WidgetTester tester) async {
      final dir = tempTestDir.createTempSync('widget_empty_');
      try {
        CryptoCatalogService.instance.testClient = MockClient((_) async {
          return http.Response('Down', 503);
        });

        final registry = ExchangeRegistry()
          ..register(BinanceExchange(dio: _failingDio(), visionDio: _failingDio()));
        final repo = JsonAlertRuleRepository(dir.path);
        final settings = SettingsService(dir.path);
        await settings.setLanguage('en');

        await tester.pumpWidget(
          ChangeNotifierProvider<SettingsService>.value(
            value: settings,
            child: MaterialApp(
              home: CreateAlertFlow(registry: registry, repository: repo),
            ),
          ),
        );
        await tester.pumpAndSettle();

        await tester.tap(find.text('Enter International Crypto Exchanges →'));
        await tester.pumpAndSettle();

        await tester.tap(find.text('Binance'));
        await tester.pumpAndSettle();

        expect(find.text('Exchange catalog unavailable'), findsOneWidget);
        expect(find.text('Retry'), findsOneWidget);
      } finally {
        dir.deleteSync(recursive: true);
      }
    });
  });
}
