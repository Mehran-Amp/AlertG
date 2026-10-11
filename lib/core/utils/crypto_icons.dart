import 'package:flutter/material.dart';

/// Helper utility for authentic cryptocurrency logos, global stocks, US bonds,
/// commodities, forex, brand colors, and alias/rebranding name mapping.
class CryptoIcons {
  // Built-in verified high-resolution icon mapping with rebranding & alias awareness
  static const Map<String, _AssetMeta> _metadata = {
    // 1. REBRANDED & MIGRATED COINS (High Priority Aliases)
    'POL': _AssetMeta('Polygon (POL / formerly MATIC)', Color(0xFF8247E5), 'https://assets.coingecko.com/coins/images/4713/small/polygon.png', aliases: 'MATIC POLYGON MATIC_NETWORK'),
    'MATIC': _AssetMeta('Polygon (POL / formerly MATIC)', Color(0xFF8247E5), 'https://assets.coingecko.com/coins/images/4713/small/polygon.png', aliases: 'POL POLYGON MATIC'),
    'RENDER': _AssetMeta('Render (RENDER / formerly RNDR)', Color(0xFFE53935), 'https://assets.coingecko.com/coins/images/11636/small/rndr.png', aliases: 'RNDR RENDER_TOKEN'),
    'RNDR': _AssetMeta('Render (RENDER / formerly RNDR)', Color(0xFFE53935), 'https://assets.coingecko.com/coins/images/11636/small/rndr.png', aliases: 'RENDER RNDR'),
    'S': _AssetMeta('Sonic (S / formerly Fantom FTM)', Color(0xFF1969FF), 'https://assets.coingecko.com/coins/images/4001/small/Fantom_round.png', aliases: 'FTM FANTOM SONIC'),
    'FTM': _AssetMeta('Sonic (S / formerly Fantom FTM)', Color(0xFF1969FF), 'https://assets.coingecko.com/coins/images/4001/small/Fantom_round.png', aliases: 'S SONIC FANTOM'),
    'SKY': _AssetMeta('Sky (SKY / formerly Maker MKR)', Color(0xFF1AAB9B), 'https://assets.coingecko.com/coins/images/1364/small/Mark_Maker.png', aliases: 'MKR MAKER SKY_ECOSYSTEM'),
    'MKR': _AssetMeta('Sky (SKY / formerly Maker MKR)', Color(0xFF1AAB9B), 'https://assets.coingecko.com/coins/images/1364/small/Mark_Maker.png', aliases: 'SKY MKR MAKER'),
    'KAIA': _AssetMeta('Kaia (KAIA / formerly Klaytn KLAY)', Color(0xFFB1EC39), 'https://assets.coingecko.com/coins/images/9672/small/klaytn.png', aliases: 'KLAY KLAYTN FNSA FINSCHIA'),
    'KLAY': _AssetMeta('Kaia (KAIA / formerly Klaytn KLAY)', Color(0xFFB1EC39), 'https://assets.coingecko.com/coins/images/9672/small/klaytn.png', aliases: 'KAIA KLAYTN'),
    'G': _AssetMeta('Gravity (G / formerly Galxe GAL)', Color(0xFF0052FF), 'https://assets.coingecko.com/coins/images/25016/small/galxe.png', aliases: 'GAL GALXE GRAVITY'),
    'GAL': _AssetMeta('Gravity (G / formerly Galxe GAL)', Color(0xFF0052FF), 'https://assets.coingecko.com/coins/images/25016/small/galxe.png', aliases: 'G GALXE GRAVITY'),
    'VANRY': _AssetMeta('Vanar Chain (VANRY / formerly Virtua TVK)', Color(0xFF00FF88), 'https://assets.coingecko.com/coins/images/13386/small/TVK_logo_-_White_Background.png', aliases: 'TVK VIRTUA VANAR'),
    'TVK': _AssetMeta('Vanar Chain (VANRY / formerly Virtua TVK)', Color(0xFF00FF88), 'https://assets.coingecko.com/coins/images/13386/small/TVK_logo_-_White_Background.png', aliases: 'VANRY VIRTUA'),
    'SLF': _AssetMeta('Self Chain (SLF / formerly Frontier FRONT)', Color(0xFF5B60F6), 'https://assets.coingecko.com/coins/images/12470/small/front.png', aliases: 'FRONT FRONTIER SELF'),
    'FRONT': _AssetMeta('Self Chain (SLF / formerly Frontier FRONT)', Color(0xFF5B60F6), 'https://assets.coingecko.com/coins/images/12470/small/front.png', aliases: 'SLF SELF FRONTIER'),
    'VIC': _AssetMeta('Viction (VIC / formerly TomoChain TOMO)', Color(0xFFE53935), 'https://assets.coingecko.com/coins/images/3416/small/Tomochain.png', aliases: 'TOMO TOMOCHAIN VICTION'),
    'TOMO': _AssetMeta('Viction (VIC / formerly TomoChain TOMO)', Color(0xFFE53935), 'https://assets.coingecko.com/coins/images/3416/small/Tomochain.png', aliases: 'VIC VICTION TOMOCHAIN'),
    'BTTC': _AssetMeta('BitTorrent (BTTC / formerly BTT)', Color(0xFF000000), 'https://assets.coingecko.com/coins/images/22457/small/bttc.png', aliases: 'BTT BITTORRENT'),
    'BTT': _AssetMeta('BitTorrent (BTTC / formerly BTT)', Color(0xFF000000), 'https://assets.coingecko.com/coins/images/22457/small/bttc.png', aliases: 'BTTC BITTORRENT'),
    'XEC': _AssetMeta('eCash (XEC / formerly BCHA)', Color(0xFF0074C2), 'https://assets.coingecko.com/coins/images/16646/small/ECASH.png', aliases: 'BCHA ECASH BITCOIN_ABC'),
    'BEAM': _AssetMeta('Beam (BEAM / formerly Merit Circle MC)', Color(0xFF2CD5C4), 'https://assets.coingecko.com/coins/images/32417/small/beam-logo.png', aliases: 'MC MERIT_CIRCLE'),
    'MC': _AssetMeta('Beam (BEAM / formerly Merit Circle MC)', Color(0xFF2CD5C4), 'https://assets.coingecko.com/coins/images/32417/small/beam-logo.png', aliases: 'BEAM MERIT_CIRCLE'),
    'FET': _AssetMeta('Artificial Superintelligence Alliance (ASI / FET)', Color(0xFF1B2430), 'https://assets.coingecko.com/coins/images/5681/small/Fetch.jpg', aliases: 'ASI AGIX OCEAN FETCH_AI'),
    'ASI': _AssetMeta('Artificial Superintelligence Alliance (ASI / FET)', Color(0xFF1B2430), 'https://assets.coingecko.com/coins/images/5681/small/Fetch.jpg', aliases: 'FET AGIX OCEAN FETCH_AI'),
    'AGIX': _AssetMeta('SingularityNET (ASI / FET)', Color(0xFF6916FF), 'https://assets.coingecko.com/coins/images/2138/small/singularitynet.png', aliases: 'ASI FET OCEAN SINGULARITYNET'),
    'OCEAN': _AssetMeta('Ocean Protocol (ASI / FET)', Color(0xFF7B1173), 'https://assets.coingecko.com/coins/images/3687/small/ocean-protocol-logo.png', aliases: 'ASI FET AGIX OCEAN_PROTOCOL'),
    'LUNC': _AssetMeta('Terra Classic (LUNC / former LUNA)', Color(0xFFFFD83D), 'https://assets.coingecko.com/coins/images/8284/small/luna1557227471663.png', aliases: 'LUNA TERRA_CLASSIC'),
    'LUNA': _AssetMeta('Terra 2.0 (LUNA)', Color(0xFFFFD83D), 'https://assets.coingecko.com/coins/images/25767/small/01_LunaToken_Round.png', aliases: 'TERRA LUNC'),

    // 2. TOP BLUECHIP CRYPTOCURRENCIES
    'BTC': _AssetMeta('Bitcoin', Color(0xFFF7931A), 'https://assets.coingecko.com/coins/images/1/small/bitcoin.png', aliases: 'BITCOIN BTC XBT'),
    'ETH': _AssetMeta('Ethereum', Color(0xFF627EEA), 'https://assets.coingecko.com/coins/images/279/small/ethereum.png', aliases: 'ETHEREUM ETHER ETH'),
    'SOL': _AssetMeta('Solana', Color(0xFF14F195), 'https://assets.coingecko.com/coins/images/4128/small/solana.png', aliases: 'SOLANA SOL'),
    'BNB': _AssetMeta('BNB', Color(0xFFF3BA2F), 'https://assets.coingecko.com/coins/images/825/small/bnb-icon2_2x.png', aliases: 'BINANCE_COIN BNB BSC'),
    'XRP': _AssetMeta('XRP (Ripple)', Color(0xFF23292F), 'https://assets.coingecko.com/coins/images/44/small/xrp-symbol-white-128.png', aliases: 'RIPPLE XRP'),
    'DOGE': _AssetMeta('Dogecoin', Color(0xFFC2A633), 'https://assets.coingecko.com/coins/images/5/small/dogecoin.png', aliases: 'DOGECOIN DOGE MEME'),
    'ADA': _AssetMeta('Cardano', Color(0xFF0033AD), 'https://assets.coingecko.com/coins/images/975/small/cardano.png', aliases: 'CARDANO ADA'),
    'AVAX': _AssetMeta('Avalanche', Color(0xFFE84142), 'https://assets.coingecko.com/coins/images/12559/small/Avalanche_Circle_RedWhite_Trans.png', aliases: 'AVALANCHE AVAX'),
    'DOT': _AssetMeta('Polkadot', Color(0xFFE6007A), 'https://assets.coingecko.com/coins/images/12171/small/polkadot.png', aliases: 'POLKADOT DOT'),
    'TON': _AssetMeta('Toncoin (Telegram)', Color(0xFF0098EA), 'https://assets.coingecko.com/coins/images/17980/small/ton_symbol.png', aliases: 'TONCOIN TELEGRAM THE_OPEN_NETWORK'),
    'SUI': _AssetMeta('Sui', Color(0xFF2A82E4), 'https://assets.coingecko.com/coins/images/26375/small/sui-ocean-square.png', aliases: 'SUI MYSTEN'),
    'APT': _AssetMeta('Aptos', Color(0xFF14B8A6), 'https://assets.coingecko.com/coins/images/26455/small/aptos_round.png', aliases: 'APTOS APT'),
    'NEAR': _AssetMeta('NEAR Protocol', Color(0xFF000000), 'https://assets.coingecko.com/coins/images/10365/small/near.png', aliases: 'NEAR_PROTOCOL NEAR'),
    'LINK': _AssetMeta('Chainlink', Color(0xFF375BD2), 'https://assets.coingecko.com/coins/images/877/small/chainlink-new-logo.png', aliases: 'CHAINLINK LINK ORACLE'),
    'TRX': _AssetMeta('TRON', Color(0xFFFF0013), 'https://assets.coingecko.com/coins/images/1094/small/tron-logo.png', aliases: 'TRON TRX JUSTIN_SUN'),
    'LTC': _AssetMeta('Litecoin', Color(0xFF345D9D), 'https://assets.coingecko.com/coins/images/2/small/litecoin.png', aliases: 'LITECOIN LTC'),
    'BCH': _AssetMeta('Bitcoin Cash', Color(0xFF8DC351), 'https://assets.coingecko.com/coins/images/780/small/bitcoin-cash-circle.png', aliases: 'BITCOIN_CASH BCH'),
    'UNI': _AssetMeta('Uniswap', Color(0xFFFF007A), 'https://assets.coingecko.com/coins/images/12504/small/uniswap-uni.png', aliases: 'UNISWAP UNI DEX'),
    'ATOM': _AssetMeta('Cosmos', Color(0xFF2E3148), 'https://assets.coingecko.com/coins/images/1481/small/cosmos_hub.png', aliases: 'COSMOS ATOM HUB'),
    'TIA': _AssetMeta('Celestia', Color(0xFF7B2CBF), 'https://assets.coingecko.com/coins/images/31967/small/celestia.png', aliases: 'CELESTIA TIA MODULAR'),
    'SEI': _AssetMeta('Sei', Color(0xFF9013FE), 'https://assets.coingecko.com/coins/images/28205/small/Sei_Logo_-_Transparent.png', aliases: 'SEI NETWORK'),
    'INJ': _AssetMeta('Injective', Color(0xFF00B2FF), 'https://assets.coingecko.com/coins/images/12882/small/Secondary_Symbol.png', aliases: 'INJECTIVE INJ'),
    'XLM': _AssetMeta('Stellar', Color(0xFF14B6EB), 'https://assets.coingecko.com/coins/images/100/small/Stellar_symbol_black_RGB.png', aliases: 'STELLAR LUMENS XLM'),
    'ALGO': _AssetMeta('Algorand', Color(0xFF000000), 'https://assets.coingecko.com/coins/images/4380/small/download.png', aliases: 'ALGORAND ALGO'),
    'ICP': _AssetMeta('Internet Computer', Color(0xFF29ABE2), 'https://assets.coingecko.com/coins/images/14495/small/Internet_Computer_logo.png', aliases: 'DFINITY INTERNET_COMPUTER ICP'),
    'FIL': _AssetMeta('Filecoin', Color(0xFF0090FF), 'https://assets.coingecko.com/coins/images/12817/small/filecoin.png', aliases: 'FILECOIN FIL STORAGE'),
    'ARB': _AssetMeta('Arbitrum', Color(0xFF28A0F0), 'https://assets.coingecko.com/coins/images/16547/small/arbitrum_logo.png', aliases: 'ARBITRUM ARB L2'),
    'OP': _AssetMeta('Optimism', Color(0xFFFF0420), 'https://assets.coingecko.com/coins/images/25244/small/Optimism.png', aliases: 'OPTIMISM OP L2'),
    'AAVE': _AssetMeta('Aave', Color(0xFFB6509E), 'https://assets.coingecko.com/coins/images/12645/small/AAVE.png', aliases: 'AAVE LENDING DEFI'),
    'TAO': _AssetMeta('Bittensor (AI)', Color(0xFF262626), 'https://assets.coingecko.com/coins/images/28452/small/bittensor_logo.png', aliases: 'BITTENSOR TAO AI'),
    'KAS': _AssetMeta('Kaspa', Color(0xFF70C7BA), 'https://assets.coingecko.com/coins/images/28898/small/kaspa.png', aliases: 'KASPA KAS GHOSTDAG'),
    'ONDO': _AssetMeta('Ondo Finance (RWA)', Color(0xFF1E293B), 'https://assets.coingecko.com/coins/images/34582/small/ondo.png', aliases: 'ONDO RWA BLACKROCK'),
    'OM': _AssetMeta('MANTRA (RWA)', Color(0xFFD946EF), 'https://assets.coingecko.com/coins/images/12185/small/OM.png', aliases: 'MANTRA OM RWA'),
    'WLD': _AssetMeta('Worldcoin (AI)', Color(0xFF10B981), 'https://assets.coingecko.com/coins/images/31062/small/worldcoin.png', aliases: 'WORLDCOIN WLD SAM_ALTMAN'),

    // 3. POPULAR MEMECOINS & TELEGRAM ECOSYSTEM
    'SHIB': _AssetMeta('Shiba Inu', Color(0xFFFFA409), 'https://assets.coingecko.com/coins/images/11939/small/shiba.png', aliases: 'SHIBA_INU SHIB MEME'),
    'PEPE': _AssetMeta('Pepe', Color(0xFF539F37), 'https://assets.coingecko.com/coins/images/29850/small/pepe-token.png', aliases: 'PEPE MEME FROG'),
    'WIF': _AssetMeta('dogwifhat', Color(0xFFAB7C5F), 'https://assets.coingecko.com/coins/images/33566/small/dogwifhat.jpg', aliases: 'DOGWIFHAT WIF SOLANA_MEME'),
    'BONK': _AssetMeta('Bonk', Color(0xFFFF9500), 'https://assets.coingecko.com/coins/images/28600/small/bonk.jpg', aliases: 'BONK SOLANA_MEME'),
    'FLOKI': _AssetMeta('Floki', Color(0xFFEAA428), 'https://assets.coingecko.com/coins/images/16746/small/FLOKI.png', aliases: 'FLOKI_INU FLOKI MEME'),
    'NOT': _AssetMeta('Notcoin (Telegram)', Color(0xFF111827), 'https://assets.coingecko.com/coins/images/36394/small/notcoin.png', aliases: 'NOTCOIN NOT TELEGRAM'),
    'DOGS': _AssetMeta('Dogs (Telegram)', Color(0xFF000000), 'https://assets.coingecko.com/coins/images/39567/small/dogs.png', aliases: 'DOGS TELEGRAM SPOTTY'),
    'HMSTR': _AssetMeta('Hamster Kombat', Color(0xFFF59E0B), 'https://assets.coingecko.com/coins/images/38902/small/hamster.png', aliases: 'HAMSTER_KOMBAT HMSTR TELEGRAM'),
    'CATI': _AssetMeta('Catizen (Telegram)', Color(0xFF6366F1), 'https://assets.coingecko.com/coins/images/39949/small/catizen.png', aliases: 'CATIZEN CATI TELEGRAM'),
    'NEIRO': _AssetMeta('First Neiro On Ethereum', Color(0xFFFBBF24), 'https://assets.coingecko.com/coins/images/39502/small/neiro.png', aliases: 'NEIRO FIRST_NEIRO_ON_ETH'),
    'PNUT': _AssetMeta('Peanut the Squirrel', Color(0xFFB45309), 'https://assets.coingecko.com/coins/images/40960/small/pnut.png', aliases: 'PEANUT PNUT MEME'),
    'ACT': _AssetMeta('Act I : The AI Prophecy', Color(0xFF4F46E5), 'https://assets.coingecko.com/coins/images/40961/small/act.png', aliases: 'ACT AI_MEME PROPHECY'),
    'GOAT': _AssetMeta('Goatseus Maximus (AI)', Color(0xFFEC4899), 'https://assets.coingecko.com/coins/images/40538/small/goat.png', aliases: 'GOAT TRUTH_TERMINAL AI_MEME'),
    'POPCAT': _AssetMeta('Popcat', Color(0xFFD97706), 'https://assets.coingecko.com/coins/images/33760/small/popcat.png', aliases: 'POPCAT SOLANA_MEME'),
    'MEW': _AssetMeta('cat in a dogs world', Color(0xFFEC4899), 'https://assets.coingecko.com/coins/images/36427/small/mew.png', aliases: 'MEW CAT_IN_A_DOGS_WORLD'),

    // 4. STABLECOINS
    'USDT': _AssetMeta('Tether USD', Color(0xFF26A17B), 'https://assets.coingecko.com/coins/images/325/small/Tether.png', aliases: 'TETHER USDT STABLECOIN'),
    'USDC': _AssetMeta('USDC', Color(0xFF2775CA), 'https://assets.coingecko.com/coins/images/6319/small/usdc.png', aliases: 'USD_COIN USDC CIRCLE'),
    'DAI': _AssetMeta('Dai', Color(0xFFF5AC37), 'https://assets.coingecko.com/coins/images/9956/small/Badge_Dai.png', aliases: 'DAI MAKERDAO STABLECOIN'),

    // 5. US BONDS & YIELDS
    '^TNX': _AssetMeta('US 10-Year Treasury Yield', Color(0xFF10B981), '', customIcon: Icons.account_balance_rounded, aliases: 'US10Y TNX 10YEAR'),
    'US10Y': _AssetMeta('US 10-Year Treasury Yield', Color(0xFF10B981), '', customIcon: Icons.account_balance_rounded, aliases: '^TNX 10YEAR BOND'),
    '^IRX': _AssetMeta('US 2-Year Treasury Yield', Color(0xFF3B82F6), '', customIcon: Icons.account_balance_rounded, aliases: 'US02Y IRX 2YEAR'),
    'US02Y': _AssetMeta('US 2-Year Treasury Yield', Color(0xFF3B82F6), '', customIcon: Icons.account_balance_rounded, aliases: '^IRX 2YEAR BOND'),

    // 6. COMMODITIES & PRECIOUS METALS
    'GC=F': _AssetMeta('Gold (XAU/USD)', Color(0xFFFFD700), '', customIcon: Icons.monetization_on_rounded, aliases: 'GOLD XAU TALA'),
    'XAU': _AssetMeta('Gold (XAU/USD)', Color(0xFFFFD700), '', customIcon: Icons.monetization_on_rounded, aliases: 'GOLD GC=F TALA ONS'),
    'SI=F': _AssetMeta('Silver (XAG/USD)', Color(0xFFC0C0C0), '', customIcon: Icons.circle_rounded, aliases: 'SILVER XAG NOGHREH'),
    'XAG': _AssetMeta('Silver (XAG/USD)', Color(0xFFC0C0C0), '', customIcon: Icons.circle_rounded, aliases: 'SILVER SI=F NOGHREH'),
    'CL=F': _AssetMeta('Crude Oil WTI', Color(0xFF1F2937), '', customIcon: Icons.local_gas_station_rounded, aliases: 'OIL WTI NAFT'),
    'BZ=F': _AssetMeta('Brent Crude Oil', Color(0xFF111827), '', customIcon: Icons.water_drop_rounded, aliases: 'BRENT OIL NAFT'),

    // 7. GLOBAL INDICES & FOREX
    '^GSPC': _AssetMeta('S&P 500 Index', Color(0xFF2563EB), '', customIcon: Icons.trending_up_rounded, aliases: 'SP500 SPX INDEX'),
    'SPX': _AssetMeta('S&P 500 Index', Color(0xFF2563EB), '', customIcon: Icons.trending_up_rounded, aliases: 'SP500 ^GSPC INDEX'),
    '^IXIC': _AssetMeta('NASDAQ Composite', Color(0xFF00A3E0), '', customIcon: Icons.auto_graph_rounded, aliases: 'NASDAQ IXIC INDEX'),
    'DX-Y.NYB': _AssetMeta('US Dollar Index (DXY)', Color(0xFF059669), '', customIcon: Icons.attach_money_rounded, aliases: 'DXY DOLLAR_INDEX'),
    'DXY': _AssetMeta('US Dollar Index (DXY)', Color(0xFF059669), '', customIcon: Icons.attach_money_rounded, aliases: 'DX-Y.NYB DOLLAR_INDEX'),
  };

