import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:bitcoin_checker/core/utils/format_utils.dart';
import 'package:bitcoin_checker/features/alert_engine/models/alert_rule.dart';
import 'package:bitcoin_checker/features/alert_engine/scheduler/condition_evaluator.dart';
import 'package:bitcoin_checker/features/exchanges/base/crypto_catalog_service.dart';
import 'package:bitcoin_checker/features/exchanges/base/currency_pair.dart';
import 'package:bitcoin_checker/features/exchanges/binance/binance_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/bitget/bitget_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/bybit/bybit_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/gateio/gateio_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/kraken/kraken_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/kucoin/kucoin_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/lbank/lbank_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/mexc/mexc_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/okx/okx_exchange.dart';
import 'package:bitcoin_checker/features/exchanges/registry/exchange_catalog.dart';
import 'package:bitcoin_checker/features/exchanges/registry/exchange_registry.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempTestDir;

  setUpAll(() {
    tempTestDir = Directory.systemTemp.createTempSync('alertg_phase10_test_');
    CryptoCatalogService.instance.testCacheDir = tempTestDir;
  });

  tearDownAll(() {
    try {
      if (tempTestDir.existsSync()) {
        tempTestDir.deleteSync(recursive: true);
      }
    } catch (_) {}
  });

  tearDown(() {
    CryptoCatalogService.instance.clearMemoryCache();
    CryptoCatalogService.instance.testClient = null;
  });

  group('Phase 10 — Task 1: CoinEx Retirement & LBank Primacy', () {
    test('LBank is registered in ExchangeCatalog and CoinEx is completely removed', () {
      final international = ExchangeCatalog.buildInternationalCryptoExchanges();
      final all = ExchangeCatalog.buildAllExchanges();

      // 1. CoinEx must not exist anywhere
      final hasCoinEx = all.any((e) => e.id.toLowerCase() == 'coinex');
      expect(hasCoinEx, isFalse, reason: 'CoinEx must be completely removed from all exchange lists');

      // 2. LBank must be present in international and all lists
      final lbankInInt = international.any((e) => e.id == 'lbank');
      final lbankInAll = all.any((e) => e.id == 'lbank');
      expect(lbankInInt, isTrue, reason: 'LBank must be present in international crypto exchanges');
      expect(lbankInAll, isTrue, reason: 'LBank must be present in all exchanges');

      // 3. Condition evaluator resolves LBank correctly
      expect(ConditionEvaluator.getFormattedExchangeName('lbank'), equals('LBank'));
    });
  });

  group('Phase 10 — Task 2: Strict Spot USDT Exclusivity', () {
    test('LBankExchange only accepts USDT pairs and does not include BTC or ETH quotes', () async {
      final lbank = LBankExchange();
      expect(lbank.id, equals('lbank'));
      expect(lbank.defaultCounterCurrency, equals('USDT'));
    });

    test('Binance, OKX, MEXC, KuCoin, Gate.io, Bybit, Bitget, Kraken default to USDT', () {
      expect(BinanceExchange().defaultCounterCurrency, equals('USDT'));
      expect(OKXExchange().defaultCounterCurrency, equals('USDT'));
      expect(MEXCExchange().defaultCounterCurrency, equals('USDT'));
      expect(KuCoinExchange().defaultCounterCurrency, equals('USDT'));
      expect(GateioExchange().defaultCounterCurrency, equals('USDT'));
      expect(BybitExchange().defaultCounterCurrency, equals('USDT'));
      expect(BitgetExchange().defaultCounterCurrency, equals('USDT'));
      expect(KrakenExchange().defaultCounterCurrency, equals('USDT'));
    });
  });

  group('Phase 10 — Task 3: Zero Cross-Exchange Fallback in Ticker Fetching', () {
    test('LBank throws when direct endpoint fails without calling secondary aggregators', () async {
      final lbank = LBankExchange();
      final pair = CurrencyPair(baseCurrency: 'NONEXISTENTCOIN999', counterCurrency: 'USDT', marketSymbol: 'nonexistentcoin999_usdt');
      expect(() async => await lbank.fetchTicker(pair), throwsA(isA<Exception>()));
    });

    test('Bitget throws when direct endpoint fails without calling Binance', () async {
      final bitget = BitgetExchange();
      final pair = CurrencyPair(baseCurrency: 'NONEXISTENTCOIN999', counterCurrency: 'USDT', marketSymbol: 'NONEXISTENTCOIN999USDT');
      expect(() async => await bitget.fetchTicker(pair), throwsA(isA<Exception>()));
    });
  });

  group('Phase 10 — Task 4: Dynamic CryptoCatalogService & Offline Device Cache', () {
    test('loads pairs from Phase 6 server endpoint and writes to local disk cache', () async {
      final mockResponse = {
        'status': 'success',
        'exchange': 'binance',
        'count': 3,
        'as_of': 1730370000.0,
        'is_stale': false,
        'symbols': [
          {'base_currency': 'BTC', 'counter_currency': 'USDT', 'market_symbol': 'BTCUSDT'},
          {'base_currency': 'ETH', 'counter_currency': 'USDT', 'market_symbol': 'ETHUSDT'},
          {'base_currency': 'SOL', 'counter_currency': 'USDT', 'market_symbol': 'SOLUSDT'},
          {'base_currency': 'TEST', 'counter_currency': 'USDC', 'market_symbol': 'TESTUSDC'}, // non-USDT must be excluded
        ],
      };

      CryptoCatalogService.instance.testClient = MockClient((request) async {
        if (request.url.path.contains('/api/crypto/exchanges/binance/symbols')) {
          return http.Response(json.encode(mockResponse), 200, headers: {'content-type': 'application/json'});
        }
        return http.Response('Not Found', 404);
      });

      final pairs = await CryptoCatalogService.instance.fetchPairsForExchange('binance', forceRefresh: true);
      expect(pairs.length, equals(3));
      expect(pairs.map((p) => p.baseCurrency).toList(), equals(['BTC', 'ETH', 'SOL']));
      expect(pairs.every((p) => p.counterCurrency == 'USDT'), isTrue);

      // Verify that disk cache file was created
      final cacheFile = File('${tempTestDir.path}/crypto_catalog_binance.json');
      expect(cacheFile.existsSync(), isTrue);
    });

    test('offline fallback: returns cached catalog when backend network fails', () async {
      // 1. Manually write disk cache for OKX
      final cachedJson = {
        'status': 'success',
        'exchange': 'okx',
        'symbols': [
          {'base_currency': 'PEPE', 'counter_currency': 'USDT', 'market_symbol': 'PEPE-USDT'},
          {'base_currency': 'DOGE', 'counter_currency': 'USDT', 'market_symbol': 'DOGE-USDT'},
        ],
      };
      final okxCacheFile = File('${tempTestDir.path}/crypto_catalog_okx.json');
      await okxCacheFile.writeAsString(json.encode(cachedJson));

      // 2. Mock client simulates network failure (500 Server Error)
      CryptoCatalogService.instance.testClient = MockClient((request) async {
        throw const SocketException('No Internet connection');
      });

      // 3. Fetch must succeed by loading from local disk cache
      final pairs = await CryptoCatalogService.instance.fetchPairsForExchange('okx', forceRefresh: true);
      expect(pairs.length, equals(2));
      expect(pairs[0].baseCurrency, equals('PEPE'));
      expect(pairs[0].marketSymbol, equals('PEPE-USDT'));
      expect(pairs[1].baseCurrency, equals('DOGE'));
    });
  });

  group('Phase 10 — Task 5: Exact Price Display (Rule R3 / Phase 8b in Dart)', () {
    test('formatExactDecimal strips trailing zeros and preserves exact significant digits', () {
      expect(FormatUtils.formatExactDecimal(0.00000845), equals('0.00000845'));
      expect(FormatUtils.formatExactDecimal(0.0000000045), equals('0.0000000045'));
      expect(FormatUtils.formatExactDecimal(0.50000), equals('0.5'));
      expect(FormatUtils.formatExactDecimal(0.00001000), equals('0.00001'));
      expect(FormatUtils.formatExactDecimal(1.0), equals('1'));
      expect(FormatUtils.formatExactDecimal(0.0), equals('0'));
    });

    test('formatPrice never outputs \$0 for small non-zero crypto prices', () {
      // SHIB / PEPE sub-cent prices
      final pepePrice = FormatUtils.formatPrice(0.00000845, currencySymbol: 'USDT');
      expect(pepePrice, contains('0.00000845'));
      expect(pepePrice, isNot(contains('\$0.00')));
      expect(pepePrice, isNot(contains('\$0')));

      final nanoPrice = FormatUtils.formatPrice(0.0000000045, currencySymbol: 'USDT');
      expect(nanoPrice, contains('0.0000000045'));
      expect(nanoPrice, isNot(contains('\$0.00')));

      // Standard and large prices remain unchanged
      final btcPrice = FormatUtils.formatPrice(67000.5, currencySymbol: 'USDT');
      expect(btcPrice, contains('67,000.50'));

      final standardPrice = FormatUtils.formatPrice(1.25, currencySymbol: 'USDT');
      expect(standardPrice, contains('1.25'));
    });

    test('formatInputNumberForUnit preserves exact micro-decimal values without truncation', () {
      expect(FormatUtils.formatInputNumberForUnit(0.00000845, 'USDT'), equals('0.00000845'));
      expect(FormatUtils.formatInputNumberForUnit(0.0000000045, 'USDT'), equals('0.0000000045'));
      expect(FormatUtils.formatInputNumberForUnit(67000.5, 'USDT'), equals('67000.50'));
    });
  });

  group('Phase 10 — Task 6: Alert 3-Tuple Integrity', () {
    test('AlertRule strictly stores and exposes exchangeId, baseCurrency, counterCurrency, and marketSymbol', () {
      final pair = CurrencyPair(
        baseCurrency: 'PEPE',
        counterCurrency: 'USDT',
        marketSymbol: 'PEPE_USDT',
      );

      final rule = AlertRule.create(
        pair: pair,
        exchangeId: 'lbank',
        checkIntervalSeconds: 5,
        conditionType: AlertConditionType.priceThreshold,
        direction: AlertDirection.above,
        targetPrice: 0.0000095,
      );

      expect(rule.exchangeId, equals('lbank'));
      expect(rule.baseCurrency, equals('PEPE'));
      expect(rule.counterCurrency, equals('USDT'));
      expect(rule.marketSymbol, equals('PEPE_USDT'));
      expect(rule.targetPrice, equals(0.0000095));
      expect(rule.checkIntervalSeconds, equals(5));

      final jsonMap = rule.toJson();
      expect(jsonMap['exchange_id'], equals('lbank'));
      expect(jsonMap['base_currency'], equals('PEPE'));
      expect(jsonMap['counter_currency'], equals('USDT'));
      expect(jsonMap['market_symbol'], equals('PEPE_USDT'));
      expect(jsonMap['target_price'], equals(0.0000095));
    });
  });
}
