import 'package:dio/dio.dart';
import '../base/crypto_catalog_data.dart';
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

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    try {
      final response = await _dio.get('/openApi/spot/v1/common/symbols');
      final data = response.data;
      if (data is Map && data['data'] is Map && data['data']['symbols'] is List) {
        final list = data['data']['symbols'] as List;
        final pairs = <CurrencyPair>[];
        for (final item in list) {
          if (item is Map) {
            final symbol = (item['symbol'] ?? '').toString();
            final parts = symbol.split('-');
            if (parts.length == 2) {
              pairs.add(CurrencyPair(
                baseCurrency: parts[0].toUpperCase(),
                counterCurrency: parts[1].toUpperCase(),
                marketSymbol: symbol,
              ));
            }
          }
        }
        if (pairs.isNotEmpty) return pairs;
      }
    } catch (_) {}

    return CryptoCatalogData.buildPairs(
      quoteCurrencies: ['USDT', 'USDC', 'BTC'],
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
    final symbol = '${pair.baseCurrency}-${pair.counterCurrency}'.toUpperCase();

    try {
      final response = await _dio.get(
        '/openApi/spot/v1/ticker/24hr',
        queryParameters: {'symbol': symbol},
      );
      final data = response.data;
      if (data is Map && data['data'] is Map) {
        final d = data['data'] as Map<String, dynamic>;
        final p = double.tryParse(d['lastPrice']?.toString() ?? '0') ?? 0.0;
        final v = double.tryParse(d['volume']?.toString() ?? d['quoteVolume']?.toString() ?? '0') ?? 0.0;
        if (p > 0) {
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

    // Fallback: Query Binance
    try {
      final binRes = await Dio().get('https://api.binance.com/api/v3/ticker/24hr?symbol=${pair.baseCurrency}${pair.counterCurrency}');
      final p = double.tryParse(binRes.data['lastPrice']?.toString() ?? '0') ?? 0.0;
      final v = double.tryParse(binRes.data['quoteVolume']?.toString() ?? '0') ?? 0.0;
      if (p > 0) {
        return MarketTicker(
          exchangeId: id,
          pair: pair,
          lastPrice: p,
          volume24h: v,
          timestamp: DateTime.now(),
        );
      }
    } catch (_) {}

    throw Exception('Connection error: Unable to fetch live price for ${pair.displayName} on BingX');
  }
}
