import 'package:dio/dio.dart';
import '../base/crypto_catalog_data.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// Bybit REST Exchange Adapter
class BybitExchange implements Exchange {
  final Dio _dio;

  BybitExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://api.bybit.com',
              connectTimeout: const Duration(seconds: 8),
              receiveTimeout: const Duration(seconds: 8),
            ));

  @override
  String get id => 'bybit';

  @override
  String get name => 'Bybit';

  @override
  ExchangeCategory get category => ExchangeCategory.tier1;

  @override
  String get countryBadge => '🇦🇪 UAE / Global';

  @override
  String get defaultCounterCurrency => 'USDT';

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    try {
      final response = await _dio.get('/v5/market/instruments-info', queryParameters: {'category': 'spot'});
      final list = response.data?['result']?['list'] as List?;
      if (list != null && list.isNotEmpty) {
        final pairs = <CurrencyPair>[];
        for (final item in list) {
          final base = item['baseCoin']?.toString().toUpperCase() ?? '';
          final quote = item['quoteCoin']?.toString().toUpperCase() ?? '';
          final symbol = item['symbol']?.toString().toUpperCase() ?? '$base$quote';
          final status = item['status']?.toString() ?? 'Trading';

          if (status == 'Trading' && (quote == 'USDT' || quote == 'USDC')) {
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
    try {
      final symbol = '${pair.baseCurrency}${pair.counterCurrency}'.toUpperCase();
      final response = await _dio.get(
        '/v5/market/tickers',
        queryParameters: {'category': 'spot', 'symbol': symbol},
      );

      final list = response.data?['result']?['list'] as List?;
      final data = list?.firstOrNull as Map<String, dynamic>?;

      if (data == null) {
        throw Exception('Ticker not found on Bybit for $symbol');
      }

      final price = double.tryParse(data['lastPrice']?.toString() ?? '0') ?? 0.0;
      final vol = double.tryParse(data['volume24h']?.toString() ?? '0') ?? 0.0;
      final high = double.tryParse(data['highPrice24h']?.toString() ?? '0') ?? price;
      final low = double.tryParse(data['lowPrice24h']?.toString() ?? '0') ?? price;

      if (price <= 0) {
        throw Exception('Invalid price from Bybit ($price)');
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
      throw Exception('Bybit Live Connection Error for ${pair.displayName}: $e');
    }
  }
}
