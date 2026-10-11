import 'package:dio/dio.dart';
import '../base/crypto_catalog_data.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// Configurable Standard REST Exchange Adapter (inspired by BitcoinChecker DataModule)
/// Connects to verified real-time REST endpoints. Never fabricates fake prices.
class StandardRestExchange implements Exchange {
  @override
  final String id;
  @override
  final String name;
  @override
  final ExchangeCategory category;
  @override
  final String countryBadge;
  @override
  final String defaultCounterCurrency;

  final String? tickerUrlTemplate;
  final String? pairsUrl;
  final List<CurrencyPair> fallbackPairs;
  final Dio _dio;

  StandardRestExchange({
    required this.id,
    required this.name,
    required this.category,
    required this.countryBadge,
    required this.defaultCounterCurrency,
    this.tickerUrlTemplate,
    this.pairsUrl,
    required this.fallbackPairs,
    Dio? dio,
  }) : _dio = dio ??
            Dio(BaseOptions(
              connectTimeout: const Duration(seconds: 8),
              receiveTimeout: const Duration(seconds: 8),
              headers: {
                'Accept': 'application/json',
                'User-Agent': 'Alarmer/1.0',
              },
            ));

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    if (pairsUrl != null) {
      try {
        final response = await _dio.get(pairsUrl!);
        final data = response.data;
        if (data is List) {
          final pairs = <CurrencyPair>[];
          // Handle Gemini (List of strings)
          if (data.isNotEmpty && data.first is String) {
            final quotes = ['GUSDPERP', 'USDCPERP', 'PERP', 'USDT', 'USDC', 'USD', 'BTC', 'ETH', 'EUR', 'GBP', 'SGD', 'DAI', 'GUSD'];
            for (final item in data) {
              final sym = item.toString().toUpperCase();
              bool matched = false;
              for (final q in quotes) {
                if (sym.endsWith(q) && sym.length > q.length) {
                  final base = sym.substring(0, sym.length - q.length);
                  pairs.add(CurrencyPair(baseCurrency: base, counterCurrency: q, marketSymbol: item.toString()));
                  matched = true;
                  break;
                }
              }
              if (!matched) {
                pairs.add(CurrencyPair(baseCurrency: sym, counterCurrency: defaultCounterCurrency, marketSymbol: item.toString()));
              }
            }
            if (pairs.isNotEmpty) return pairs;
          }

          // Handle Bitstamp (name with slash like 'EUR/USD') & BitMEX & Standard list of maps
          for (final item in data) {
            if (item is Map) {
              if (item['name'] != null && item['name'].toString().contains('/')) {
                final parts = item['name'].toString().split('/');
                final base = parts[0].trim().toUpperCase();
                final target = parts[1].trim().toUpperCase();
                final symbol = (item['url_symbol'] ?? '$base$target').toString();
                pairs.add(CurrencyPair(baseCurrency: base, counterCurrency: target, marketSymbol: symbol));
                continue;
              }

              // BitMEX: rootSymbol/underlying + quoteCurrency
              final rawBase = (item['rootSymbol'] ?? item['underlying'] ?? item['base'] ?? item['baseCurrency'] ?? item['base_currency'] ?? '').toString().toUpperCase();
              final base = rawBase == 'XBT' ? 'BTC' : rawBase;
              final target = (item['quoteCurrency'] ?? item['quote_currency'] ?? item['target'] ?? item['quote'] ?? defaultCounterCurrency).toString().toUpperCase();
              final symbol = (item['symbol'] ?? item['id'] ?? (rawBase.isNotEmpty ? '$rawBase$target' : '')).toString();

              if (base.isNotEmpty && target.isNotEmpty) {
                pairs.add(CurrencyPair(baseCurrency: base, counterCurrency: target, marketSymbol: symbol.isNotEmpty ? symbol : '$base$target'));
              }
            }
          }
          if (pairs.isNotEmpty) return pairs;
        } else if (data is Map && data['data'] is List) {
          // Handle HTX (data['data'] list with base-currency & quote-currency)
          final pairs = <CurrencyPair>[];
          for (final item in data['data']) {
            if (item is Map) {
              final state = item['state']?.toString().toLowerCase();
              if (state != null && state != 'online') continue;
              final base = (item['base-currency'] ?? item['baseCurrency'] ?? item['base'] ?? '').toString().toUpperCase();
              final target = (item['quote-currency'] ?? item['quoteCurrency'] ?? item['target'] ?? '').toString().toUpperCase();
              final symbol = (item['symbol'] ?? '$base$target').toString();
              if (base.isNotEmpty && target.isNotEmpty) {
                pairs.add(CurrencyPair(baseCurrency: base, counterCurrency: target, marketSymbol: symbol));
              }
            }
          }
          if (pairs.isNotEmpty) return pairs;
        } else if (data is Map && data['result'] is Map) {
          final map = data['result'] as Map<String, dynamic>;
          final pairs = <CurrencyPair>[];
          for (final entry in map.entries) {
            final val = entry.value as Map<String, dynamic>?;
            final base = val?['base']?.toString().toUpperCase() ?? '';
            final quote = val?['quote']?.toString().toUpperCase() ?? '';
            if (base.isNotEmpty && quote.isNotEmpty) {
              pairs.add(CurrencyPair(baseCurrency: base, counterCurrency: quote, marketSymbol: entry.key));
            }
          }
          if (pairs.isNotEmpty) return pairs;
        }
      } catch (_) {}
    }

