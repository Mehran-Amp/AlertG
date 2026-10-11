import 'package:dio/dio.dart';
import '../base/crypto_catalog_data.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// Gate.io REST Exchange Adapter (Unrestricted access to 2,000+ crypto pairs)
class GateioExchange implements Exchange {
  final Dio _dio;

  GateioExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://api.gateio.ws/api/v4',
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 10),
            ));

  @override
  String get id => 'gateio';

  @override
  String get name => 'Gate.io';

  @override
  ExchangeCategory get category => ExchangeCategory.tier1;

  @override
  String get countryBadge => '🌐 Global (2000+ Coins)';

  @override
  String get defaultCounterCurrency => 'USDT';

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    try {
      final response = await _dio.get('/spot/currency_pairs');
      final list = response.data as List?;
      if (list != null && list.isNotEmpty) {
        final pairs = <CurrencyPair>[];
        for (final item in list) {
          final tradeStatus = item['trade_status']?.toString();
          final base = item['base']?.toString().toUpperCase() ?? '';
          final quote = item['quote']?.toString().toUpperCase() ?? '';
          final id = item['id']?.toString() ?? '${base}_$quote';

          if (tradeStatus == 'tradable' && (quote == 'USDT' || quote == 'USDC' || quote == 'BTC')) {
            pairs.add(CurrencyPair(
              baseCurrency: base,
              counterCurrency: quote,
              marketSymbol: id,
            ));
          }
        }
        if (pairs.isNotEmpty) return pairs;
      }
    } catch (_) {}

    return CryptoCatalogData.buildPairs(
      quoteCurrencies: ['USDT', 'USDC'],
      symbolFormatter: (b, q) => '${b}_$q',
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
    final pairId = '${pair.baseCurrency}_${pair.counterCurrency}'.toUpperCase();
    try {
      final response = await _dio.get(
        '/spot/tickers',
        queryParameters: {'currency_pair': pairId},
      );

      final list = response.data as List?;
      final json = list?.firstOrNull as Map<String, dynamic>?;

      if (json == null) {
        throw Exception('Market ticker not found on Gate.io for $pairId');
      }

      final price = double.tryParse(json['last']?.toString() ?? '0') ?? 0.0;
      final vol = double.tryParse(json['quote_volume']?.toString() ?? '0') ?? 0.0;
      final high = double.tryParse(json['high_24h']?.toString() ?? '0') ?? price;
      final low = double.tryParse(json['low_24h']?.toString() ?? '0') ?? price;

      if (price <= 0) {
        throw Exception('Invalid price received from Gate.io for $pairId');
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
      throw Exception('Gate.io Live Connection Error for ${pair.displayName}: $e');
    }
  }
}
