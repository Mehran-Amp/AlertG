import 'package:dio/dio.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/iran_market_gateway.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// Tabdeal Exchange Adapter (Leading Iranian Crypto Spot & OTC Exchange)
/// Direct REST API integration with real-time live price endpoints.
class TabdealExchange implements Exchange {
  final Dio _dio;
  static final Map<String, MarketTicker> _lastKnownLiveTickers = {};

  TabdealExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://api1.tabdeal.org',
              connectTimeout: const Duration(seconds: 8),
              receiveTimeout: const Duration(seconds: 8),
              headers: {
                'Accept': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
              },
            ));

  @override
  String get id => 'tabdeal';

  @override
  String get name => 'Tabdeal';

  @override
  ExchangeCategory get category => ExchangeCategory.middleEast;

  @override
  String get countryBadge => '🇮🇷 Iran';

  @override
  String get defaultCounterCurrency => 'TMN';

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    try {
      final response = await _dio.get('/r/api/v1/exchangeInfo');
      final data = response.data;
      if (data is List && data.isNotEmpty) {
        final pairs = <CurrencyPair>[];
        for (final item in data) {
          if (item is Map) {
            final base = item['baseAsset']?.toString().toUpperCase() ?? '';
            final rawQuote = item['quoteAsset']?.toString().toUpperCase() ?? '';
            final symbol = item['symbol']?.toString().toUpperCase() ?? '';
            final counter = (rawQuote == 'IRT' || rawQuote == 'RLS') ? 'TMN' : rawQuote;

            if (base.isNotEmpty && (counter == 'TMN' || counter == 'USDT')) {
              pairs.add(CurrencyPair(
                baseCurrency: base,
                counterCurrency: counter,
                marketSymbol: symbol.isNotEmpty ? symbol : '$base/$counter',
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

  static List<dynamic>? _cachedMarketInfo;
  static DateTime? _lastMarketInfoFetch;

  @override
  Future<MarketTicker> fetchTicker(CurrencyPair pair) async {
    final cacheKey = '${pair.baseCurrency}_${pair.counterCurrency}'.toUpperCase();
    final isTmn = pair.counterCurrency.toUpperCase() == 'TMN' || pair.counterCurrency.toUpperCase() == 'IRT';
    final quoteSymbol = isTmn ? 'IRT' : pair.counterCurrency.toUpperCase();
    final baseSym = pair.baseCurrency.toUpperCase();
    final tabdealSymbol = '$baseSym$quoteSymbol';
    final tabdealSymbolWithUnderscore = '${baseSym}_$quoteSymbol';

    // 0. Primary Live Source: Tabdeal market_information (1,027 live spot pairs)
    try {
      final now = DateTime.now();
      if (_cachedMarketInfo == null ||
          _lastMarketInfoFetch == null ||
          now.difference(_lastMarketInfoFetch!) > const Duration(seconds: 15)) {
        final res = await _dio.get('/r/plots/market_information/');
        if (res.data is List && (res.data as List).isNotEmpty) {
          _cachedMarketInfo = res.data as List;
          _lastMarketInfoFetch = now;
        }
      }

      if (_cachedMarketInfo != null) {
        for (final item in _cachedMarketInfo!) {
          if (item is Map) {
            final s = (item['symbol'] ?? item['tabdealSymbol'] ?? '').toString().toUpperCase();
            if (s == tabdealSymbol || s == tabdealSymbolWithUnderscore) {
              final rawPrice = double.tryParse(item['price']?.toString() ?? '') ?? 0.0;
              final vol = double.tryParse(item['volume']?.toString() ?? '') ?? 0.0;
              if (rawPrice > 0) {
                // Tabdeal prices for IRT are in Rials -> divide by 10 for Tomans
                final effectivePrice = isTmn ? (rawPrice / 10.0) : rawPrice;
                final ticker = MarketTicker(
                  exchangeId: id,
                  pair: pair,
                  lastPrice: effectivePrice,
                  volume24h: vol,
                  timestamp: DateTime.now(),
                );
                _lastKnownLiveTickers[cacheKey] = ticker;
                return ticker;
              }
            }
          }
        }
      }
    } catch (_) {}

    // 1. Direct Tabdeal Trades API (strip underscore so no 500 error)
    try {
      final response = await _dio.get('/r/api/v1/trades?symbol=$tabdealSymbol');
      final data = response.data;
      if (data is List && data.isNotEmpty && data[0] is Map) {
        final latestTrade = data[0];
        final rawPrice = double.tryParse(latestTrade['price']?.toString() ?? '0') ?? 0.0;
        final q = double.tryParse(latestTrade['qty']?.toString() ?? '0') ?? 0.0;
        if (rawPrice > 0) {
          final effectivePrice = isTmn ? (rawPrice / 10.0) : rawPrice;
          final ticker = MarketTicker(
            exchangeId: id,
            pair: pair,
            lastPrice: effectivePrice,
            volume24h: q,
            timestamp: DateTime.now(),
          );
          _lastKnownLiveTickers[cacheKey] = ticker;
          return ticker;
        }
      }
    } catch (_) {}

    // 1b. Try Tabdeal Depth Orderbook
    try {
      final depthRes = await _dio.get('/r/api/v1/depth?symbol=$tabdealSymbol');
      final bids = depthRes.data?['bids'] as List?;
      if (bids != null && bids.isNotEmpty && bids[0] is List) {
        final rawPrice = double.tryParse(bids[0][0]?.toString() ?? '0') ?? 0.0;
        if (rawPrice > 0) {
          final effectivePrice = isTmn ? (rawPrice / 10.0) : rawPrice;
          final ticker = MarketTicker(
            exchangeId: id,
            pair: pair,
            lastPrice: effectivePrice,
            volume24h: 0.0,
            timestamp: DateTime.now(),
          );
          _lastKnownLiveTickers[cacheKey] = ticker;
          return ticker;
        }
      }
    } catch (_) {}

    // 2. Persistent Last Known Live Ticker (Preserves authentic online price when offline)
    if (_lastKnownLiveTickers.containsKey(cacheKey)) {
      return _lastKnownLiveTickers[cacheKey]!;
    }

    throw Exception('Connection error: Unable to fetch live price for ${pair.displayName} on Tabdeal');
  }
}
