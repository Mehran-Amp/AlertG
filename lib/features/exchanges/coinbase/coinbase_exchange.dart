import 'package:dio/dio.dart';
import '../base/crypto_catalog_service.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// Coinbase REST Exchange Adapter
class CoinbaseExchange implements Exchange {
  final Dio _dio;

  CoinbaseExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://api.exchange.coinbase.com',
              connectTimeout: const Duration(seconds: 8),
              receiveTimeout: const Duration(seconds: 8),
            ));

  final Map<String, double> _cachedLivePrices = {};

  @override
  String get id => 'coinbase';

  @override
  String get name => 'Coinbase';

  @override
  ExchangeCategory get category => ExchangeCategory.tier1;

  @override
  String get countryBadge => '🇺🇸 USA';

  @override
  String get defaultCounterCurrency => 'USD';

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    try {
      final response = await _dio.get('/products');
      final data = response.data as List;
      final pairs = <CurrencyPair>[];
      for (final item in data) {
        if (item is Map && item['status'] == 'online') {
          final quote = item['quote_currency']?.toString().toUpperCase() ?? '';
          if (quote == 'USD' || quote == 'USDT') {
            final base = item['base_currency']?.toString().toUpperCase() ?? '';
            final id = item['id']?.toString().toUpperCase() ?? '$base-$quote';
            pairs.add(CurrencyPair(
              baseCurrency: base,
              counterCurrency: quote,
              marketSymbol: id,
            ));
          }
        }
      }
      if (pairs.isNotEmpty) return pairs;
    } catch (_) {}

    // Rule R4: Last successfully cached catalog of Coinbase on device disk
    try {
      final diskCached = await CryptoCatalogService.instance.fetchPairsForExchange(
        id,
        forceRefresh: false,
      );
      if (diskCached.isNotEmpty) return diskCached;
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
    final symKey = '${pair.baseCurrency}-${pair.counterCurrency}'.toUpperCase();

    // Check memory cache first
    if (_cachedLivePrices.containsKey(symKey) && (_cachedLivePrices[symKey] ?? 0) > 0) {
      return MarketTicker(
        exchangeId: id,
        pair: pair,
        lastPrice: _cachedLivePrices[symKey]!,
        volume24h: 0.0,
        timestamp: DateTime.now(),
      );
    }

    try {
      final productId = (pair.marketSymbol.isNotEmpty && pair.marketSymbol.contains('-'))
          ? pair.marketSymbol.toUpperCase()
          : symKey;
      final response = await _dio.get('/products/$productId/ticker');
      final data = response.data as Map<String, dynamic>;
      final price = double.tryParse(data['price']?.toString() ?? '0') ?? 0.0;
      final vol = double.tryParse(data['volume']?.toString() ?? '0') ?? 0.0;

      if (price <= 0) {
        throw Exception('Invalid price from Coinbase ($price)');
      }

      _cachedLivePrices[symKey] = price;

      return MarketTicker(
        exchangeId: id,
        pair: pair,
        lastPrice: price,
        volume24h: vol,
        timestamp: DateTime.now(),
      );
    } catch (e) {
      if (_cachedLivePrices.containsKey(symKey) && (_cachedLivePrices[symKey] ?? 0) > 0) {
        return MarketTicker(
          exchangeId: id,
          pair: pair,
          lastPrice: _cachedLivePrices[symKey]!,
          volume24h: 0.0,
          timestamp: DateTime.now(),
        );
      }
      throw Exception('Coinbase Live Connection Error for ${pair.displayName}: $e');
    }
  }
}
