import 'package:dio/dio.dart';
import '../base/crypto_catalog_service.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// Toobit Exchange Adapter (Leading Global Crypto Derivatives & Spot Exchange)
class ToobitExchange implements Exchange {
  final Dio _dio;

  ToobitExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://api.toobit.com',
              connectTimeout: const Duration(seconds: 6),
              receiveTimeout: const Duration(seconds: 6),
              headers: {
                'Accept': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
              },
            ));

  @override
  String get id => 'toobit';

  @override
  String get name => 'Toobit';

  @override
  ExchangeCategory get category => ExchangeCategory.tier1;

  @override
  String get countryBadge => '🌐 Global';

  @override
  String get defaultCounterCurrency => 'USDT';

  static final Map<String, double> _cachedLivePrices = {};
  static DateTime? _lastLivePriceUpdate;

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    // 1. Try Toobit official ticker/price endpoint (Fast, returns all 1,072 pairs + live prices)
    try {
      final response = await _dio.get('/quote/v1/ticker/price');
      final data = response.data;
      if (data is List && data.isNotEmpty) {
        final pairs = <CurrencyPair>[];
        for (final item in data) {
          if (item is Map) {
            final sym = (item['s'] ?? item['symbol'] ?? '').toString().toUpperCase();
            if (sym.endsWith('USDT') && sym.length > 4) {
              final base = sym.substring(0, sym.length - 4);
              final p = double.tryParse(item['p']?.toString() ?? item['price']?.toString() ?? '0') ?? 0.0;
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
      final response = await _dio.get('/api/v1/exchangeInfo');
      if (response.data is Map && response.data['symbols'] is List) {
        final list = response.data['symbols'] as List;
        final pairs = <CurrencyPair>[];
        for (final item in list) {
          if (item is Map) {
            final base = (item['baseAsset'] ?? '').toString().toUpperCase();
            final quote = (item['quoteAsset'] ?? '').toString().toUpperCase();
            final symbol = (item['symbol'] ?? '$base$quote').toString().toUpperCase();
            if (base.isNotEmpty && quote == 'USDT') {
              pairs.add(CurrencyPair(
                baseCurrency: base,
                counterCurrency: quote,
                marketSymbol: symbol,
              ));
            }
          }
        }
        if (pairs.isNotEmpty) return pairs;
      }
    } catch (_) {}

    return [];
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

    // 1. Direct Toobit API (Verified live endpoints: /quote/v1/ticker/price & /quote/v1/ticker/24hr)
    try {
      final response = await _dio.get('/quote/v1/ticker/price', queryParameters: {'symbol': symbol});
      final data = response.data;
      if (data is List && data.isNotEmpty && data.first is Map) {
        final d = data.first as Map<String, dynamic>;
        final p = double.tryParse(d['p']?.toString() ?? d['price']?.toString() ?? '0') ?? 0.0;
        if (p > 0) {
          _cachedLivePrices[symbol] = p;
          return MarketTicker(
            exchangeId: id,
            pair: pair,
            lastPrice: p,
            volume24h: 0.0,
            timestamp: DateTime.now(),
          );
        }
      } else if (data is Map) {
        final d = data as Map<String, dynamic>;
        final p = double.tryParse(d['p']?.toString() ?? d['price']?.toString() ?? d['lastPrice']?.toString() ?? '0') ?? 0.0;
        final v = double.tryParse(d['v']?.toString() ?? d['volume']?.toString() ?? '0') ?? 0.0;
        if (p > 0) {
          _cachedLivePrices[symbol] = p;
          return MarketTicker(
            exchangeId: id,
            pair: pair,
            lastPrice: p,
            volume24h: v,
            timestamp: DateTime.now(),
          );
        }
      }
    } catch (_) {}

    try {
      final response = await _dio.get('/quote/v1/ticker/24hr', queryParameters: {'symbol': symbol});
      final data = response.data;
      if (data is List && data.isNotEmpty && data.first is Map) {
        final d = data.first as Map<String, dynamic>;
        final p = double.tryParse(d['c']?.toString() ?? d['lastPrice']?.toString() ?? '0') ?? 0.0;
        final v = double.tryParse(d['v']?.toString() ?? '0') ?? 0.0;
        if (p > 0) {
          _cachedLivePrices[symbol] = p;
          return MarketTicker(
            exchangeId: id,
            pair: pair,
            lastPrice: p,
            volume24h: v,
            timestamp: DateTime.now(),
          );
        }
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

    throw Exception('Connection error: Unable to fetch live price for ${pair.displayName} on Toobit');
  }
}
