import time
import random
import asyncio
from typing import Dict, Any, List, Optional, Tuple
import httpx

from app.config import (
    APP_VERSION,
    FINNHUB_API_KEY,
    TWELVE_DATA_API_KEY,
    FRED_API_KEY,
)
from app.markets.common import normalize_symbol
from app.markets.limiter import record_provider_metric, acquire_provider_slot
from app.state import METRICS
from app.engine.categories import resolve_symbol_category



# ===================================================================
# 1. EXACT MAPS & SYMBOL RESOLUTION (PRESERVED 100%)
# ===================================================================
EXACT_YF_MAP: Dict[str, str] = {
    'DXY': 'DX-Y.NYB',
    'DX-Y.NYB': 'DX-Y.NYB',
    'USDX': 'DX-Y.NYB',
    'US10Y': '^TNX',
    '^TNX': '^TNX',
    'TNX': '^TNX',
    'US05Y': '^FVX',
    'US5Y': '^FVX',
    '^FVX': '^FVX',
    'FVX': '^FVX',
    'US13W': '^IRX',
    '^IRX': '^IRX',
    'US30Y': '^TYX',
    '^TYX': '^TYX',
    'TYX': '^TYX',
    'VIX': '^VIX',
    '^VIX': '^VIX',
    'SPX': '^GSPC',
    'SP500': '^GSPC',
    '^GSPC': '^GSPC',
    'NDX': '^NDX',
    'NASDAQ': '^NDX',
    '^NDX': '^NDX',
    'DJI': '^DJI',
    '^DJI': '^DJI',
    'RUT': '^RUT',
    '^RUT': '^RUT',
    'DAX': '^GDAXI',
    '^GDAXI': '^GDAXI',
    'FTSE': '^FTSE',
    '^FTSE': '^FTSE',
    'CAC40': '^FCHI',
    '^FCHI': '^FCHI',
    'NIKKEI': '^N225',
    '^N225': '^N225',
    'NIFTY': '^NSEI',
    'NIFTY50': '^NSEI',
    '^NSEI': '^NSEI',
    'KOSPI': '^KS11',
    '^KS11': '^KS11',
    'GOLD': 'GC=F',
    'XAU': 'GC=F',
    'XAUUSD': 'GC=F',
    'GC=F': 'GC=F',
    'SILVER': 'SI=F',
    'XAG': 'SI=F',
    'XAGUSD': 'SI=F',
    'XAG/USD': 'SI=F',
    'SI=F': 'SI=F',
    'BRENT': 'BZ=F',
    'OILBRENT': 'BZ=F',
    'OIL_BRENT': 'BZ=F',
    'BRENT/USD': 'BZ=F',
    'BZ=F': 'BZ=F',
    'WTI': 'CL=F',
    'OILWTI': 'CL=F',
    'OIL_WTI': 'CL=F',
    'WTI/USD': 'CL=F',
    'OIL': 'CL=F',
    'CRUDE': 'CL=F',
    'CL=F': 'CL=F',
    'XAU/USD': 'GC=F',
    'S&P 500': '^GSPC',
    'NASDAQ100': '^NDX',
    'DOWJONES': '^DJI',
    'NATGAS': 'NG=F',
    'NG=F': 'NG=F',
    'COPPER': 'HG=F',
    'HG=F': 'HG=F',
    'PLATINUM': 'PL=F',
    'PL=F': 'PL=F',
    'BRK.B': 'BRK-B',
    'BRKB': 'BRK-B',
    'BRK-B': 'BRK-B',
    'BRK/B': 'BRK-B',
    'BF.B': 'BF-B',
    'BFB': 'BF-B',
    'BF-B': 'BF-B',
    'BF/B': 'BF-B',
    'BTC.D': 'BTC.D',
    'USDT.D': 'USDT.D',
    'ETH.D': 'ETH.D',
    'TOTAL': 'TOTAL',
    'TOTAL2': 'TOTAL2',
    'TOTAL3': 'TOTAL3',
    'CRYPTO_FGI': 'CRYPTO_FGI',
}

# ===================================================================
# SYMBOL ALIASES & CANONICAL RESOLUTION (Phase 5 / v3.3.0)
# Maps legacy labels, shorthand codes, and alternate notations to canonical symbols.
# ===================================================================
SYMBOL_ALIASES: Dict[str, str] = {
    # Commodities
    'GOLD': 'GOLD',
    'XAU': 'GOLD',
    'XAUUSD': 'GOLD',
    'XAU/USD': 'GOLD',
    'GC=F': 'GOLD',
    'SILVER': 'SILVER',
    'XAG': 'SILVER',
    'XAGUSD': 'SILVER',
    'XAG/USD': 'SILVER',
    'SI=F': 'SILVER',
    'OIL': 'OIL_WTI',
    'WTI': 'OIL_WTI',
    'CRUDE': 'OIL_WTI',
    'OILWTI': 'OIL_WTI',
    'OIL_WTI': 'OIL_WTI',
    'WTI/USD': 'OIL_WTI',
    'CL=F': 'OIL_WTI',
    'BRENT': 'OIL_BRENT',
    'OILBRENT': 'OIL_BRENT',
    'OIL_BRENT': 'OIL_BRENT',
    'BRENT/USD': 'OIL_BRENT',
    'BZ=F': 'OIL_BRENT',
    'NATGAS': 'NATGAS',
    'NG=F': 'NATGAS',
    'COPPER': 'COPPER',
    'HG=F': 'COPPER',
    'PLATINUM': 'PLATINUM',
    'PL=F': 'PLATINUM',
    # Indices
    'DXY': 'DXY',
    'USDX': 'DXY',
    'DX-Y.NYB': 'DXY',
    'SP500': 'SP500',
    'SPX': 'SP500',
    'S&P 500': 'SP500',
    '^GSPC': 'SP500',
    'NASDAQ': 'NASDAQ100',
    'NASDAQ100': 'NASDAQ100',
    'NDX': 'NASDAQ100',
    '^NDX': 'NASDAQ100',
    'DOWJONES': 'DOWJONES',
    'DJI': 'DOWJONES',
    '^DJI': 'DOWJONES',
    'RUT': 'RUT',
    'RUSSELL2000': 'RUT',
    '^RUT': 'RUT',
    'VIX': 'VIX',
    '^VIX': 'VIX',
    'DAX': 'DAX',
    '^GDAXI': 'DAX',
    'FTSE': 'FTSE',
    '^FTSE': 'FTSE',
    'NIKKEI': 'NIKKEI',
    '^N225': 'NIKKEI',
    # Bonds & Yields
    'US10Y': 'US10Y',
    'TNX': 'US10Y',
    '^TNX': 'US10Y',
    'DGS10': 'US10Y',
    'US02Y': 'US02Y',
    'US2Y': 'US02Y',
    '^2YY': 'US02Y',
    'DGS2': 'US02Y',
    'US13W': 'US13W',
    '^IRX': 'US13W',
    'DTB3': 'US13W',
    'US05Y': 'US05Y',
    'US5Y': 'US05Y',
    '^FVX': 'US05Y',
    'DGS5': 'US05Y',
    'US30Y': 'US30Y',
    '^TYX': 'US30Y',
    'TYX': 'US30Y',
    'DGS30': 'US30Y',
    # Dotted share classes
    'BRKB': 'BRK.B',
    'BRK-B': 'BRK.B',
    'BRK/B': 'BRK.B',
    'BRK.B': 'BRK.B',
    'BFB': 'BF.B',
    'BF-B': 'BF.B',
    'BF/B': 'BF.B',
    'BF.B': 'BF.B',
    # China/HK local vs ADR separation
    'BABA': 'BABA',
    '9988': '9988.HK',
    '9988.HK': '9988.HK',
    'TCEHY': 'TCEHY',
    '0700': '0700.HK',
    '0700.HK': '0700.HK',
    'XIACY': 'XIACY',
    '1810': '1810.HK',
    '1810.HK': '1810.HK',
    'BYDDY': 'BYDDY',
    '1211': '1211.HK',
    '1211.HK': '1211.HK',
    'BIDU': 'BIDU',
    '9888': '9888.HK',
    '9888.HK': '9888.HK',
    'JD': 'JD',
    '9618': '9618.HK',
    '9618.HK': '9618.HK',
    # Forex duplicates
    'USDCNY': 'USD_CNY',
    'USD/CNY': 'USD_CNY',
}

