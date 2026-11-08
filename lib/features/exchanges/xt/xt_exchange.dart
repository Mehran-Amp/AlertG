import 'package:dio/dio.dart';
import '../base/crypto_catalog_service.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// XT.COM Exchange Adapter (Global Crypto Spot & Web3 Trading Platform)
class XTExchange implements Exchange {
  final Dio _dio;

  XTExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://sapi.xt.com',
              connectTimeout: const Duration(seconds: 6),
              receiveTimeout: const Duration(seconds: 6),
              headers: {
                'Accept': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
              },
            ));

  @override
  String get id => 'xt';

  @override
  String get name => 'XT.COM';

  @override
  ExchangeCategory get category => ExchangeCategory.tier1;

  @override
  String get countryBadge => '🌐 Global';

  @override
  String get defaultCounterCurrency => 'USDT';

  static final Map<String, double> _cachedLivePrices = {};
  static DateTime? _lastLivePriceUpdate;

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    // 1. Try XT official ticker/price endpoint (Fast, returns all 944 pairs + live prices)
    try {
      final response = await _dio.get('/v4/public/ticker/price');
      if (response.data is Map && response.data['result'] is List) {
        final list = response.data['result'] as List;
        final pairs = <CurrencyPair>[];
        for (final item in list) {
          if (item is Map) {
            final sym = (item['s'] ?? item['symbol'] ?? '').toString().toLowerCase();
            if (sym.endsWith('_usdt')) {
              final parts = sym.split('_');
              if (parts.length == 2 && parts[0].isNotEmpty) {
                final base = parts[0].toUpperCase();
                final p = double.tryParse(item['p']?.toString() ?? item['price']?.toString() ?? '0') ?? 0.0;
                if (p > 0) {
                  _cachedLivePrices[sym] = p;
                  _cachedLivePrices['${base}USDT'] = p;
                }
                pairs.add(CurrencyPair(
                  baseCurrency: base,
                  counterCurrency: 'USDT',
                  marketSymbol: sym,
                ));
              }
            }
          }
        }
        if (pairs.isNotEmpty) {
          _lastLivePriceUpdate = DateTime.now();
          return pairs;
        }
      }
    } catch (_) {}

    // 2. Fallback: symbol
    try {
      final response = await _dio.get('/v4/public/symbol');
      if (response.data is Map && response.data['result'] is Map && response.data['result']['symbols'] is List) {
        final list = response.data['result']['symbols'] as List;
        final pairs = <CurrencyPair>[];
        for (final item in list) {
          if (item is Map) {
            final base = (item['baseCurrency'] ?? '').toString().toUpperCase();
            final quote = (item['quoteCurrency'] ?? '').toString().toUpperCase();
            final symbol = (item['symbol'] ?? '${base}_$quote').toString().toLowerCase();
            if (base.isNotEmpty && quote == 'USDT') {
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
    final symbol = '${pair.baseCurrency.toLowerCase()}_${pair.counterCurrency.toLowerCase()}';

    // 1. Direct XT.COM API
    try {
      final response = await _dio.get('/v4/public/ticker/price', queryParameters: {'symbol': symbol});
      if (response.data is Map && response.data['result'] is List) {
        final list = response.data['result'] as List;
        if (list.isNotEmpty && list.first is Map) {
          final p = double.tryParse(list.first['p']?.toString() ?? list.first['price']?.toString() ?? '0') ?? 0.0;
          if (p > 0) {
            _cachedLivePrices[symbol] = p;
            return MarketTicker(
              exchangeId: id,
              pair: pair,
              lastPrice: p,
              volume24h: 0.0,
              timestamp: DateTime.now(),
            );
          }
        }
      }
    } catch (_) {}

    // Check cached live price from catalog fetch
    final cachedP = _cachedLivePrices[symbol] ?? _cachedLivePrices['${pair.baseCurrency.toUpperCase()}${pair.counterCurrency.toUpperCase()}'];
    if (cachedP != null && cachedP > 0) {
      return MarketTicker(
        exchangeId: id,
        pair: pair,
        lastPrice: cachedP,
        volume24h: 0.0,
        timestamp: DateTime.now(),
      );
    }

    throw Exception('Connection error: Unable to fetch live price for ${pair.displayName} on XT.COM');
  }
}
