// Comprehensive Symbol Full Names & Spoken Names Dictionary

export const SYMBOL_ENGLISH_NAMES: Record<string, string> = {
  // Top Cryptocurrencies
  'BTC': 'Bitcoin',
  'ETH': 'Ethereum',
  'SOL': 'Solana',
  'BNB': 'Binance Coin',
  'XRP': 'Ripple',
  'DOGE': 'Dogecoin',
  'ADA': 'Cardano',
  'AVAX': 'Avalanche',
  'POL': 'Polygon',
  'RENDER': 'Render',
  'RNDR': 'Render',
  'S': 'Sonic',
  'PEPE': 'Pepe',
  'TON': 'Toncoin',
  'SUI': 'Sui',
  'NEAR': 'NEAR Protocol',
  'LINK': 'Chainlink',
  'DOT': 'Polkadot',
  'LTC': 'Litecoin',
  'USDT': 'Tether',
  'USDC': 'USD Coin',
  'TRX': 'TRON',
  'SHIB': 'Shiba Inu',
  'BCH': 'Bitcoin Cash',
  'XMR': 'Monero',
  'ETC': 'Ethereum Classic',
  'XLM': 'Stellar',
  'ALGO': 'Algorand',
  'FIL': 'Filecoin',
  'ICP': 'Internet Computer',
  'HBAR': 'Hedera',
  'VET': 'VeChain',
  'AAVE': 'Aave',
  'CRV': 'Curve DAO',
  'UNI': 'Uniswap',
  'ATOM': 'Cosmos',
  'ARB': 'Arbitrum',
  'OP': 'Optimism',
  'KAS': 'Kaspa',
  'TIA': 'Celestia',
  'WIF': 'dogwifhat',
  'BONK': 'Bonk',
  'FLOKI': 'Floki',
  'FET': 'Artificial Superintelligence Alliance',
  'APT': 'Aptos',
  'TAO': 'Bittensor',
  'INJ': 'Injective',
  'SEI': 'Sei',
  'RUNE': 'THORChain',
  'STX': 'Stacks',
  'NOT': 'Notcoin',
  'HMSTR': 'Hamster Kombat',
  'CATI': 'Catizen',
  'DOGS': 'Dogs',
  'TURBO': 'Turbo',
  'BABYDOGE': 'Baby Doge Coin',
  'EOS': 'EOS',
  'EGLD': 'MultiversX',
  'NEO': 'NEO',
  'IOTA': 'IOTA',
  'QNT': 'Quant',
  'STRK': 'Starknet',
  'BLUR': 'Blur',
  'IMX': 'Immutable',
  'LDO': 'Lido DAO',
  'MANTA': 'Manta Network',
  'METIS': 'Metis',
  'ZRO': 'LayerZero',
  'BLAST': 'Blast',
  'ZK': 'ZKsync',
  'DYM': 'Dymension',
  'SAGA': 'Saga',
  'GALA': 'Gala',
  'SAND': 'The Sandbox',
  'MANA': 'Decentraland',
  'AXS': 'Axie Infinity',
  'BEAM': 'Beam',
  'RON': 'Ronin',
  'PIXEL': 'Pixels',
  'CHZ': 'Chiliz',
  'PENDLE': 'Pendle',
  'ENA': 'Ethena',
  'JUP': 'Jupiter',
  'ENS': 'Ethereum Name Service',
  'DYDX': 'dYdX',
  'ONDO': 'Ondo',
  'OM': 'MANTRA',
  'HNT': 'Helium',
  'JASMY': 'JasmyCoin',
  'BAT': 'Basic Attention Token',
  'QTUM': 'Qtum',
  'XEC': 'eCash',
  'ZEN': 'Horizen',
  'RVN': 'Ravencoin',
  'CKB': 'Nervos Network',
  'ONE': 'Harmony',
  'WLD': 'Worldcoin',
  'ARKM': 'Arkham',
  'IO': 'io.net',
  'GRASS': 'Grass',
  'ATH': 'Aethir',
  'GLM': 'Golem',

  // Crypto Market Total Caps
  'TOTAL': 'Crypto Total Market',
  'TOTAL2': 'Crypto Total Market Excl BTC',
  'TOTAL3': 'Crypto Total Market Excl BTC and ETH',
  'OTHERS': 'Crypto Others Market Cap',

  // Bonds & Rates
  'US10Y': 'US 10-Year Treasury Yield',
  'US02Y': 'US 2-Year Treasury Yield',
  'US30Y': 'US 30-Year Treasury Bond',

  // Forex Pairs
  'EURUSD': 'Euro / US Dollar',
  'GBPUSD': 'British Pound / US Dollar',
  'USDJPY': 'US Dollar / Japanese Yen',
  'USDCHF': 'US Dollar / Swiss Franc',
  'AUDUSD': 'Australian Dollar / US Dollar',
  'USDCAD': 'US Dollar / Canadian Dollar',
  'EUR/USD': 'Euro / US Dollar',
  'GBP/USD': 'British Pound / US Dollar',
  'USD/JPY': 'US Dollar / Japanese Yen',
  'USD/CHF': 'US Dollar / Swiss Franc',
  'AUD/USD': 'Australian Dollar / US Dollar',
  'USD/CAD': 'US Dollar / Canadian Dollar',

  // Major Stocks
  'NVDA': 'NVIDIA',
  'AAPL': 'Apple',
  'MSFT': 'Microsoft',
  'AMZN': 'Amazon',
  'GOOGL': 'Alphabet Google',
  'META': 'Meta Platforms',
  'TSLA': 'Tesla',
  'PLTR': 'Palantir Technologies',
  'BRKB': 'Berkshire Hathaway',
  'SPACEX': 'SpaceX',
  'STARLINK': 'Starlink',
  'XAI': 'xAI',
  'X_CORP': 'X Corp',
  'NEURALINK': 'Neuralink',
  'BORING': 'The Boring Company',
  'MSTR': 'MicroStrategy',
  'COIN': 'Coinbase',
  'MARA': 'MARA Holdings',
  'RIOT': 'Riot Platforms',
  'CLSK': 'CleanSpark',
  'HOOD': 'Robinhood',
  'RDDT': 'Reddit',
  'SHOP': 'Shopify',
  'SNOW': 'Snowflake',
  'RACE': 'Ferrari',
  'TSM': 'TSMC',
  'ASML': 'ASML Holding',
  'AMD': 'AMD',
  'AVGO': 'Broadcom',
  'OPENAI': 'OpenAI',
  'ANTHROPIC': 'Anthropic',
  'STRIPE': 'Stripe',
  'BYTEDANCE': 'ByteDance TikTok',

  // Commodities & Indices
  'GOLD': 'Gold Spot',
  'SILVER': 'Silver Spot',
  'COPPER': 'Copper Futures',
  'NATGAS': 'Natural Gas Futures',
  'PLATINUM': 'Platinum Spot',
  'URANIUM': 'Uranium ETF',
  'OIL_WTI': 'Crude Oil WTI',
  'OIL_BRENT': 'Brent Crude Oil',
  'WTI': 'Crude Oil WTI',
  'BRENT': 'Brent Crude Oil',
  'VIX': 'Volatility Index VIX',
  'RUT': 'Russell 2000 Index',
  'DAX': 'DAX 40 Germany',
  'NIKKEI': 'Nikkei 225 Japan',
  'FTSE': 'FTSE 100 UK',
  'SP500': 'S&P 500 Index',
  'NASDAQ100': 'NASDAQ 100 Index',
  'DOWJONES': 'Dow Jones Industrial',
  'DXY': 'US Dollar Index',
  'TEDPIX': 'شاخص بورس تهران',
};

