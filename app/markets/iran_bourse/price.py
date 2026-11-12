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
from app.markets.iran_bourse.mapping import quote_to_price_result

SOURCE = "tsetmc-gateway"
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
    if error:
        t["error"] = error
    return t


def _finish(result: Dict[str, Any], t0: float, cached: bool) -> Tuple[Optional[float], List[Dict[str, Any]]]:
    live = result["state"] == "LIVE" and result["price"] is not None
    err = None if live else f"state={result['state']}"
    tr = _trace(live, (time.perf_counter() - t0) * 1000.0, error=err, result=result, cached=cached)
    return (float(result["price"]) if live else None), [tr]


async def fetch_bourse_price(symbol: str) -> Tuple[Optional[float], List[Dict[str, Any]]]:
    t0 = time.perf_counter()

    def fail(msg: str, state: str = "no_data"):
        tr = _trace(False, (time.perf_counter() - t0) * 1000.0, error=msg)
        tr["state"] = state
        return None, [tr]

    if not getattr(config, "IRAN_BOURSE_ENABLED", False):
        return fail("Iranian Bourse is disabled (IRAN_BOURSE_ENABLED=false)", "disabled")
    iid = str(symbol or "").strip()
    if not (iid.isdigit() and 15 <= len(iid) <= 18):
        return fail(f"invalid instrument id {iid!r} (must be a 15-18 digit string)")

    from app.markets.iran_bourse.poller import get_poller
    poller = get_poller()
    poller.touch([iid])           # keeps the id in the snapshot and the poller awake

    def from_snapshot():
        e = poller.store.get(iid)
        return e

    e = from_snapshot()
    if e is not None and not e["stale"]:
        return _finish(quote_to_price_result(e["quote"], e["meta"]), t0, True)

    # miss or stale: one on-demand quote, serialized, rate-limited, never retried
    async with _ondemand_lock:
        e = from_snapshot()
        if e is not None and not e["stale"]:
            return _finish(quote_to_price_result(e["quote"], e["meta"]), t0, True)
        from app.markets.limiter import acquire_provider_slot
        if not await acquire_provider_slot(PROVIDER_KEY, wait=False):
            if e is not None:
                return _finish(quote_to_price_result(e["quote"], {**e["meta"], "stale": True}), t0, True)
            return fail("rate limited or provider disabled", "no_data")
        try:
            quote, meta = await poller._get_client().quote(iid)
        except BourseError as ex:
            poller.store.record_error(f"{type(ex).__name__}: {ex}")
            if e is not None:
                return _finish(quote_to_price_result(e["quote"], {**e["meta"], "stale": True}), t0, True)
            return fail(f"{type(ex).__name__}: {ex}")
        poller.store.put(quote, meta)
        return _finish(quote_to_price_result(quote, meta), t0, False)
