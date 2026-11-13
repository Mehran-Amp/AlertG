import 'package:dio/dio.dart';
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

  static final Map<String, double> _cachedLivePrices = {};
  static DateTime? _lastLivePriceUpdate;

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    // 1. Try MEXC official ticker/price endpoint (Fast 300ms, returns all 1,420 pairs + live prices)
    try {
      final response = await _dio.get('/api/v3/ticker/price');
      if (response.data is List && (response.data as List).isNotEmpty) {
        final pairs = <CurrencyPair>[];
        for (final item in response.data as List) {
          if (item is Map) {
            final sym = (item['symbol'] ?? '').toString().toUpperCase();
            if (sym.endsWith('USDT') && sym.length > 4) {
              final base = sym.substring(0, sym.length - 4);
              final p = double.tryParse(item['price']?.toString() ?? '0') ?? 0.0;
              if (p > 0) {
                _cachedLivePrices[sym] = p;
              }
              pairs.add(CurrencyPair(
                baseCurrency: base,
                counterCurrency: 'USDT',
                marketSymbol: sym,
              ));
            }
          }
        }
        if (pairs.isNotEmpty) {
          _lastLivePriceUpdate = DateTime.now();
          return pairs;
        }
      }
    } catch (_) {}

    // 2. Fallback: exchangeInfo
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
              quote == 'USDT') {
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

    return <CurrencyPair>[];
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

      if (price > 0) {
        _cachedLivePrices[symbol] = price;
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
    } catch (_) {}

    // Check cached live price from catalog fetch
    final cachedP = _cachedLivePrices[symbol];
    if (cachedP != null && cachedP > 0) {
      return MarketTicker(
        exchangeId: id,
        pair: pair,
        lastPrice: cachedP,
        volume24h: 0.0,
        timestamp: DateTime.now(),
      );
    }

    throw Exception('MEXC Live Connection Error for ${pair.displayName}');
  }
}
