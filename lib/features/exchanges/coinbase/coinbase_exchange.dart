import 'package:dio/dio.dart';
import '../base/crypto_catalog_data.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// Coinbase REST Exchange Adapter
class CoinbaseExchange implements Exchange {
  final Dio _dio;

  CoinbaseExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://api.exchange.coinbase.com',
              connectTimeout: const Duration(seconds: 8),
              receiveTimeout: const Duration(seconds: 8),
            ));

  @override
  String get id => 'coinbase';

  @override
  String get name => 'Coinbase';

  @override
  ExchangeCategory get category => ExchangeCategory.tier1;

  @override
  String get countryBadge => '🇺🇸 USA';

  @override
  String get defaultCounterCurrency => 'USD';

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    try {
      final response = await _dio.get('/products');
      final data = response.data as List;
      final pairs = data
          .where((item) => item['status'] == 'online')
          .map((item) => CurrencyPair(
                baseCurrency: (item['base_currency'] as String).toUpperCase(),
                counterCurrency: (item['quote_currency'] as String).toUpperCase(),
                marketSymbol: (item['id'] as String).toUpperCase(),
              ))
          .toList();
      if (pairs.isNotEmpty) return pairs;
    } catch (_) {}

    return CryptoCatalogData.buildPairs(
      quoteCurrencies: ['USD', 'USDT', 'EUR'],
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
      final productId = '${pair.baseCurrency}-${pair.counterCurrency}'.toUpperCase();
      final response = await _dio.get('/products/$productId/ticker');
      final data = response.data as Map<String, dynamic>;
      final price = double.tryParse(data['price']?.toString() ?? '0') ?? 0.0;
      final vol = double.tryParse(data['volume']?.toString() ?? '0') ?? 0.0;

      if (price <= 0) {
        throw Exception('Invalid price from Coinbase ($price)');
      }

      return MarketTicker(
        exchangeId: id,
        pair: pair,
        lastPrice: price,
        volume24h: vol,
        timestamp: DateTime.now(),
      );
    } catch (e) {
      throw Exception('Coinbase Live Connection Error for ${pair.displayName}: $e');
    }
  }
}
