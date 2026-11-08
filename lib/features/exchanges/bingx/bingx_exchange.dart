import 'package:dio/dio.dart';
import '../base/crypto_catalog_service.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// BingX Exchange Adapter (Global Top Tier Crypto & Derivatives Exchange)
/// Direct REST API integration with real-time live price endpoints.
class BingXExchange implements Exchange {
  final Dio _dio;

  BingXExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://open-api.bingx.com',
              connectTimeout: const Duration(seconds: 8),
              receiveTimeout: const Duration(seconds: 8),
              headers: {
                'Accept': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Alarmer/1.0)',
              },
            ));

  @override
  String get id => 'bingx';

  @override
  String get name => 'BingX';

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
    // 1. Try BingX official ticker/24hr endpoint (Fast, returns all 630 pairs + live prices)
    try {
      final response = await _dio.get('/openApi/spot/v1/ticker/24hr');
      final data = response.data;
      if (data is Map && data['data'] is List) {
        final list = data['data'] as List;
        final pairs = <CurrencyPair>[];
        for (final item in list) {
          if (item is Map) {
            final symbol = (item['symbol'] ?? '').toString().toUpperCase();
            if (symbol.endsWith('-USDT')) {
              final parts = symbol.split('-');
              if (parts.length == 2 && parts[0].isNotEmpty) {
                final base = parts[0];
                final p = double.tryParse(item['lastPrice']?.toString() ?? '0') ?? 0.0;
                if (p > 0) {
                  _cachedLivePrices[symbol] = p;
                }
                pairs.add(CurrencyPair(
                  baseCurrency: base,
                  counterCurrency: 'USDT',
                  marketSymbol: symbol,
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

    // 2. Fallback: symbols
    try {
      final response = await _dio.get('/openApi/spot/v1/common/symbols');
      final data = response.data;
      if (data is Map && data['data'] is Map && data['data']['symbols'] is List) {
        final list = data['data']['symbols'] as List;
        final pairs = <CurrencyPair>[];
        for (final item in list) {
          if (item is Map) {
            final symbol = (item['symbol'] ?? '').toString().toUpperCase();
            final parts = symbol.split('-');
            if (parts.length == 2) {
              final base = parts[0];
              final quote = parts[1];
              if (quote == 'USDT' && base.isNotEmpty) {
                pairs.add(CurrencyPair(
                  baseCurrency: base,
                  counterCurrency: quote,
                  marketSymbol: symbol,
                ));
              }
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
    final symbol = '${pair.baseCurrency}-${pair.counterCurrency}'.toUpperCase();

    try {
      final response = await _dio.get(
        '/openApi/spot/v1/ticker/24hr',
        queryParameters: {'symbol': symbol},
      );
      final data = response.data;
      if (data is Map && data['data'] != null) {
        final d = (data['data'] is List && (data['data'] as List).isNotEmpty)
            ? (data['data'] as List).first as Map<String, dynamic>
            : (data['data'] is Map ? data['data'] as Map<String, dynamic> : null);
        if (d != null) {
          final p = double.tryParse(d['lastPrice']?.toString() ?? '0') ?? 0.0;
          final v = double.tryParse(d['volume']?.toString() ?? d['quoteVolume']?.toString() ?? '0') ?? 0.0;
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

    throw Exception('Connection error: Unable to fetch live price for ${pair.displayName} on BingX');
  }
}
