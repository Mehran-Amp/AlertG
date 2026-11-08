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

  static final Map<String, double> _cachedLivePrices = {};
  static DateTime? _lastLivePriceUpdate;

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    // 1. Try Gate.io official /spot/tickers (Fast, returns all 2,039 pairs + live prices)
    try {
      final response = await _dio.get('/spot/tickers');
      if (response.data is List && (response.data as List).isNotEmpty) {
        final pairs = <CurrencyPair>[];
        for (final item in response.data as List) {
          if (item is Map) {
            final id = (item['currency_pair'] ?? item['id'] ?? '').toString().toUpperCase();
            if (id.endsWith('_USDT')) {
              final parts = id.split('_');
              if (parts.length == 2 && parts[0].isNotEmpty) {
                final base = parts[0];
                final p = double.tryParse(item['last']?.toString() ?? item['price']?.toString() ?? '0') ?? 0.0;
                if (p > 0) {
                  _cachedLivePrices[id] = p;
                }
                pairs.add(CurrencyPair(
                  baseCurrency: base,
                  counterCurrency: 'USDT',
                  marketSymbol: id,
                ));
              }
            }
          }
        }
        if (pairs.isNotEmpty) {
          _lastLivePriceUpdate = DateTime.now();
          return pairs;
        }
      }
    } catch (_) {}

    // 2. Fallback: currency_pairs
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

          if (tradeStatus == 'tradable' && quote == 'USDT') {
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
      quoteCurrencies: ['USDT'],
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

      if (json != null) {
        final price = double.tryParse(json['last']?.toString() ?? '0') ?? 0.0;
        final vol = double.tryParse(json['quote_volume']?.toString() ?? '0') ?? 0.0;
        final high = double.tryParse(json['high_24h']?.toString() ?? '0') ?? price;
        final low = double.tryParse(json['low_24h']?.toString() ?? '0') ?? price;

        if (price > 0) {
          _cachedLivePrices[pairId] = price;
          return MarketTicker(
            exchangeId: id,
            pair: pair,
            lastPrice: price,
            volume24h: vol,
            high24h: high,
            low24h: low,
            timestamp: DateTime.now(),
          );
        }
      }
    } catch (_) {}

    // Check cached live price from catalog fetch
    final cachedP = _cachedLivePrices[pairId];
    if (cachedP != null && cachedP > 0) {
      return MarketTicker(
        exchangeId: id,
        pair: pair,
        lastPrice: cachedP,
        volume24h: 0.0,
        timestamp: DateTime.now(),
      );
    }

    throw Exception('Gate.io Live Connection Error for ${pair.displayName}');
  }
}
