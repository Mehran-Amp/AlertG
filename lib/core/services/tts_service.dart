import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Professional Financial Market Text-to-Speech (TTS) Engine.
/// Always speaks in clear, fluent English with comprehensive financial asset recognition.
///
/// Features:
/// 1. Comprehensive mapping for 200+ Cryptocurrencies, Stocks, US Bond Yields, Indices, Forex, and Commodities.
/// 2. Smart financial unit detection (Yields -> "percent", Indices/VIX -> "points", Commodities/Crypto/Stocks -> "dollars/euros/toman").
/// 3. Authentic spoken names (e.g. TNX -> "10-Year Treasury Yield", BTC -> "Bitcoin", AAPL -> "Apple", GC=F -> "Gold").
/// 4. Fallback spelling letter-by-letter for unknown tickers (e.g. "W I F").
class TtsService {
  static final TtsService instance = TtsService._();
  TtsService._();

  static const MethodChannel _channel = MethodChannel('com.example.bitcoin_checker/app_lifecycle');

  // -------------------------------------------------------------
  // 1. MACRO YIELDS, INDICES, COMMODITIES & FOREX DICTIONARY
  // -------------------------------------------------------------
  static const Map<String, _AssetVoiceInfo> _macroAssetDirectory = {
    // US Treasury Bond Yields (Spoken with "percent")
    'TNX': _AssetVoiceInfo('10-Year Treasury Yield', overrideUnit: 'percent'),
    '^TNX': _AssetVoiceInfo('10-Year Treasury Yield', overrideUnit: 'percent'),
    'US10Y': _AssetVoiceInfo('10-Year Treasury Yield', overrideUnit: 'percent'),
    '10YEAR': _AssetVoiceInfo('10-Year Treasury Yield', overrideUnit: 'percent'),

    'TYX': _AssetVoiceInfo('30-Year Treasury Yield', overrideUnit: 'percent'),
    '^TYX': _AssetVoiceInfo('30-Year Treasury Yield', overrideUnit: 'percent'),
    'US30Y': _AssetVoiceInfo('30-Year Treasury Yield', overrideUnit: 'percent'),

    'FVX': _AssetVoiceInfo('5-Year Treasury Yield', overrideUnit: 'percent'),
    '^FVX': _AssetVoiceInfo('5-Year Treasury Yield', overrideUnit: 'percent'),
    'US5Y': _AssetVoiceInfo('5-Year Treasury Yield', overrideUnit: 'percent'),

    'IRX': _AssetVoiceInfo('2-Year Treasury Yield', overrideUnit: 'percent'),
    '^IRX': _AssetVoiceInfo('2-Year Treasury Yield', overrideUnit: 'percent'),
    'US02Y': _AssetVoiceInfo('2-Year Treasury Yield', overrideUnit: 'percent'),
    'US2Y': _AssetVoiceInfo('2-Year Treasury Yield', overrideUnit: 'percent'),

    'US13W': _AssetVoiceInfo('13-Week Treasury Bill', overrideUnit: 'percent'),

    // Market Volatility & Currency Indices
    'VIX': _AssetVoiceInfo('VIX Volatility', overrideUnit: 'points'),
    '^VIX': _AssetVoiceInfo('VIX Volatility', overrideUnit: 'points'),
    'DXY': _AssetVoiceInfo('Dollar Index', overrideUnit: 'points'),
    'DX-Y.NYB': _AssetVoiceInfo('Dollar Index', overrideUnit: 'points'),
    'USDX': _AssetVoiceInfo('Dollar Index', overrideUnit: 'points'),

    // Global Indices
    'SPX': _AssetVoiceInfo('S and P 500', overrideUnit: 'points'),
    '^GSPC': _AssetVoiceInfo('S and P 500', overrideUnit: 'points'),
    'SP500': _AssetVoiceInfo('S and P 500', overrideUnit: 'points'),
    'SPY': _AssetVoiceInfo('S and P 500 ETF', overrideUnit: 'dollars'),

    'NDX': _AssetVoiceInfo('Nasdaq', overrideUnit: 'points'),
    '^IXIC': _AssetVoiceInfo('Nasdaq', overrideUnit: 'points'),
    'NASDAQ': _AssetVoiceInfo('Nasdaq', overrideUnit: 'points'),
    'QQQ': _AssetVoiceInfo('Nasdaq ETF', overrideUnit: 'dollars'),

    'DJI': _AssetVoiceInfo('Dow Jones', overrideUnit: 'points'),
    '^DJI': _AssetVoiceInfo('Dow Jones', overrideUnit: 'points'),
    'DOW': _AssetVoiceInfo('Dow Jones', overrideUnit: 'points'),
    'DIA': _AssetVoiceInfo('Dow Jones ETF', overrideUnit: 'dollars'),

    'RUT': _AssetVoiceInfo('Russell 2000', overrideUnit: 'points'),
    '^RUT': _AssetVoiceInfo('Russell 2000', overrideUnit: 'points'),
    'IWM': _AssetVoiceInfo('Russell 2000 ETF', overrideUnit: 'dollars'),

    'FTSE': _AssetVoiceInfo('FTSE 100', overrideUnit: 'points'),
    '^FTSE': _AssetVoiceInfo('FTSE 100', overrideUnit: 'points'),
    'DAX': _AssetVoiceInfo('DAX Index', overrideUnit: 'points'),
    '^GDAX': _AssetVoiceInfo('DAX Index', overrideUnit: 'points'),
    'N225': _AssetVoiceInfo('Nikkei 225', overrideUnit: 'points'),
    '^N225': _AssetVoiceInfo('Nikkei 225', overrideUnit: 'points'),
    'HSI': _AssetVoiceInfo('Hang Seng', overrideUnit: 'points'),
    '^HSI': _AssetVoiceInfo('Hang Seng', overrideUnit: 'points'),

    // Commodities & Precious Metals
    'GOLD': _AssetVoiceInfo('Gold'),
    'XAU': _AssetVoiceInfo('Gold'),
    'GC=F': _AssetVoiceInfo('Gold'),
    'XAUUSD': _AssetVoiceInfo('Gold'),

    'SILVER': _AssetVoiceInfo('Silver'),
    'XAG': _AssetVoiceInfo('Silver'),
    'SI=F': _AssetVoiceInfo('Silver'),
    'XAGUSD': _AssetVoiceInfo('Silver'),

    'OIL': _AssetVoiceInfo('Crude Oil'),
    'WTI': _AssetVoiceInfo('Crude Oil'),
    'CL=F': _AssetVoiceInfo('Crude Oil'),

    'BRENT': _AssetVoiceInfo('Brent Crude'),
    'BZ=F': _AssetVoiceInfo('Brent Crude'),

    'NATGAS': _AssetVoiceInfo('Natural Gas'),
    'NG=F': _AssetVoiceInfo('Natural Gas'),

    'COPPER': _AssetVoiceInfo('Copper'),
    'HG=F': _AssetVoiceInfo('Copper'),

    'PLATINUM': _AssetVoiceInfo('Platinum'),
    'PL=F': _AssetVoiceInfo('Platinum'),

    'PALLADIUM': _AssetVoiceInfo('Palladium'),
    'PA=F': _AssetVoiceInfo('Palladium'),

    // Major Forex Pairs
    'EURUSD': _AssetVoiceInfo('Euro US Dollar', overrideUnit: ''),
    'GBPUSD': _AssetVoiceInfo('British Pound US Dollar', overrideUnit: ''),
    'USDJPY': _AssetVoiceInfo('US Dollar Japanese Yen', overrideUnit: 'yen'),
    'AUDUSD': _AssetVoiceInfo('Australian Dollar US Dollar', overrideUnit: ''),
    'USDCAD': _AssetVoiceInfo('US Dollar Canadian Dollar', overrideUnit: ''),
    'USDCHF': _AssetVoiceInfo('US Dollar Swiss Franc', overrideUnit: 'francs'),
    'NZDUSD': _AssetVoiceInfo('New Zealand Dollar US Dollar', overrideUnit: ''),
    'EURGBP': _AssetVoiceInfo('Euro British Pound', overrideUnit: 'pounds'),
    'EURJPY': _AssetVoiceInfo('Euro Japanese Yen', overrideUnit: 'yen'),
    'GBPJPY': _AssetVoiceInfo('British Pound Japanese Yen', overrideUnit: 'yen'),
  };

