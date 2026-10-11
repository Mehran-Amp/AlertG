import os
import json
import hashlib
import gzip
import re
from typing import Optional, List, Dict, Any
try:
    from fastapi import APIRouter, Query, HTTPException, Header, Response, Request
    from fastapi.responses import JSONResponse
    # If imported as MagicMock in test environment, fallback to concrete classes
    if not isinstance(Response, type) or getattr(Response, '_mock_name', None) is not None:
        raise ImportError("Response is a mock")
except (ImportError, AttributeError):
    class APIRouter:
        def __init__(self, *args, **kwargs): pass
        def get(self, *args, **kwargs): return lambda f: f
        def post(self, *args, **kwargs): return lambda f: f
    def Query(default=None, **kwargs): return default
    def Header(default=None, **kwargs): return default
    class HTTPException(Exception):
        def __init__(self, status_code=500, detail=""):
            self.status_code = status_code
            self.detail = detail
    class Response:
        def __init__(self, content=b"", status_code=200, headers=None, media_type=None):
            self.content = content if isinstance(content, bytes) else str(content).encode("utf-8")
            self.status_code = status_code
            self.headers = headers or {}
            self.media_type = media_type
    class JSONResponse(Response):
        def __init__(self, content=None, status_code=200, headers=None):
            body = json.dumps(content).encode("utf-8")
            super().__init__(content=body, status_code=status_code, headers=headers, media_type="application/json")
            self.json_data = content
from app.markets.global_stocks import WALLSTREET_MACRO_SYMBOLS
from app.engine.sync import load_catalog, get_catalog_delta
from app.engine.calendar import get_symbol_market_detail
from app.engine.checker import get_cached_price
from app.state import PRICE_CACHE
from app.security import API_DEP, ADMIN_DEP

router = APIRouter()

def normalize_search_query(text: Optional[str]) -> str:
    """Normalizes Persian/Arabic letters, diacritics, and zero-width non-joiners for search matching."""
    if not text:
        return ""
    t = str(text).strip().lower()
    t = re.sub(r'[\u200c\u200b\u200e\u200f]', '', t)
    t = t.replace('ي', 'ی').replace('ك', 'ک')
    t = t.replace('آ', 'ا').replace('أ', 'ا').replace('إ', 'ا')
    t = t.replace('ة', 'ه').replace('ؤ', 'و').replace('ئ', 'ی')
    t = re.sub(r'\s+', ' ', t)
    return t

def enrich_symbol(item: dict) -> dict:
    """Enriches symbol with single_source and is_delayed indicators."""
    s = dict(item)
    cat = (s.get("category") or "stock").lower()
    sym_id = (s.get("id") or s.get("symbol") or "").upper()

    if "single_source" not in s:
        # Multi-source: Treasuries with dual FRED & Yahoo feeds or major indices
        if cat == "bond" or sym_id in {"US10Y", "US05Y", "US13W", "US30Y", "US02Y"}:
            s["single_source"] = False
        else:
            s["single_source"] = True
    else:
        s["single_source"] = bool(s["single_source"])

    if "is_delayed" not in s:
        # US stocks, indices, macro observations have exchange delay on standard feeds
        if cat in {"stock", "index", "macro", "bond"}:
            s["is_delayed"] = True
        else:
            s["is_delayed"] = False
    else:
        s["is_delayed"] = bool(s["is_delayed"])

    return s

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

LEGACY_GOLDEN_SNAPSHOT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "snapshots", "golden_phase0.json"
)

