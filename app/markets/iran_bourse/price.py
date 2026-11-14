# -*- coding: utf-8 -*-
"""
Iranian Bourse — price path (IB-6).

fetch_bourse_price(symbol) -> (price | None, traces), same shape as fetch_price_with_trace.
Reads the snapshot first; on a miss/stale entry makes ONE rate-limited on-demand
/v1/quote/{id} call. Price is returned only when state == LIVE (Rial, no conversion);
STALE / NO_TRADE_TODAY / errors return None with the state in the trace, so nothing
downstream can mistake an old price for a live one. CLOSED and alert eligibility
arrive in IB-7/IB-8. Imports nothing from other markets except the shared limiter.
"""
import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

import app.config as config
from app.markets.iran_bourse.client import BourseError
from app.markets.iran_bourse.alert_rules import EXTRA_KEYS
from app.markets.iran_bourse.mapping import quote_to_price_result
from app.markets.iran_bourse.session import classify

SOURCE = "tsetmc-gateway"
# Real gateway data (3,248 instruments, 2026-11-14) has ids of 14-17 digits, so the plan's "15-18" was too tight.
MIN_ID_LEN = 12
MAX_ID_LEN = 20
PROVIDER_KEY = "iran_bourse"
_ondemand_lock = asyncio.Lock()


def _trace(ok: bool, latency_ms: float, *, error: Optional[str] = None,
           result: Optional[Dict[str, Any]] = None, cached: bool = False) -> Dict[str, Any]:
    t: Dict[str, Any] = {
        "source": SOURCE, "url": "", "status_code": 200 if ok or result else 0,
        "latency_ms": round(latency_ms, 2), "success": ok,
        "currency": "IRR", "cached_bulk": cached,
    }
    if result:
        t.update({"parsed_price": result["price"], "asOf": result["asOf"], "state": result["state"]})
        for k in EXTRA_KEYS:
            if k in result:
                t[k] = result[k]
    if error:
        t["error"] = error
    return t


def _finish(result: Dict[str, Any], t0: float, cached: bool) -> Tuple[Optional[float], List[Dict[str, Any]]]:
    from app.markets.iran_bourse.poller import get_poller
    state, eligible = classify(result, get_poller().store)
    result = {**result, "state": state}
    live = eligible and result["price"] is not None
    err = None if live else f"state={result['state']}"
    tr = _trace(live, (time.perf_counter() - t0) * 1000.0, error=err, result=result, cached=cached)
    tr["alert_eligible"] = bool(live)
    return (float(result["price"]) if live else None), [tr]


class NoQuote(Exception):
    """No usable quote: carries the gateway error (if any) and the state to report."""
    def __init__(self, message: str, state: str = "no_data", cause: Optional[BaseException] = None):
        super().__init__(message)
        self.state = state
        self.cause = cause


async def resolve_result(iid: str) -> Tuple[Dict[str, Any], bool]:
    """
    Mapped quote result for a valid instrument id: snapshot first, else ONE rate-limited
    on-demand /v1/quote. Returns (result, from_cache). Raises NoQuote. Shared by the price
    path and the quote route (which also wants CLOSED/STALE quotes, not only LIVE ones).
    """
    from app.markets.iran_bourse.poller import get_poller
    poller = get_poller()
    poller.touch([iid])           # keeps the id in the snapshot and the poller awake

    e = poller.store.get(iid)
    if e is not None and not e["stale"]:
        return quote_to_price_result(e["quote"], e["meta"]), True

    # miss or stale: one on-demand quote, serialized, rate-limited, never retried
    async with _ondemand_lock:
        e = poller.store.get(iid)
        if e is not None and not e["stale"]:
            return quote_to_price_result(e["quote"], e["meta"]), True
        from app.markets.limiter import acquire_provider_slot
        stale_result = (lambda: quote_to_price_result(e["quote"], {**e["meta"], "stale": True})) if e is not None else None
        if not await acquire_provider_slot(PROVIDER_KEY, wait=False):
            if stale_result:
                return stale_result(), True
            raise NoQuote("rate limited or provider disabled")
        try:
            quote, meta = await poller._get_client().quote(iid)
        except BourseError as ex:
            poller.store.record_error(f"{type(ex).__name__}: {ex}")
            if stale_result:
                return stale_result(), True
            raise NoQuote(f"{type(ex).__name__}: {ex}", cause=ex)
        poller.store.put(quote, meta)
        return quote_to_price_result(quote, meta), False


def valid_instrument_id(iid: str) -> bool:
    return iid.isascii() and iid.isdigit() and MIN_ID_LEN <= len(iid) <= MAX_ID_LEN


async def fetch_bourse_price(symbol: str) -> Tuple[Optional[float], List[Dict[str, Any]]]:
    t0 = time.perf_counter()

    def fail(msg: str, state: str = "no_data"):
        tr = _trace(False, (time.perf_counter() - t0) * 1000.0, error=msg)
        tr["state"] = state
        return None, [tr]

    if not getattr(config, "IRAN_BOURSE_ENABLED", False):
        return fail("Iranian Bourse is disabled (IRAN_BOURSE_ENABLED=false)", "disabled")
    iid = str(symbol or "").strip()
    if not valid_instrument_id(iid):
        return fail(f"invalid instrument id {iid!r} (must be a numeric string)")
    try:
        result, cached = await resolve_result(iid)
    except NoQuote as ex:
        return fail(str(ex), ex.state)
    return _finish(result, t0, cached)
