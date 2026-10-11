import 'package:dio/dio.dart';
import '../base/crypto_catalog_data.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/iran_market_gateway.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// Bitbarg Exchange Adapter (Popular Iranian Crypto Instant Purchase & Sell Broker)
/// Direct REST API integration with real-time live price endpoints.
class BitbargExchange implements Exchange {
  final Dio _dio;
  static final Map<String, MarketTicker> _lastKnownLiveTickers = {};

  BitbargExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://api.bitbarg.com',
              connectTimeout: const Duration(seconds: 8),
              receiveTimeout: const Duration(seconds: 8),
              headers: {
                'Accept': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
              },
            ));

  @override
  String get id => 'bitbarg';

  @override
  String get name => 'Bitbarg';

  @override
  ExchangeCategory get category => ExchangeCategory.middleEast;

  @override
  String get countryBadge => '🇮🇷 Iran';

  @override
  String get defaultCounterCurrency => 'TMN';

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    try {
      final response = await _dio.get('/api/v1/currencies?page=1&page_size=200');
      final data = response.data;
      final list = (data is Map && data['result']?['items'] is List)
          ? data['result']['items'] as List
          : (data is Map && data['data'] is List ? data['data'] as List : null);

      if (list != null && list.isNotEmpty) {
        final pairs = <CurrencyPair>[];
        for (final item in list) {
          if (item is Map) {
            final coin = (item['coin'] ?? item['symbol'] ?? item['enName'] ?? item['en_name'] ?? '').toString().toUpperCase();
            if (coin.isNotEmpty) {
              pairs.add(CurrencyPair(
                baseCurrency: coin,
                counterCurrency: 'TMN',
                marketSymbol: '$coin/TMN',
              ));
              pairs.add(CurrencyPair(
                baseCurrency: coin,
                counterCurrency: 'USDT',
                marketSymbol: '$coin/USDT',
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

    // Fallback static pairs catalog for Bitbarg
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
    final coin = pair.baseCurrency.toUpperCase();
    final cacheKey = '${pair.baseCurrency}_${pair.counterCurrency}'.toUpperCase();

    // 1. Direct Bitbarg REST API
    try {
      final response = await _dio.get('/api/v1/currencies?search=$coin');
      final data = response.data;
      final list = (data is Map && data['result']?['items'] is List)
          ? data['result']['items'] as List
          : (data is Map && data['data'] is List ? data['data'] as List : null);

      if (list != null) {
        for (final item in list) {
          if (item is Map && ((item['coin'] ?? item['symbol'])?.toString().toUpperCase() == coin)) {
            final usdPrice = double.tryParse(item['price']?.toString() ?? '0') ?? 0.0;
            if (usdPrice > 0) {
              double finalPrice = usdPrice;
              if (pair.counterCurrency == 'TMN' || pair.counterCurrency == 'IRT') {
                final rate = await IranMarketGateway.getLiveUsdtTomanRate();
                finalPrice = usdPrice * rate;
              }
              final ticker = MarketTicker(
                exchangeId: id,
                pair: pair,
                lastPrice: finalPrice,
                volume24h: 0.0,
                timestamp: DateTime.now(),
              );
              _lastKnownLiveTickers[cacheKey] = ticker;
              return ticker;
            }
          }
        }
      }
    } catch (_) {}

    // 2. Multi-Gateway Fallback (Nobitex/Wallex/Binance)
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

    throw Exception('Connection error: Unable to fetch live price for ${pair.displayName} on Bitbarg');
  }
}