  // -------------------------------------------------------------
  // 2. TOP CRYPTOCURRENCIES DICTIONARY
  // -------------------------------------------------------------
  static const Map<String, String> _cryptoAssetNames = {
    // Bluechips & Layer 1 / Layer 2
    'BTC': 'Bitcoin',
    'XBT': 'Bitcoin',
    'BITCOIN': 'Bitcoin',
    'ETH': 'Ethereum',
    'ETHEREUM': 'Ethereum',
    'SOL': 'Solana',
    'SOLANA': 'Solana',
    'BNB': 'BNB',
    'XRP': 'Ripple',
    'RIPPLE': 'Ripple',
    'DOGE': 'Dogecoin',
    'DOGECOIN': 'Dogecoin',
    'ADA': 'Cardano',
    'CARDANO': 'Cardano',
    'AVAX': 'Avalanche',
    'AVALANCHE': 'Avalanche',
    'DOT': 'Polkadot',
    'POLKADOT': 'Polkadot',
    'TON': 'Toncoin',
    'TONCOIN': 'Toncoin',
    'SUI': 'Sui',
    'APT': 'Aptos',
    'APTOS': 'Aptos',
    'NEAR': 'Near Protocol',
    'LINK': 'Chainlink',
    'CHAINLINK': 'Chainlink',
    'TRX': 'Tron',
    'TRON': 'Tron',
    'LTC': 'Litecoin',
    'LITECOIN': 'Litecoin',
    'BCH': 'Bitcoin Cash',
    'UNI': 'Uniswap',
    'UNISWAP': 'Uniswap',
    'ATOM': 'Cosmos',
    'COSMOS': 'Cosmos',
    'TIA': 'Celestia',
    'CELESTIA': 'Celestia',
    'SEI': 'Sei',
    'ICP': 'Internet Computer',
    'XLM': 'Stellar',
    'STELLAR': 'Stellar',
    'ETC': 'Ethereum Classic',
    'FIL': 'Filecoin',
    'HBAR': 'Hedera',
    'KAS': 'Kaspa',
    'POL': 'Polygon',
    'MATIC': 'Polygon',
    'POLYGON': 'Polygon',
    'RENDER': 'Render',
    'RNDR': 'Render',
    'FET': 'Artificial Superintelligence',
    'ASI': 'Artificial Superintelligence',
    'AGIX': 'Artificial Superintelligence',
    'OCEAN': 'Artificial Superintelligence',
    'INJ': 'Injective',
    'ALGO': 'Algorand',
    'XMR': 'Monero',
    'MONERO': 'Monero',
    'TAO': 'Bittensor',
    'WLD': 'Worldcoin',
    'OM': 'Mantra',
    'ONDO': 'Ondo',
    'ARB': 'Arbitrum',
    'OP': 'Optimism',
    'AAVE': 'Aave',
    'MKR': 'Maker',
    'SKY': 'Maker',
    'FTM': 'Fantom',
    'S': 'Sonic',
    'STX': 'Stacks',
    'KAVA': 'Kava',
    'IMX': 'Immutable',
    'GALA': 'Gala',
    'SAND': 'Sandbox',
    'MANA': 'Decentraland',
    'VET': 'VeChain',
    'GRT': 'The Graph',
    'THETA': 'Theta',
    'CRV': 'Curve',
    'DYDX': 'dYdX',
    'PENDLE': 'Pendle',
    'ENA': 'Ethena',
    'EIGEN': 'EigenLayer',
    'JUP': 'Jupiter',
    'PYTH': 'Pyth Network',
    'W': 'Wormhole',
    'STRK': 'Starknet',
    'ZK': 'ZKsync',
    'ZRO': 'LayerZero',
    'BLUR': 'Blur',
    'FLOW': 'Flow',
    'AXS': 'Axie Infinity',
    'CHZ': 'Chiliz',
    'EOS': 'EOS',
    'XTZ': 'Tezos',
    'IOTA': 'IOTA',
    'NEO': 'NEO',
    'ZEC': 'Zcash',
    'DASH': 'Dash',
    'COMP': 'Compound',
    'SNX': 'Synthetix',
    'LDO': 'Lido',
    'RPL': 'Rocket Pool',
    'EGLD': 'MultiversX',
    'RON': 'Ronin',
    'ROSE': 'Oasis Network',
    'BEAM': 'Beam',
    'VANRY': 'Vanar',
    'SLF': 'Self Chain',
    'VIC': 'Viction',
    'BTTC': 'BitTorrent',
    'XEC': 'eCash',
    'LUNC': 'Terra Classic',
    'LUNA': 'Terra',
    'KAIA': 'Kaia',
    'G': 'Gravity',

    // Memecoins & Ecosystem Tokens
    'SHIB': 'Shiba Inu',
    'SHIBA': 'Shiba Inu',
    'PEPE': 'Pepe',
    'WIF': 'Dogwifhat',
    'BONK': 'Bonk',
    'FLOKI': 'Floki',
    'NOT': 'Notcoin',
    'DOGS': 'Dogs',
    'HMSTR': 'Hamster Kombat',
    'CATI': 'Catizen',
    'NEIRO': 'Neiro',
    'PNUT': 'Peanut',
    'ACT': 'Act',
    'GOAT': 'Goatseus',
    'POPCAT': 'Popcat',
    'MEW': 'Cat in a Dogs World',
    'BRETT': 'Brett',
    'MOG': 'Mog Coin',
    'BOME': 'Book of Meme',
    'TURBO': 'Turbo',
    'BABYDOGE': 'Baby Doge',
    'MYRO': 'Myro',
    'TOSHI': 'Toshi',
    'DEGEN': 'Degen',
    'SLERF': 'Slerf',
    'PONKE': 'Ponke',
    'MOODENG': 'Moo Deng',
  };

