import 'package:dio/dio.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// OKX REST Exchange Adapter
class OKXExchange implements Exchange {
  final Dio _dio;

  OKXExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://www.okx.com',
              connectTimeout: const Duration(seconds: 8),
              receiveTimeout: const Duration(seconds: 8),
            ));

  @override
  String get id => 'okx';

  @override
  String get name => 'OKX';

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
    // 1. Try OKX official market/tickers (Fast, returns all 468 pairs + live prices)
    try {
      final response = await _dio.get('/api/v5/market/tickers', queryParameters: {'instType': 'SPOT'});
      final data = response.data?['data'] as List?;
      if (data != null && data.isNotEmpty) {
        final pairs = <CurrencyPair>[];
        for (final item in data) {
          final instId = (item['instId'] ?? '').toString().toUpperCase();
          if (instId.endsWith('-USDT')) {
            final parts = instId.split('-');
            if (parts.length == 2 && parts[0].isNotEmpty) {
              final base = parts[0];
              final p = double.tryParse(item['last']?.toString() ?? '0') ?? 0.0;
              if (p > 0) {
                _cachedLivePrices[instId] = p;
              }
              pairs.add(CurrencyPair(
                baseCurrency: base,
                counterCurrency: 'USDT',
                marketSymbol: instId,
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

    // 2. Fallback: instruments
    try {
      final response = await _dio.get('/api/v5/public/instruments', queryParameters: {'instType': 'SPOT'});
      final data = response.data?['data'] as List?;
      if (data != null && data.isNotEmpty) {
        final pairs = <CurrencyPair>[];
        for (final item in data) {
          final base = item['baseCcy']?.toString().toUpperCase() ?? '';
          final quote = item['quoteCcy']?.toString().toUpperCase() ?? '';
          final instId = item['instId']?.toString() ?? '$base-$quote';
          final state = item['state']?.toString() ?? 'live';

          if (state == 'live' && quote == 'USDT') {
            pairs.add(CurrencyPair(
              baseCurrency: base,
              counterCurrency: quote,
              marketSymbol: instId,
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
    final instId = '${pair.baseCurrency}-${pair.counterCurrency}'.toUpperCase();
    try {
      final response = await _dio.get(
        '/api/v5/market/ticker',
        queryParameters: {'instId': instId},
      );

      final data = (response.data?['data'] as List?)?.firstOrNull as Map<String, dynamic>?;
      if (data != null) {
        final price = double.tryParse(data['last']?.toString() ?? '0') ?? 0.0;
        final vol = double.tryParse(data['vol24h']?.toString() ?? '0') ?? 0.0;
        final high = double.tryParse(data['high24h']?.toString() ?? '0') ?? price;
        final low = double.tryParse(data['low24h']?.toString() ?? '0') ?? price;

        if (price > 0) {
          _cachedLivePrices[instId] = price;
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
    final cachedP = _cachedLivePrices[instId];
    if (cachedP != null && cachedP > 0) {
      return MarketTicker(
        exchangeId: id,
        pair: pair,
        lastPrice: cachedP,
        volume24h: 0.0,
        timestamp: DateTime.now(),
      );
    }

    throw Exception('OKX Live Connection Error for ${pair.displayName}');
  }
}
