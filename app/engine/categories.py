from typing import Dict, Any, Optional

# Category-specific Cache TTL configuration (Seconds)
# 1. Forex: 20s
# 2. Stocks / Indices / Commodities: 30s
# 3. Macro / Bonds / Yields: 60s
# 4. Crypto: 2.0s (Real-time volatile)
# 5. Iran Market: 60.0s (Strict domestic policy)
CATEGORY_CACHE_TTL: Dict[str, float] = {
    'forex': 20.0,
    'stock': 30.0,
    'index': 30.0,
    'commodity': 30.0,
    'macro': 60.0,
    'bond': 60.0,
    'iran_market': 60.0,
    'crypto': 2.0,
    'default': 2.0
}

# Category-specific Outlier Protection Jump Thresholds:
# Any single-tick leap exceeding this percentage requires 3 consecutive confirmations.
# 1. Forex: 5%
# 2. Index: 10%
# 3. Commodity: 15%
# 4. Stock: 25%
# 5. Crypto & Iran Market: 50% (Default)
CATEGORY_OUTLIER_THRESHOLDS: Dict[str, float] = {
    'forex': 0.05,
    'index': 0.10,
    'commodity': 0.15,
    'stock': 0.25,
    'macro': 0.20,
    'bond': 0.15,
    'crypto': 0.50,
    'iran_market': 0.50,
    'default': 0.50
}

import os
import json
import app.config as config

_CATALOG_CACHE: Dict[str, str] = {}
_CATALOG_MTIME: float = 0.0
_CATALOG_PATH_LOADED: str = ""

def _get_catalog_categories() -> Dict[str, str]:
    global _CATALOG_CACHE, _CATALOG_MTIME, _CATALOG_PATH_LOADED
    cat_file = getattr(config, "CATALOG_FILE", "catalog.json")
    if not cat_file or not os.path.exists(cat_file):
        candidates = ["catalog.json", "/catalog.json", os.path.join(getattr(config, "DATA_DIR", "."), "catalog.json")]
        for c in candidates:
            if os.path.exists(c):
                cat_file = c
                break
    if not cat_file or not os.path.exists(cat_file):
        return _CATALOG_CACHE
    try:
        mtime = os.path.getmtime(cat_file)
        if mtime != _CATALOG_MTIME or cat_file != _CATALOG_PATH_LOADED:
            with open(cat_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                symbols = data.get("symbols", []) if isinstance(data, dict) else []
                new_map = {}
                for s in symbols:
                    s_id = s.get("id")
                    s_cat = s.get("category")
                    if s_id and s_cat:
                        new_map[str(s_id).upper().strip()] = str(s_cat).lower().strip()
                _CATALOG_CACHE = new_map
                _CATALOG_MTIME = mtime
                _CATALOG_PATH_LOADED = cat_file
    except Exception:
        pass
    return _CATALOG_CACHE

def resolve_symbol_category(exchange: str, symbol: Optional[str] = None) -> str:
    """
    Identifies the financial category of an exchange:symbol pair
    to apply category-tailored Cache TTL and Outlier Thresholds.
    Can also be called with single argument: resolve_symbol_category(symbol).
    """
    if symbol is None:
        symbol = exchange
        exchange = 'global_stocks'
    ex = (exchange or '').lower().strip()
    sym = (symbol or '').upper().strip()

    if ex in ['tabdeal', 'nobitex', 'wallex', 'bitpin', 'tetherland', 'abantether', 'ramzinex', 'bitbarg', 'sarmayex', 'exir', 'iran_market', 'bonbast', 'bridge', 'tse']:
        return 'iran_market'
    if sym.endswith('TMN') or sym.endswith('IRT') or sym.endswith('RLS') or sym.startswith('USDT_') or sym.startswith('GOLD_'):
        return 'iran_market'

    # 1. First read catalog.json (id -> category):
    # UNRATE, CPIAUCSL, FEDFUNDS, WALCL, M2SL and all macro series in catalog must return 'macro', not 'stock'.
    cat_map = _get_catalog_categories()
    if sym in cat_map:
        cat = cat_map[sym]
        if cat == 'macro':
            return 'macro'
        if sym in ['US10Y', '^TNX', 'TNX', 'US02Y', '^IRX', 'US2Y', '^2YY', 'US30Y', '^TYX']:
            return 'macro'
        if cat in CATEGORY_CACHE_TTL:
            return cat

    # Global Stocks / Forex / Macro
    from app.markets.global_stocks import FOREX_PAIRS, EXACT_YF_MAP, WALLSTREET_MACRO_SYMBOLS

    sym_clean = sym.replace('/', '').replace(' ', '').replace('-', '').replace('_', '')
    if sym_clean in FOREX_PAIRS or ex == 'forex' or (sym.endswith('=X') and not sym.startswith('^')):
        return 'forex'

    if sym in ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'NZDUSD', 'EURGBP', 'EURJPY', 'GBPJPY']:
        return 'forex'

    if sym in ['SPX', 'SP500', '^GSPC', 'NDX', 'NASDAQ', '^NDX', 'DJI', 'DOWJONES', '^DJI', 'RUT', '^RUT', 'DAX', '^GDAXI', 'FTSE', '^FTSE', 'CAC40', '^FCHI', 'NIKKEI', '^N225', 'NIFTY', '^NSEI', 'KOSPI', '^KS11', 'VIX', '^VIX']:
        return 'index'

    if sym in ['GOLD', 'XAU', 'XAUUSD', 'GC=F', 'SILVER', 'XAG', 'XAGUSD', 'SI=F', 'BRENT', 'OILBRENT', 'BZ=F', 'WTI', 'OILWTI', 'CL=F', 'NATGAS', 'NG=F', 'COPPER', 'HG=F', 'PLATINUM', 'PL=F']:
        return 'commodity'

    if sym in ['DXY', 'DX-Y.NYB', 'USDX', 'US10Y', '^TNX', 'TNX', 'US02Y', '^IRX', 'US2Y', '^2YY', 'US30Y', '^TYX', 'BTC.D', 'USDT.D', 'ETH.D', 'TOTAL', 'TOTAL2', 'TOTAL3']:
        return 'macro'

    # Catalog lookup if in WALLSTREET_MACRO_SYMBOLS
    for item in WALLSTREET_MACRO_SYMBOLS:
        if item.get('id') == sym or item.get('symbol') == sym or item.get('symbol') == symbol:
            cat = item.get('category')
            if cat in CATEGORY_CACHE_TTL:
                return cat

    if ex in ['stocks', 'global_stocks', 'wallstreet']:
        return 'stock'

    return 'crypto'

def get_category_cache_ttl(category: str) -> float:
    return CATEGORY_CACHE_TTL.get(category, CATEGORY_CACHE_TTL['default'])

def get_category_outlier_threshold(category: str) -> float:
    return CATEGORY_OUTLIER_THRESHOLDS.get(category, CATEGORY_OUTLIER_THRESHOLDS['default'])
