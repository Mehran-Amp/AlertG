import '../base/exchange.dart';
import '../base/exchange_category.dart';
import '../base/standard_rest_exchange.dart';
import '../binance/binance_exchange.dart';
import '../bingx/bingx_exchange.dart';
import '../bitget/bitget_exchange.dart';
import '../bybit/bybit_exchange.dart';
import '../coinbase/coinbase_exchange.dart';
import '../coingecko/coingecko_exchange.dart';
import '../coinmarketcap/coinmarketcap_exchange.dart';
import '../gateio/gateio_exchange.dart';
import '../kcex/kcex_exchange.dart';
import '../kifpool/kifpool_exchange.dart';
import '../kraken/kraken_exchange.dart';
import '../kucoin/kucoin_exchange.dart';
import '../lbank/lbank_exchange.dart';
import '../mexc/mexc_exchange.dart';
import '../okx/okx_exchange.dart';
import '../ourbit/ourbit_exchange.dart';
import '../stocks/global_stocks_exchange.dart';
import '../stocks/iran_domestic_exchange.dart';
import '../tabdeal/tabdeal_exchange.dart';
import '../toobit/toobit_exchange.dart';
import '../xt/xt_exchange.dart';

/// Standard Catalog of cryptocurrency and global markets adapters.
class ExchangeCatalog {
  static const String globalStocksId = 'global_stocks';
  static const String iranMarketId = 'iran_market';

  /// Equities, indices, commodities, and macro market adapters
  static List<Exchange> buildMarketsProviders() => [
    GlobalStocksExchange(),
  ];

  /// Iran Domestic Market: Gold, Coins, Free FX, Bourse
  static List<Exchange> buildIranDomesticProviders() => [
    IranDomesticExchange(),
  ];

  /// Iranian domestic cryptocurrency exchanges (Approved: Tabdeal & Kifpool with full TMN & USDT support)
  static List<Exchange> buildIranCryptoExchanges() {
    return <Exchange>[
      TabdealExchange(),
      KifpoolExchange(),
    ];
  }

  /// International cryptocurrency exchanges (Pure Global - No Domestic Mix)
  static List<Exchange> buildInternationalCryptoExchanges() {
    return <Exchange>[
      // --- 16 CANONICAL GLOBAL CRYPTO EXCHANGES (Crypto Version 2) ---
      BinanceExchange(),
      MEXCExchange(),
      KuCoinExchange(),
      GateioExchange(),
      LBankExchange(),
      OKXExchange(),
      KrakenExchange(),
      BybitExchange(),
      BitgetExchange(),
      StandardRestExchange(
        id: 'htx',
        name: 'HTX / Huobi',
        category: ExchangeCategory.tier1,
        countryBadge: '🌐 Global',
        defaultCounterCurrency: 'USDT',
        pairsUrl: 'https://api.huobi.pro/v1/common/symbols',
        tickerUrlTemplate: 'https://api.huobi.pro/market/detail/merged?symbol={BASE}{QUOTE}',
      ),
      BingXExchange(),
      XTExchange(),
      ToobitExchange(),
      StandardRestExchange(
        id: 'poloniex',
        name: 'Poloniex',
        category: ExchangeCategory.tier1,
        countryBadge: '🌐 Global',
        defaultCounterCurrency: 'USDT',
        tickerUrlTemplate: 'https://api.poloniex.com/markets/{BASE_UPPER}_{QUOTE_UPPER}/ticker24h',
      ),
      CoinbaseExchange(),
      StandardRestExchange(
        id: 'bitfinex',
        name: 'Bitfinex',
        category: ExchangeCategory.tier1,
        countryBadge: '🌐 Global',
        defaultCounterCurrency: 'USDT',
        tickerUrlTemplate: 'https://api-pub.bitfinex.com/v2/ticker/t{BASE_UPPER}UST',
      ),
    ];
  }

  /// Combined crypto exchanges (Strictly International & Global)
  static List<Exchange> buildCryptoExchanges() {
    return buildInternationalCryptoExchanges();
  }

  /// Combined catalog containing all market providers and crypto exchanges
  static List<Exchange> buildAllExchanges() {
    final exchanges = <Exchange>[
      ...buildMarketsProviders(),
      ...buildIranDomesticProviders(),
      ...buildCryptoExchanges(),
    ];

    // Strictly sort all exchanges alphabetically A-Z by English name with global stocks prioritized
    exchanges.sort((a, b) {
      if (a.id == globalStocksId) return -1;
      if (b.id == globalStocksId) return 1;
      if (a.id == iranMarketId) return -1;
      if (b.id == iranMarketId) return 1;
      return a.name.toLowerCase().compareTo(b.name.toLowerCase());
    });

    return exchanges;
  }
}
