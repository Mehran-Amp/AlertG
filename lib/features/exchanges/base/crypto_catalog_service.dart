import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import '../../../core/services/server_alert_service.dart';
import 'crypto_catalog_data.dart';
import 'currency_pair.dart';
import 'exchange.dart';

/// Diagnostics record for catalog origin tracking (CAT-4 / Diagnostics).
class CatalogDiagnostic {
  final String exchangeId;
  final String source; // 'server', 'disk_cache', 'direct_exchange', 'static_fallback'
  final int pairCount;
  final DateTime timestamp;
  final String? error;

  CatalogDiagnostic({
    required this.exchangeId,
    required this.source,
    required this.pairCount,
    required this.timestamp,
    this.error,
  });

  Map<String, dynamic> toMap() => {
        'exchange_id': exchangeId,
        'source': source,
        'pair_count': pairCount,
        'timestamp': timestamp.toIso8601String(),
        'error': error,
      };
}

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
  final Map<String, CatalogDiagnostic> _diagnostics = {};
  static const Duration memCacheTtl = Duration(minutes: 15);

  /// Test hook for injected HTTP client
  @visibleForTesting
  http.Client? testClient;

  /// Test hook for custom cache directory
  @visibleForTesting
  Directory? testCacheDir;

  /// Diagnostics getters
  CatalogDiagnostic? getDiagnostic(String exchangeId) =>
      _diagnostics[exchangeId.trim().toLowerCase()];

  Map<String, CatalogDiagnostic> getAllDiagnostics() =>
      Map.unmodifiable(_diagnostics);

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
    final stopwatch = Stopwatch()..start();
    int pageCount = 0;

    // 1. Check in-memory cache if not forcing refresh
    if (!forceRefresh &&
        _memCache.containsKey(cleanId) &&
        _memCacheTimestamps.containsKey(cleanId) &&
        now.difference(_memCacheTimestamps[cleanId]!) < memCacheTtl) {
      final cached = _memCache[cleanId]!;
      debugPrint('[CryptoCatalog] ex=$cleanId source=memory pairs=${cached.length} ms=${stopwatch.elapsedMilliseconds} pages=0 err=none');
      return cached;
    }

    String? lastError;

    // 2. Attempt fetching from Server endpoint with pagination support (CAT-2)
    try {
      final baseUrl = ServerAlertService.effectiveBaseUrl;
      final client = testClient ?? http.Client();
      final pairs = <CurrencyPair>[];
      int? cursor;
      bool hasMore = true;
      const int maxPages = 10; // Max 5,000 symbols safety cap

      while (hasMore && pageCount < maxPages) {
        pageCount++;
        final queryParams = <String, String>{
          'limit': '500',
        };
        if (cursor != null) {
          queryParams['cursor'] = cursor.toString();
        }

        final uri = Uri.parse('$baseUrl/api/crypto/exchanges/$cleanId/symbols')
            .replace(queryParameters: queryParams);

        final response = await client
            .get(
              uri,
              headers: {
                'Accept': 'application/json',
                'User-Agent': 'AlertG-Flutter-CryptoCatalog/2.0',
              },
            )
            .timeout(const Duration(seconds: 8));

        if (response.statusCode == 200) {
          final decoded = json.decode(utf8.decode(response.bodyBytes));
          if (decoded is Map && decoded['status'] == 'success' && decoded['symbols'] is List) {
            final symbolList = decoded['symbols'] as List;
            for (final item in symbolList) {
              if (item is Map) {
                // Dual compatibility (CAT-2): Reads base_currency or base, counter_currency or quote
                final base = (item['base_currency'] ?? item['base'] ?? '').toString().toUpperCase();
                final rawQuote = (item['counter_currency'] ?? item['quote'] ?? 'USDT').toString().toUpperCase();
                final quote = (rawQuote == 'IRT' || rawQuote == 'RLS') ? 'TMN' : rawQuote;
                final marketSym = (item['market_symbol'] ?? item['native_symbol'] ?? item['symbol'] ?? '$base$quote').toString();

                if (base.isNotEmpty && quote.isNotEmpty) {
                  pairs.add(CurrencyPair(
                    baseCurrency: base,
                    counterCurrency: quote,
                    marketSymbol: marketSym,
                  ));
                }
              }
            }

            hasMore = decoded['has_more'] == true;
            if (hasMore && decoded['cursor'] != null) {
              cursor = int.tryParse(decoded['cursor'].toString());
              if (cursor == null) hasMore = false;
            } else {
              hasMore = false;
            }
          } else {
            hasMore = false;
          }
        } else {
          lastError = 'HTTP ${response.statusCode}';
          debugPrint('[CryptoCatalog] ex=$cleanId page_fail cursor=${cursor ?? 0} status=${response.statusCode}');
          hasMore = false;
        }
      }

      if (pairs.isNotEmpty) {
        // Save to memory cache
        _memCache[cleanId] = pairs;
        _memCacheTimestamps[cleanId] = now;
        _diagnostics[cleanId] = CatalogDiagnostic(
          exchangeId: cleanId,
          source: 'server',
          pairCount: pairs.length,
          timestamp: now,
        );

        // Save complete catalog to offline local disk cache
        _savePairsToDiskCache(cleanId, pairs).catchError((e) {
          debugPrint('Failed to save crypto catalog disk cache for $cleanId: $e');
        });

        debugPrint('[CryptoCatalog] ex=$cleanId source=server pairs=${pairs.length} ms=${stopwatch.elapsedMilliseconds} pages=$pageCount err=none');
        return pairs;
      }
    } catch (e) {
      lastError = e.toString();
      debugPrint('[CryptoCatalog] ex=$cleanId page_fail cursor=0 status=$e');
      debugPrint('Network fetch failed for crypto catalog ($cleanId): $e. Checking offline cache...');
    }

    // 3. Fallback: Load last healthy cached catalog from device disk
    final cached = await _loadFromDiskCache(cleanId);
    if (cached.isNotEmpty) {
      _memCache[cleanId] = cached;
      _memCacheTimestamps[cleanId] = now;
      _diagnostics[cleanId] = CatalogDiagnostic(
        exchangeId: cleanId,
        source: 'disk_cache',
        pairCount: cached.length,
        timestamp: now,
        error: lastError,
      );
      debugPrint('[CryptoCatalog] ex=$cleanId source=disk pairs=${cached.length} ms=${stopwatch.elapsedMilliseconds} pages=$pageCount err=${lastError ?? "none"}');
      return cached;
    }

    // 4. Fallback: Direct exchange adapter if available
    if (fallbackExchange != null) {
      try {
        final directPairs = await fallbackExchange.fetchCurrencyPairs();
        if (directPairs.isNotEmpty) {
          _memCache[cleanId] = directPairs;
          _memCacheTimestamps[cleanId] = now;
          _diagnostics[cleanId] = CatalogDiagnostic(
            exchangeId: cleanId,
            source: 'direct_exchange',
            pairCount: directPairs.length,
            timestamp: now,
            error: lastError,
          );
          // Persist direct pairs to disk cache as well
          _savePairsToDiskCache(cleanId, directPairs).catchError((_) {});
          debugPrint('[CryptoCatalog] ex=$cleanId source=direct pairs=${directPairs.length} ms=${stopwatch.elapsedMilliseconds} pages=$pageCount err=${lastError ?? "none"}');
          return directPairs;
        }
      } catch (e) {
        lastError = 'Direct exchange error: $e';
        debugPrint('Direct exchange fallback failed for $cleanId: $e');
      }
    }

    // 5. Guaranteed Fallback: Safe static baseline if network and cache failed
    final defaultQuote = fallbackExchange?.defaultCounterCurrency ??
        (cleanId == 'tabdeal' || cleanId == 'kifpool' ? 'TMN' : 'USDT');
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
    _diagnostics[cleanId] = CatalogDiagnostic(
      exchangeId: cleanId,
      source: 'static_fallback',
      pairCount: fallbackList.length,
      timestamp: now,
      error: lastError ?? 'Offline / server unavailable',
    );
    debugPrint('[CryptoCatalog] ex=$cleanId source=static pairs=${fallbackList.length} ms=${stopwatch.elapsedMilliseconds} pages=$pageCount err=${lastError ?? "none"}');
    return fallbackList;
  }

  /// Saves unified pairs list to device disk cache
  Future<void> _savePairsToDiskCache(String exchangeId, List<CurrencyPair> pairs) async {
    try {
      final dir = testCacheDir ?? await getApplicationDocumentsDirectory();
      final file = File('${dir.path}/crypto_catalog_$exchangeId.json');
      final payload = {
        'status': 'success',
        'exchange': exchangeId,
        'symbols': pairs
            .map((p) => {
                  'base_currency': p.baseCurrency,
                  'counter_currency': p.counterCurrency,
                  'market_symbol': p.marketSymbol,
                  'base': p.baseCurrency,
                  'quote': p.counterCurrency,
                  'native_symbol': p.marketSymbol,
                })
            .toList(),
      };
      await file.writeAsString(json.encode(payload), flush: true);
    } catch (_) {}
  }

  /// Loads cached catalog from device disk file supporting both field conventions
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
              final base = (item['base_currency'] ?? item['base'] ?? '').toString().toUpperCase();
              final rawQuote = (item['counter_currency'] ?? item['quote'] ?? 'USDT').toString().toUpperCase();
              final quote = (rawQuote == 'IRT' || rawQuote == 'RLS') ? 'TMN' : rawQuote;
              final marketSym = (item['market_symbol'] ?? item['native_symbol'] ?? item['symbol'] ?? '$base$quote').toString();

              if (base.isNotEmpty && quote.isNotEmpty) {
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
