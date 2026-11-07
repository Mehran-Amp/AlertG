import 'package:dio/dio.dart';
import '../base/crypto_catalog_service.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// Kifpool Exchange Adapter (Official Iranian Crypto Exchange & Multi-Currency Platform)
/// Direct REST API integration with official https://api.kifpool.app endpoints.
/// Supports 1,200+ coins in both TMN (Toman) and USDT quotes.
class KifpoolExchange implements Exchange {
  final Dio _dio;
  static final Map<String, MarketTicker> _lastKnownLiveTickers = {};

  KifpoolExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://api.kifpool.app',
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 10),
              headers: {
                'Accept': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
              },
            ));

  @override
  String get id => 'kifpool';

  @override
  String get name => 'Kifpool';

  @override
  ExchangeCategory get category => ExchangeCategory.middleEast;

  @override
  String get countryBadge => '🇮🇷 Iran';

  @override
  String get defaultCounterCurrency => 'TMN';

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    try {
      final response = await _dio.get('/api/spot/price');
      final data = response.data;
      if (data is List && data.isNotEmpty) {
        final pairs = <CurrencyPair>[];
        for (final item in data) {
          if (item is Map) {
            final base = (item['symbol'] ?? '').toString().toUpperCase().trim();
            if (base.isEmpty) continue;

            // 1. Add TMN pair
            if (item['priceBuyIRT'] != null || item['priceSellIRT'] != null) {
              pairs.add(CurrencyPair(
                baseCurrency: base,
                counterCurrency: 'TMN',
                marketSymbol: '${base}TMN',
              ));
            }

            // 2. Add USDT pair
            if (item['price'] != null) {
              pairs.add(CurrencyPair(
                baseCurrency: base,
                counterCurrency: 'USDT',
                marketSymbol: '${base}USDT',
              ));
            }
          }
        }

        if (pairs.isNotEmpty) {
          pairs.sort((a, b) {
            if (a.counterCurrency == 'TMN' && b.counterCurrency != 'TMN') return -1;
            if (a.counterCurrency != 'TMN' && b.counterCurrency == 'TMN') return 1;
            return a.baseCurrency.compareTo(b.baseCurrency);
          });
          return pairs;
        }
      }
    } catch (_) {}

    // Fallback to disk cache or dynamic server catalog service
    try {
      final cached = await CryptoCatalogService.instance.fetchPairsForExchange(
        id,
        forceRefresh: false,
      );
      if (cached.isNotEmpty) return cached;
    } catch (_) {}

    // Safe base fallback for primary coins
    return [
      CurrencyPair(baseCurrency: 'BTC', counterCurrency: 'TMN', marketSymbol: 'BTCTMN'),
      CurrencyPair(baseCurrency: 'ETH', counterCurrency: 'TMN', marketSymbol: 'ETHTMN'),
      CurrencyPair(baseCurrency: 'USDT', counterCurrency: 'TMN', marketSymbol: 'USDTTMN'),
      CurrencyPair(baseCurrency: 'DOGE', counterCurrency: 'TMN', marketSymbol: 'DOGETMN'),
      CurrencyPair(baseCurrency: 'SHIB', counterCurrency: 'TMN', marketSymbol: 'SHIBTMN'),
      CurrencyPair(baseCurrency: 'BTC', counterCurrency: 'USDT', marketSymbol: 'BTCUSDT'),
      CurrencyPair(baseCurrency: 'ETH', counterCurrency: 'USDT', marketSymbol: 'ETHUSDT'),
      CurrencyPair(baseCurrency: 'SOL', counterCurrency: 'USDT', marketSymbol: 'SOLUSDT'),
    ];
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

  static List<dynamic>? _cachedSpotPrices;
  static DateTime? _lastSpotPriceFetch;

  @override
  Future<MarketTicker> fetchTicker(CurrencyPair pair) async {
    final cacheKey = '${pair.baseCurrency}_${pair.counterCurrency}'.toUpperCase();
    final baseSym = pair.baseCurrency.toUpperCase();
    final isTmn = pair.counterCurrency.toUpperCase() == 'TMN' || pair.counterCurrency.toUpperCase() == 'IRT';

    try {
      final now = DateTime.now();
      if (_cachedSpotPrices == null ||
          _lastSpotPriceFetch == null ||
          now.difference(_lastSpotPriceFetch!) > const Duration(seconds: 15)) {
        final response = await _dio.get('/api/spot/price');
        if (response.data is List && (response.data as List).isNotEmpty) {
          _cachedSpotPrices = response.data as List;
          _lastSpotPriceFetch = now;
        }
      }

      if (_cachedSpotPrices != null) {
        for (final item in _cachedSpotPrices!) {
          if (item is Map && (item['symbol'] ?? '').toString().toUpperCase() == baseSym) {
            double price = 0.0;
            if (isTmn) {
              final buyIrt = double.tryParse(item['priceBuyIRT']?.toString() ?? '') ?? 0.0;
              final sellIrt = double.tryParse(item['priceSellIRT']?.toString() ?? '') ?? 0.0;
              if (buyIrt > 0 && sellIrt > 0) {
                price = ((buyIrt + sellIrt) / 2.0) / 10.0; // 1 TMN = 10 Rials (IRT)
              } else if (buyIrt > 0) {
                price = buyIrt / 10.0;
              } else if (sellIrt > 0) {
                price = sellIrt / 10.0;
              }
            } else {
              price = double.tryParse(item['price']?.toString() ?? '') ?? 0.0;
            }

            if (price > 0) {
              final vol = double.tryParse(item['volume']?.toString() ?? '') ?? 0.0;
              final high = double.tryParse(item['high']?.toString() ?? '') ?? 0.0;
              final low = double.tryParse(item['low']?.toString() ?? '') ?? 0.0;

              final ticker = MarketTicker(
                exchangeId: id,
                pair: pair,
                lastPrice: price,
                volume24h: vol,
                high24h: high > 0 ? high : null,
                low24h: low > 0 ? low : null,
                timestamp: DateTime.now(),
              );
              _lastKnownLiveTickers[cacheKey] = ticker;
              return ticker;
            }
          }
        }
      }
    } catch (_) {}

    final cached = _lastKnownLiveTickers[cacheKey];
    if (cached != null) return cached;

    throw Exception('No live price returned from Kifpool for ${pair.baseCurrency}/${pair.counterCurrency}');
  }
}
