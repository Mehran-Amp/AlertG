# -*- coding: utf-8 -*-
"""
AlertG — Iranian Bourse API (IB-9). Search, classification, quote, admin status.
Prices are Rial (decision D1). Instrument ids are digit strings (rule N6).
Everything here is behind IRAN_BOURSE_ENABLED and touches no other market.
"""
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

import app.config as config
from app.security import API_DEP, ADMIN_DEP
from app.markets.iran_bourse.client import BourseError, BourseNotFound, BourseUnauthorized
from app.markets.iran_bourse.directory import DIRECTORY, normalize_query
from app.markets.iran_bourse.price import NoQuote, resolve_result, valid_instrument_id
from app.markets.iran_bourse.session import classify

router = APIRouter()


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
        raise HTTPException(status_code=400, detail="instrument_id must be a 15-18 digit string.")
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
    if probe and out["enabled"]:
        try:
            from app.markets.iran_bourse.poller import get_poller
            out["gateway"] = await get_poller()._get_client().health()
        except BourseError as e:
            out["gateway"] = {"error": f"{type(e).__name__}: {e}"}
    return out
