import 'currency_pair.dart';
import '../../../core/utils/symbol_filter_helper.dart';

/// Currency Pairs Map Helper (Direct Dart port of BitcoinChecker CurrencyPairsMapHelper)
/// Provides structured querying, base/quote asset extraction, and instant filtering.
class CurrencyPairsHelper {
  final List<CurrencyPair> pairs;
  final DateTime updatedAt;

  CurrencyPairsHelper({
    required this.pairs,
    DateTime? updatedAt,
  }) : updatedAt = updatedAt ?? DateTime.now();

  bool get isEmpty => pairs.isEmpty;
  int get size => pairs.length;

  /// Returns all unique base assets (e.g. BTC, ETH, SOL, TON, DOGE)
  List<String> get baseAssets {
    final seen = <String>{};
    final list = <String>[];
    for (final p in pairs) {
      final b = p.baseCurrency.toUpperCase();
      if (seen.add(b)) {
        list.add(b);
      }
    }
    return list;
  }

  /// Returns all available quote/counter currencies for a given base asset (e.g. [USDT, TMN, BTC])
  List<String> getQuoteAssets(String baseAsset) {
    final b = baseAsset.toUpperCase();
    final seen = <String>{};
    final quotes = <String>[];
    for (final p in pairs) {
      if (p.baseCurrency.toUpperCase() == b) {
        final q = p.counterCurrency.toUpperCase();
        if (seen.add(q)) {
          quotes.add(q);
        }
      }
    }
    return quotes;
  }

  /// Finds the specific CurrencyPair for a base and quote combination
  CurrencyPair? findPair(String baseAsset, String quoteAsset) {
    final b = baseAsset.toUpperCase();
    final q = quoteAsset.toUpperCase();
    for (final p in pairs) {
      if (p.baseCurrency.toUpperCase() == b && p.counterCurrency.toUpperCase() == q) {
        return p;
      }
    }
    return null;
  }

  /// Fast search for pairs matching a user's text query with startsWith prioritization
  List<CurrencyPair> search(String query) {
    return SymbolFilterHelper.filterAndSort(pairs, query);
  }
}