// Iranian Assets Map (Always Persian name as per user request)
export const IRAN_ASSETS_MAP: Record<string, string> = {
  'GOLD18': 'طلای ۱۸ عیار',
  'GOLD18_BONBAST': 'طلای ۱۸ عیار',
  'MITHQAL': 'مظنه آبشده مثقال',
  'MITHQAL_BONBAST': 'مظنه آبشده مثقال',
  'EMAMI': 'سکه تمام بهار امامی',
  'EMAMI_BONBAST': 'سکه تمام بهار امامی',
  'COIN_EMAMI': 'سکه تمام امامی',
  'BAHAR': 'سکه بهار آزادی',
  'BAHAR_BONBAST': 'سکه بهار آزادی',
  'COIN_BAHAR': 'سکه بهار آزادی',
  'HALF': 'نیم‌سکه بهار آزادی',
  'HALF_BONBAST': 'نیم‌سکه بهار آزادی',
  'COIN_HALF': 'نیم‌سکه بهار آزادی',
  'QUARTER': 'ربع‌سکه بهار آزادی',
  'QUARTER_BONBAST': 'ربع‌سکه بهار آزادی',
  'COIN_QUARTER': 'ربع‌سکه بهار آزادی',
  'GRAM': 'سکه یک گرمی',
  'GRAM_BONBAST': 'سکه یک گرمی',
  'COIN_GRAM': 'سکه یک گرمی',
  'USD_BONBAST': 'دلار آزاد تهران',
  'EUR_BONBAST': 'یورو آزاد تهران',
  'AED_BONBAST': 'درهم امارات',
  'GBP_BONBAST': 'پوند انگلیس',
  'TRY_BONBAST': 'لیر ترکیه',
  'BOURSE_BONBAST': 'شاخص کل بورس تهران',
  'USDT_TMN': 'تتر به تومان',
  'USD/TMN': 'دلار تهران',
  'EUR/TMN': 'یورو تهران',
  'AED/TMN': 'درهم امارات',
};

