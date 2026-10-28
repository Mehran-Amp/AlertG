# -*- coding: utf-8 -*-
"""
AlertG — Crypto Symbols API Router (Phase 1 Fix / Version 2).
Provides endpoints for cryptocurrency exchanges and dynamic symbol catalogs:
1. GET /api/crypto/exchanges:
   Lists supported exchanges reading from crypto_registry.py (Rule R5):
   id, name, display_name, category, market='spot', quote='USDT', total_pairs,
   last_updated_at, is_stale (flag + age > 12h), alert_capable.
2. GET /api/crypto/exchanges/{exchange}/symbols and GET /api/crypto/symbols/{exchange}:
   Retrieves symbols for a given exchange with:
   - Multi-tier search ranking: Exact match -> Prefix match (starts-with) -> Substring match (contains).
   - Filter leveraged tokens: include_leveraged=False by default (E1.2).
   - Pagination: limit and offset / cursor, strictly capped at MAX_PAGE_LIMIT (500).
   - Caching: deterministic ETag with 304 Not Modified support.
   - Gzip compression on demand (gzip=true).
   - Quote currency filtering (e.g. quote=USDT).
3. 404 with informative detail on unknown/unsupported exchange.
4. Standard API key authentication via API_DEP.
"""

import gzip
import hashlib
import json
import re
import time
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Query, HTTPException, Header, Response
from fastapi.responses import JSONResponse

from app.security import API_DEP
from app.markets.crypto_registry import (
    get_crypto_exchange,
    list_crypto_exchanges,
    get_supported_exchange_ids,
    is_supported_crypto_exchange,
)
from app.markets.crypto_catalog import (
    load_exchange_catalog,
    get_crypto_catalogs_status,
    DEFAULT_SYNC_HOURS,
)

router = APIRouter()

DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 500

# Backward compatibility mapping for callers/tests importing EXCHANGE_METADATA
EXCHANGE_METADATA = {
    meta.id: {
        "name": meta.name,
        "display_name": meta.name,
        "notes": meta.notes or "",
        "doc_url": meta.markets_url,
    }
    for meta in list_crypto_exchanges()
}


def normalize_search_query(text: Optional[str]) -> str:
    """Normalizes query string for case-insensitive and whitespace-trimmed search matching."""
    if not text:
        return ""
    t = str(text).strip().lower()
    t = re.sub(r'[\u200c\u200b\u200e\u200f]', '', t)
    t = re.sub(r'[\s/_\-]+', '', t)
    return t


