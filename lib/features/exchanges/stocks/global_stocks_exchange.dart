import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../../../core/services/catalog_sync_service.dart';
import '../../../core/services/server_alert_service.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';

/// Comprehensive Global Stock Markets, Commodities, Forex, Crypto Macro & Top 100 Companies Adapter
class GlobalStocksExchange implements Exchange {
  final http.Client _client;

  GlobalStocksExchange({http.Client? client})
      : _client = client ?? http.Client();

  @override
  String get id => 'global_stocks';

  @override
  String get name => 'Global Markets (Stocks / Macro / Forex / Commodities)';

  @override
  ExchangeCategory get category => ExchangeCategory.all;

  @override
  String get countryBadge => '🏛️ Global Equities & Commodities';

  @override
  String get defaultCounterCurrency => 'USD';

  /// Crypto-macro indices (TOTAL*, dominance, Fear & Greed) are fetched from CoinGecko / AlternativeMe
  /// and are not part of the server catalog (crypto is handled separately from the symbol catalog).
  static const List<Map<String, dynamic>> cryptoMacroSymbols = [
    {
      'symbol': 'TOTAL',
      'name': 'Crypto Total Market Cap (TOTAL)',
      'nameFa': 'شاخص کل ارزش بازار کریپتو (TOTAL)',
      'cat': 'CryptoMacro',
      'icon': '🌐',
      'price': 2450.0, // B USD
      'unit': 'B USD',
    },
    {
      'symbol': 'TOTAL2',
      'name': 'Crypto Market Cap Excl. BTC (TOTAL2)',
      'nameFa': 'شاخص بازار کریپتو منهای بیت‌کوین (TOTAL2)',
      'cat': 'CryptoMacro',
      'icon': '🔷',
      'price': 1080.0, // B USD
      'unit': 'B USD',
    },
    {
      'symbol': 'TOTAL3',
      'name': 'Altcoin Market Cap Excl. BTC & ETH (TOTAL3)',
      'nameFa': 'شاخص آلت‌کوین‌ها منهای بیت‌کوین و اتریوم (TOTAL3)',
      'cat': 'CryptoMacro',
      'icon': '🚀',
      'price': 685.0, // B USD
      'unit': 'B USD',
    },
    {
      'symbol': 'BTC.D',
      'name': 'Bitcoin Dominance Index (BTC.D)',
      'nameFa': 'شاخص دامیننس و سهم بازار بیت‌کوین (BTC.D %)',
      'cat': 'CryptoMacro',
      'icon': '₿',
      'price': 58.60, // %
      'unit': '%',
    },
    {
      'symbol': 'USDT.D',
      'name': 'Tether Dominance Index (USDT.D)',
      'nameFa': 'شاخص دامیننس تتر و نقدینگی دلاری (USDT.D %)',
      'cat': 'CryptoMacro',
      'icon': '💵',
      'price': 5.15, // %
      'unit': '%',
    },
    {
      'symbol': 'ETH.D',
      'name': 'Ethereum Dominance Index (ETH.D)',
      'nameFa': 'شاخص دامیننس و سهم بازار اتریوم (ETH.D %)',
      'cat': 'CryptoMacro',
      'icon': '⟠',
      'price': 14.30, // %
      'unit': '%',
    },
    {
      'symbol': 'CRYPTO_FGI',
      'name': 'Crypto Fear & Greed Index',
      'nameFa': 'شاخص احساسات، ترس و طمع کریپتو (0-100)',
      'cat': 'CryptoMacro',
      'icon': '🧭',
      'price': 68.0,
      'unit': 'pts',
    },
  ];

  static const Map<String, String> _catalogCategoryToUiCategory = {
    'stock': 'Top100',
    'forex': 'Forex',
    'commodity': 'Commodities',
    'index': 'Indices',
    'bond': 'Macro',
    'macro': 'Macro',
  };

  static const Map<String, String> _uiCategoryIcon = {
    'Top100': '📈',
    'Forex': '💱',
    'Commodities': '🛢️',
    'Indices': '📊',
    'Macro': '🏛️',
  };

  static const Map<String, String> _catalogUnitToCounterCurrency = {
    r'$': 'USD',
    '¥': 'JPY',
    '€': 'EUR',
    '£': 'GBP',
    'Fr': 'CHF',
  };