  // -------------------------------------------------------------
  // 3. GLOBAL STOCKS DICTIONARY
  // -------------------------------------------------------------
  static const Map<String, String> _stockAssetNames = {
    'AAPL': 'Apple',
    'TSLA': 'Tesla',
    'NVDA': 'Nvidia',
    'MSFT': 'Microsoft',
    'AMZN': 'Amazon',
    'GOOGL': 'Google',
    'GOOG': 'Google',
    'META': 'Meta',
    'NFLX': 'Netflix',
    'AMD': 'AMD',
    'INTC': 'Intel',
    'COIN': 'Coinbase',
    'MSTR': 'MicroStrategy',
    'BABA': 'Alibaba',
    'DIS': 'Disney',
    'PYPL': 'PayPal',
    'UBER': 'Uber',
    'ARM': 'Arm',
    'PLTR': 'Palantir',
    'TSM': 'TSMC',
    'AVGO': 'Broadcom',
    'ORCL': 'Oracle',
    'QCOM': 'Qualcomm',
    'CRM': 'Salesforce',
    'ADBE': 'Adobe',
    'TXN': 'Texas Instruments',
    'IBM': 'IBM',
    'CSCO': 'Cisco',
    'JPM': 'JPMorgan',
    'BAC': 'Bank of America',
    'WFC': 'Wells Fargo',
    'GS': 'Goldman Sachs',
    'MS': 'Morgan Stanley',
    'V': 'Visa',
    'MA': 'Mastercard',
    'BRK.A': 'Berkshire Hathaway',
    'BRK.B': 'Berkshire Hathaway',
    'BRK': 'Berkshire Hathaway',
    'WMT': 'Walmart',
    'COST': 'Costco',
    'HD': 'Home Depot',
    'NKE': 'Nike',
    'MCD': "McDonald's",
    'SBUX': 'Starbucks',
    'KO': 'Coca-Cola',
    'PEP': 'Pepsi',
    'PFE': 'Pfizer',
    'JNJ': 'Johnson and Johnson',
    'LLY': 'Eli Lilly',
    'UNH': 'UnitedHealth',
    'XOM': 'ExxonMobil',
    'CVX': 'Chevron',
    'BA': 'Boeing',
    'CAT': 'Caterpillar',
    'GE': 'General Electric',
    'SPOT': 'Spotify',
    'SQ': 'Block',
    'HOOD': 'Robinhood',
    'RIVN': 'Rivian',
    'LCID': 'Lucid',
    'NIO': 'NIO',
    'BBD': 'Banco Bradesco',
    'SONY': 'Sony',
    'NTDOY': 'Nintendo',
  };