    if (fallbackPairs.isNotEmpty) {
      return fallbackPairs;
    }

    return CryptoCatalogData.buildPairs(quoteCurrencies: [defaultCounterCurrency]);
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

  void dispose() {
    _dio.close(force: false);
  }

  @override
  Future<MarketTicker> fetchTicker(CurrencyPair pair) async {
    // 1. If specific tickerUrlTemplate provided, query official exchange endpoint
    if (tickerUrlTemplate != null) {
      try {
        final bitmexBase = (id == 'bitmex' && (pair.baseCurrency.toUpperCase() == 'BTC' || pair.baseCurrency.toUpperCase() == 'XBT')) ? 'XBT' : pair.baseCurrency.toUpperCase();
        final bitmexSym = (id == 'bitmex' && pair.marketSymbol.isNotEmpty && !pair.marketSymbol.contains('/'))
            ? pair.marketSymbol
            : (id == 'bitmex' && pair.counterCurrency.toUpperCase() == 'USD'
                ? '${bitmexBase}USD'
                : '${bitmexBase}_${pair.counterCurrency.toUpperCase()}');

        final url = tickerUrlTemplate!
            .replaceAll('{BASE}', pair.baseCurrency.toLowerCase())
            .replaceAll('{QUOTE}', pair.counterCurrency.toLowerCase())
            .replaceAll('{BASE_UPPER}', bitmexBase)
            .replaceAll('{QUOTE_UPPER}', pair.counterCurrency.toUpperCase())
            .replaceAll('{BITMEX_SYMBOL}', bitmexSym)
            .replaceAll('{SYMBOL}', (pair.marketSymbol.isNotEmpty ? pair.marketSymbol : '${pair.baseCurrency}${pair.counterCurrency}').toLowerCase())
            .replaceAll('{SYMBOL_UPPER}', (pair.marketSymbol.isNotEmpty ? pair.marketSymbol : '${pair.baseCurrency}${pair.counterCurrency}').toUpperCase());

        final response = await _dio.get(url);
        final data = response.data;

        double price = 0.0;
        double vol = 0.0;

        if (data is Map<String, dynamic>) {
          // Check tick (HTX), data (Standard), or root object
          final d = data['tick'] is Map
              ? data['tick'] as Map<String, dynamic>
              : (data['data'] is Map ? data['data'] as Map<String, dynamic> : data);
          price = double.tryParse(d['lastPrice']?.toString() ?? d['last']?.toString() ?? d['price']?.toString() ?? d['close']?.toString() ?? '0') ?? 0.0;
          vol = double.tryParse(d['volume']?.toString() ?? d['vol']?.toString() ?? d['volume24h']?.toString() ?? d['quoteVolume']?.toString() ?? d['amount']?.toString() ?? '0') ?? 0.0;
        } else if (data is List && data.isNotEmpty && data.first is Map) {
          final first = data.first as Map<String, dynamic>;
          price = double.tryParse(first['lastPrice']?.toString() ?? first['last']?.toString() ?? first['price']?.toString() ?? first['close']?.toString() ?? '0') ?? 0.0;
          vol = double.tryParse(first['volume24h']?.toString() ?? first['volume']?.toString() ?? first['quote_volume']?.toString() ?? '0') ?? 0.0;
        }

        if (price > 0) {
          return MarketTicker(
            exchangeId: id,
            pair: pair,
            lastPrice: price,
            volume24h: vol,
            timestamp: DateTime.now(),
          );
        }
      } catch (_) {}
    }

    // Zero fake Binance fallback: Throw honest connection error on failure
    throw Exception('Connection error: Unable to fetch live price for ${pair.displayName} on $name');
  }
}
