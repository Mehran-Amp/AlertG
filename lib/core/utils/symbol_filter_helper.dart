import '../../features/exchanges/base/currency_pair.dart';
import 'crypto_icons.dart';

/// Intelligent Symbol Filtering and Priority Scoring Engine.
/// Guarantees that prefix matches (e.g. typing 'B' shows BTC, BNB, BCH first; typing 'BT' shows BTC, BTM)
/// are always placed at the very top of search results before substring/contain matches.
class SymbolFilterHelper {
  /// Filters and orders currency pairs with deterministic startsWith prioritization.
  static List<CurrencyPair> filterAndSort(List<CurrencyPair> pairs, String query) {
    final raw = query.trim();
    if (raw.isEmpty) return pairs;

    final cleanOriginal = raw.toUpperCase();
    final q = cleanOriginal
        .replaceAll('/', '')
        .replaceAll('-', '')
        .replaceAll('_', '')
        .replaceAll(' ', '');

    final scored = <(CurrencyPair, int)>[];

    for (final pair in pairs) {
      final base = pair.baseCurrency.toUpperCase();
      final counter = pair.counterCurrency.toUpperCase();
      final symbol = pair.marketSymbol
          .toUpperCase()
          .replaceAll('/', '')
          .replaceAll('-', '')
          .replaceAll('_', '')
          .replaceAll(' ', '');
      final display = pair.displayName.toUpperCase().replaceAll(' ', '');
      final name = CryptoIcons.getName(pair.baseCurrency).toUpperCase();

      int score = -1;

      // Rank 0: Exact base currency match (e.g. query "BTC" matches base "BTC")
      if (base == q || base == cleanOriginal) {
        score = 0;
      }
      // Rank 1: Base currency strictly starts with query (e.g. query "B" matches "BTC", "BNB"; query "BT" matches "BTC")
      else if (base.startsWith(q) || base.startsWith(cleanOriginal)) {
        score = 1;
      }
      // Rank 2: Market symbol starts with query (e.g. "BTCUSDT" starts with "BTC")
      else if (symbol.startsWith(q)) {
        score = 2;
      }
      // Rank 3: Display name starts with query (e.g. "BTC / USDT")
      else if (display.startsWith(q) || pair.displayName.toUpperCase().startsWith(cleanOriginal)) {
        score = 3;
      }
      // Rank 4: Asset full name starts with query (e.g. "Bitcoin" starts with "BIT")
      else if (name.startsWith(q) || name.startsWith(cleanOriginal)) {
        score = 4;
      }
      // Rank 5: Counter currency starts with query (e.g. "USDT")
      else if (counter.startsWith(q)) {
        score = 5;
      }
      // Rank 6: Base currency contains query
      else if (base.contains(q)) {
        score = 6;
      }
      // Rank 7: Symbol or full name contains query
      else if (symbol.contains(q) || display.contains(q) || name.contains(q)) {
        score = 7;
      }

      if (score >= 0) {
        scored.add((pair, score));
      }
    }

    scored.sort((a, b) {
      // 1. Primary sort: Score (Rank 0 -> Rank 7)
      final scoreCmp = a.$2.compareTo(b.$2);
      if (scoreCmp != 0) return scoreCmp;

      // 2. Secondary sort: Base currency length (shorter base currency is cleaner)
      final lenCmp = a.$1.baseCurrency.length.compareTo(b.$1.baseCurrency.length);
      if (lenCmp != 0) return lenCmp;

      // 3. Tertiary sort: Common counter currencies (USDT, USD, TMN) prioritized
      final aCounter = a.$1.counterCurrency.toUpperCase();
      final bCounter = b.$1.counterCurrency.toUpperCase();
      if (aCounter == 'USDT' && bCounter != 'USDT') return -1;
      if (bCounter == 'USDT' && aCounter != 'USDT') return 1;
      if (aCounter == 'USD' && bCounter != 'USD') return -1;
      if (bCounter == 'USD' && aCounter != 'USD') return 1;
      if (aCounter == 'TMN' && bCounter != 'TMN') return -1;
      if (bCounter == 'TMN' && aCounter != 'TMN') return 1;

      // 4. Quaternary sort: Alphabetical display name
      return a.$1.displayName.compareTo(b.$1.displayName);
    });

    return scored.map((e) => e.$1).toList();
  }
}
