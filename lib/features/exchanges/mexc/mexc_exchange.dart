import 'package:dio/dio.dart';
import '../base/crypto_catalog_data.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// MEXC Global REST Exchange Adapter (Unrestricted access to 2,000+ crypto pairs)
class MEXCExchange implements Exchange {
  final Dio _dio;

  MEXCExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://api.mexc.com',
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 10),
            ));

  @override
  String get id => 'mexc';

  @override
  String get name => 'MEXC Global';

  @override
  ExchangeCategory get category => ExchangeCategory.tier1;

  @override
  String get countryBadge => '🌐 Global (2000+ Coins)';

  @override
  String get defaultCounterCurrency => 'USDT';

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    try {
      final response = await _dio.get('/api/v3/exchangeInfo');
      final symbols = response.data?['symbols'] as List?;
      if (symbols != null && symbols.isNotEmpty) {
        final pairs = <CurrencyPair>[];
        for (final item in symbols) {
          final status = item['status']?.toString();
          final isSpot = (item['isSpotTradingAllowed'] as bool?) ?? true;
          final base = item['baseAsset']?.toString().toUpperCase() ?? '';
          final quote = item['quoteAsset']?.toString().toUpperCase() ?? '';
          final symbol = item['symbol']?.toString().toUpperCase() ?? '$base$quote';

          if ((status == '1' || status == 'ENABLED' || status == null) &&
              isSpot &&
              (quote == 'USDT' || quote == 'USDC' || quote == 'BTC')) {
            pairs.add(CurrencyPair(
              baseCurrency: base,
              counterCurrency: quote,
              marketSymbol: symbol,
            ));
          }
        }
        if (pairs.isNotEmpty) return pairs;
      }
    } catch (_) {}

    return CryptoCatalogData.buildPairs(quoteCurrencies: ['USDT', 'USDC']);
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
    final symbol = '${pair.baseCurrency}${pair.counterCurrency}'.toUpperCase();
    try {
      final response = await _dio.get(
        '/api/v3/ticker/24hr',
        queryParameters: {'symbol': symbol},
      );

      final json = response.data as Map<String, dynamic>;
      final price = double.tryParse(json['lastPrice']?.toString() ?? '0') ?? 0.0;
      final vol = double.tryParse(json['quoteVolume']?.toString() ?? json['volume']?.toString() ?? '0') ?? 0.0;
      final high = double.tryParse(json['highPrice']?.toString() ?? '0') ?? price;
      final low = double.tryParse(json['lowPrice']?.toString() ?? '0') ?? price;

      if (price <= 0) {
        throw Exception('Invalid price received from MEXC for $symbol');
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
      throw Exception('MEXC Live Connection Error for ${pair.displayName}: $e');
    }
  }
}
