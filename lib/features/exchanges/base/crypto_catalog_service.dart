import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import '../../../core/services/server_alert_service.dart';
import 'crypto_catalog_data.dart';
import 'currency_pair.dart';
import 'exchange.dart';

/// Dynamic Cryptocurrency Catalog Service (Phase 10 / R4 & R9 Discipline).
/// Replaces static hardcoded coin catalogs with dynamic server-synced catalogs
/// from `/api/crypto/exchanges/{exchange}/symbols` and provides guaranteed
/// offline persistence with local device cache.
class CryptoCatalogService {
  static final CryptoCatalogService instance = CryptoCatalogService._internal();

  CryptoCatalogService._internal();

  /// In-memory cache for fast lookups during active session
  final Map<String, List<CurrencyPair>> _memCache = {};
  final Map<String, DateTime> _memCacheTimestamps = {};
  static const Duration memCacheTtl = Duration(minutes: 15);

  /// Test hook for injected HTTP client
  @visibleForTesting
  http.Client? testClient;

  /// Test hook for custom cache directory
  @visibleForTesting
  Directory? testCacheDir;

  /// Fetches the dynamic coin catalog for the specified exchange.
  /// 1. Tries the backend API endpoint (`/api/crypto/exchanges/{exchange}/symbols`).
  /// 2. On success, atomically saves to local disk cache.
  /// 3. On network error or offline, falls back to the last healthy local cache.
  /// 4. If neither is available, calls direct exchange adapter.
  Future<List<CurrencyPair>> fetchPairsForExchange(
    String exchangeId, {
    Exchange? fallbackExchange,
    bool forceRefresh = false,
  }) async {
    final cleanId = exchangeId.trim().toLowerCase();
    final now = DateTime.now();

    // 1. Check in-memory cache if not forcing refresh
    if (!forceRefresh &&
        _memCache.containsKey(cleanId) &&
        _memCacheTimestamps.containsKey(cleanId) &&
        now.difference(_memCacheTimestamps[cleanId]!) < memCacheTtl) {
      return _memCache[cleanId]!;
    }

    // 2. Attempt fetching from Server Phase 6 endpoint
    try {
      final baseUrl = ServerAlertService.effectiveBaseUrl;
      final uri = Uri.parse('$baseUrl/api/crypto/exchanges/$cleanId/symbols');
      final client = testClient ?? http.Client();

      final response = await client
          .get(
            uri,
            headers: {
              'Accept': 'application/json',
              'User-Agent': 'AlertG-Flutter-CryptoCatalog/2.0',
            },
          )
          .timeout(const Duration(seconds: 6));

      if (response.statusCode == 200) {
        final decoded = json.decode(utf8.decode(response.bodyBytes));
        if (decoded is Map && decoded['status'] == 'success' && decoded['symbols'] is List) {
          final symbolList = decoded['symbols'] as List;
          final pairs = <CurrencyPair>[];
          for (final item in symbolList) {
            if (item is Map) {
              final base = (item['base_currency'] ?? '').toString().toUpperCase();
              final rawQuote = (item['counter_currency'] ?? 'USDT').toString().toUpperCase();
              final quote = (rawQuote == 'IRT' || rawQuote == 'RLS') ? 'TMN' : rawQuote;
              final marketSym = (item['market_symbol'] ?? '$base$quote').toString();

              if (base.isNotEmpty && quote.isNotEmpty) {
                pairs.add(CurrencyPair(
                  baseCurrency: base,
                  counterCurrency: quote,
                  marketSymbol: marketSym,
                ));
              }
            }
          }

          if (pairs.isNotEmpty) {
            // Save to memory cache
            _memCache[cleanId] = pairs;
            _memCacheTimestamps[cleanId] = now;

            // Save to offline local disk cache asynchronously
            _saveToDiskCache(cleanId, response.body).catchError((e) {
              debugPrint('Failed to save crypto catalog disk cache for $cleanId: $e');
            });

            return pairs;
          }
        }
      }
    } catch (e) {
      debugPrint('Network fetch failed for crypto catalog ($cleanId): $e. Checking offline cache...');
    }

    // 3. Fallback: Load last healthy cached catalog from device disk
    final cached = await _loadFromDiskCache(cleanId);
    if (cached.isNotEmpty) {
      _memCache[cleanId] = cached;
      _memCacheTimestamps[cleanId] = now;
      return cached;
    }

    // 4. Fallback: Direct exchange adapter if available
    if (fallbackExchange != null) {
      try {
        final directPairs = await fallbackExchange.fetchCurrencyPairs();
        if (directPairs.isNotEmpty) {
          _memCache[cleanId] = directPairs;
          _memCacheTimestamps[cleanId] = now;
          return directPairs;
        }
      } catch (e) {
        debugPrint('Direct exchange fallback failed for $cleanId: $e');
      }
    }

    // 5. Guaranteed Fallback: Never display 0 pairs
    final defaultQuote = fallbackExchange?.defaultCounterCurrency ?? (cleanId == 'tabdeal' || cleanId == 'kifpool' ? 'TMN' : 'USDT');
    final fallbackList = CryptoCatalogData.buildPairs(
      quoteCurrencies: [
        defaultQuote,
        if (defaultQuote != 'USDT') 'USDT',
        if (cleanId == 'tabdeal' || cleanId == 'kifpool') 'TMN',
      ],
      symbolFormatter: (b, q) {
        if (cleanId == 'tabdeal') {
          return '${b.toUpperCase()}_${q == "TMN" ? "IRT" : q.toUpperCase()}';
        }
        return '${b.toUpperCase()}${q.toUpperCase()}';
      },
    );
    _memCache[cleanId] = fallbackList;
    _memCacheTimestamps[cleanId] = now;
    return fallbackList;
  }

  /// Saves raw JSON to device cache file
  Future<void> _saveToDiskCache(String exchangeId, String rawJson) async {
    try {
      final dir = testCacheDir ?? await getApplicationDocumentsDirectory();
      final file = File('${dir.path}/crypto_catalog_$exchangeId.json');
      await file.writeAsString(rawJson, flush: true);
    } catch (_) {}
  }

  /// Loads cached catalog from device disk file
  Future<List<CurrencyPair>> _loadFromDiskCache(String exchangeId) async {
    try {
      final dir = testCacheDir ?? await getApplicationDocumentsDirectory();
      final file = File('${dir.path}/crypto_catalog_$exchangeId.json');
      if (await file.exists()) {
        final raw = await file.readAsString();
        final decoded = json.decode(raw);
        if (decoded is Map && decoded['symbols'] is List) {
          final symbolList = decoded['symbols'] as List;
          final pairs = <CurrencyPair>[];
          for (final item in symbolList) {
            if (item is Map) {
              final base = (item['base_currency'] ?? '').toString().toUpperCase();
              final quote = (item['counter_currency'] ?? 'USDT').toString().toUpperCase();
              final marketSym = (item['market_symbol'] ?? '$base$quote').toString();

              if (base.isNotEmpty && quote == 'USDT') {
                pairs.add(CurrencyPair(
                  baseCurrency: base,
                  counterCurrency: quote,
                  marketSymbol: marketSym,
                ));
              }
            }
          }
          return pairs;
        }
      }
    } catch (_) {}
    return <CurrencyPair>[];
  }

  /// Clears in-memory cache
  void clearMemoryCache() {
    _memCache.clear();
    _memCacheTimestamps.clear();
  }
}
