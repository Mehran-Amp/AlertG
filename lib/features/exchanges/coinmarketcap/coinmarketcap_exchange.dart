import 'package:dio/dio.dart';
import '../base/crypto_catalog_data.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// CoinMarketCap Global Crypto Benchmark & Aggregator
/// Queries official CoinMarketCap data API directly.
class CoinMarketCapExchange implements Exchange {
  final Dio _dio = Dio(BaseOptions(
    connectTimeout: const Duration(seconds: 8),
    receiveTimeout: const Duration(seconds: 8),
    headers: {
      'Accept': 'application/json',
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Alarmer/1.0',
    },
  ));

  @override
  String get id => 'coinmarketcap';

  @override
  String get name => 'CoinMarketCap';

  @override
  ExchangeCategory get category => ExchangeCategory.aggregator;

  @override
  String get countryBadge => '📊 Global Benchmark';

  @override
  String get defaultCounterCurrency => 'USD';

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    return CryptoCatalogData.buildPairs(
      quoteCurrencies: ['USD', 'USDT', 'BTC', 'EUR'],
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
    final base = pair.baseCurrency.toUpperCase();
    try {
      final res = await _dio.get(
        'https://api.coinmarketcap.com/data-api/v3/cryptocurrency/detail',
        queryParameters: {'symbol': base},
      );
      if (res.data is Map && res.data['data'] != null) {
        final priceVal = res.data['data']['statistics']?['price'];
        if (priceVal != null) {
          final p = double.tryParse(priceVal.toString()) ?? 0.0;
          if (p > 0) {
            return MarketTicker(
              exchangeId: id,
              pair: pair,
              lastPrice: p,
              volume24h: 0.0,
              timestamp: DateTime.now(),
            );
          }
        }
      }
    } catch (e) {
      throw Exception('Connection error: Unable to fetch live price for ${pair.displayName} on CoinMarketCap: $e');
    }

    throw Exception('Connection error: Unable to fetch live price for ${pair.displayName} on CoinMarketCap');
  }
}
