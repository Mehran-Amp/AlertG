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
      StandardRestExchange(
        id: 'bitvavo',
        name: 'Bitvavo',
        category: ExchangeCategory.tier1,
        countryBadge: '🇳🇱 Netherlands',
        defaultCounterCurrency: 'EUR',
        tickerUrlTemplate: 'https://api.bitvavo.com/v2/ticker/24h?market={BASE_UPPER}-{QUOTE_UPPER}',
      ),
      StandardRestExchange(
        id: 'upbit',
        name: 'Upbit',
        category: ExchangeCategory.tier1,
        countryBadge: '🇰🇷 South Korea',
        defaultCounterCurrency: 'KRW',
        tickerUrlTemplate: 'https://api.upbit.com/v1/ticker?markets={QUOTE_UPPER}-{BASE_UPPER}',
      ),
      StandardRestExchange(
        id: 'bitmex',
        name: 'BitMEX',
        category: ExchangeCategory.tier1,
        countryBadge: '🌐 Global',
        defaultCounterCurrency: 'USD',
        pairsUrl: 'https://www.bitmex.com/api/v1/instrument?filter=%7B%22typ%22%3A%22FFWCSX%22%7D',
        tickerUrlTemplate: 'https://www.bitmex.com/api/v1/instrument?symbol={BITMEX_SYMBOL}',
      ),
      StandardRestExchange(
        id: 'bitstamp',
        name: 'Bitstamp',
        category: ExchangeCategory.tier1,
        countryBadge: '🇪🇺 Europe',
        defaultCounterCurrency: 'USD',
        pairsUrl: 'https://www.bitstamp.net/api/v2/trading-pairs-info/',
        tickerUrlTemplate: 'https://www.bitstamp.net/api/v2/ticker/{BASE_LOWER}{QUOTE_LOWER}/',
      ),
      StandardRestExchange(
        id: 'gemini',
        name: 'Gemini',
        category: ExchangeCategory.tier1,
        countryBadge: '🇺🇸 USA',
        defaultCounterCurrency: 'USD',
        pairsUrl: 'https://api.gemini.com/v1/symbols',
        tickerUrlTemplate: 'https://api.gemini.com/v1/pubticker/{BASE_LOWER}{QUOTE_LOWER}',
      ),
    ];
  }

  /// Combined crypto exchanges (Iranian Tabdeal & Kifpool pinned at top, plus 16 canonical international)
  static List<Exchange> buildCryptoExchanges() {
    return <Exchange>[
      ...buildIranCryptoExchanges(),
      ...buildInternationalCryptoExchanges(),
    ];
  }

  /// Combined catalog containing all market providers and crypto exchanges
  static List<Exchange> buildAllExchanges() {
    final exchanges = <Exchange>[
      ...buildMarketsProviders(),
      ...buildIranDomesticProviders(),
      ...buildCryptoExchanges(),
    ];

    // Keep global stocks and iran market at top, followed by crypto exchanges
    exchanges.sort((a, b) {
      if (a.id == globalStocksId) return -1;
      if (b.id == globalStocksId) return 1;
      if (a.id == iranMarketId) return -1;
      if (b.id == iranMarketId) return 1;
      if (a.id == 'tabdeal') return -1;
      if (b.id == 'tabdeal') return 1;
      if (a.id == 'kifpool') return -1;
      if (b.id == 'kifpool') return 1;
      return a.name.toLowerCase().compareTo(b.name.toLowerCase());
    });

    return exchanges;
  }
}
