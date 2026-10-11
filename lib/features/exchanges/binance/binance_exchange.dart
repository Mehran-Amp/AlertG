import 'package:dio/dio.dart';
import '../base/crypto_catalog_data.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// Production-grade Binance Exchange Adapter.
/// Pure REST endpoints for pair discovery, lightweight snapshots, and 24h ticker metrics.
class BinanceExchange implements Exchange {
  final Dio _dio;

  BinanceExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://api.binance.com',
              connectTimeout: const Duration(seconds: 8),
              receiveTimeout: const Duration(seconds: 8),
            ));

  @override
  String get id => 'binance';

  @override
  String get name => 'Binance';

  @override
  ExchangeCategory get category => ExchangeCategory.tier1;

  @override
  String get countryBadge => '🌐 Global #1';

  @override
  String get defaultCounterCurrency => 'USDT';

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    try {
      final response = await _dio.get('/api/v3/exchangeInfo');
      final data = response.data as Map<String, dynamic>;
      final symbols = data['symbols'] as List<dynamic>;

      final pairs = <CurrencyPair>[];
      for (final item in symbols) {
        final symbolMap = item as Map<String, dynamic>;
        final status = symbolMap['status'] as String?;
        final isSpot = (symbolMap['isSpotTradingAllowed'] as bool?) ?? true;
        final quote = symbolMap['quoteAsset'] as String? ?? '';

        if (status == 'TRADING' && isSpot && (quote == 'USDT' || quote == 'USDC' || quote == 'BTC')) {
          pairs.add(CurrencyPair(
            baseCurrency: symbolMap['baseAsset'] as String,
            counterCurrency: quote,
            marketSymbol: symbolMap['symbol'] as String,
          ));
        }
      }
      if (pairs.isNotEmpty) return pairs;
    } catch (_) {}

    // Instant complete fallback list for uninterrupted access
    return CryptoCatalogData.buildPairs(quoteCurrencies: ['USDT', 'BTC', 'USDC']);
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
    final symbol = pair.marketSymbol.toUpperCase();
    try {
      final response = await _dio.get(
        '/api/v3/ticker/24hr',
        queryParameters: {'symbol': symbol},
      );
      final json = response.data as Map<String, dynamic>;
      final price = double.tryParse(json['lastPrice']?.toString() ?? '0') ?? 0.0;
      final vol = double.tryParse(json['quoteVolume']?.toString() ?? '0') ?? 0.0;
      final high = double.tryParse(json['highPrice']?.toString() ?? '0') ?? price;
      final low = double.tryParse(json['lowPrice']?.toString() ?? '0') ?? price;

      if (price <= 0) {
        throw Exception('Invalid price received from Binance for $symbol');
      }

      return MarketTicker(
        exchangeId: id,
        pair: pair,
        lastPrice: price,
        volume24h: vol,
        high24h: high,
        low24h: low,
        timestamp: DateTime.now(),
      );
    } catch (e) {
      throw Exception('Binance Live Connection Error for ${pair.displayName}: $e');
    }
  }
}
