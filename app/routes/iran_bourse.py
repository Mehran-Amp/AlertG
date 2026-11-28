# -*- coding: utf-8 -*-
"""
AlertG — Iranian Bourse API (IB-9). Search, classification, quote, admin status.
Prices are Rial (decision D1). Instrument ids are digit strings (rule N6).
Everything here is behind IRAN_BOURSE_ENABLED and touches no other market.
"""
import collections
import time
from typing import Any, Deque, Dict, Optional, Tuple

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response

import app.config as config
from app.security import API_DEP, ADMIN_DEP
from app.markets.iran_bourse.board import GROUPS, MAX_LIMIT, DEFAULT_LIMIT, SORT_KEYS, get_board
from app.markets.iran_bourse.client import BourseError, BourseNotFound, BourseUnauthorized
from app.markets.iran_bourse.directory import DIRECTORY, normalize_query
from app.markets.iran_bourse.price import NoQuote, resolve_result, valid_instrument_id
from app.markets.iran_bourse.session import classify

router = APIRouter()

CATALOG_RATE_LIMIT_MAX = 12
CATALOG_RATE_LIMIT_WINDOW_SECONDS = 60.0
CATALOG_CACHE_CONTROL = "private, max-age=300"


class _CatalogRateLimiter:
    """Memory-bounded per-client sliding-window rate limiter for the large catalog endpoint."""

    def __init__(self, max_requests: int = CATALOG_RATE_LIMIT_MAX,
                 window_seconds: float = CATALOG_RATE_LIMIT_WINDOW_SECONDS,
                 max_keys: int = 4096):
        self.max_requests = max_requests
        self.window_seconds = float(window_seconds)
        self.max_keys = max_keys
        self._hits: Dict[str, Deque[float]] = {}

    def reset(self) -> None:
        self._hits.clear()

    def check(self, key: str, now: Optional[float] = None) -> Tuple[bool, int]:
        ts = time.monotonic() if now is None else float(now)
        window = float(getattr(config, "IRAN_BOURSE_CATALOG_RATE_WINDOW", self.window_seconds))
        limit = int(getattr(config, "IRAN_BOURSE_CATALOG_RATE_LIMIT", self.max_requests))
        if limit <= 0 or window <= 0:
            return True, 0
        cutoff = ts - window

        if len(self._hits) >= self.max_keys and key not in self._hits:
            stale_keys = [k for k, dq in self._hits.items() if not dq or dq[-1] <= cutoff]
            for sk in stale_keys:
                self._hits.pop(sk, None)
            if len(self._hits) >= self.max_keys:
                oldest = next(iter(self._hits))
                self._hits.pop(oldest, None)

        dq = self._hits.setdefault(key, collections.deque())
        while dq and dq[0] <= cutoff:
            dq.popleft()
        if len(dq) >= limit:
            retry_after = max(1, int(window - (ts - dq[0])) + 1)
            return False, retry_after
        dq.append(ts)
        return True, 0


_CATALOG_RATE_LIMITER = _CatalogRateLimiter()


def _client_key(request: Optional[Request]) -> str:
    if request is None:
        return "local"
    host = (request.client.host if request.client else "") or "unknown"
    if host in ("127.0.0.1", "::1"):
        xff = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        if xff:
            return xff[:64]
    return host[:64]


def _etag_matches(if_none_match: Optional[str], current_etag: str) -> bool:
    if not if_none_match:
        return False
    cur = current_etag.strip().strip('"')
    raw = if_none_match.strip()
    if raw == "*":
        return True
    for part in raw.split(",")[:16]:
        token = part.strip()
        if token.startswith("W/") or token.startswith("w/"):
            token = token[2:].strip()
        if token.strip('"') == cur:
            return True
    return False


def _enabled() -> None:
    if not getattr(config, "IRAN_BOURSE_ENABLED", False):
        raise HTTPException(status_code=503, detail="Iranian Bourse is not enabled on this server.")


def _unavailable(e: BaseException) -> HTTPException:
    return HTTPException(status_code=503,
                         detail=f"Iranian Bourse data source unavailable ({type(e).__name__}); try again shortly.")


@router.get("/api/iran-bourse/symbols", dependencies=API_DEP)
async def bourse_symbols(
    q: str = Query(..., min_length=1, max_length=64),
    market: str = Query("", max_length=32),
    board: str = Query("", max_length=32),
    type: str = Query("", max_length=32),
    sector: str = Query("", max_length=32),
    traded: Optional[bool] = None,
    limit: int = Query(20, ge=1),
) -> Dict[str, Any]:
    _enabled()
    if not normalize_query(q):
        raise HTTPException(status_code=400, detail="q must not be empty.")
    limit = min(limit, 50)
    try:
        rows, meta = await DIRECTORY.search(q, limit, market, board, type, sector, traded)
    except BourseError as e:
        raise _unavailable(e)
    return {"query": normalize_query(q), "count": len(rows), "limit": limit, "unit": "IRR",
            "stale": bool(meta.get("stale", False)), "items": rows}


