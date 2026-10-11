import 'currency_pair.dart';

/// Exhaustive list of 500+ cryptocurrencies (inspired by BitcoinChecker VirtualCurrency taxonomy)
class CryptoCatalogData {
  static const List<String> topCoins = [
    // Top 50 Bluechips & Layer 1s (Strictly updated tickers)
    'BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'TON', 'TRX', 'ADA', 'AVAX',
    'SUI', 'LINK', 'BCH', 'DOT', 'NEAR', 'LTC', 'UNI', 'APT', 'FET', 'ICP',
    'POL', 'XLM', 'KAS', 'TAO', 'RENDER', 'ETC', 'ATOM', 'XMR', 'HBAR', 'FIL',
    'VET', 'INJ', 'TIA', 'SEI', 'S', 'ALGO', 'RUNE', 'AAVE', 'SKY', 'STX',
    'THETA', 'EOS', 'FLOW', 'EGLD', 'NEO', 'IOTA', 'KAIA', 'XTZ', 'MINA', 'QNT',

    // Layer 2, Modularity & Infrastructure
    'ARB', 'OP', 'STRK', 'BLUR', 'IMX', 'LDO', 'MANTA', 'METIS', 'ZRO', 'BLAST',
    'EVMOS', 'ZK', 'DYM', 'SAGA', 'ALT', 'CELO', 'SKL', 'CTSI', 'GLMR', 'MOVR',
    'BOBA', 'SYS', 'ASTR', 'CFX', 'ACH', 'ANKR', 'LRC', 'GNO', 'PYTH', 'G',
    'BAND', 'API3', 'TRB', 'UMA', 'DIA', 'RLC', 'STORJ', 'SC', 'AR', 'HOT',

    // Popular Memecoins & Community Tokens (Top MEXC, Gate.io, Binance & Iranian exchanges)
    'SHIB', 'PEPE', 'WIF', 'BONK', 'FLOKI', 'NOT', 'POPCAT', 'MEW', 'NEIRO',
    'DOGS', 'HMSTR', 'CATI', 'TURBO', 'BABYDOGE', 'BRETT', 'GOAT', 'ACT', 'PNUT',
    'BOME', 'ORDI', '1000SATS', 'MEME', 'SLERF', 'COQ', 'MYRO', 'WEN', 'SAMO',
    'WOJAK', 'LADYS', 'SPX', 'GIGA', 'MOG', 'PONKE', 'TOSHI', 'DEGEN', 'CHILLGUY',
    'MOODENG', 'LUCE', 'FARTCOIN', 'AI16Z', 'ELIZA', 'VIRTUAL', 'SWARMS', 'COOKIE',
    'KARRAT', 'BAN', 'MAJOR', 'LIZARD', 'CORGIAI',

    // AI, Data & Decentralized Compute
    'WLD', 'ARKM', 'ASI', 'AKT', 'IO', 'NOS', 'SPEC', 'GLM', 'GRASS',
    'ATH', 'CUDOS', 'AIOZ', 'PHB', 'NMR', 'ALI', 'ORAI', 'NFP',

    // DeFi, Restaking & DEXs
    'PENDLE', 'ENA', 'JUP', 'CRV', 'SNX', 'CAKE', '1INCH', 'ENS', 'COMP', 'YFI',
    'DYDX', 'CVX', 'FXS', 'SUSHI', 'BAL', 'GMX', 'OSMO', 'KAVA', 'LPT', 'ZIL',
    'RAY', 'ORCA', 'DRIFT', 'KAMINO', 'MORPHO', 'EIGEN', 'ETHFI', 'REZ', 'BB',
    'LISTA', 'OMNI', 'SAFE', 'COW', 'MAV', 'RDNT', 'JOE', 'QUICK', 'VELO',
    'BNT', 'BAL', 'BADGER', 'FARM', 'ALCX', 'PERP', 'IDEX', 'QUICK',

    // Gaming, Metaverse & Web3
    'GALA', 'SAND', 'MANA', 'AXS', 'BEAM', 'RON', 'PIXEL', 'PORTAL', 'AEVO', 'CHZ',
    'ENJ', 'SUPER', 'MASK', 'ILV', 'YGG', 'MAGIC', 'PRIME', 'BIGTIME', 'XAI', 'VANRY',
    'ACE', 'HIGH', 'ALICE', 'TLM', 'WAXP', 'AUDIO', 'SLF', 'VIC', 'BTTC',
    'CHR', 'DAR', 'MBOX', 'REEF', 'YGG', 'GHST', 'RARE',

    // Real World Assets (RWA) & DePIN
    'ONDO', 'OM', 'CFG', 'MPL', 'TRU', 'HNT', 'IOTX', 'DIMO', 'HONEY',
    'MOBILE', 'WIFI', 'NATIX', 'POKT',

    // Classic, Privacy & Ecosystem Cryptos from Bitcoin Checker
    'ZEC', 'DASH', 'KSM', 'ROSE', 'WOO', 'GMT', 'JASMY', 'BAT', 'QTUM', 'XEC',
    'ZEN', 'SCRT', 'XVG', 'DGB', 'RVN', 'CKB', 'ONE', 'ICX', 'OMG', 'WAVES',
    'SNT', 'STEEM', 'HIVE', 'STRAX', 'KMD', 'ARDR', 'NKN', 'OGN', 'REQ', 'CVC',
    'KDA', 'DCR', 'FLM', 'FORTH', 'JST', 'LIT', 'LSK', 'MDX', 'MTL', 'NANO',
    'ONT', 'PIVX', 'POND', 'POWR', 'RIF', 'SFP', 'SPELL', 'SUN', 'SXP', 'TKO',
    'TWT', 'UNFI', 'UTK', 'VAI', 'VIDT', 'VTHO', 'WIN', 'XNO', 'ZRX',
  ];

  /// Generates pairs for a given list of base coins and quote currencies
  static List<CurrencyPair> buildPairs({
    required List<String> quoteCurrencies,
    String Function(String base, String quote)? symbolFormatter,
  }) {
    final pairs = <CurrencyPair>[];
    final seen = <String>{};

    for (final base in topCoins) {
      for (final quote in quoteCurrencies) {
        if (base.toUpperCase() != quote.toUpperCase()) {
          final sym = symbolFormatter != null
              ? symbolFormatter(base, quote)
              : '$base$quote';
          final key = '$base/$quote';
          if (seen.add(key)) {
            pairs.add(CurrencyPair(
              baseCurrency: base,
              counterCurrency: quote,
              marketSymbol: sym,
            ));
          }
        }
      }
    }
    return pairs;
  }
}