# FRED Series Update Frequency Rule:
# Daily and Monthly series are authoritative only for daily/macro alerts; never high-frequency intraday alerts.
FRED_SERIES_FREQUENCY: Dict[str, str] = {
    'DGS10': 'daily',
    'DGS2': 'daily',
    'DGS5': 'daily',
    'DTB3': 'daily',
    'DGS30': 'daily',
    'FEDFUNDS': 'daily',
    'CPIAUCSL': 'monthly',
    'UNRATE': 'monthly',
    'WALCL': 'daily',
    'M2SL': 'monthly',
    'DTWEXBGS': 'daily',
}

def validate_fred_alert_frequency(symbol: str, timeframe: Optional[str] = None) -> Tuple[bool, str]:
    """
    Validates that FRED series (daily/monthly) are only used for macro/daily alerts,
    never high-frequency intraday alerts.
    """
    clean_sym = (symbol or '').upper().strip().replace(' ', '')
    # Check if symbol maps to a known FRED series
    series_id = clean_sym
    from app.markets.global_stocks import FredAdapter
    if clean_sym in FredAdapter.FRED_SERIES_MAP:
        series_id = FredAdapter.FRED_SERIES_MAP[clean_sym]
    
    freq = FRED_SERIES_FREQUENCY.get(series_id)
    if not freq:
        return True, "Not a FRED series"

    tf = (timeframe or '').strip().lower()
    intraday_timeframes = {'1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h'}
    if tf in intraday_timeframes:
        return False, f"FRED series '{symbol}' ({series_id}) updates {freq}; intraday timeframe '{tf}' is prohibited. Only macro/daily alerts allowed."

    return True, f"Valid {freq} frequency for macro alert"

def resolve_symbol_alias(symbol: str) -> str:
    """Resolves legacy alias or alternative notation to canonical symbol."""
    if not symbol:
        return ''
    clean = symbol.strip().upper()
    return SYMBOL_ALIASES.get(clean, clean)

FOREX_PAIRS = {
    'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD',
    'EURGBP', 'EURJPY', 'GBPJPY', 'EURCHF', 'AUDJPY', 'GBPAUD', 'USDCNY',
    'USDTRY', 'USDMXN', 'USDZAR', 'EURCAD', 'EURAUD'
}

# 2-year Treasury yield and macro series exist only on FRED.
FRED_ONLY_SYMBOLS = frozenset({
    'US02Y', 'US2Y', '^2YY', 'DGS2',
    'FEDFUNDS', 'UNRATE', 'CPIAUCSL', 'CPI', 'WALCL', 'M2SL', 'M2'
})

# Foreign exchange suffixes on Yahoo Finance (.L, .T, .HK, .SS, .SZ, .DE, .PA, .AX, .TO, etc.)
# These MUST be preserved with dot notation and NEVER converted to dashes.
YF_EXCHANGE_SUFFIXES = frozenset({
    'L', 'T', 'HK', 'SS', 'SZ', 'DE', 'PA', 'AX', 'TO', 'V', 'F',
    'MI', 'MC', 'AS', 'BR', 'LS', 'VI', 'SW', 'CO', 'ST', 'OL',
    'HE', 'IC', 'IR', 'TA', 'SA', 'MX', 'BA', 'SN', 'JK', 'KL',
    'BK', 'SI', 'KS', 'KQ', 'TW', 'TWO', 'NZ', 'JO', 'SG', 'SR',
    'VN', 'WA', 'IS', 'AT', 'BE', 'CH', 'CN', 'DK', 'ES', 'FI', 'FR'
})


def resolve_yf_symbol(symbol_or_exchange: str, symbol: Optional[str] = None, category: Optional[str] = None) -> str:
    """
    Standardizes user/UI symbols into clean Yahoo Finance query symbols:
    - Strips /USD, -USD, USD quote suffixes from stock pairs (AAPL/USD -> AAPL)
    - Preserves share classes with dash (BRK-B) and foreign exchanges with dot (7203.T, HSBA.L)
    - Maps major Forex pairs to {PAIR}=X (EUR/USD -> EURUSD=X)
    - Resolves Macro, Yields & Commodities to exact futures tickers
    - Can be called as resolve_yf_symbol(symbol) or resolve_yf_symbol(exchange, symbol)
    """
    if symbol is not None:
        target = symbol
    else:
        target = symbol_or_exchange
    s = (target or '').upper().strip()

    # Dow Inc. (equity) guard: Dow Inc. stock ticker is 'DOW', not the '^DJI' index
    if s == 'DOW':
        return 'DOW'

    # 0. Already standard Yahoo format with =X
    if s.endswith('=X'):
        return s

    s_clean = s.replace('/', '').replace(' ', '')

    # 1. Exact map check (handles XAUUSD -> GC=F, DXY -> DX-Y.NYB, etc.)
    if s in EXACT_YF_MAP:
        return EXACT_YF_MAP[s]
    if s_clean in EXACT_YF_MAP:
        return EXACT_YF_MAP[s_clean]

    # 2. Forex pair check (BEFORE any quote stripping so EURUSD is never stripped to EUR!)
    if s_clean in FOREX_PAIRS:
        return f'{s_clean}=X'

    # 3. Explicit pair with slash (e.g. AAPL/USD -> AAPL, EUR/USD -> handled in forex or base)
    if '/' in s:
        base, quote = s.split('/', 1)
        base = base.strip()
        quote = quote.strip()
        pair_candidate = f'{base}{quote}'
        if pair_candidate in EXACT_YF_MAP:
            return EXACT_YF_MAP[pair_candidate]
        if pair_candidate in FOREX_PAIRS:
            return f'{pair_candidate}=X'
        return EXACT_YF_MAP.get(base, base)

    # 4. Trailing USD or USDT on equities (e.g. TSLAUSD -> TSLA, AAPLUSDT -> AAPL)
    # Notice: Do NOT strip if starts with ^ or contains dot (7203.T) or dash (BRK-B)
    if not s.startswith('^') and '.' not in s and '-' not in s:
        for q in ['USDT', 'USD']:
            if s.endswith(q) and len(s) > len(q):
                candidate = s[:-len(q)]
                if candidate in EXACT_YF_MAP:
                    return EXACT_YF_MAP[candidate]
                return candidate

    # 5. Dotted US share classes: BRK.B -> BRK-B, BF.B -> BF-B
    # Foreign exchange suffixes (.L, .T, .HK, .SS, .SZ, .DE, .PA, .AX, .TO, etc.) and crypto metrics (.D) MUST NOT be converted.
    if '.' in s and not s.startswith('^'):
        parts = s.split('.')
        if len(parts) == 2 and not parts[0].isdigit():
            base = parts[0].upper()
            suffix = parts[1].upper()
            if (suffix not in YF_EXCHANGE_SUFFIXES and
                suffix not in {'D'} and
                base not in {'BTC', 'USDT', 'ETH', 'TOTAL'} and
                len(suffix) == 1 and suffix.isalpha()):
                return f"{parts[0]}-{parts[1]}"

    return s

