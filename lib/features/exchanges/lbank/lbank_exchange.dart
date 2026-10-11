import 'package:dio/dio.dart';
import '../base/crypto_catalog_data.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';
import '../base/universal_price_aggregator.dart';

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
            pairs.add(CurrencyPair(
              baseCurrency: parts[0].toUpperCase(),
              counterCurrency: parts[1].toUpperCase(),
              marketSymbol: sym,
            ));
          }
        }
        if (pairs.isNotEmpty) return pairs;
      }
    } catch (_) {}

    return CryptoCatalogData.buildPairs(
      quoteCurrencies: ['USDT', 'BTC', 'ETH'],
      symbolFormatter: (b, q) => '${b.toLowerCase()}_${q.toLowerCase()}',
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
    final symbol = '${pair.baseCurrency.toLowerCase()}_${pair.counterCurrency.toLowerCase()}';

    // 1. Direct LBank API
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
    } catch (_) {}

    // 2. Multi-gateway fallback
    final result = await UniversalPriceAggregator.fetchPriceAndVolume(
      baseCoin: pair.baseCurrency,
      quoteCurrency: pair.counterCurrency,
    );

    if (result != null && result['price'] != null && result['price']! > 0) {
      return MarketTicker(
        exchangeId: id,
        pair: pair,
        lastPrice: result['price']!,
        volume24h: result['volume'] ?? 0.0,
        timestamp: DateTime.now(),
      );
    }

    throw Exception('Connection error: Unable to fetch live price for ${pair.displayName} on LBank');
  }
}