/**
 * Returns the full clean English name for symbols (or Persian name for Iranian market assets).
 */
export const getSymbolEnglishFullName = (symbolOrCode: string, fallbackName?: string): string => {
  if (!symbolOrCode) return fallbackName || '';

  const raw = symbolOrCode.trim();
  const upper = raw.toUpperCase();

  // 1. Check Iranian assets first
  if (IRAN_ASSETS_MAP[upper]) {
    return IRAN_ASSETS_MAP[upper];
  }
  const irKey = upper.replace(/_BONBAST$/, '');
  if (IRAN_ASSETS_MAP[irKey]) {
    return IRAN_ASSETS_MAP[irKey];
  }

  // 2. Direct English map match
  if (SYMBOL_ENGLISH_NAMES[upper]) {
    return SYMBOL_ENGLISH_NAMES[upper];
  }

  // 3. Normalized check: remove special characters / slash / spaces
  // E.g., "TOTAL / B USD" -> check "TOTAL"
  if (upper.startsWith('TOTAL2')) return 'Crypto Total Market Excl BTC';
  if (upper.startsWith('TOTAL3')) return 'Crypto Total Market Excl BTC and ETH';
  if (upper.startsWith('TOTAL')) return 'Crypto Total Market';

  // If pair like "BTC/USDT" or "BTC / USDT"
  const cleanBase = upper.split(/[\/\s\-_]/)[0].trim();
  if (SYMBOL_ENGLISH_NAMES[cleanBase]) {
    return SYMBOL_ENGLISH_NAMES[cleanBase];
  }

  // Fallback
  return fallbackName || raw;
};

/**
 * Returns spoken representation for TTS speech synthesizer.
 */
export const getSymbolSpokenName = (baseCurrency: string, marketSymbol?: string, fallbackName?: string): string => {
  const sym = baseCurrency || marketSymbol || '';
  const fullName = getSymbolEnglishFullName(sym, fallbackName || marketSymbol);
  return fullName;
};