  /// Builds clean, natural English voice speech sentence for an alert.
  /// Pattern: [Asset Name] [Price] [Currency / Unit] (+ Note)
  static String buildAlertSpeech({
    required String symbol,
    required double price,
    String lang = 'en',
    String? baseCurrency,
    String? counterCurrency,
    String? customNote,
  }) {
    // 1. Sanitize base and counter symbols
    final sanitized = _sanitizeSymbolPair(
      symbol: symbol,
      baseCurrency: baseCurrency,
      counterCurrency: counterCurrency,
    );

    final base = sanitized.base;
    final counter = sanitized.counter;

    // 2. Lookup Asset Spoken Name and Unit
    final lookup = _resolveAssetSpokenInfo(base, counter);
    final spokenAssetName = lookup.name;
    final spokenUnit = lookup.unit;

    // 3. Format Price appropriately
    final priceStr = _formatSpokenPrice(price, lookup.isYield);

    // 4. Assemble clean sentence: [Asset Name] [Price] [Currency / Unit]
    var sentence = spokenUnit.isNotEmpty
        ? '$spokenAssetName $priceStr $spokenUnit'
        : '$spokenAssetName $priceStr';

    // Append custom note if present and written in English (Latin characters)
    if (customNote != null && customNote.trim().isNotEmpty) {
      final cleanNote = customNote.trim().replaceAll(RegExp(r'^[📝📌ℹ️🚨⚠️\s]+'), '');
      final isEnglish = RegExp(r'^[A-Za-z0-9\s.,!?:;%+\-\$/]+$').hasMatch(cleanNote);
      if (isEnglish && cleanNote.isNotEmpty) {
        sentence += ', Note: $cleanNote';
      }
    }

    return sentence;
  }

