import 'package:dio/dio.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// Kraken REST Exchange Adapter (Unrestricted access to all Kraken pairs)
class KrakenExchange implements Exchange {
  final Dio _dio;

  KrakenExchange({Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: 'https://api.kraken.com',
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 10),
            ));

  @override
  String get id => 'kraken';

  @override
  String get name => 'Kraken';

  @override
  ExchangeCategory get category => ExchangeCategory.tier1;

  @override
  String get countryBadge => '🇺🇸 USA / EU (700+ Pairs)';

  @override
  String get defaultCounterCurrency => 'USDT';

  static final Map<String, double> _cachedLivePrices = {};
  static DateTime? _lastLivePriceUpdate;

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    // 1. Try Kraken official /0/public/Ticker (Fast, returns all 739 pairs + live prices)
    try {
      final response = await _dio.get('/0/public/Ticker');
      final result = response.data?['result'] as Map<String, dynamic>?;
      if (result != null && result.isNotEmpty) {
        final pairs = <CurrencyPair>[];
        for (final entry in result.entries) {
          final sym = entry.key.toUpperCase();
          if (sym.endsWith('USDT') || sym.endsWith('USD')) {
            final isUsdt = sym.endsWith('USDT');
            final quote = isUsdt ? 'USDT' : 'USD';
            var rawBase = sym.substring(0, sym.length - quote.length);
            rawBase = rawBase.replaceAll('XXBT', 'BTC').replaceAll('XBT', 'BTC').replaceAll('XETH', 'ETH');
            if (rawBase.startsWith('X') && rawBase.length == 4) {
              rawBase = rawBase.substring(1);
            }
            if (rawBase.isNotEmpty) {
              final c = entry.value?['c'] as List?;
              final p = double.tryParse(c?.firstOrNull?.toString() ?? '0') ?? 0.0;
              if (p > 0) {
                _cachedLivePrices[sym] = p;
                _cachedLivePrices['${rawBase}${quote}'] = p;
              }
              pairs.add(CurrencyPair(
                baseCurrency: rawBase,
                counterCurrency: quote,
                marketSymbol: entry.key,
              ));
            }
          }
        }
        if (pairs.isNotEmpty) {
          _lastLivePriceUpdate = DateTime.now();
          return pairs;
        }
      }
    } catch (_) {}

    // 2. Fallback: AssetPairs
    try {
      final response = await _dio.get('/0/public/AssetPairs');
      final result = response.data?['result'] as Map<String, dynamic>?;
      if (result != null && result.isNotEmpty) {
        final pairs = <CurrencyPair>[];
        for (final entry in result.entries) {
          final val = entry.value as Map<String, dynamic>?;
          final wsname = val?['wsname']?.toString();
          final status = val?['status']?.toString();

          if (status != 'cancel_only' && status != 'delisted') {
            String base = '';
            String quote = '';
            if (wsname != null && wsname.contains('/')) {
              final parts = wsname.split('/');
              base = parts[0].replaceAll('XBT', 'BTC').toUpperCase();
              quote = parts[1].toUpperCase();
            } else {
              base = (val?['base']?.toString() ?? '').replaceAll('XXBT', 'BTC').replaceAll('XETH', 'ETH').replaceAll('ZUSD', 'USD').toUpperCase();
              quote = (val?['quote']?.toString() ?? '').replaceAll('ZUSD', 'USD').replaceAll('ZEUR', 'EUR').toUpperCase();
            }
            if (base.isNotEmpty && (quote == 'USDT' || quote == 'USD')) {
              pairs.add(CurrencyPair(
                baseCurrency: base,
                counterCurrency: quote,
                marketSymbol: entry.key,
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
    final symbol = pair.marketSymbol;
    try {
      final response = await _dio.get(
        '/0/public/Ticker',
        queryParameters: {'pair': symbol},
      );

      final result = response.data?['result'] as Map<String, dynamic>?;
      final pairData = result?.values.firstOrNull as Map<String, dynamic>?;

      if (pairData != null) {
        final c = pairData['c'] as List?;
        final price = double.tryParse(c?.firstOrNull?.toString() ?? '0') ?? 0.0;
        final v = pairData['v'] as List?;
        final vol = double.tryParse(v?.lastOrNull?.toString() ?? '0') ?? 0.0;

        if (price > 0) {
          _cachedLivePrices[symbol] = price;
          return MarketTicker(
            exchangeId: id,
            pair: pair,
            lastPrice: price,
            volume24h: vol,
            timestamp: DateTime.now(),
          );
        }
      }
    } catch (_) {}

    // Check cached live price from catalog fetch
    final cachedP = _cachedLivePrices[symbol] ?? _cachedLivePrices['${pair.baseCurrency}${pair.counterCurrency}'];
    if (cachedP != null && cachedP > 0) {
      return MarketTicker(
        exchangeId: id,
        pair: pair,
        lastPrice: cachedP,
        volume24h: 0.0,
        timestamp: DateTime.now(),
      );
    }

    throw Exception('Kraken Live Connection Error for ${pair.displayName}');
  }
}