  /// Returns official human readable display name with alias indicator
  static String getName(String symbol) {
    final clean = _cleanSymbol(symbol);
    return _metadata[clean]?.name ?? clean;
  }

  /// Returns all aliases/former names for search filtering
  static String getAliases(String symbol) {
    final clean = _cleanSymbol(symbol);
    return _metadata[clean]?.aliases ?? '';
  }

  /// Returns official branding color for a coin/asset symbol
  static Color getBrandColor(String symbol) {
    final clean = _cleanSymbol(symbol);
    return _metadata[clean]?.brandColor ?? _deriveColor(clean);
  }

  /// Returns official human readable display name
  static String getDisplayName(String symbol) {
    return getName(symbol);
  }

  /// Builds a high-fidelity crypto / asset logo widget with multi-tier fallback
  static Widget buildLogo(String symbol, {double size = 36}) {
    final clean = _cleanSymbol(symbol);
    final meta = _metadata[clean] ?? _metadata[symbol.toUpperCase()];
    final color = meta?.brandColor ?? _deriveColor(clean);

    // 1. If meta provides a custom vector icon (for Bonds, Commodities, Indices, Stocks)
    if (meta?.customIcon != null) {
      return Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: color.withValues(alpha: 0.15),
          border: Border.all(color: color.withValues(alpha: 0.4), width: 1.5),
        ),
        alignment: Alignment.center,
        child: Icon(meta!.customIcon, color: color, size: size * 0.55),
      );
    }

    // 2. If meta provides a verified icon URL
    if (meta != null && meta.iconUrl.isNotEmpty) {
      return Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: color.withValues(alpha: 0.12),
          border: Border.all(color: color.withValues(alpha: 0.3), width: 1.2),
        ),
        clipBehavior: Clip.antiAlias,
        child: Image.network(
          meta.iconUrl,
          fit: BoxFit.cover,
          errorBuilder: (_, __, ___) => _buildFallback(clean, color, size),
          loadingBuilder: (context, child, loadingProgress) {
            if (loadingProgress == null) return child;
            return _buildFallback(clean, color, size);
          },
        ),
      );
    }

    // 3. Fallback to decentralized crypto icons CDN (supports 1000+ coins)
    final cdnUrl = 'https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/${clean.toLowerCase()}.png';
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: color.withValues(alpha: 0.12),
        border: Border.all(color: color.withValues(alpha: 0.3), width: 1.2),
      ),
      clipBehavior: Clip.antiAlias,
      child: Image.network(
        cdnUrl,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => _buildFallback(clean, color, size),
      ),
    );
  }

  static Widget _buildFallback(String clean, Color color, double size) {
    final shortName = clean.length > 4 ? clean.substring(0, 3) : clean;
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            color.withValues(alpha: 0.9),
            color.withValues(alpha: 0.5),
          ],
        ),
        border: Border.all(color: Colors.white.withValues(alpha: 0.25), width: 1),
      ),
      alignment: Alignment.center,
      child: Text(
        shortName,
        style: TextStyle(
          color: Colors.white,
          fontSize: size * 0.36,
          fontWeight: FontWeight.w800,
          letterSpacing: -0.5,
        ),
      ),
    );
  }

  static String _cleanSymbol(String raw) {
    var s = raw.toUpperCase().trim();
    if (s.contains('/')) s = s.split('/').first;
    if (s.endsWith('USDT') && s.length > 4) s = s.replaceAll('USDT', '');
    if (s.endsWith('USDC') && s.length > 4) s = s.replaceAll('USDC', '');
    if (s.endsWith('TMN') && s.length > 3) s = s.replaceAll('TMN', '');
    if (s.endsWith('IRT') && s.length > 3) s = s.replaceAll('IRT', '');
    if (s.endsWith('USD') && s.length > 3) s = s.replaceAll('USD', '');
    return s;
  }

  static Color _deriveColor(String text) {
    final hash = text.hashCode;
    final r = (hash & 0xFF0000) >> 16;
    final g = (hash & 0x00FF00) >> 8;
    final b = hash & 0x0000FF;
    return Color.fromARGB(255, (r % 180) + 40, (g % 180) + 40, (b % 180) + 40);
  }
}

class _AssetMeta {
  final String name;
  final Color brandColor;
  final String iconUrl;
  final IconData? customIcon;
  final String aliases;

  const _AssetMeta(
    this.name,
    this.brandColor,
    this.iconUrl, {
    this.customIcon,
    this.aliases = '',
  });
}
