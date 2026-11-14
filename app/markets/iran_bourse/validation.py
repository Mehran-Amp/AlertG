# -*- coding: utf-8 -*-
"""
Iranian Bourse — alert creation rules (IB-9). Used by the alert routes only for exchange 'tsetmc'.

An alert needs: feature enabled, user allowed (if a rollout list is set), a digit-only
instrument id that exists in the gateway, a supported alert type, price_field last/close.
The ticker is stored in market_symbol. Percent / absolute alerts get the daily base
(yesterday) filled in so the shared alert filter picks them up.
"""
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException

import app.config as config
from app.markets.iran_bourse.client import BourseError
from app.markets.iran_bourse.directory import DIRECTORY
from app.markets.iran_bourse.price import valid_instrument_id

BOURSE = "tsetmc"
SUPPORTED_TYPES = ("priceThreshold", "percentChange", "absolutePriceChange")


class BourseAlertError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _get(obj: Any, name: str, default=None):
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def _set(obj: Any, name: str, value) -> None:
    if isinstance(obj, dict):
        obj[name] = value
    else:
        setattr(obj, name, value)


async def check_bourse_alert(alert: Any) -> None:
    """Validate + normalize one alert (model or dict). Raises BourseAlertError."""
    if not getattr(config, "IRAN_BOURSE_ENABLED", False):
        raise BourseAlertError(503, "Iranian Bourse alerts are not enabled on this server.")
    allowed = getattr(config, "IRAN_BOURSE_ALLOWED_USER_IDS", [])
    uid = str(_get(alert, "user_id", "") or "").strip()
    if allowed and uid not in allowed:
        raise BourseAlertError(403, "Iranian Bourse alerts are not available for this user yet.")

    iid = str(_get(alert, "symbol", "") or "").strip()
    if not valid_instrument_id(iid):
        raise BourseAlertError(400, "Bourse alerts need the numeric instrument id, not a ticker or name.")

    ctype = _get(alert, "condition_type") or "priceThreshold"
    if ctype not in SUPPORTED_TYPES:
        raise BourseAlertError(400, f"Alert type '{ctype}' is not supported for the Bourse "
                                    f"(use {', '.join(SUPPORTED_TYPES)}).")
    if (_get(alert, "alert_nature") or "price") != "price":
        raise BourseAlertError(400, "Bourse supports price alerts only.")
    raw = _get(alert, "raw_rule")
    if raw is not None and not isinstance(raw, dict):
        raise BourseAlertError(400, "raw_rule must be an object.")
    if (raw or {}).get("price_field", "last") not in ("last", "close"):
        raise BourseAlertError(400, "raw_rule.price_field must be 'last' or 'close'.")

    try:
        info = await DIRECTORY.lookup(iid)
    except BourseError as e:
        raise BourseAlertError(503, f"Iranian Bourse gateway unavailable ({type(e).__name__}); try again shortly.")
    if info is None:
        raise BourseAlertError(400, f"Unknown Bourse instrument id {iid}.")

    _set(alert, "market_symbol", info.get("ticker") or None)
    yesterday = info.get("yesterday")
    if ctype in ("percentChange", "absolutePriceChange"):
        if not isinstance(yesterday, (int, float)) or yesterday <= 0:
            raise BourseAlertError(400, "This instrument has no previous close yet; use a price-level alert.")
        _set(alert, "base_price", float(yesterday))
        if ctype == "absolutePriceChange":
            delta = _get(alert, "delta_absolute")
            if not isinstance(delta, (int, float)) or delta <= 0:
                raise BourseAlertError(400, "delta_absolute must be a positive number.")
            _set(alert, "percent", float(delta) / float(yesterday) * 100.0)
        else:
            pct = _get(alert, "percent")
            if not isinstance(pct, (int, float)) or pct <= 0:
                raise BourseAlertError(400, "percent must be a positive number.")


async def validate_bourse_alert(alert: Any) -> None:
    """HTTP wrapper for POST /api/alerts."""
    try:
        await check_bourse_alert(alert)
    except BourseAlertError as e:
        raise HTTPException(status_code=e.status, detail=e.message)


async def prevalidate_sync_items(items: List[Dict[str, Any]], user_id: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    For /api/alerts/sync: validate only NEW or CHANGED tsetmc items. Alerts already on the server
    pass through untouched (like crypto). An invalid item is dropped with a warning, so the user's
    other alerts still sync.
    """
    import app.storage as storage
    from app.routes.alerts import _trigger_signature
    existing = {a.id: a for a in storage.ALERTS_DB if a.user_id == user_id}
    kept: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    for item in items:
        if str(item.get("exchange") or "").strip().lower() != BOURSE:
            kept.append(item)
            continue
        old = existing.get(item.get("id"))
        if old is not None and _trigger_signature(old) == _trigger_signature(item):
            kept.append(item)
            continue
        try:
            await check_bourse_alert(item)
            kept.append(item)
        except BourseAlertError as e:
            warnings.append({"id": item.get("id"), "exchange": BOURSE, "symbol": item.get("symbol"),
                             "error_code": f"BOURSE_{e.status}", "error": e.message})
    return kept, warnings
