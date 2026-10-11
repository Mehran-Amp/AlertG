import 'package:dio/dio.dart';
import '../base/crypto_catalog_data.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// KuCoin REST Exchange Adapter
class KuCoinExchange implements Exchange {
  final Dio _dio;

  KuCoinExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://api.kucoin.com',
              connectTimeout: const Duration(seconds: 8),
              receiveTimeout: const Duration(seconds: 8),
            ));

  @override
  String get id => 'kucoin';

  @override
  String get name => 'KuCoin';

  @override
  ExchangeCategory get category => ExchangeCategory.tier1;

  @override
  String get countryBadge => '🌐 Global';

  @override
  String get defaultCounterCurrency => 'USDT';

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    try {
      final response = await _dio.get('/api/v1/symbols');
      final data = response.data['data'] as List;
      final pairs = data
          .map((item) => CurrencyPair(
                baseCurrency: (item['baseCurrency'] as String).toUpperCase(),
                counterCurrency: (item['quoteCurrency'] as String).toUpperCase(),
                marketSymbol: (item['symbol'] as String).toUpperCase(),
              ))
          .toList();
      if (pairs.isNotEmpty) return pairs;
    } catch (_) {}

    return CryptoCatalogData.buildPairs(
      quoteCurrencies: ['USDT', 'BTC', 'USDC'],
      symbolFormatter: (b, q) => '$b-$q',
    );
  }

  @override
  Future<PriceSnapshot> fetchSnapshot(CurrencyPair pair) async {
    final ticker = await fetchTicker(pair);
    return PriceSnapshot(
      price: ticker.lastPrice,
      volume: ticker.volume24h,
      fetchedAt: ticker.timestamp,
    );
  }

  @override
  Future<MarketTicker> fetchTicker(CurrencyPair pair) async {
    try {
      final symbol = '${pair.baseCurrency}-${pair.counterCurrency}'.toUpperCase();
      final response = await _dio.get('/api/v1/market/orderbook/level1', queryParameters: {'symbol': symbol});
      final data = response.data['data'] as Map<String, dynamic>;
      final price = double.tryParse(data['price']?.toString() ?? '0') ?? 0.0;
      final vol = double.tryParse(data['size']?.toString() ?? '0') ?? 0.0;

      if (price <= 0) {
        throw Exception('Invalid price from KuCoin ($price)');
      }

      return MarketTicker(
        exchangeId: id,
        pair: pair,
        lastPrice: price,
        volume24h: vol,
        timestamp: DateTime.now(),
      );
    } catch (e) {
      throw Exception('KuCoin Live Connection Error for ${pair.displayName}: $e');
    }
  }
}
