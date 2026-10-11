import 'package:flutter/foundation.dart';
import '../base/currency_pair.dart';
import '../base/currency_pairs_helper.dart';
import '../base/exchange.dart';
import '../base/models/price_snapshot.dart';
import '../base/standard_rest_exchange.dart';
import '../../../core/utils/symbol_filter_helper.dart';

/// Central Exchange Registry (inspired by aneonex/BitcoinChecker).
/// Manages all registered exchanges, handles dynamic pair discovery,
/// provides TTL-based caching, in-flight request collapsing, and parallel searching.
class ExchangeRegistry {
  static const String globalStocksId = 'global_stocks';
  static const String iranMarketId = 'iran_market';
  static const Duration pairCacheTtl = Duration(minutes: 10);

  final Map<String, Exchange> _exchanges = {};
  final Map<String, List<CurrencyPair>> _cachedPairsByExchange = {};
  final Map<String, DateTime> _pairCacheTimestamps = {};
  final Map<String, CurrencyPairsHelper> _cachedHelpersByExchange = {};
  final Map<String, Future<List<CurrencyPair>>> _pendingPairFetches = {};

  ExchangeRegistry();

  /// Registers an exchange adapter instance
  void register(Exchange exchange) {
    _exchanges[exchange.id] = exchange;
  }

  /// Retrieves an exchange adapter by its unique ID
  Exchange? get(String exchangeId) => _exchanges[exchangeId];

  /// Returns all currently registered exchanges strictly sorted alphabetically A-Z by English name
  List<Exchange> getAll() => _exchanges.values.toList()
    ..sort((a, b) {
      if (a.id == globalStocksId) return -1;
      if (b.id == globalStocksId) return 1;
      if (a.id == iranMarketId) return -1;
      if (b.id == iranMarketId) return 1;
      return a.name.toLowerCase().compareTo(b.name.toLowerCase());
    });

  /// Map of all exchanges
  Map<String, Exchange> get asMap => Map.unmodifiable(_exchanges);

  /// Fetches a lightweight price & volume snapshot directly from the specified exchange
  Future<PriceSnapshot?> fetchSnapshotFrom(String exchangeId, CurrencyPair pair) async {
    final exchange = _exchanges[exchangeId];
    if (exchange == null) return null;
    return await exchange.fetchSnapshot(pair);
  }

  /// Preloads or gets cached currency pairs for a specific exchange respecting TTL and collapsing in-flight requests
  Future<List<CurrencyPair>> getCurrencyPairs(String exchangeId) async {
    final cached = _cachedPairsByExchange[exchangeId];
    final timestamp = _pairCacheTimestamps[exchangeId];
    final now = DateTime.now();

    // Check if cache is fresh within TTL
    if (cached != null && timestamp != null && now.difference(timestamp) < pairCacheTtl) {
      return cached;
    }

    // Collapse concurrent requests to single in-flight Future
    if (_pendingPairFetches.containsKey(exchangeId)) {
      return await _pendingPairFetches[exchangeId]!;
    }

    return await refreshCurrencyPairs(exchangeId);
  }

  /// Returns a CurrencyPairsHelper instance for smart filtering
  Future<CurrencyPairsHelper> getPairsHelper(String exchangeId) async {
    final cachedHelper = _cachedHelpersByExchange[exchangeId];
    if (cachedHelper != null && !cachedHelper.isEmpty) {
      return cachedHelper;
    }

    final pairs = await getCurrencyPairs(exchangeId);
    final helper = CurrencyPairsHelper(pairs: pairs);
    _cachedHelpersByExchange[exchangeId] = helper;
    return helper;
  }

