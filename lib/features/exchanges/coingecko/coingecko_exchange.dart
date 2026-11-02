import 'package:dio/dio.dart';
import '../base/crypto_catalog_data.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// CoinGecko Global Crypto Index & DeFi Aggregator
class CoinGeckoExchange implements Exchange {
  final Dio _dio;
  List<CurrencyPair>? _cachedPairs;
  DateTime? _pairsCacheTimestamp;

  CoinGeckoExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://api.coingecko.com/api/v3',
              connectTimeout: const Duration(seconds: 8),
              receiveTimeout: const Duration(seconds: 8),
              headers: {
                'Accept': 'application/json',
                'User-Agent': 'Alarmer/1.0',
              },
            ));

  @override
  String get id => 'coingecko';

  @override
  String get name => 'CoinGecko';

  @override
  ExchangeCategory get category => ExchangeCategory.aggregator;

  @override
  String get countryBadge => '📊 Global Index';

  @override
  String get defaultCounterCurrency => 'USD';

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    if (_cachedPairs != null && _pairsCacheTimestamp != null) {
      final cacheAge = DateTime.now().difference(_pairsCacheTimestamp!);
      if (cacheAge < const Duration(hours: 2)) {
        return _cachedPairs!;
      }
    }

    try {
      final response = await _dio.get(
        '/coins/markets',
        queryParameters: {
          'vs_currency': 'usd',
          'order': 'market_cap_desc',
          'per_page': 250,
          'page': 1,
          'sparkline': false,
        },
      );

      final list = response.data as List<dynamic>;
      final pairs = <CurrencyPair>[];

      for (final item in list) {
        final coin = item as Map<String, dynamic>;
        final symbol = (coin['symbol'] as String).toUpperCase();
        pairs.add(CurrencyPair(
          baseCurrency: symbol,
          counterCurrency: 'USD',
          marketSymbol: '$symbol-USD',
        ));
      }

      if (pairs.isNotEmpty) {
        // Merge with CryptoCatalogData to provide 1000+ coins
        final catalog = CryptoCatalogData.buildPairs(quoteCurrencies: ['USD', 'USDT']);
        final set = <String>{};
        final combined = <CurrencyPair>[];
        for (final p in [...pairs, ...catalog]) {
          if (set.add(p.displayName)) {
            combined.add(p);
          }
        }
        _cachedPairs = combined;
        _pairsCacheTimestamp = DateTime.now();
        return combined;
      }
    } catch (_) {}

    final fallback = CryptoCatalogData.buildPairs(quoteCurrencies: ['USD', 'USDT']);
    _cachedPairs = fallback;
    return fallback;
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

  static const Map<String, String> _knownCoinGeckoIds = {
    'BTC': 'bitcoin',
    'ETH': 'ethereum',
    'USDT': 'tether',
    'SOL': 'solana',
    'BNB': 'binancecoin',
    'XRP': 'ripple',
    'DOGE': 'dogecoin',
    'ADA': 'cardano',
    'TRX': 'tron',
    'AVAX': 'avalanche-2',
    'SHIB': 'shiba-inu',
    'TON': 'the-open-network',
    'DOT': 'polkadot',
    'LINK': 'chainlink',
    'NEAR': 'near',
    'SUI': 'sui',
    'PEPE': 'pepe',
    'LTC': 'litecoin',
    'APT': 'aptos',
  };

  @override
  Future<MarketTicker> fetchTicker(CurrencyPair pair) async {
    final base = pair.baseCurrency.toUpperCase();
    final quote = pair.counterCurrency.toLowerCase();
    final coinId = _knownCoinGeckoIds[base] ?? base.toLowerCase();

    try {
      final res = await _dio.get('/simple/price', queryParameters: {
        'ids': coinId,
        'vs_currencies': quote,
        'include_24hr_vol': 'true',
      });

      if (res.data is Map && res.data[coinId] != null) {
        final d = res.data[coinId] as Map<String, dynamic>;
        final p = double.tryParse(d[quote]?.toString() ?? '0') ?? 0.0;
        final v = double.tryParse(d['${quote}_24h_vol']?.toString() ?? '0') ?? 0.0;
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
    } catch (e) {
      throw Exception('Connection error: Unable to fetch live price for ${pair.displayName} on CoinGecko: $e');
    }

    throw Exception('Connection error: Unable to fetch live price for ${pair.displayName} on CoinGecko');
  }
}
