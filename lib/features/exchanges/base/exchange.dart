import '../base/currency_pair.dart';
import 'exchange_category.dart';
import 'models/market_ticker.dart';
import 'models/price_snapshot.dart';

/// Abstract contract for any crypto exchange adapter (inspired by BitcoinChecker).
/// Allows adding unlimited exchanges without modifying core app or evaluation logic.
abstract class Exchange {
  /// Unique identifier of the exchange (e.g. "binance", "coinbase", "kraken")
  String get id;

  /// User-friendly display name (e.g. "Binance", "Coinbase Advanced")
  String get name;

  /// Classification category (Tier-1, Aggregator, Regional, etc.)
  ExchangeCategory get category => ExchangeCategory.tier1;

  /// Country / Origin badge (e.g. "🌐 Global", "🇮🇷 Iran", "🇺🇸 USA", "🇪🇺 Europe")
  String get countryBadge => '🌐 Global';

  /// Default counter currency typically paired on this exchange (e.g. "USDT", "USD")
  String get defaultCounterCurrency;

  /// Dynamically discovers and fetches all active trading currency pairs from the exchange API
  Future<List<CurrencyPair>> fetchCurrencyPairs();

  /// Fetches a lightweight price & volume snapshot for alert rule evaluation
  Future<PriceSnapshot> fetchSnapshot(CurrencyPair pair);

  /// Fetches the latest 24h ticker for a specific currency pair via REST
  Future<MarketTicker> fetchTicker(CurrencyPair pair);
}