WALLSTREET_MACRO_SYMBOLS = [
    {"id": "GOLD18_BONBAST", "symbol": "GOLD18", "nameEn": "Gold 18K (Gram)", "nameFa": "طلای ۱۸ عیار - هر گرم (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "MITHQAL_BONBAST", "symbol": "MITHQAL", "nameEn": "Gold Mithqal (Melted)", "nameFa": "مظنه آبشده / مثقال طلا تهران (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "EMAMI_BONBAST", "symbol": "EMAMI", "nameEn": "Emami Gold Coin", "nameFa": "سکه تمام طرح جدید / امامی (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "BAHAR_BONBAST", "symbol": "AZADI", "nameEn": "Bahar Azadi Coin", "nameFa": "سکه تمام بهار آزادی طرح قدیم (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "HALF_BONBAST", "symbol": "HALF", "nameEn": "Half Azadi Coin", "nameFa": "نیم‌سکه بهار آزادی (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "QUARTER_BONBAST", "symbol": "QUARTER", "nameEn": "Quarter Azadi Coin", "nameFa": "ربع‌سکه بهار آزادی (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "GRAM_BONBAST", "symbol": "GRAM", "nameEn": "Central Bank Gram Coin", "nameFa": "سکه یک گرمی بانک مرکزی (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "USD_BONBAST", "symbol": "USD/TMN", "nameEn": "US Dollar (Tehran Cash)", "nameFa": "دلار آزاد تهران - اسکناس (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "EUR_BONBAST", "symbol": "EUR/TMN", "nameEn": "Euro Cash", "nameFa": "یورو آزاد تهران - اسکناس (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "AED_BONBAST", "symbol": "AED/TMN", "nameEn": "UAE Dirham Cash", "nameFa": "درهم امارات - اسکناس/حواله (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "GBP_BONBAST", "symbol": "GBP/TMN", "nameEn": "British Pound Cash", "nameFa": "پوند انگلیس - اسکناس (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "TRY_BONBAST", "symbol": "TRY/TMN", "nameEn": "Turkish Lira", "nameFa": "لیر ترکیه (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "IQD_BONBAST", "symbol": "IQD/TMN", "nameEn": "Iraqi Dinar (100)", "nameFa": "۱۰۰ دینار عراق (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "BOURSE_BONBAST", "symbol": "TEDPIX", "nameEn": "Tehran Stock Exchange Index", "nameFa": "شاخص کل بورس اوراق بهادار تهران (TEDPIX)", "category": "iran_market", "marketName": "بورس تهران (مرجع بن‌بست)", "unit": "واحد"},
    {"id": "AFN_BONBAST", "symbol": "AFN/TMN", "nameEn": "Afghan Afghani (Herat)", "nameFa": "افغانی افغانستان - بازار هرات (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "CAD_BONBAST", "symbol": "CAD/TMN", "nameEn": "Canadian Dollar Cash", "nameFa": "دلار کانادا - اسکناس آزاد (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "AUD_BONBAST", "symbol": "AUD/TMN", "nameEn": "Australian Dollar Cash", "nameFa": "دلار استرالیا - اسکناس آزاد (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "CHF_BONBAST", "symbol": "CHF/TMN", "nameEn": "Swiss Franc Cash", "nameFa": "فرانک سوئیس - اسکناس آزاد (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "CNY_BONBAST", "symbol": "CNY/TMN", "nameEn": "Chinese Yuan Cash", "nameFa": "یوان چین - اسکناس آزاد (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "KWD_BONBAST", "symbol": "KWD/TMN", "nameEn": "Kuwaiti Dinar", "nameFa": "دینار کویت (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "SAR_BONBAST", "symbol": "SAR/TMN", "nameEn": "Saudi Riyal Cash", "nameFa": "ریال عربستان (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "QAR_BONBAST", "symbol": "QAR/TMN", "nameEn": "Qatari Riyal Cash", "nameFa": "ریال قطر (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "OMR_BONBAST", "symbol": "OMR/TMN", "nameEn": "Omani Rial Cash", "nameFa": "ریال عمان (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "JPY_BONBAST", "symbol": "JPY/TMN", "nameEn": "Japanese Yen (10)", "nameFa": "۱۰ ین ژاپن (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "US10Y", "symbol": "^TNX", "nameEn": "US 10-Year Treasury Yield", "nameFa": "بازده اوراق قرضه ۱۰ ساله آمریکا (US10Y)", "category": "bond", "marketName": "US Treasury", "unit": "%"},
    {"id": "US02Y", "symbol": "DGS2", "nameEn": "US 2-Year Treasury Yield", "nameFa": "بازده اوراق قرضه ۲ ساله آمریکا (US02Y)", "category": "bond", "marketName": "US Treasury", "unit": "%"},
    {"id": "US13W", "symbol": "^IRX", "nameEn": "US 13-Week Treasury Bill Yield", "nameFa": "بازده اوراق ۱۳ هفته‌ای خزانه‌داری آمریکا (US13W)", "category": "bond", "marketName": "US Treasury", "unit": "%"},
    {"id": "US30Y", "symbol": "^TYX", "nameEn": "US 30-Year Treasury Bond", "nameFa": "بازده اوراق قرضه ۳۰ ساله آمریکا (US30Y)", "category": "bond", "marketName": "US Treasury", "unit": "%"},
    {"id": "EURUSD", "symbol": "EUR/USD", "nameEn": "Euro / US Dollar", "nameFa": "یورو به دلار آمریکا (EUR/USD)", "category": "forex", "marketName": "Forex Major", "unit": "$"},
    {"id": "GBPUSD", "symbol": "GBP/USD", "nameEn": "British Pound / US Dollar", "nameFa": "پوند انگلیس به دلار (GBP/USD)", "category": "forex", "marketName": "Forex Major", "unit": "$"},
    {"id": "USDJPY", "symbol": "USD/JPY", "nameEn": "US Dollar / Japanese Yen", "nameFa": "دلار به ین ژاپن (USD/JPY)", "category": "forex", "marketName": "Forex Major", "unit": "¥"},
    {"id": "USDCHF", "symbol": "USD/CHF", "nameEn": "US Dollar / Swiss Franc", "nameFa": "دلار به فرانک سوئیس (USD/CHF)", "category": "forex", "marketName": "Forex Major", "unit": "Fr"},
    {"id": "AUDUSD", "symbol": "AUD/USD", "nameEn": "Australian Dollar / USD", "nameFa": "دلار استرالیا به دلار آمریکا (AUD/USD)", "category": "forex", "marketName": "Forex Major", "unit": "$"},
    {"id": "USDCAD", "symbol": "USD/CAD", "nameEn": "US Dollar / Canadian Dollar", "nameFa": "دلار آمریکا به دلار کانادا (USD/CAD)", "category": "forex", "marketName": "Forex Major", "unit": "C$"},
    {"id": "NVDA", "symbol": "NVDA", "nameEn": "NVIDIA Corporation", "nameFa": "سهام انویدیا (NVIDIA)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "AAPL", "symbol": "AAPL", "nameEn": "Apple Inc.", "nameFa": "سهام اپل (Apple)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "MSFT", "symbol": "MSFT", "nameEn": "Microsoft Corporation", "nameFa": "سهام مایکروسافت (Microsoft)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "AMZN", "symbol": "AMZN", "nameEn": "Amazon.com Inc.", "nameFa": "سهام آمازون (Amazon)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "GOOGL", "symbol": "GOOGL", "nameEn": "Alphabet Inc. (Google)", "nameFa": "سهام گوگل (آلفابت)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "META", "symbol": "META", "nameEn": "Meta Platforms (Facebook)", "nameFa": "سهام متا (فیسبوک)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "PLTR", "symbol": "PLTR", "nameEn": "Palantir Technologies", "nameFa": "سهام پالانتیر (Palantir)", "category": "stock", "marketName": "NYSE", "unit": "$"},
    {"id": "BRKB", "symbol": "BRK.B", "nameEn": "Berkshire Hathaway", "nameFa": "برکشایر هاتاوی (وارن بافت)", "category": "stock", "marketName": "NYSE", "unit": "$"},
    {"id": "TSLA", "symbol": "TSLA", "nameEn": "Tesla Inc.", "nameFa": "سهام تسلا (خودروهای برقی، هوش مصنوعی، ربات اپتیموس و انرژی ایلان ماسک)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "DXYZ", "symbol": "DXYZ", "nameEn": "Destiny Tech100 (SpaceX & OpenAI ETF)", "nameFa": "صندوق سرنوشت ۱۰۰ (سبد سهام عمومی اسپیس‌ایکس و اوپن‌ای‌آی)", "category": "stock", "marketName": "NYSE", "unit": "$"},
    {"id": "RKLB", "symbol": "RKLB", "nameEn": "Rocket Lab USA", "nameFa": "راکت لب (پرتاب‌های فضایی مداری تجاری و ماهواره‌های ناسا)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "ASTS", "symbol": "ASTS", "nameEn": "AST SpaceMobile", "nameFa": "ای‌اس‌تی اسپیس‌موبایل (شبکه پهن‌باند ماهواره‌ای به گوشی هوشمند)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "BA", "symbol": "BA", "nameEn": "The Boeing Company", "nameFa": "بوئینگ (غول هواپیماسازی، فضاپیما و کپسول فضایی استارلاینر)", "category": "stock", "marketName": "NYSE", "unit": "$"},
    {"id": "TSM", "symbol": "TSM", "nameEn": "Taiwan Semiconductor Manufacturing (TSMC)", "nameFa": "تی‌اس‌ام‌سی (سازنده انحصاری تراشه‌های پیشرفته جهان)", "category": "stock", "marketName": "NYSE", "unit": "$"},
    {"id": "ASML", "symbol": "ASML", "nameEn": "ASML Holding N.V.", "nameFa": "ای‌اس‌ام‌ال هلند (انحصار ۱۰۰٪ ماشین‌آلات لیتوگرافی فرابنفش چاپ تراشه)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "AMD", "symbol": "AMD", "nameEn": "Advanced Micro Devices Inc.", "nameFa": "ای‌ام‌دی (پردازنده‌های هوش مصنوعی و کارت‌های گرافیک)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "AVGO", "symbol": "AVGO", "nameEn": "Broadcom Inc.", "nameFa": "برودکام (غول تراشه‌های شبکه و هوش مصنوعی اختصاصی)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "LVMH", "symbol": "MC.PA", "nameEn": "LVMH Moët Hennessy Louis Vuitton", "nameFa": "ال‌وی‌ام‌اچ فرانسه (لویی ویتون، دیور، تیفانی، بولگاری - پادشاه برندهای لوکس)", "category": "stock", "marketName": "Euronext Paris", "unit": "€"},
    {"id": "HERMES", "symbol": "RMS.PA", "nameEn": "Hermès International", "nameFa": "هرمس فرانسه (گران‌قیمت‌ترین خانه مد، کیف برکین و چرم دست‌ساز)", "category": "stock", "marketName": "Euronext Paris", "unit": "€"},
    {"id": "PORSCHE", "symbol": "P911.DE", "nameEn": "Porsche AG", "nameFa": "پورشه آلمان (سوپراسپرت‌های لوکس اشتوتگارت)", "category": "stock", "marketName": "XETRA", "unit": "€"},
    {"id": "USD_AED", "symbol": "USD/AED", "nameEn": "US Dollar / UAE Dirham", "nameFa": "دلار آمریکا به درهم امارات (USD/AED)", "category": "forex", "marketName": "Forex Major", "unit": "AED"},
    {"id": "USD_CNY", "symbol": "USD/CNY", "nameEn": "US Dollar / Chinese Yuan", "nameFa": "دلار آمریکا به یوان چین (USD/CNY)", "category": "forex", "marketName": "Forex Major", "unit": "¥"},
    {"id": "MSTR", "symbol": "MSTR", "nameEn": "MicroStrategy Inc.", "nameFa": "میکرواستراتژی (بزرگ‌ترین خزانه‌داری بیت‌کوین سازمانی)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "COIN", "symbol": "COIN", "nameEn": "Coinbase Global Inc.", "nameFa": "کوین‌بیس (بزرگ‌ترین صرافی مجاز کریپتو آمریکا)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "MARA", "symbol": "MARA", "nameEn": "MARA Holdings (Marathon)", "nameFa": "ماراتون دیجیتال / MARA (بزرگ‌ترین استخراج‌کننده بیت‌کوین)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "RIOT", "symbol": "RIOT", "nameEn": "Riot Platforms Inc.", "nameFa": "رایوت پلتفرمز (زیرساخت استخراج و مزارع بیت‌کوین)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "CLSK", "symbol": "CLSK", "nameEn": "CleanSpark Inc.", "nameFa": "کلین‌اسپارک (استخراج سبز و پربازده بیت‌کوین)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "HOOD", "symbol": "HOOD", "nameEn": "Robinhood Markets", "nameFa": "رابین‌هود (کارگزاری معامله سهام و رمزارز)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "RDDT", "symbol": "RDDT", "nameEn": "Reddit Inc.", "nameFa": "ردیت (انجمن وب و مرجع داده‌های آموزش AI)", "category": "stock", "marketName": "NYSE", "unit": "$"},
    {"id": "SHOP", "symbol": "SHOP", "nameEn": "Shopify Inc.", "nameFa": "شاپیفای (فروشگاه‌ساز آنلاین جهانی)", "category": "stock", "marketName": "NYSE", "unit": "$"},
    {"id": "SNOW", "symbol": "SNOW", "nameEn": "Snowflake Inc.", "nameFa": "اسنوفلیک (انبار داده‌های کلاد هوش مصنوعی)", "category": "stock", "marketName": "NYSE", "unit": "$"},
    {"id": "RACE", "symbol": "RACE", "nameEn": "Ferrari N.V.", "nameFa": "فراری (سوپراسپرت‌های لوکس ایتالیا)", "category": "stock", "marketName": "NYSE", "unit": "$"},
    {"id": "GOLD", "symbol": "XAU/USD", "nameEn": "Gold Spot", "nameFa": "انس طلای جهانی (Gold XAU/USD)", "category": "commodity", "marketName": "Commodities", "unit": "$"},
    {"id": "SILVER", "symbol": "XAG/USD", "nameEn": "Silver Spot", "nameFa": "انس نقره جهانی (Silver XAG/USD)", "category": "commodity", "marketName": "Commodities", "unit": "$"},
    {"id": "COPPER", "symbol": "HG=F", "nameEn": "Copper Futures (Dr. Copper)", "nameFa": "مس صنعتی جهانی (دکتر مس - دماسنج اقتصاد)", "category": "commodity", "marketName": "COMEX", "unit": "$"},
    {"id": "NATGAS", "symbol": "NG=F", "nameEn": "Natural Gas Futures", "nameFa": "گاز طبیعی هنری هاب (Henry Hub)", "category": "commodity", "marketName": "NYMEX", "unit": "$"},
    {"id": "PLATINUM", "symbol": "PL=F", "nameEn": "Platinum Spot (XPT/USD)", "nameFa": "پلاتین جهانی (فلز فوق‌لوکس صنعتی)", "category": "commodity", "marketName": "NYMEX", "unit": "$"},
    {"id": "URANIUM", "symbol": "URNM", "nameEn": "Sprott Uranium Miners ETF", "nameFa": "صندوق اورانیوم و سوخت هسته‌ای هوش مصنوعی", "category": "commodity", "marketName": "NYSE", "unit": "$"},
    {"id": "OIL_WTI", "symbol": "WTI", "nameEn": "Crude Oil (WTI)", "nameFa": "نفت خام تگزاس (WTI Oil)", "category": "commodity", "marketName": "NYMEX", "unit": "$"},
    {"id": "OIL_BRENT", "symbol": "BRENT", "nameEn": "Brent Crude Oil", "nameFa": "نفت برنت دریای شمال", "category": "commodity", "marketName": "ICE", "unit": "$"},
    {"id": "VIX", "symbol": "^VIX", "nameEn": "CBOE Volatility Index (VIX)", "nameFa": "شاخص نوسان و ترس وال‌استریت (VIX)", "category": "index", "marketName": "CBOE", "unit": "pts"},
    {"id": "RUT", "symbol": "^RUT", "nameEn": "Russell 2000 Index", "nameFa": "شاخص ۲۰۰۰ شرکت کوچک آمریکا (Russell 2000)", "category": "index", "marketName": "US Indices", "unit": "pts"},
    {"id": "DAX", "symbol": "^GDAXI", "nameEn": "DAX 40 Germany", "nameFa": "شاخص ۴۰ غول صنعتی بورس آلمان (DAX)", "category": "index", "marketName": "Deutsche Börse", "unit": "pts"},
    {"id": "NIKKEI", "symbol": "^N225", "nameEn": "Nikkei 225 Japan", "nameFa": "شاخص ۲۲۵ شرکت برتر بورس توکیو ژاپن (Nikkei)", "category": "index", "marketName": "Tokyo Stock Exchange", "unit": "pts"},
    {"id": "FTSE", "symbol": "^FTSE", "nameEn": "FTSE 100 UK", "nameFa": "شاخص ۱۰۰ شرکت برتر بورس لندن انگلستان (FTSE)", "category": "index", "marketName": "London Stock Exchange", "unit": "pts"},
    {"id": "SP500", "symbol": "S&P 500", "nameEn": "S&P 500 Index", "nameFa": "شاخص ۵۰۰ شرکت برتر آمریکا (S&P 500)", "category": "index", "marketName": "US Indices", "unit": "pts"},
    {"id": "NASDAQ100", "symbol": "NDX", "nameEn": "NASDAQ 100 Index", "nameFa": "شاخص ۱۰۰ غول فناوری (Nasdaq 100)", "category": "index", "marketName": "NASDAQ", "unit": "pts"},
    {"id": "DOWJONES", "symbol": "DJI", "nameEn": "Dow Jones Industrial", "nameFa": "شاخص صنعتی داوجونز (Dow Jones)", "category": "index", "marketName": "NYSE", "unit": "pts"},
    {"id": "DXY", "symbol": "DXY", "nameEn": "US Dollar Index", "nameFa": "شاخص قدرت جهانی دلار (DXY)", "category": "index", "marketName": "ICE", "unit": "pts"}
]


# ===================================================================
# 2. CIRCUIT BREAKER & RESILIENCE INFRASTRUCTURE
# ===================================================================
class CircuitBreakerOpenError(Exception):
    """Raised when an adapter's circuit breaker is in OPEN state."""
    pass


class CircuitBreaker:
    """
    Standard Circuit Breaker pattern with CLOSED, OPEN, and HALF_OPEN states.
    - Trips to OPEN after failure_threshold consecutive failures.
    - Stays in OPEN for recovery_timeout seconds, then transitions to HALF_OPEN.
    - In HALF_OPEN, allows a single probe attempt; success closes, failure re-opens.
    """
    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = "CLOSED"  # "CLOSED", "OPEN", "HALF_OPEN"
        self.last_failure_time = 0.0

    def can_execute(self) -> bool:
        now = time.time()
        if self.state == "OPEN":
            if now - self.last_failure_time >= self.recovery_timeout:
                self.state = "HALF_OPEN"
                return True
            return False
        return True

    def record_success(self):
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"


# ===================================================================
# 3. BASE MARKET ADAPTER (COMMON CONTRACT)
# ===================================================================
class BaseMarketAdapter:
    """
    Abstract Base Class for Market Data Providers.
    Every provider provides:
      - fetch_quotes(symbols, client) -> Dict[str, Optional[Dict[str, Any]]]
      - fetch_catalog() -> List[Dict[str, Any]]
      - Resilient execution with timeout, exponential backoff, jitter, circuit breaker, quota logging.
    """
    name: str = "base"

    def __init__(self, api_key: str = "", timeout: float = 3.5, max_retries: int = 2):
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)

    async def fetch_quotes(
        self,
        symbols: List[str],
        client: httpx.AsyncClient
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        results: Dict[str, Optional[Dict[str, Any]]] = {}
        for s in symbols:
            results[s] = await self.fetch_quote(s, client)
        return results

    async def fetch_quote(
        self,
        symbol: str,
        client: httpx.AsyncClient
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def fetch_catalog(self) -> List[Dict[str, Any]]:
        return []

    async def _execute_http(
        self,
        url: str,
        extractor_func,
        client: httpx.AsyncClient,
        headers: Optional[Dict[str, str]] = None
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """
        Executes HTTP request with Circuit Breaker, Exponential Backoff + Jitter, and Quota metrics.
        Returns: (parsed_meta, trace_dict)
        """
        trace: Dict[str, Any] = {
            'source': self.name,
            'url': url,
            'status_code': 0,
            'latency_ms': 0.0,
            'success': False,
        }

        # 1. Circuit Breaker Check
        if not self.circuit_breaker.can_execute():
            trace['error'] = 'Circuit breaker OPEN'
            record_provider_metric(self.name, "errors")
            return None, trace

        # 2. Rate Limiting slot
        await acquire_provider_slot(self.name, wait=True)

        req_headers = {'User-Agent': f'SignalAlert/{APP_VERSION}'}
        if headers:
            req_headers.update(headers)

        last_error = None
        base_backoff = 0.2

        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                # Exponential backoff with random jitter
                backoff_wait = (base_backoff * (2 ** (attempt - 1))) + random.uniform(0.02, 0.08)
                await asyncio.sleep(backoff_wait)

            t0 = time.time()
            try:
                res = await client.get(url, headers=req_headers, timeout=self.timeout)
                trace['latency_ms'] = round((time.time() - t0) * 1000, 2)
                trace['status_code'] = res.status_code
                self.last_trace = dict(trace)

                if res.status_code == 200:
                    try:
                        data = res.json()
                    except Exception as json_err:
                        self.circuit_breaker.record_failure()
                        record_provider_metric(self.name, "errors")
                        trace['error'] = f"Malformed JSON: {str(json_err)}"
                        return None, trace

                    parsed = extractor_func(data)
                    if parsed is not None and isinstance(parsed, dict):
                        self.circuit_breaker.record_success()
                        record_provider_metric(self.name, "success")
                        trace['success'] = True
                        trace['parsed_price'] = parsed.get('price')
                        trace['asOf'] = parsed.get('asOf')
                        trace['state'] = parsed.get('state', 'LIVE')
                        trace['currency'] = parsed.get('currency', 'USD')
                        return parsed, trace
                    else:
                        trace['error'] = 'Extractor returned None'
                        return None, trace

                elif res.status_code == 429:
                    self.circuit_breaker.record_failure()
                    record_provider_metric(self.name, "rate_limits_429")
                    record_provider_metric(self.name, "errors")
                    trace['error'] = 'HTTP 429 Rate Limit'
                    return None, trace

                elif res.status_code in (400, 401, 403, 404):
                    # Permanent client/auth/not-found error: do NOT retry
                    record_provider_metric(self.name, "errors")
                    trace['error'] = f'HTTP {res.status_code}'
                    return None, trace

                else:
                    # 5xx server error: eligible for retry
                    last_error = f'HTTP {res.status_code}'
                    trace['error'] = last_error

            except (httpx.TimeoutException, asyncio.TimeoutError) as te:
                last_error = f'Timeout: {str(te)}'
                trace['latency_ms'] = round((time.time() - t0) * 1000, 2)
                trace['error'] = last_error
            except Exception as exc:
                last_error = f'Network exception: {str(exc)}'
                trace['latency_ms'] = round((time.time() - t0) * 1000, 2)
                trace['error'] = last_error

        # If all retries exhausted
        self.circuit_breaker.record_failure()
        record_provider_metric(self.name, "errors")
        trace['error'] = f'Failed after {self.max_retries} retries ({last_error})'
        return None, trace


# ===================================================================
# 4. CONCRETE ADAPTERS: Yahoo, Finnhub, Twelve Data, FRED
# ===================================================================

class YahooFinanceAdapter(BaseMarketAdapter):
    """
    Adapter for Yahoo Finance (query1 with query2 fallback).
    Free, no API key required. Supports stocks, forex, indices, commodities, bonds.
    """
    name = "yahoo"

    def fetch_catalog(self) -> List[Dict[str, Any]]:
        return WALLSTREET_MACRO_SYMBOLS

    def resolve_symbol(self, symbol: str) -> str:
        """Resolves symbol for Yahoo Finance, including dotted share classes and futures."""
        return resolve_yf_symbol(symbol)

    def _extract_yf(self, data):
        if isinstance(data, dict):
            chart = data.get('chart', {}).get('result', [])
            if chart and isinstance(chart, list) and len(chart) > 0:
                meta = chart[0].get('meta', {})
                p = meta.get('regularMarketPrice')
                as_of_ts = meta.get('regularMarketTime') or meta.get('currentTradingPeriod', {}).get('regular', {}).get('end')
                m_state = meta.get('marketState', 'REGULAR')
                currency = meta.get('currency', 'USD')
                if p is not None and float(p) > 0:
                    return {
                        'price': float(p),
                        'asOf': int(as_of_ts) if as_of_ts else int(time.time()),
                        'state': m_state,
                        'currency': currency,
                        'source': 'Yahoo Finance'
                    }
                elif m_state in ['CLOSED', 'closed', 'POST', 'PRE']:
                    prev_p = meta.get('chartPreviousClose') or meta.get('previousClose')
                    return {
                        'price': float(prev_p) if prev_p else None,
                        'asOf': int(as_of_ts) if as_of_ts else int(time.time()),
                        'state': 'closed',
                        'currency': currency,
                        'source': 'Yahoo Finance'
                    }
        return None

    async def fetch_quote(self, symbol: str, client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
        yf_symbol = resolve_yf_symbol(symbol)

        # 1. Primary: query1
        url1 = f'https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}?interval=1m&range=1d'
        parsed, trace = await self._execute_http(url1, self._extract_yf, client)
        if parsed:
            return parsed

        # 2. Secondary fallback: query2 (if not 404)
        if trace.get('status_code') != 404:
            url2 = f'https://query2.finance.yahoo.com/v8/finance/chart/{yf_symbol}?interval=1m&range=1d'
            parsed2, _ = await self._execute_http(url2, self._extract_yf, client)
            if parsed2:
                return parsed2

        return None


class FinnhubAdapter(BaseMarketAdapter):
    """
    Adapter for Finnhub Stock & Forex REST API.
    Supports US Equities (AAPL, TSLA, MSFT) and major Forex pairs.
    """
    name = "finnhub"

    def fetch_catalog(self) -> List[Dict[str, Any]]:
        return [s for s in WALLSTREET_MACRO_SYMBOLS if s.get('category') in ('stock', 'forex')]

    def resolve_symbol(self, symbol: str) -> str:
        """Resolves symbol for Finnhub REST API."""
        return self._resolve_symbol(symbol)

    def _resolve_symbol(self, symbol: str) -> str:
        s = symbol.upper().strip().replace(' ', '')
        if s.endswith('=X'):
            s = s[:-2]
        if '/' in s:
            parts = s.split('/')
            return f"OANDA:{parts[0]}_{parts[1]}"
        if s in FOREX_PAIRS:
            return f"OANDA:{s[:3]}_{s[3:]}"
        # Dotted US equities in Finnhub: BRK.B, BF.B
        if s in ('BRKB', 'BRK-B', 'BRK/B', 'BRK.B'):
            return 'BRK.B'
        if s in ('BFB', 'BF-B', 'BF/B', 'BF.B'):
            return 'BF.B'
        # US ADRs (BABA, TCEHY, XIACY, BYDDY, BIDU, JD)
        if s in ('BABA', 'TCEHY', 'XIACY', 'BYDDY', 'BIDU', 'JD'):
            return s
        return s

    def _extract_finnhub(self, data):
        if isinstance(data, dict):
            c = data.get('c')
            if c is not None and float(c) > 0:
                t = data.get('t')
                return {
                    'price': float(c),
                    'asOf': int(t) if t else int(time.time()),
                    'state': 'LIVE',
                    'currency': 'USD',
                    'source': 'Finnhub',
                    'change_pct': float(data.get('dp', 0.0)),
                    'prev_close': float(data.get('pc', 0.0)),
                    'high': float(data.get('h', 0.0)),
                    'low': float(data.get('l', 0.0))
                }
            elif data.get('pc') and float(data.get('pc')) > 0:
                return {
                    'price': float(data.get('pc')),
                    'asOf': int(data.get('t') or time.time()),
                    'state': 'closed',
                    'currency': 'USD',
                    'source': 'Finnhub'
                }
        return None

    async def fetch_quote(self, symbol: str, client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
        active_key = self.api_key or os.getenv("FINNHUB_API_KEY", "").strip()
        if not active_key:
            return None

        finnhub_sym = self._resolve_symbol(symbol)
        url = f"https://finnhub.io/api/v1/quote?symbol={finnhub_sym}&token={active_key}"
        parsed, _ = await self._execute_http(url, self._extract_finnhub, client)
        return parsed


class TwelveDataAdapter(BaseMarketAdapter):
    """
    Adapter for Twelve Data REST API.
    Supports Stocks, Forex, Indices, Commodities.
    """
    name = "twelvedata"

    def fetch_catalog(self) -> List[Dict[str, Any]]:
        return [s for s in WALLSTREET_MACRO_SYMBOLS if s.get('category') in ('stock', 'forex', 'index', 'commodity')]

    def resolve_symbol(self, symbol: str) -> str:
        """Resolves symbol for Twelve Data REST API."""
        return self._resolve_symbol(symbol)

    def _resolve_symbol(self, symbol: str) -> str:
        s = symbol.upper().strip()
        # Commodities
        if s in ('GOLD', 'XAU', 'XAUUSD', 'XAU/USD', 'GC=F'):
            return 'XAU/USD'
        if s in ('SILVER', 'XAG', 'XAGUSD', 'XAG/USD', 'SI=F'):
            return 'XAG/USD'
        if s in ('WTI', 'CL=F', 'OIL', 'CRUDE', 'OILWTI', 'OIL_WTI', 'WTI/USD'):
            return 'WTI/USD'
        if s in ('BRENT', 'BZ=F', 'OILBRENT', 'OIL_BRENT', 'BRENT/USD'):
            return 'BRENT'
        if s in ('NATGAS', 'NG=F'):
            return 'NATGAS'
        if s in ('COPPER', 'HG=F'):
            return 'COPPER'
        if s in ('PLATINUM', 'PL=F'):
            return 'PLATINUM'
        # Indices
        if s in ('SP500', 'SPX', '^GSPC', 'S&P 500'):
            return 'SPX'
        if s in ('NASDAQ', 'NASDAQ100', 'NDX', '^NDX'):
            return 'NDX'
        if s in ('DOWJONES', 'DJI', '^DJI'):
            return 'DJI'
        if s in ('VIX', '^VIX'):
            return 'VIX'
        if s in ('DXY', 'USDX', 'DX-Y.NYB'):
            return 'DXY'
        if s in ('RUT', '^RUT'):
            return 'RUT'
        if s in ('DAX', '^GDAXI'):
            return 'DAX'
        if s in ('FTSE', '^FTSE'):
            return 'FTSE'
        if s in ('NIKKEI', '^N225'):
            return 'N225'
        # Dotted US equities
        if s in ('BRKB', 'BRK-B', 'BRK/B', 'BRK.B'):
            return 'BRK.B'
        if s in ('BFB', 'BF-B', 'BF/B', 'BF.B'):
            return 'BF.B'
        # Hong Kong local shares vs US ADRs
        if s.endswith('.HK'):
            return s[:-3]  # e.g., '0700.HK' -> '0700'
        if s in ('BABA', 'TCEHY', 'XIACY', 'BYDDY', 'BIDU', 'JD'):
            return s
        if s.endswith('=X'):
            s_pair = s[:-2]
            if len(s_pair) == 6:
                return f"{s_pair[:3]}/{s_pair[3:]}"
            return s_pair
        if '/' in s:
            return s
        if s in FOREX_PAIRS:
            return f"{s[:3]}/{s[3:]}"
        if s.startswith('^'):
            return s[1:]
        return s

    def _extract_td(self, data):
        if isinstance(data, dict):
            if data.get('status') == 'error' or 'code' in data:
                return None
            close_p = data.get('close') or data.get('price')
            if close_p is not None and float(close_p) > 0:
                is_open = bool(data.get('is_market_open', True))
                ts = data.get('timestamp')
                return {
                    'price': float(close_p),
                    'asOf': int(ts) if ts else int(time.time()),
                    'state': 'LIVE' if is_open else 'closed',
                    'currency': data.get('currency', 'USD'),
                    'source': 'Twelve Data'
                }
        return None

    async def fetch_quote(self, symbol: str, client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
        active_key = self.api_key or os.getenv("TWELVE_DATA_API_KEY", "").strip()
        if not active_key:
            return None

        td_sym = self._resolve_symbol(symbol)
        url = f"https://api.twelvedata.com/quote?symbol={td_sym}&apikey={active_key}"
        parsed, _ = await self._execute_http(url, self._extract_td, client)
        return parsed


class FredAdapter(BaseMarketAdapter):
    """
    Adapter for Federal Reserve Economic Data (FRED).
    Authoritative provider for US Macroeconomic indicators and Treasury yields.
    """
    name = "fred"

    FRED_SERIES_MAP: Dict[str, str] = {
        'US10Y': 'DGS10',
        '^TNX': 'DGS10',
        'TNX': 'DGS10',
        'US02Y': 'DGS2',
        'US2Y': 'DGS2',
        '^2YY': 'DGS2',
        'US05Y': 'DGS5',
        'US5Y': 'DGS5',
        '^FVX': 'DGS5',
        'US13W': 'DTB3',
        '^IRX': 'DTB3',
        'US30Y': 'DGS30',
        '^TYX': 'DGS30',
        'DXY': 'DTWEXBGS',
        'USDX': 'DTWEXBGS',
        'DX-Y.NYB': 'DTWEXBGS',
        'FEDFUNDS': 'FEDFUNDS',
        'CPI': 'CPIAUCSL',
        'CPIAUCSL': 'CPIAUCSL',
        'UNRATE': 'UNRATE',
        'M2': 'M2SL',
        'M2SL': 'M2SL',
        'WALCL': 'WALCL',
    }

    def resolve_symbol(self, symbol: str) -> Optional[str]:
        """Resolves user symbol or market symbol to FRED series ID."""
        if not symbol:
            return None
        clean_sym = symbol.upper().strip().replace(' ', '')
        series_id = self.FRED_SERIES_MAP.get(clean_sym)
        if series_id:
            return series_id
        if clean_sym in self.FRED_SERIES_MAP.values():
            return clean_sym
        if clean_sym in FRED_SERIES_FREQUENCY:
            return clean_sym
        return None

    def get_series_frequency(self, symbol: str) -> Optional[str]:
        """Returns the update frequency ('daily' or 'monthly') of a FRED series."""
        series_id = self.resolve_symbol(symbol)
        if series_id:
            return FRED_SERIES_FREQUENCY.get(series_id, 'daily')
        return None

    def fetch_catalog(self) -> List[Dict[str, Any]]:
        return [s for s in WALLSTREET_MACRO_SYMBOLS if s.get('category') in ('bond', 'macro')]

    FRED_SERIES_METADATA: Dict[str, Dict[str, Any]] = {
        'CPIAUCSL': {
            'id': 'CPIAUCSL',
            'title': 'Consumer Price Index for All Urban Consumers: All Items in U.S. City Average',
            'units': 'Index 1982-1984=100',
            'units_short': 'Index 1982-1984=100',
            'frequency': 'Monthly',
            'currency': 'PTS',
        },
        'WALCL': {
            'id': 'WALCL',
            'title': 'Assets: Total Assets: Total Assets (Less Eliminations from Consolidation)',
            'units': 'Millions of U.S. Dollars',
            'units_short': 'Mil. of U.S. $',
            'frequency': 'Weekly',
            'currency': 'USD',
        },
        'M2SL': {
            'id': 'M2SL',
            'title': 'M2',
            'units': 'Billions of U.S. Dollars',
            'units_short': 'Bil. of U.S. $',
            'frequency': 'Monthly',
            'currency': 'USD',
        },
        'FEDFUNDS': {
            'id': 'FEDFUNDS',
            'title': 'Federal Funds Effective Rate',
            'units': 'Percent',
            'units_short': '%',
            'frequency': 'Daily',
            'currency': '%',
        },
        'UNRATE': {
            'id': 'UNRATE',
            'title': 'Civilian Unemployment Rate',
            'units': 'Percent',
            'units_short': '%',
            'frequency': 'Monthly',
            'currency': '%',
        },
        'DGS10': {
            'id': 'DGS10',
            'title': '10-Year Treasury Constant Maturity Rate',
            'units': 'Percent',
            'units_short': '%',
            'frequency': 'Daily',
            'currency': '%',
        },
        'DGS2': {
            'id': 'DGS2',
            'title': '2-Year Treasury Constant Maturity Rate',
            'units': 'Percent',
            'units_short': '%',
            'frequency': 'Daily',
            'currency': '%',
        },
        'DGS5': {
            'id': 'DGS5',
            'title': '5-Year Treasury Constant Maturity Rate',
            'units': 'Percent',
            'units_short': '%',
            'frequency': 'Daily',
            'currency': '%',
        },
        'DTB3': {
            'id': 'DTB3',
            'title': '3-Month Treasury Bill Secondary Market Rate',
            'units': 'Percent',
            'units_short': '%',
            'frequency': 'Daily',
            'currency': '%',
        },
        'DGS30': {
            'id': 'DGS30',
            'title': '30-Year Treasury Constant Maturity Rate',
            'units': 'Percent',
            'units_short': '%',
            'frequency': 'Daily',
            'currency': '%',
        },
        'DTWEXBGS': {
            'id': 'DTWEXBGS',
            'title': 'Nominal Broad U.S. Dollar Index',
            'units': 'Index Jan 2006=100',
            'units_short': 'Index Jan 2006=100',
            'frequency': 'Daily',
            'currency': 'PTS',
        },
    }

    def _make_extractor(self, series_id: str, dynamic_units: Optional[str] = None):
        def _extract(data):
            if isinstance(data, dict):
                obs = data.get('observations', [])
                if obs and isinstance(obs, list) and len(obs) > 0:
                    val_str = obs[0].get('value')
                    if val_str and val_str != '.':
                        try:
                            val = float(val_str)
                            meta = self.FRED_SERIES_METADATA.get(series_id, {})
                            units_val = dynamic_units or meta.get('units', '%')
                            curr_val = meta.get('currency') or ('%' if '%' in str(units_val) else 'USD')
                            return {
                                'price': val,
                                'asOf': int(time.time()),
                                'date': obs[0].get('date'),
                                'state': 'LIVE',
                                'units': units_val,
                                'unit': meta.get('units_short', units_val),
                                'currency': curr_val,
                                'source': 'FRED'
                            }
                        except ValueError:
                            pass
            return None
        return _extract

    async def fetch_quote(self, symbol: str, client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
        clean_sym = symbol.upper().strip().replace(' ', '')
        series_id = self.FRED_SERIES_MAP.get(clean_sym)
        if not series_id:
            if clean_sym in self.FRED_SERIES_MAP.values():
                series_id = clean_sym
            else:
                return None

        meta = self.FRED_SERIES_METADATA.get(series_id, {})
        dynamic_units = meta.get('units')
        active_key = self.api_key or os.getenv("FRED_API_KEY", "").strip()

        if active_key and active_key != 'demo_fred':
            # 1. Fetch units metadata from fred/series if available
            try:
                meta_url = f"https://api.stlouisfed.org/fred/series?series_id={series_id}&api_key={active_key}&file_type=json"
                resp_meta = await client.get(meta_url, timeout=5.0)
                if resp_meta.status_code == 200:
                    m_data = resp_meta.json()
                    seriess = m_data.get('seriess', [])
                    if seriess and isinstance(seriess, list) and len(seriess) > 0:
                        live_units = seriess[0].get('units')
                        if live_units:
                            dynamic_units = live_units
            except Exception:
                pass

            # 2. Fetch latest observation
            url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={active_key}&file_type=json&sort_order=desc&limit=1"
            parsed, _ = await self._execute_http(url, self._make_extractor(series_id, dynamic_units), client)
            if parsed:
                return parsed

        # Fallback to FRED CSV public endpoint (requires no API key)
        csv_url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        try:
            resp = await client.get(csv_url, timeout=10.0)
            if resp.status_code == 200:
                lines = resp.text.splitlines()
                for line in reversed(lines):
                    if not line or line.startswith('DATE'):
                        continue
                    parts = line.split(',')
                    if len(parts) >= 2:
                        date_str, val_str = parts[0].strip(), parts[1].strip()
                        if val_str and val_str != '.' and val_str.lower() != 'nan':
                            val = float(val_str)
                            units_val = dynamic_units or meta.get('units', '%')
                            curr_val = meta.get('currency') or ('%' if '%' in str(units_val) else 'USD')
                            return {
                                'price': val,
                                'asOf': int(time.time()),
                                'date': date_str,
                                'state': 'LIVE',
                                'units': units_val,
                                'unit': meta.get('units_short', units_val),
                                'currency': curr_val,
                                'source': 'FRED'
                            }
        except Exception:
            pass
        return None


yahoo_adapter = YahooFinanceAdapter()
finnhub_adapter = FinnhubAdapter(api_key=FINNHUB_API_KEY)
twelve_data_adapter = TwelveDataAdapter(api_key=TWELVE_DATA_API_KEY)
fred_adapter = FredAdapter(api_key=FRED_API_KEY)

def get_fallback_chain(symbol: str) -> List[BaseMarketAdapter]:
    """
    Returns the ordered fallback chain of market adapters for a symbol.
    Strictly prevents fallback from commercial/market data (stocks, forex, commodities, indices) to FRED.
    """
    clean_sym = (symbol or '').upper().strip()
    try:
        category = resolve_symbol_category(clean_sym)
    except Exception:
        category = 'stock'

    # FRED-only symbols & macro series (e.g. US02Y, FEDFUNDS, UNRATE, CPIAUCSL) only FRED
    if clean_sym in FRED_ONLY_SYMBOLS or clean_sym in ('FEDFUNDS', 'UNRATE', 'CPIAUCSL', 'CPI', 'WALCL', 'M2SL', 'M2'):
        return [fred_adapter]

    if category in ('stock', 'forex'):
        return [yahoo_adapter, finnhub_adapter, twelve_data_adapter]
    elif category in ('index', 'commodity'):
        return [yahoo_adapter, twelve_data_adapter]
    elif category in ('bond', 'macro'):
        # Substitutable bonds: order [fred, yahoo]
        return [fred_adapter, yahoo_adapter]
    return [yahoo_adapter]


async def fetch_global_stocks(client: Any, exchange: str, symbol: str, try_fetch_func: Any = None, traces: Optional[list] = None, collect_all_traces: bool = False, _try_fetch: Any = None) -> Optional[float]:
    if try_fetch_func is None and _try_fetch is not None:
        try_fetch_func = _try_fetch
    if traces is None:
        traces = []
    adapters = get_fallback_chain(symbol)

    for i, adapter in enumerate(adapters):
        try:
            q = await adapter.fetch_quote(symbol, client)
            if q and q.get('price') is not None:
                price = float(q['price'])
                source = q.get('source', adapter.name)
                if traces is not None:
                    traces.append({'source': source, 'provider': source, 'price': price, 'status': 'ok'})
                if not collect_all_traces:
                    return price
            else:
                last_tr = getattr(adapter, 'last_trace', None) or {}
                if traces is not None:
                    tr = {'source': adapter.name, 'provider': adapter.name, 'success': False}
                    tr.update(last_tr)
                    traces.append(tr)
                if last_tr.get('status_code') == 404:
                    # Break on 404 only for the first authoritative adapter of that category,
                    # and never before FRED's turn is reached.
                    has_pending_fred = any(a is fred_adapter or getattr(a, 'name', '').lower() == 'fred' for a in adapters[i + 1:])
                    if i == 0 and not has_pending_fred:
                        break
        except Exception as e:
            if traces is not None:
                traces.append({'source': adapter.name, 'provider': adapter.name, 'error': str(e), 'status': 'error'})
    return None