  /// Force refresh currency pairs from the specified exchange with error handling and deduplication
  Future<List<CurrencyPair>> refreshCurrencyPairs(String exchangeId) async {
    final exchange = _exchanges[exchangeId];
    if (exchange == null) {
      throw Exception('Exchange $exchangeId not found in registry');
    }

    if (_pendingPairFetches.containsKey(exchangeId)) {
      return await _pendingPairFetches[exchangeId]!;
    }

    final future = () async {
      try {
        final pairs = await exchange.fetchCurrencyPairs();
        _cachedPairsByExchange[exchangeId] = pairs;
        _pairCacheTimestamps[exchangeId] = DateTime.now();
        _cachedHelpersByExchange[exchangeId] = CurrencyPairsHelper(pairs: pairs);
        return pairs;
      } catch (e) {
        debugPrint('Error fetching currency pairs for $exchangeId: $e');
        if (_cachedPairsByExchange.containsKey(exchangeId)) {
          return _cachedPairsByExchange[exchangeId]!;
        }
        // Cache empty list with timestamp to avoid thrashing failed endpoints
        _cachedPairsByExchange[exchangeId] = [];
        _pairCacheTimestamps[exchangeId] = DateTime.now();
        return <CurrencyPair>[];
      } finally {
        _pendingPairFetches.remove(exchangeId);
      }
    }();

    _pendingPairFetches[exchangeId] = future;
    return await future;
  }

  /// Cross-exchange search: Finds matching currency pairs in parallel batches with concurrency limit of 6-8
  Future<Map<String, List<CurrencyPair>>> searchPairsAcrossExchanges(
    String query, {
    int concurrencyLimit = 6,
  }) async {
    final cleanQuery = query.trim();
    if (cleanQuery.isEmpty) return {};

    final candidates = _exchanges.values
        .where((e) => e.id != globalStocksId)
        .toList();

    final results = <String, List<CurrencyPair>>{};

    for (int i = 0; i < candidates.length; i += concurrencyLimit) {
      final end = (i + concurrencyLimit < candidates.length)
          ? i + concurrencyLimit
          : candidates.length;
      final batch = candidates.sublist(i, end);

      final batchFutures = batch.map((exchange) async {
        try {
          final pairs = await getCurrencyPairs(exchange.id)
              .timeout(const Duration(seconds: 4));
          final matched = SymbolFilterHelper.filterAndSort(pairs, cleanQuery)
              .take(50)
              .toList();
          if (matched.isNotEmpty) {
            return MapEntry(exchange.id, matched);
          }
        } catch (e) {
          debugPrint('Error searching pairs on ${exchange.id}: $e');
        }
        return null;
      });

      final batchResults = await Future.wait(batchFutures);
      for (final entry in batchResults) {
        if (entry != null) {
          results[entry.key] = entry.value;
        }
      }
    }

    return results;
  }

  /// Finds which registered exchanges offer a specific pair in parallel batches
  Future<List<Exchange>> findExchangesForPair({
    required String baseCurrency,
    required String counterCurrency,
    int concurrencyLimit = 6,
  }) async {
    final b = baseCurrency.toUpperCase();
    final c = counterCurrency.toUpperCase();
    final candidates = _exchanges.values
        .where((e) => e.id != globalStocksId)
        .toList();

    final available = <Exchange>[];

    for (int i = 0; i < candidates.length; i += concurrencyLimit) {
      final end = (i + concurrencyLimit < candidates.length)
          ? i + concurrencyLimit
          : candidates.length;
      final batch = candidates.sublist(i, end);

      final batchFutures = batch.map((exchange) async {
        try {
          final pairs = await getCurrencyPairs(exchange.id)
              .timeout(const Duration(seconds: 4));
          final exists = pairs.any(
            (p) =>
                p.baseCurrency.toUpperCase() == b &&
                p.counterCurrency.toUpperCase() == c,
          );
          if (exists) {
            return exchange;
          }
        } catch (e) {
          debugPrint('Error searching pair on ${exchange.id}: $e');
        }
        return null;
      });

      final batchResults = await Future.wait(batchFutures);
      for (final ex in batchResults) {
        if (ex != null) {
          available.add(ex);
        }
      }
    }

    return available;
  }

  /// Clears all registered exchanges, caches, helpers, and disposes active clients
  void disposeAll() {
    for (final exchange in _exchanges.values) {
      try {
        if (exchange is StandardRestExchange) {
          exchange.dispose();
        }
      } catch (e) {
        debugPrint('Error disposing exchange ${exchange.id}: $e');
      }
    }
    _exchanges.clear();
    _cachedPairsByExchange.clear();
    _cachedHelpersByExchange.clear();
    _pairCacheTimestamps.clear();
    _pendingPairFetches.clear();
  }
}