  /// Resolves the authentic spoken name and appropriate currency/unit
  static _ResolvedSpokenInfo _resolveAssetSpokenInfo(String base, String counter) {
    // 1. Check Macro / Yields / Commodities / Forex
    if (_macroAssetDirectory.containsKey(base)) {
      final info = _macroAssetDirectory[base]!;
      final unit = info.overrideUnit ?? _getSpokenCurrency(counter);
      final isYield = info.overrideUnit == 'percent';
      return _ResolvedSpokenInfo(info.spokenName, unit, isYield: isYield);
    }

    // 2. Check Cryptocurrencies
    if (_cryptoAssetNames.containsKey(base)) {
      final name = _cryptoAssetNames[base]!;
      final unit = _getSpokenCurrency(counter);
      return _ResolvedSpokenInfo(name, unit);
    }

    // 3. Check Global Stocks
    if (_stockAssetNames.containsKey(base)) {
      final name = _stockAssetNames[base]!;
      final unit = _getSpokenCurrency(counter);
      return _ResolvedSpokenInfo(name, unit);
    }

    // 4. Fallback for unlisted tickers: spell letter-by-letter with space separation (e.g. "W I F")
    final spelledOut = base.length <= 5 ? base.split('').join(' ') : base;
    final unit = _getSpokenCurrency(counter);
    return _ResolvedSpokenInfo(spelledOut, unit);
  }

  /// Formats price cleanly for vocal synthesis
  static String _formatSpokenPrice(double price, bool isYield) {
    if (isYield) {
      return price.toStringAsFixed(2);
    }
    if (price >= 1000) {
      return price.toStringAsFixed(0);
    } else if (price >= 1) {
      return price.toStringAsFixed(2);
    } else if (price >= 0.0001) {
      return price.toStringAsFixed(4);
    } else {
      return price.toStringAsFixed(6);
    }
  }

  /// Returns natural spoken currency word
  static String _getSpokenCurrency(String counterSymbol) {
    final c = counterSymbol.toUpperCase().replaceAll(RegExp(r'[^A-Z]'), '');
    switch (c) {
      case 'USDT':
      case 'USD':
      case 'USDC':
      case 'BUSD':
      case 'DAI':
      case 'FDUSD':
        return 'dollars';
      case 'EUR':
        return 'euros';
      case 'GBP':
        return 'pounds';
      case 'JPY':
        return 'yen';
      case 'TMN':
      case 'IRT':
      case 'TOMAN':
        return 'toman';
      case 'BTC':
      case 'XBT':
        return 'bitcoin';
      case 'ETH':
        return 'ethereum';
      case 'TRY':
        return 'lira';
      case 'AUD':
        return 'Australian dollars';
      case 'CAD':
        return 'Canadian dollars';
      case 'CHF':
        return 'Swiss francs';
      case 'CNY':
      case 'RMB':
        return 'yuan';
      case '':
        return '';
      default:
        if (c.length <= 4) {
          return c.split('').join(' ');
        }
        return c;
    }
  }

