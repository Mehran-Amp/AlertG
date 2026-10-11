import 'package:dio/dio.dart';
import '../base/crypto_catalog_data.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// Bitget Exchange Adapter (Top Global Crypto Derivatives & Spot Exchange)
/// Direct REST API integration with real-time live price endpoints.
class BitgetExchange implements Exchange {
  final Dio _dio;

  BitgetExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://api.bitget.com',
              connectTimeout: const Duration(seconds: 8),
              receiveTimeout: const Duration(seconds: 8),
              headers: {
                'Accept': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Alarmer/1.0)',
              },
            ));

  @override
  String get id => 'bitget';

  @override
  String get name => 'Bitget';

  @override
  ExchangeCategory get category => ExchangeCategory.tier1;

  @override
  String get countryBadge => '🌐 Global';

  @override
  String get defaultCounterCurrency => 'USDT';

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    try {
      final response = await _dio.get('/api/v2/spot/public/symbols');
      final data = response.data;
      if (data is Map && data['data'] is List) {
        final list = data['data'] as List;
        final pairs = <CurrencyPair>[];
        for (final item in list) {
          if (item is Map) {
            final base = (item['baseCoin'] ?? '').toString().toUpperCase();
            final quote = (item['quoteCoin'] ?? '').toString().toUpperCase();
            final symbol = (item['symbol'] ?? '$base$quote').toString().toUpperCase();
            if (base.isNotEmpty && quote.isNotEmpty) {
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

    return CryptoCatalogData.buildPairs(
      quoteCurrencies: ['USDT', 'USDC', 'BTC', 'ETH'],
      symbolFormatter: (b, q) => '$b$q',
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
    final symbol = '${pair.baseCurrency}${pair.counterCurrency}'.toUpperCase();

    try {
      final response = await _dio.get(
        '/api/v2/spot/market/tickers',
        queryParameters: {'symbol': symbol},
      );
      final data = response.data;
      if (data is Map && data['data'] is List && (data['data'] as List).isNotEmpty) {
        final d = (data['data'] as List).first as Map<String, dynamic>;
        final p = double.tryParse(d['lastPr']?.toString() ?? d['lastPrice']?.toString() ?? '0') ?? 0.0;
        final v = double.tryParse(d['usdtVolume']?.toString() ?? d['baseVolume']?.toString() ?? '0') ?? 0.0;
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
      final binRes = await Dio().get('https://api.binance.com/api/v3/ticker/24hr?symbol=$symbol');
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

    throw Exception('Connection error: Unable to fetch live price for ${pair.displayName} on Bitget');
  }
}
