import 'package:dio/dio.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// LBank Exchange Adapter (Top Global Crypto Spot & Memecoin Exchange)
class LBankExchange implements Exchange {
  final Dio _dio;

  LBankExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://api.lbkex.com',
              connectTimeout: const Duration(seconds: 6),
              receiveTimeout: const Duration(seconds: 6),
              headers: {
                'Accept': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
              },
            ));

  @override
  String get id => 'lbank';

  @override
  String get name => 'LBank';

  @override
  ExchangeCategory get category => ExchangeCategory.tier1;

  @override
  String get countryBadge => '🌐 Global';

  @override
  String get defaultCounterCurrency => 'USDT';

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    try {
      final response = await _dio.get('/v2/currencyPairs.do');
      if (response.data is Map && response.data['data'] is List) {
        final list = response.data['data'] as List;
        final pairs = <CurrencyPair>[];
        for (final item in list) {
          final sym = item.toString();
          final parts = sym.split('_');
          if (parts.length == 2) {
            final base = parts[0].toUpperCase();
            final quote = parts[1].toUpperCase();
            if (quote == 'USDT') {
              pairs.add(CurrencyPair(
                baseCurrency: base,
                counterCurrency: quote,
                marketSymbol: sym,
              ));
            }
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
    final symbol = '${pair.baseCurrency.toLowerCase()}_${pair.counterCurrency.toLowerCase()}';

    // Direct LBank API (Strict R1: No fallback to other exchanges or aggregators)
    try {
      final response = await _dio.get('/v2/ticker/24hr.do', queryParameters: {'symbol': symbol});
      if (response.data is Map && response.data['data'] is List) {
        final list = response.data['data'] as List;
        if (list.isNotEmpty && list.first is Map) {
          final d = list.first as Map<String, dynamic>;
          final tickerData = d['ticker'] as Map<String, dynamic>? ?? d;
          final p = double.tryParse(tickerData['latest']?.toString() ?? tickerData['lastPrice']?.toString() ?? '0') ?? 0.0;
          final v = double.tryParse(tickerData['vol']?.toString() ?? tickerData['turnover']?.toString() ?? '0') ?? 0.0;
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
      }
    } catch (e) {
      throw Exception('LBank Live Connection Error for ${pair.displayName}: $e');
    }

    throw Exception('Connection error: Unable to fetch live price for ${pair.displayName} on LBank');
  }
}