def load_golden_legacy_wallstreet_macro() -> dict:
    """
    Returns the golden Phase 0 frozen snapshot for /api/symbols/wallstreet-macro.
    Strictly isolated so hundreds of newly added catalog symbols are NEVER dumped into this legacy endpoint.
    """
    if os.path.exists(LEGACY_GOLDEN_SNAPSHOT_PATH):
        try:
            with open(LEGACY_GOLDEN_SNAPSHOT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                ep = data.get("endpoints", {}).get("api_symbols_wallstreet_macro")
                if ep and isinstance(ep, dict):
                    return {
                        "status": "success",
                        "catalog_version": 1,
                        "last_sync_at": ep.get("last_sync_at", "2026-10-09T08:58:00Z"),
                        "market": ep.get("market", "Wall Street & Macroeconomics"),
                        "total_count": ep.get("total_count", len(ep.get("symbols", []))),
                        "total_symbols_in_db": ep.get("total_count", len(ep.get("symbols", []))),
                        "categories": ep.get("categories", {}),
                        "symbols": ep.get("symbols", [])
                    }
        except Exception:
            pass

    iran_symbols = load_iran_symbols()
    macro_active = [s for s in WALLSTREET_MACRO_SYMBOLS if s.get("category") != "iran_market"]
    combined_symbols = iran_symbols + macro_active
    return {
        "status": "success",
        "catalog_version": 1,
        "last_sync_at": "2026-10-09T08:58:00Z",
        "market": "Wall Street & Macroeconomics",
        "total_count": len(combined_symbols),
        "total_symbols_in_db": len(combined_symbols),
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

@router.get("/api/symbols", dependencies=API_DEP)
def get_symbols_catalog_filtered(
    symbol_class: Optional[str] = Query(None, alias="class"),
    category: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    cursor: Optional[int] = Query(0, ge=0),
    limit: Optional[int] = Query(50, ge=1, le=200),
    gzip_flag: Optional[bool] = Query(False, alias="gzip"),
    if_none_match: Optional[str] = Header(None, alias="If-None-Match")
):
    """
    Phase 9 (v3.6.0) /api/symbols:
    Comprehensive catalog endpoint with:
    - class / category filtering
    - Persian & English normalized full-text search in q
    - cursor & limit pagination
    - ETag / If-None-Match caching (returns 304 Not Modified)
    - gzip compression support
    - single_source and is_delayed indicators on each symbol
    """
    cat = load_catalog()
    cat_ver = cat.get("catalog_version", 1)
    last_sync = cat.get("last_sync_at")

    # Combine active global symbols + iran catalog symbols
    raw_symbols = [s for s in cat.get("symbols", []) if s.get("is_active", 1)]
    iran_symbols = [s for s in load_iran_symbols() if s.get("is_active", 1)]

    # Dedup by symbol id
    seen_ids = set()
    all_symbols = []
    for s in raw_symbols + iran_symbols:
        sid = s.get("id") or s.get("symbol")
        if sid and sid not in seen_ids:
            seen_ids.add(sid)
            all_symbols.append(enrich_symbol(s))

    # 1. Filter by class / category
    target_cls = (symbol_class or category or "").strip().lower()
    if target_cls:
        alias_map = {
            "stocks": "stock",
            "indices": "index",
            "commodities": "commodity",
            "bonds": "bond",
            "iran": "iran_market",
            "iran_domestic": "iran_market",
            "macros": "macro"
        }
        eff_cls = alias_map.get(target_cls, target_cls)
        all_symbols = [s for s in all_symbols if s.get("category", "").lower() == eff_cls]

    # 2. Filter by search query q (both Persian and English)
    clean_q = normalize_search_query(q)
    if clean_q:
        filtered = []
        for s in all_symbols:
            sym_text = normalize_search_query(s.get("symbol"))
            id_text = normalize_search_query(s.get("id"))
            en_text = normalize_search_query(s.get("nameEn") or s.get("name"))
            fa_text = normalize_search_query(s.get("nameFa") or s.get("name_fa"))
            mkt_text = normalize_search_query(s.get("marketName"))

            if (clean_q in sym_text or clean_q in id_text or
                clean_q in en_text or clean_q in fa_text or clean_q in mkt_text):
                filtered.append(s)
        all_symbols = filtered

    total_count = len(all_symbols)
    cur_offset = max(0, cursor or 0)
    page_limit = min(max(1, limit or 50), 200)

    page_items = all_symbols[cur_offset : cur_offset + page_limit]
    next_cursor = (cur_offset + page_limit) if (cur_offset + page_limit) < total_count else None
    has_more = next_cursor is not None

    payload = {
        "status": "success",
        "catalog_version": cat_ver,
        "last_sync_at": last_sync,
        "total_count": total_count,
        "count": len(page_items),
        "cursor": next_cursor,
        "has_more": has_more,
        "symbols": page_items
    }

    # Deterministic ETag calculation
    content_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    content_bytes = content_str.encode("utf-8")
    etag = f'"{hashlib.md5(content_bytes).hexdigest()}"'

    headers = {
        "ETag": etag,
        "Cache-Control": "public, max-age=60"
    }

    if if_none_match:
        req_etag = if_none_match.strip().lstrip("W/").strip('"')
        cur_etag = etag.strip('"')
        if req_etag == cur_etag:
            return Response(status_code=304, headers=headers)

    # Explicit gzip response handling
    if gzip_flag:
        compressed = gzip.compress(content_bytes)
        headers["Content-Encoding"] = "gzip"
        return Response(content=compressed, status_code=200, headers=headers, media_type="application/json")

    return JSONResponse(content=payload, status_code=200, headers=headers)


@router.get("/api/symbols/changes", dependencies=API_DEP)
def get_symbols_changes(
    since: Optional[str] = Query(None),
    if_none_match: Optional[str] = Header(None, alias="If-None-Match")
):
    """
    Phase 9 (v3.6.0) /api/symbols/changes:
    Delta sync changes endpoint supporting since=version or timestamp.
    Returns added, updated, and delisted symbols with delta flags.
    """
    since_version = None
    if since is not None and str(since).strip():
        s_val = str(since).strip()
        if s_val.isdigit():
            since_version = int(s_val)
        else:
            try:
                since_version = int(float(s_val))
            except Exception:
                since_version = None

    delta = get_catalog_delta(since_version=since_version)

    added = [enrich_symbol(s) for s in delta.get("added", [])]
    updated = [enrich_symbol(s) for s in delta.get("updated", [])]
    delisted = delta.get("delisted", [])

    payload = {
        "status": delta.get("status", "success"),
        "is_delta": delta.get("is_delta", True),
        "has_changes": delta.get("has_changes", False),
        "catalog_version": delta.get("catalog_version", 1),
        "since_version": since_version,
        "last_sync_at": delta.get("last_sync_at"),
        "total_count": delta.get("total_count", 0),
        "added": added,
        "updated": updated,
        "delisted": delisted
    }

    content_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    content_bytes = content_str.encode("utf-8")
    etag = f'"{hashlib.md5(content_bytes).hexdigest()}"'
    headers = {
        "ETag": etag,
        "Cache-Control": "public, max-age=60"
    }

    if if_none_match:
        req_etag = if_none_match.strip().lstrip("W/").strip('"')
        cur_etag = etag.strip('"')
        if req_etag == cur_etag:
            return Response(status_code=304, headers=headers)

    return JSONResponse(content=payload, status_code=200, headers=headers)


@router.get("/api/symbols/catalog", dependencies=API_DEP)
@router.get("/api/debug/symbols/catalog", dependencies=ADMIN_DEP)
def get_catalog_symbols(since_version: Optional[int] = Query(None)):
    cat = load_catalog()
    if isinstance(since_version, int) and since_version > 0:
        return get_catalog_delta(since_version)
    active_symbols = [s for s in cat.get("symbols", []) if s.get("is_active", 1)]
    return {
        "status": "success",
        "catalog_version": cat.get("catalog_version", 1),
        "last_sync_at": cat.get("last_sync_at"),
        "total_count": len(active_symbols),
        "symbols": active_symbols
    }

@router.get("/api/symbols/wallstreet-macro", dependencies=API_DEP)
@router.get("/api/debug/symbols/macro", dependencies=ADMIN_DEP)
def get_debug_wallstreet_macro_symbols(since_version: Optional[int] = Query(None)):
    """
    Legacy backward-compatible endpoint for older clients.
    Guaranteed to return the golden 94 symbols without contamination from 600+ new catalog items.
    """
    return load_golden_legacy_wallstreet_macro()


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
    enriched = enrich_symbol(found_item) if found_item else {}

    return {
        "status": "success",
        "symbol": sym_clean,
        "nameEn": name_en,
        "nameFa": name_fa,
        "unit": unit,
        "exchange": eff_exchange,
        "single_source": enriched.get("single_source", True),
        "is_delayed": enriched.get("is_delayed", False),
        "source": enriched.get("source", "Default"),
        "price": price_val if (price_val is not None and price_val > 0) else (found_item.get("price") if found_item else None),
        "asOf": as_of if (price_val is not None and price_val > 0) else None,
        "meta": meta or {},
        "market": market_meta
    }