@router.get("/api/iran-bourse/board", dependencies=API_DEP)
async def bourse_board(
    group: str = Query("", max_length=16),
    market: str = Query("", max_length=32),
    sector: str = Query("", max_length=32),
    type: str = Query("", max_length=32),
    traded: Optional[bool] = None,
    q: str = Query("", max_length=64),
    sort: str = Query("value", max_length=16),
    order: str = Query("", max_length=4),
    offset: int = Query(0, ge=0, le=100000),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> Dict[str, Any]:
    """Browse lists: every symbol with its last price, by category, sorted and paged (IB-16a).

    No group means everything except options/futures (group=derivatives shows those).
    Prices are the last traded price, also when the market is closed: `session` tells the app
    which one it is looking at (OPEN = live, CLOSED / STALE = last known price)."""
    _enabled()
    if group and group not in GROUPS:
        raise HTTPException(status_code=400, detail=f"group must be one of {', '.join(GROUPS)}.")
    if sort not in SORT_KEYS:
        raise HTTPException(status_code=400, detail=f"sort must be one of {', '.join(SORT_KEYS)}.")
    if order and order.lower() not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="order must be asc or desc.")
    board = get_board()
    try:
        await board.ensure_fresh()
    except BourseError as e:
        raise _unavailable(e)
    return board.query(group=group, market=market, sector=sector, type_code=type, traded=traded,
                       q=q, sort=sort, order=order, offset=offset, limit=limit)


@router.get("/api/iran-bourse/catalog", dependencies=API_DEP)
async def bourse_catalog(
    request: Request,
    if_none_match: Optional[str] = Header(None, alias="If-None-Match"),
    accept_encoding: Optional[str] = Header(None, alias="Accept-Encoding"),
) -> Response:
    """Full projected market catalog for on-device caching (ETag/304, gzip, rate-limited)."""
    _enabled()
    allowed, retry_after = _CATALOG_RATE_LIMITER.check(_client_key(request))
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many catalog requests; please retry shortly.",
            headers={"Retry-After": str(retry_after)},
        )

    board = get_board()
    try:
        await board.ensure_fresh()
    except BourseError as e:
        raise _unavailable(e)

    raw_bytes, gzip_bytes, etag = board.catalog_encoded()
    headers = {
        "ETag": etag,
        "Cache-Control": CATALOG_CACHE_CONTROL,
        "Vary": "Accept-Encoding",
    }
    if _etag_matches(if_none_match, etag):
        return Response(status_code=304, headers=headers)

    accepts_gzip = "gzip" in (accept_encoding or "").lower()
    if accepts_gzip:
        return Response(
            content=gzip_bytes,
            status_code=200,
            headers={**headers, "Content-Encoding": "gzip"},
            media_type="application/json",
        )
    return Response(
        content=raw_bytes,
        status_code=200,
        headers=headers,
        media_type="application/json",
    )


@router.get("/api/iran-bourse/classification", dependencies=API_DEP)
async def bourse_classification() -> Dict[str, Any]:
    _enabled()
    try:
        data, meta = await DIRECTORY.classification()
    except BourseError as e:
        raise _unavailable(e)
    return {"stale": bool(meta.get("stale", False)), "classification": data}


@router.get("/api/iran-bourse/quote/{instrument_id}", dependencies=API_DEP)
async def bourse_quote(instrument_id: str) -> Dict[str, Any]:
    _enabled()
    iid = (instrument_id or "").strip()
    if not valid_instrument_id(iid):
        raise HTTPException(status_code=400, detail="instrument_id must be a numeric string (12-20 digits).")
    try:
        result, cached = await resolve_result(iid)
    except NoQuote as e:
        if isinstance(e.cause, BourseNotFound):
            raise HTTPException(status_code=404, detail=f"Unknown Bourse instrument id {iid}.")
        raise _unavailable(e.cause or e)
    state, eligible = classify(result)
    out = {**result, "state": state, "alert_eligible": eligible, "unit": "IRR", "cached": cached}
    out["price"] = result["price"]            # shown even when CLOSED/STALE; the state says how to read it
    return out


@router.get("/api/iran-bourse/status", dependencies=ADMIN_DEP)
async def bourse_status(probe: bool = False) -> Dict[str, Any]:
    """Admin: poller / feed health. Makes NO gateway request unless probe=true (one /health call)."""
    from app.markets.iran_bourse import poller as pmod
    p = pmod.BOURSE_POLLER
    out: Dict[str, Any] = {
        "enabled": bool(getattr(config, "IRAN_BOURSE_ENABLED", False)),
        "gateway_url_set": bool(getattr(config, "IRAN_BOURSE_GATEWAY_URL", "")),
        "poll_seconds": getattr(config, "IRAN_BOURSE_POLL_SECONDS", None),
        "allowed_users": len(getattr(config, "IRAN_BOURSE_ALLOWED_USER_IDS", [])),
        "poller": None,
        "directory": {"entries": len(DIRECTORY.cache), "hits": DIRECTORY.hits, "misses": DIRECTORY.misses},
        "now": time.time(),
    }
    if p is not None:
        out["poller"] = {**p.store.stats(), "leader": p.is_leader, "running": p._running,
                         "requests_made": p.requests_made, "failures": p._failures,
                         "has_demand": p.has_demand()}
    vs = getattr(getattr(p, "_client", None), "version_state", None)
    if callable(vs):
        out["gateway_version"] = vs()
    if probe and out["enabled"]:
        try:
            from app.markets.iran_bourse.poller import get_poller
            out["gateway"] = await get_poller()._get_client().health()
        except BourseError as e:
            out["gateway"] = {"error": f"{type(e).__name__}: {e}"}
    return out