  /// Global symbols (stocks, forex, commodities, indices, bonds, macro) come ONLY from the server catalog
  /// (/api/symbols/catalog + delta sync by catalog_version), cached by [CatalogSyncService].
  /// When the app is offline with an empty cache, CatalogSyncService seeds a minimal fallback (max 20 symbols).
  /// Same map shape as the former const list, so existing UI code keeps working.
  static List<Map<String, dynamic>> get predefinedStocks {
    final seen = <String>{};
    final result = <Map<String, dynamic>>[];
    for (final m in cryptoMacroSymbols) {
      seen.add(m['symbol'] as String);
      result.add(m);
    }
    for (final item in CatalogSyncService.instance.items) {
      final uiCat = _catalogCategoryToUiCategory[item.category];
      if (uiCat == null || !item.isActive) continue; // iran_market is served by IranDomesticExchange
      final sym = item.id;
      if (sym.isEmpty || !seen.add(sym)) continue;
      result.add({
        'symbol': sym,
        'name': item.nameEn,
        'nameFa': item.nameFa,
        'cat': uiCat,
        'icon': _uiCategoryIcon[uiCat] ?? '📈',
        'price': item.price ?? 0.0,
        'isTop100': item.category == 'stock',
        'unit': _catalogUnitToCounterCurrency[item.unit] ?? item.unit,
      });
    }
    return result;
  }

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    await CatalogSyncService.instance.initialize(); // idempotent: loads cache / seeds offline fallback
    return predefinedStocks.map<CurrencyPair>((s) {
      final sym = s['symbol'] as String;
      final unit = (s['unit'] as String?) ?? 'USD';
      return CurrencyPair(
        baseCurrency: sym,
        counterCurrency: unit,
        marketSymbol: '$sym/USD',
      );
    }).toList();
  }

  @override
  Future<PriceSnapshot> fetchSnapshot(CurrencyPair pair) async {
    final ticker = await fetchTicker(pair);
    return PriceSnapshot(
      price: ticker.lastPrice,
      volume: ticker.volume24h,
      fetchedAt: ticker.timestamp,
      asOf: ticker.asOf,
      state: ticker.state,
      quoteUnit: ticker.quoteUnit,
      source: ticker.source,
    );
  }

  static final Map<String, MarketTicker> _lastKnownLiveTickers = {};
  static Map<String, dynamic>? _cachedCoinGeckoGlobalData;
  static DateTime? _cachedCoinGeckoTime;

  @override
  Future<MarketTicker> fetchTicker(CurrencyPair pair) async {
    final cleanSymbol = pair.baseCurrency;

    // 1. Specialized Handler for Crypto Macro & Dominance Indices
    if (cleanSymbol == 'TOTAL' ||
        cleanSymbol == 'TOTAL2' ||
        cleanSymbol == 'TOTAL3' ||
        cleanSymbol == 'BTC.D' ||
        cleanSymbol == 'USDT.D' ||
        cleanSymbol == 'ETH.D') {
      try {
        Map<String, dynamic>? data;
        final now = DateTime.now();
        if (_cachedCoinGeckoGlobalData != null &&
            _cachedCoinGeckoTime != null &&
            now.difference(_cachedCoinGeckoTime!) < const Duration(seconds: 60)) {
          data = _cachedCoinGeckoGlobalData;
        } else {
          final res = await _client
              .get(Uri.parse('https://api.coingecko.com/api/v3/global'))
              .timeout(const Duration(seconds: 5));
          if (res.statusCode == 200) {
            final body = jsonDecode(utf8.decode(res.bodyBytes));
            if (body is Map && body['data'] is Map<String, dynamic>) {
              data = body['data'] as Map<String, dynamic>;
              _cachedCoinGeckoGlobalData = data;
              _cachedCoinGeckoTime = now;
            }
          } else {
            debugPrint('CoinGecko /global error: HTTP ${res.statusCode}');
          }
        }

        if (data != null) {
          final totalUsdNum = data['total_market_cap']?['usd'] as num?;
          final marketCapPct = data['market_cap_percentage'] as Map<String, dynamic>?;

          if (totalUsdNum != null && marketCapPct != null) {
            final double totalUsd = totalUsdNum.toDouble();
            final btcPct = (marketCapPct['btc'] as num?)?.toDouble();
            final ethPct = (marketCapPct['eth'] as num?)?.toDouble();
            final usdtPct = (marketCapPct['usdt'] as num?)?.toDouble();

            double targetValue = 0.0;
            String quoteUnit = 'B USD';

            if (cleanSymbol == 'TOTAL') {
              targetValue = totalUsd / 1e9; // in Billions USD
              quoteUnit = 'B USD';
            } else if (cleanSymbol == 'TOTAL2' && btcPct != null) {
              targetValue = (totalUsd * (100 - btcPct) / 100) / 1e9;
              quoteUnit = 'B USD';
            } else if (cleanSymbol == 'TOTAL3' && btcPct != null && ethPct != null) {
              targetValue = (totalUsd * (100 - btcPct - ethPct) / 100) / 1e9;
              quoteUnit = 'B USD';
            } else if (cleanSymbol == 'BTC.D' && btcPct != null) {
              targetValue = btcPct;
              quoteUnit = '%';
            } else if (cleanSymbol == 'USDT.D' && usdtPct != null) {
              targetValue = usdtPct;
              quoteUnit = '%';
            } else if (cleanSymbol == 'ETH.D' && ethPct != null) {
              targetValue = ethPct;
              quoteUnit = '%';
            }

            final updatedAt = data['updated_at'] as int?;
            final asOf = updatedAt != null
                ? DateTime.fromMillisecondsSinceEpoch(updatedAt * 1000, isUtc: true)
                : now;

            if (targetValue > 0) {
              final ticker = MarketTicker(
                exchangeId: id,
                pair: pair,
                lastPrice: targetValue,
                volume24h: 0.0,
                timestamp: asOf,
                asOf: asOf,
                state: 'live',
                quoteUnit: quoteUnit,
                source: 'CoinGecko',
              );
              _lastKnownLiveTickers[cleanSymbol] = ticker;
              return ticker;
            }
          }
        }
      } catch (e) {
        debugPrint('GlobalStocksExchange CoinGecko fetch error ($cleanSymbol): $e');
      }
    }

    if (cleanSymbol == 'CRYPTO_FGI') {
      try {
        final res = await _client
            .get(Uri.parse('https://api.alternative.me/fng/'))
            .timeout(const Duration(seconds: 4));
        if (res.statusCode == 200) {
          final data = jsonDecode(utf8.decode(res.bodyBytes));
          final first = data['data']?[0];
          final valStr = first?['value'];
          final val = double.tryParse(valStr?.toString() ?? '');
          final tsStr = first?['timestamp']?.toString();
          final tsSec = tsStr != null ? int.tryParse(tsStr) : null;
          final asOf = tsSec != null
              ? DateTime.fromMillisecondsSinceEpoch(tsSec * 1000, isUtc: true)
              : null;

          if (val != null && val > 0) {
            final ticker = MarketTicker(
              exchangeId: id,
              pair: pair,
              lastPrice: val,
              volume24h: 0.0,
              timestamp: asOf ?? DateTime.now(),
              asOf: asOf,
              state: 'delayed',
              quoteUnit: 'pts',
              source: 'AlternativeMe',
            );
            _lastKnownLiveTickers[cleanSymbol] = ticker;
            return ticker;
          }
        }
      } catch (e) {
        debugPrint('GlobalStocksExchange CRYPTO_FGI fetch error: $e');
      }
    }

    // 2. Live price comes only from the Python server (/api/price); the app never calls providers directly
    final details = await ServerAlertService.fetchPriceDetailsViaServer(id, cleanSymbol);
    final serverPrice = (details?['price'] as num?)?.toDouble() ?? 0.0;
    if (details != null && serverPrice > 0) {
      final asOfSec = (details['asOf'] as num?)?.toInt();
      final DateTime? asOf = asOfSec != null
          ? DateTime.fromMillisecondsSinceEpoch(asOfSec * 1000, isUtc: true)
          : null;
      final rawState = (details['state'] as String?)?.toUpperCase();
      String state = 'live';
      if (rawState == 'CLOSED') {
        state = 'closed';
      } else if (rawState != null && rawState != 'LIVE') {
        state = 'delayed';
      }
      final ticker = MarketTicker(
        exchangeId: id,
        pair: pair,
        lastPrice: serverPrice,
        volume24h: (details['volume'] as num?)?.toDouble() ?? 0.0,
        high24h: (details['high'] as num?)?.toDouble() ?? serverPrice,
        low24h: (details['low'] as num?)?.toDouble() ?? serverPrice,
        timestamp: asOf ?? DateTime.now(),
        asOf: asOf,
        state: state,
        quoteUnit: (details['currency'] as String?)?.toUpperCase() ?? 'USD',
        source: (details['source'] as String?) ?? 'Server',
      );
      _lastKnownLiveTickers[cleanSymbol] = ticker;
      return ticker;
    }

    // 3. Return cached live ticker if available from previous successful server fetch
    if (_lastKnownLiveTickers.containsKey(cleanSymbol)) {
      return _lastKnownLiveTickers[cleanSymbol]!;
    }

    // If completely offline and never fetched before, do NOT return static catalog price which would corrupt rule state!
    throw Exception('Connection error: Live price unavailable for $cleanSymbol');
  }
}