def build_crypto_symbols_response(
    exchange_param: str,
    q: Optional[str] = None,
    limit: Optional[int] = DEFAULT_PAGE_LIMIT,
    offset: Optional[int] = 0,
    cursor: Optional[int] = None,
    quote: Optional[str] = None,
    include_leveraged: Optional[bool] = False,
    gzip_flag: Optional[bool] = False,
    if_none_match: Optional[str] = None,
    catalog_dir: Optional[str] = None,
) -> Response:
    """
    Core implementation of the symbols retrieval endpoint.
    Handles exchange validation from registry, leveraged token filtering,
    3-tier search ranking, pagination, and ETag/gzip generation.
    """
    ex_clean = (exchange_param or "").strip().lower()
    meta = get_crypto_exchange(ex_clean)
    active_ids = get_supported_exchange_ids(active_only=True)

    if not meta or meta.status != 'active':
        supported_str = ", ".join(active_ids)
        raise HTTPException(
            status_code=404,
            detail=f"Unknown or unsupported exchange '{exchange_param}'. Supported exchanges: {supported_str}"
        )

    canonical_id = meta.id
    catalog_data = load_exchange_catalog(canonical_id, override_dir=catalog_dir)

    raw_pairs = catalog_data.get("pairs", [])
    last_updated = catalog_data.get("updated_at")
    is_stale_flag = catalog_data.get("is_stale", False)
    error_msg = catalog_data.get("error")

    # Staleness by age check (Rule Task 11)
    is_stale_by_age = False
    now_ts = int(time.time())
    max_age_seconds = DEFAULT_SYNC_HOURS * 2 * 3600  # 12 hours
    if last_updated:
        try:
            if (now_ts - int(last_updated)) > max_age_seconds:
                is_stale_by_age = True
        except (ValueError, TypeError):
            is_stale_by_age = True

    is_stale = is_stale_flag or is_stale_by_age
    if is_stale_by_age and not error_msg:
        error_msg = "Catalog data is stale by age (> 12h)"

    # 1. Leveraged / ETF tokens filtering (Default: False per Owner Decision E1.2)
    if not include_leveraged:
        raw_pairs = [p for p in raw_pairs if not (p.get("is_leveraged") or p.get("is_etf"))]

    # 2. Quote currency filtering if requested
    if quote:
        clean_quote = quote.strip().upper()
        raw_pairs = [p for p in raw_pairs if (p.get("quote") or "").upper() == clean_quote]

    # 3. Search & 3-tier ranking (Exact -> Starts-with -> Contains)
    clean_q = normalize_search_query(q)
    if not clean_q:
        matched_pairs = list(raw_pairs)
    else:
        exact_matches = []
        prefix_matches = []
        substring_matches = []

        for p in raw_pairs:
            base_norm = normalize_search_query(p.get("base"))
            native_norm = normalize_search_query(p.get("native_symbol"))
            sym_norm = normalize_search_query(f"{p.get('base')}{p.get('quote')}")

            # Tier 1: Exact match on base symbol or native pair or combined symbol
            if base_norm == clean_q or native_norm == clean_q or sym_norm == clean_q:
                exact_matches.append(p)
            # Tier 2: Prefix match (starts with query)
            elif base_norm.startswith(clean_q) or native_norm.startswith(clean_q) or sym_norm.startswith(clean_q):
                prefix_matches.append(p)
            # Tier 3: Substring match (contains query anywhere)
            elif clean_q in base_norm or clean_q in native_norm or clean_q in sym_norm:
                substring_matches.append(p)

        exact_matches.sort(key=lambda x: (x.get("base", ""), x.get("quote", "")))
        prefix_matches.sort(key=lambda x: (x.get("base", ""), x.get("quote", "")))
        substring_matches.sort(key=lambda x: (x.get("base", ""), x.get("quote", "")))

        matched_pairs = exact_matches + prefix_matches + substring_matches

    # 4. Pagination & limit enforcement (Max limit 500)
    total_count = len(matched_pairs)
    effective_limit = min(max(1, limit or DEFAULT_PAGE_LIMIT), MAX_PAGE_LIMIT)
    cur_offset = cursor if cursor is not None else (offset or 0)
    cur_offset = max(0, cur_offset)

    page_items = matched_pairs[cur_offset : cur_offset + effective_limit]
    next_cursor = (cur_offset + effective_limit) if (cur_offset + effective_limit) < total_count else None
    has_more = next_cursor is not None

    payload = {
        "status": "success",
        "exchange": canonical_id,
        "exchange_id": canonical_id,
        "display_name": meta.name,
        "market": "spot",
        "quote": "USDT",
        "last_updated_at": last_updated,
        "is_stale": is_stale,
        "error": error_msg,
        "total_count": total_count,
        "count": len(page_items),
        "offset": cur_offset,
        "limit": effective_limit,
        "cursor": next_cursor,
        "has_more": has_more,
        "symbols": page_items,
    }

    # 5. Deterministic ETag calculation
    content_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    content_bytes = content_str.encode("utf-8")
    etag = f'"{hashlib.md5(content_bytes).hexdigest()}"'

    headers = {
        "ETag": etag,
        "Cache-Control": "private, max-age=60"
    }

    if if_none_match:
        req_etag = if_none_match.strip().lstrip("W/").strip('"')
        cur_etag = etag.strip('"')
        if req_etag == cur_etag:
            return Response(status_code=304, headers=headers)

    # 6. Gzip compression handling
    if gzip_flag:
        compressed = gzip.compress(content_bytes)
        headers["Content-Encoding"] = "gzip"
        return Response(content=compressed, status_code=200, headers=headers, media_type="application/json")

    return JSONResponse(content=payload, status_code=200, headers=headers)


