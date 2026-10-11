import 'package:dio/dio.dart';
import '../base/crypto_catalog_data.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/iran_market_gateway.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// TetherLand Exchange Adapter (Leading Iranian USDT Trading Platform)
/// Direct REST API integration with real-time Toman & USDT rates.
class TetherlandExchange implements Exchange {
  final Dio _dio;
  static final Map<String, MarketTicker> _lastKnownLiveTickers = {};

  TetherlandExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://api.tetherland.com',
              connectTimeout: const Duration(seconds: 8),
              receiveTimeout: const Duration(seconds: 8),
              headers: {
                'Accept': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
              },
            ));

  @override
  String get id => 'tetherland';

  @override
  String get name => 'TetherLand';

  @override
  ExchangeCategory get category => ExchangeCategory.middleEast;

  @override
  String get countryBadge => '🇮🇷 Iran';

  @override
  String get defaultCounterCurrency => 'TMN';

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    return CryptoCatalogData.buildPairs(
      quoteCurrencies: ['TMN', 'USDT'],
      symbolFormatter: (b, q) => '$b/$q',
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
    final cacheKey = '${pair.baseCurrency}_${pair.counterCurrency}'.toUpperCase();

    // 1. Direct TetherLand API for USDT/TMN
    try {
      if (pair.baseCurrency.toUpperCase() == 'USDT' &&
          (pair.counterCurrency.toUpperCase() == 'TMN' || pair.counterCurrency.toUpperCase() == 'IRT')) {
        final response = await _dio.get('/currencies');
        final currencies = response.data?['data']?['currencies'] as Map<String, dynamic>?;
        final usdtData = currencies?['USDT'] as Map<String, dynamic>?;
        if (usdtData != null) {
          final p = double.tryParse(usdtData['price']?.toString() ?? '0') ?? 0.0;
          final high = double.tryParse(usdtData['last24hMax']?.toString() ?? '0') ?? 0.0;
          final low = double.tryParse(usdtData['last24hMin']?.toString() ?? '0') ?? 0.0;

          if (p > 0) {
            final ticker = MarketTicker(
              exchangeId: id,
              pair: pair,
              lastPrice: p,
              high24h: high > 0 ? high : null,
              low24h: low > 0 ? low : null,
              volume24h: 0.0,
              timestamp: DateTime.now(),
            );
            _lastKnownLiveTickers[cacheKey] = ticker;
            return ticker;
          }
        }
      }
    } catch (_) {}

    // 2. Multi-Gateway Resilient Fallback for all other crypto pairs
    try {
      final estimatedPrice = await IranMarketGateway.getEstimatedPrice(
        baseCoin: pair.baseCurrency,
        quoteCurrency: pair.counterCurrency,
      );
      if (estimatedPrice > 0) {
        final ticker = MarketTicker(
          exchangeId: id,
          pair: pair,
          lastPrice: estimatedPrice,
          volume24h: 0.0,
          timestamp: DateTime.now(),
        );
        _lastKnownLiveTickers[cacheKey] = ticker;
        return ticker;
      }
    } catch (_) {}

    // 3. Persistent Last Known Live Ticker (Preserves authentic online price when offline)
    if (_lastKnownLiveTickers.containsKey(cacheKey)) {
      return _lastKnownLiveTickers[cacheKey]!;
    }

    throw Exception('Connection error: Live price unavailable for ${pair.displayName} on TetherLand');
  }
}