  /// Sanitizes pair strings (e.g. "^TNX", "BINANCE:BTCUSDT", "ETH/USD")
  static _PairInfo _sanitizeSymbolPair({
    required String symbol,
    String? baseCurrency,
    String? counterCurrency,
  }) {
    var raw = symbol.toUpperCase().trim();
    // Strip exchange prefixes (e.g. "BINANCE:", "FRED:")
    if (raw.contains(':')) {
      raw = raw.split(':').last.trim();
    }

    String base;
    String counter;

    if (baseCurrency != null && baseCurrency.isNotEmpty) {
      base = baseCurrency.toUpperCase().trim();
    } else if (raw.contains('/')) {
      base = raw.split('/')[0].trim();
    } else if (raw.contains('-')) {
      base = raw.split('-')[0].trim();
    } else {
      base = raw;
    }

    if (counterCurrency != null && counterCurrency.isNotEmpty) {
      counter = counterCurrency.toUpperCase().trim();
    } else if (raw.contains('/')) {
      counter = raw.split('/')[1].trim();
    } else if (raw.contains('-')) {
      counter = raw.split('-')[1].trim();
    } else {
      counter = 'USD';
    }

    // Clean common prefixes (e.g. "^" from Yahoo Finance symbols like ^TNX)
    if (base.startsWith('^')) {
      // Keep ^ for dictionary lookup or clean
      if (!_macroAssetDirectory.containsKey(base)) {
        base = base.substring(1);
      }
    }

    return _PairInfo(base, counter);
  }

  final List<String> _speechQueue = [];
  bool _isSpeakingQueue = false;

  /// Queues speech so multiple simultaneous alerts are vocalized sequentially and completely without overlap
  void enqueueSpeech(String text) {
    if (text.trim().isEmpty) return;
    _speechQueue.add(text);
    if (!_isSpeakingQueue) {
      _processQueue();
    }
  }

  Future<void> _processQueue() async {
    if (_speechQueue.isEmpty) {
      _isSpeakingQueue = false;
      return;
    }
    _isSpeakingQueue = true;
    final nextText = _speechQueue.removeAt(0);
    await speak(text: nextText);

    // Word count calculation to wait for utterance to finish completely before next item speaks
    final wordCount = nextText.split(RegExp(r'\s+')).length;
    final estimatedDurationMs = (wordCount * 260 + 2000).clamp(2800, 12000);
    await Future.delayed(Duration(milliseconds: estimatedDurationMs));
    _processQueue();
  }

  /// Speaks the given text using the platform English TTS engine
  Future<void> speak({
    required String text,
    String lang = 'en',
    double rate = 1.0,
    double pitch = 1.0,
  }) async {
    try {
      debugPrint('[TTS] Speaking (English): "$text"');
      await _channel.invokeMethod('speak', {
        'text': text,
        'lang': 'en',
        'rate': rate,
        'pitch': pitch,
      });
    } catch (e) {
      debugPrint('[TTS] Error invoking speak: $e');
    }
  }

  /// Stops any currently playing speech
  Future<void> stop() async {
    _speechQueue.clear();
    _isSpeakingQueue = false;
    try {
      await _channel.invokeMethod('stopSpeak');
    } catch (_) {}
  }

  /// Plays a quick voice test utterance in English
  Future<void> testVoice([String lang = 'en']) async {
    final sample = buildAlertSpeech(
      symbol: 'BTC/USDT',
      baseCurrency: 'BTC',
      counterCurrency: 'USDT',
      price: 87420.0,
      customNote: 'Take profit',
    );
    await speak(text: sample, lang: 'en');
  }
}

class _AssetVoiceInfo {
  final String spokenName;
  final String? overrideUnit;

  const _AssetVoiceInfo(this.spokenName, {this.overrideUnit});
}

class _ResolvedSpokenInfo {
  final String name;
  final String unit;
  final bool isYield;

  const _ResolvedSpokenInfo(this.name, this.unit, {this.isYield = false});
}

class _PairInfo {
  final String base;
  final String counter;

  const _PairInfo(this.base, this.counter);
}