@router.get("/api/crypto/exchanges", dependencies=API_DEP)
def get_crypto_exchanges(
    catalog_dir: Optional[str] = None,
    include_pending: Optional[bool] = Query(False, alias="include_pending")
):
    """
    Returns list of crypto exchanges from crypto_registry.py with health and pair counts.
    By default returns active exchanges capable of live alerts.
    """
    statuses = get_crypto_catalogs_status(override_dir=catalog_dir)
    exchanges_status = statuses.get("exchanges", {})

    items = []
    exchanges_to_list = list_crypto_exchanges() if include_pending else list_crypto_exchanges(status="active")
    for meta in exchanges_to_list:
        ex_id = meta.id
        stat = exchanges_status.get(ex_id, {})
        items.append({
            "id": ex_id,
            "exchange_id": ex_id,
            "name": meta.name,
            "display_name": meta.name,
            "category": meta.category,
            "market": "spot",
            "quote": "USDT",
            "total_pairs": stat.get("total_pairs", 0),
            "last_updated_at": stat.get("updated_at"),
            "is_stale": stat.get("is_stale", False),
            "alert_capable": (meta.status == "active"),
            "status": meta.status,
            "error": stat.get("error"),
        })

    payload = {
        "status": "success",
        "total": len(items),
        "total_exchanges": len(items),
        "exchanges": items,
    }

    content_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    etag = f'"{hashlib.md5(content_str.encode("utf-8")).hexdigest()}"'
    headers = {
        "ETag": etag,
        "Cache-Control": "private, max-age=60"
    }
    return JSONResponse(content=payload, status_code=200, headers=headers)


@router.get("/api/crypto/exchanges/{exchange}/symbols", dependencies=API_DEP)
@router.get("/api/crypto/symbols/{exchange}", dependencies=API_DEP)
def get_crypto_symbols_by_path(
    exchange: str,
    q: Optional[str] = Query(None),
    limit: Optional[int] = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: Optional[int] = Query(0, ge=0),
    cursor: Optional[int] = Query(None, ge=0),
    quote: Optional[str] = Query(None),
    include_leveraged: Optional[bool] = Query(False, alias="include_leveraged"),
    gzip_flag: Optional[bool] = Query(False, alias="gzip"),
    if_none_match: Optional[str] = Header(None, alias="If-None-Match"),
):
    """
    Returns symbol catalog for a specific crypto exchange via path parameter.
    """
    return build_crypto_symbols_response(
        exchange_param=exchange,
        q=q,
        limit=limit,
        offset=offset,
        cursor=cursor,
        quote=quote,
        include_leveraged=include_leveraged,
        gzip_flag=gzip_flag,
        if_none_match=if_none_match,
    )


@router.get("/api/crypto/symbols", dependencies=API_DEP)
def get_crypto_symbols_by_query(
    exchange: str = Query(..., description="Exchange identifier (e.g. binance, mexc, etc.)"),
    q: Optional[str] = Query(None),
    limit: Optional[int] = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: Optional[int] = Query(0, ge=0),
    cursor: Optional[int] = Query(None, ge=0),
    quote: Optional[str] = Query(None),
    include_leveraged: Optional[bool] = Query(False, alias="include_leveraged"),
    gzip_flag: Optional[bool] = Query(False, alias="gzip"),
    if_none_match: Optional[str] = Header(None, alias="If-None-Match"),
):
    """
    Returns symbol catalog for a specific crypto exchange via query parameter.
    """
    return build_crypto_symbols_response(
        exchange_param=exchange,
        q=q,
        limit=limit,
        offset=offset,
        cursor=cursor,
        quote=quote,
        include_leveraged=include_leveraged,
        gzip_flag=gzip_flag,
        if_none_match=if_none_match,
    )
