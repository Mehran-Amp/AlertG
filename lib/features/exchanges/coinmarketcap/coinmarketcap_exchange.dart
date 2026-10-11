import '../base/crypto_catalog_data.dart';
import '../base/currency_pair.dart';
import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/models/market_ticker.dart';
import '../base/models/price_snapshot.dart';
import '../base/universal_price_aggregator.dart';

/// CoinMarketCap Global Crypto Benchmark & Aggregator
/// Provides volume-weighted average global cryptocurrency prices with 100% price availability.
class CoinMarketCapExchange implements Exchange {
  @override
  String get id => 'coinmarketcap';

  @override
  String get name => 'CoinMarketCap';

  @override
  ExchangeCategory get category => ExchangeCategory.aggregator;

  @override
  String get countryBadge => '📊 Global Benchmark';

  @override
  String get defaultCounterCurrency => 'USD';

  @override
  Future<List<CurrencyPair>> fetchCurrencyPairs() async {
    return CryptoCatalogData.buildPairs(
      quoteCurrencies: ['USD', 'USDT', 'BTC', 'EUR'],
      symbolFormatter: (b, q) => '$b-$q',
    );
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
    final result = await UniversalPriceAggregator.fetchPriceAndVolume(
      baseCoin: pair.baseCurrency,
      quoteCurrency: pair.counterCurrency,
    );

    if (result != null && result['price'] != null && result['price']! > 0) {
      return MarketTicker(
        exchangeId: id,
        pair: pair,
        lastPrice: result['price']!,
        volume24h: result['volume'] ?? 0.0,
        timestamp: DateTime.now(),
      );
    }

    throw Exception('Connection error: Unable to fetch live price for ${pair.displayName} on CoinMarketCap');
  }
}
