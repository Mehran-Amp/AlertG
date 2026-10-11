import os
import json
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException
from app.markets.global_stocks import WALLSTREET_MACRO_SYMBOLS
from app.engine.sync import load_catalog, get_catalog_delta
from app.engine.calendar import get_symbol_market_detail
from app.engine.checker import get_cached_price
from app.state import PRICE_CACHE
from app.security import API_DEP, ADMIN_DEP

router = APIRouter()

IRAN_CATALOG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "iran_catalog.json"
)

def load_iran_symbols() -> List[dict]:
    """Loads isolated Iran domestic market symbols from dedicated iran_catalog.json."""
    if os.path.exists(IRAN_CATALOG_FILE):
        try:
            with open(IRAN_CATALOG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("symbols", [])
        except Exception:
            pass
    return [s for s in WALLSTREET_MACRO_SYMBOLS if s.get("category") == "iran_market"]

@router.get("/api/symbols/global", dependencies=API_DEP)
def get_global_catalog_symbols(since_version: Optional[int] = Query(None)):
    """Returns pure global assets catalog (stocks, ETFs, forex, indices, commodities, bonds, macro)."""
    cat = load_catalog()
    if since_version is not None and since_version > 0:
        return get_catalog_delta(since_version)
    active_symbols = [s for s in cat.get("symbols", []) if s.get("is_active", 1)]
    return {
        "status": "success",
        "catalog_version": cat.get("catalog_version", 1),
        "last_sync_at": cat.get("last_sync_at"),
        "market": "Global Markets",
        "total_count": len(active_symbols),
        "symbols": active_symbols
    }

@router.get("/api/symbols/catalog", dependencies=API_DEP)
@router.get("/api/symbols/wallstreet-macro", dependencies=API_DEP)
@router.get("/api/debug/symbols/macro", dependencies=ADMIN_DEP)
def get_debug_wallstreet_macro_symbols(since_version: Optional[int] = Query(None)):
    cat = load_catalog()
    if isinstance(since_version, int) and since_version > 0:
        return get_catalog_delta(since_version)

    active_symbols = [s for s in cat.get("symbols", []) if s.get("is_active", 1)]
    iran_symbols = load_iran_symbols()
    combined_symbols = iran_symbols + active_symbols

    return {
        "status": "success",
        "catalog_version": cat.get("catalog_version", 1),
        "last_sync_at": cat.get("last_sync_at"),
        "market": "Wall Street & Macroeconomics",
        "total_count": len(combined_symbols),
        "total_symbols_in_db": len(iran_symbols) + len(cat.get("symbols", [])),
        "categories": {
            "stock": len([s for s in combined_symbols if s.get("category") == "stock"]),
            "forex": len([s for s in combined_symbols if s.get("category") == "forex"]),
            "bond": len([s for s in combined_symbols if s.get("category") == "bond"]),
            "commodity": len([s for s in combined_symbols if s.get("category") == "commodity"]),
            "index": len([s for s in combined_symbols if s.get("category") == "index"]),
            "iran_market": len([s for s in combined_symbols if s.get("category") == "iran_market"]),
            "macro": len([s for s in combined_symbols if s.get("category") == "macro"])
        },
        "symbols": combined_symbols
    }


@router.get("/api/symbols/detail", dependencies=API_DEP)
@router.get("/api/symbols/{symbol}/detail", dependencies=API_DEP)
def get_symbol_detail(symbol: Optional[str] = None, exchange: Optional[str] = "global_stocks"):
    """
    Returns rich symbol details including market status, opening hours, schedule,
    source label and delay tag for symbol detail page and watchlists.
    """
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol parameter is required")

    sym_clean = symbol.strip().upper()
    cat = load_catalog()
    found_item = None
    for s in cat.get("symbols", []):
        if (s.get("symbol") or "").upper() == sym_clean or (s.get("id") or "").upper() == sym_clean:
            found_item = s
            break

    # Resolve exchange and category
    eff_exchange = exchange or "global_stocks"
    market_meta = get_symbol_market_detail(eff_exchange, sym_clean)

    # Get cached price if available from PRICE_CACHE
    cache_key = f"{eff_exchange.lower()}:{sym_clean.lower()}"
    cached_entry = PRICE_CACHE.get(cache_key) or PRICE_CACHE.get(f"global_stocks:{sym_clean.lower()}")
    price_val = None
    as_of = None
    meta = {}
    if cached_entry and len(cached_entry) >= 2:
        price_val = cached_entry[0]
        as_of = cached_entry[1]
        if len(cached_entry) > 2 and isinstance(cached_entry[2], dict):
            meta = cached_entry[2]

    name_en = found_item.get("nameEn") if found_item else sym_clean
    name_fa = found_item.get("nameFa") if found_item else sym_clean
    unit = found_item.get("unit", "$") if found_item else "$"

    return {
        "status": "success",
        "symbol": sym_clean,
        "nameEn": name_en,
        "nameFa": name_fa,
        "unit": unit,
        "exchange": eff_exchange,
        "price": price_val if (price_val is not None and price_val > 0) else (found_item.get("price") if found_item else None),
        "asOf": as_of if (price_val is not None and price_val > 0) else None,
        "meta": meta or {},
        "market": market_meta
    }
