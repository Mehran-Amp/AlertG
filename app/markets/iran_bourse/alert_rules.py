# -*- coding: utf-8 -*-
"""
Iranian Bourse — alert semantics (IB-8). Pure helpers, no I/O, nothing from other markets.

* price_field: raw_rule.price_field is 'last' (default) or 'close'.
* percent change: the daily base is the instrument's `yesterday` (prev_close), re-read every
  evaluation. absolutePriceChange is turned into the same percent rule (delta / yesterday).
* outlier filter: a price inside the instrument's own [lower_limit, upper_limit] is never held back.
* asOf (set in price.py/mapping.py) is the gateway fetch time; last_trade_time is a separate field.
"""
import math
from typing import Any, Dict, Optional, Tuple

EXTRA_KEYS = (
    "last_trade_time", "prev_close", "close", "lower_limit", "upper_limit",
    "change_pct", "ticker", "name", "alert_eligible",
    "queue", "best_bid", "best_ask", "volume", "traded_today",
)

BOURSE_SPECIAL_TYPES = ("queueBuy", "queueSell", "volumeAbove")
_BLOCKED_STATES = frozenset({
    "CLOSED", "STALE", "NO_TRADE_TODAY", "CARRIED_OVER",
    "closed", "no_trade_today", "no_data",
})


def meta_extras(trace: Dict[str, Any]) -> Dict[str, Any]:
    """Bourse-specific keys copied from a price trace into the cached price meta."""
    return {k: trace[k] for k in EXTRA_KEYS if k in trace}


def within_limits(price: float, traces) -> bool:
    """True if `price` lies inside the instrument's own daily limits (limits known and valid)."""
    for tr in traces or []:
        lo, hi = tr.get("lower_limit"), tr.get("upper_limit")
        if tr.get("success") and isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and 0 < lo <= hi:
            return lo <= price <= hi
    return False


def _pos(x: Any) -> Optional[float]:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    f = float(x)
    return f if math.isfinite(f) and f > 0 else None


def _is_live_traded(meta: Optional[Dict[str, Any]]) -> bool:
    """True only when the Bourse quote is live, eligible, and traded today."""
    if not isinstance(meta, dict):
        return False
    if meta.get("alert_eligible") is False:
        return False
    if meta.get("is_stale") is True or meta.get("carried_over") is True:
        return False
    if meta.get("state") in _BLOCKED_STATES:
        return False
    if meta.get("traded_today") is not True:
        return False
    return True


def is_bourse_special_alert(alert: Any) -> bool:
    """True for Iranian-market alerts evaluated via order-book/volume rules."""
    ex = str(getattr(alert, "exchange", "") or "").strip().lower()
    ctype = getattr(alert, "condition_type", None) or ""
    return ex == "tsetmc" and ctype in BOURSE_SPECIAL_TYPES


def min_queue_volume_of(alert: Any) -> Optional[float]:
    """Optional minimum queue volume (shares) from alert.raw_rule.min_queue_volume."""
    raw = getattr(alert, "raw_rule", None)
    if not isinstance(raw, dict):
        return None
    return _pos(raw.get("min_queue_volume"))


def is_buy_queue(meta: Optional[Dict[str, Any]], min_queue_volume: Optional[float] = None) -> bool:
    """True when the instrument is locked in a live buy queue at today's upper limit.

    Real TSETMC captures (e.g. خگلپا, زبینا) may show an unfillable `best_ask` above
    `upper_limit`; any ask at or below `upper_limit` (e.g. معیار) disqualifies a buy queue.
    """
    if not _is_live_traded(meta):
        return False
    assert meta is not None
    if meta.get("queue") == "sell":
        return False

    upper = _pos(meta.get("upper_limit"))
    bid = meta.get("best_bid")
    if upper is None or not isinstance(bid, dict):
        return False
    bid_price = _pos(bid.get("price"))
    bid_vol = _pos(bid.get("volume"))
    if bid_price is None or bid_vol is None or abs(bid_price - upper) > 1e-6:
        return False

    ask = meta.get("best_ask")
    if isinstance(ask, dict):
        ask_price = _pos(ask.get("price"))
        ask_vol = _pos(ask.get("volume"))
        if ask_price is not None and ask_price <= upper + 1e-6 and (ask_vol is None or ask_vol > 0):
            return False

    min_vol = _pos(min_queue_volume)
    if min_vol is not None and bid_vol < min_vol:
        return False
    return True


def is_sell_queue(meta: Optional[Dict[str, Any]], min_queue_volume: Optional[float] = None) -> bool:
    """True when the instrument is locked in a live sell queue at today's lower limit.

    Allows `best_bid` to be None or strictly below `lower_limit` (unfillable out-of-band bid).
    """
    if not _is_live_traded(meta):
        return False
    assert meta is not None
    if meta.get("queue") == "buy":
        return False

    lower = _pos(meta.get("lower_limit"))
    ask = meta.get("best_ask")
    if lower is None or not isinstance(ask, dict):
        return False
    ask_price = _pos(ask.get("price"))
    ask_vol = _pos(ask.get("volume"))
    if ask_price is None or ask_vol is None or abs(ask_price - lower) > 1e-6:
        return False

    bid = meta.get("best_bid")
    if isinstance(bid, dict):
        bid_price = _pos(bid.get("price"))
        bid_vol = _pos(bid.get("volume"))
        if bid_price is not None and bid_price >= lower - 1e-6 and (bid_vol is None or bid_vol > 0):
            return False

    min_vol = _pos(min_queue_volume)
    if min_vol is not None and ask_vol < min_vol:
        return False
    return True


def is_volume_above(meta: Optional[Dict[str, Any]], threshold: Optional[float]) -> bool:
    """True when today's cumulative traded share volume meets or exceeds `threshold`."""
    if not _is_live_traded(meta):
        return False
    assert meta is not None
    limit = _pos(threshold)
    vol = _pos(meta.get("volume"))
    if limit is None or vol is None:
        return False
    return vol >= limit


def evaluate_special_alert(
    alert: Any,
    current_price: float,
    meta: Dict[str, Any],
) -> Tuple[bool, bool, Optional[float]]:
    """Edge-triggered evaluation for Bourse queueBuy / queueSell / volumeAbove alerts.

    Returns `(triggered, is_above, triggered_target)`.
    Sets `alert.waiting_for_cross = True` upon firing so staying in the queue or above
    volume does not spam repeats; re-arms automatically once the condition turns False.
    """
    ctype = getattr(alert, "condition_type", None) or ""
    if ctype == "queueBuy":
        condition_met = is_buy_queue(meta, min_queue_volume=min_queue_volume_of(alert))
        is_above = True
        triggered_target = _pos(meta.get("upper_limit"))
    elif ctype == "queueSell":
        condition_met = is_sell_queue(meta, min_queue_volume=min_queue_volume_of(alert))
        is_above = False
        triggered_target = _pos(meta.get("lower_limit"))
    elif ctype == "volumeAbove":
        condition_met = is_volume_above(meta, getattr(alert, "target_price", None))
        is_above = True
        triggered_target = None  # target_price is shares, not Rial
    else:
        return False, True, None

    waiting = bool(getattr(alert, "waiting_for_cross", False))
    alert.last_eval_price = current_price
    raw_vol = (meta or {}).get("volume")
    if not isinstance(raw_vol, bool) and isinstance(raw_vol, (int, float)):
        fv = float(raw_vol)
        if math.isfinite(fv) and fv >= 0:
            alert.last_eval_volume = fv
    if waiting:
        if not condition_met:
            alert.waiting_for_cross = False
        return False, is_above, None

    if not condition_met:
        return False, is_above, None

    alert.waiting_for_cross = True
    return True, is_above, triggered_target


def _non_neg_float(x: Any) -> Optional[float]:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    f = float(x)
    return f if math.isfinite(f) and f >= 0 else None


def current_volume_for_alert(alert: Any) -> Optional[float]:
    """Return today's traded share volume for a Bourse (`tsetmc`) alert without I/O.

    Reads the live in-memory snapshot from `BOURSE_POLLER.store` first, falling back
    to `alert.last_eval_volume` recorded during the latest server evaluation.
    Returns None for non-Bourse alerts or when no volume has been observed yet.
    """
    ex = str(getattr(alert, "exchange", "") or "").strip().lower()
    if ex != "tsetmc":
        return None
    iid = str(getattr(alert, "symbol", "") or "").strip()
    if iid:
        try:
            from app.markets.iran_bourse import poller as pmod
            if pmod.BOURSE_POLLER is not None:
                entry = pmod.BOURSE_POLLER.store.get(iid)
                if entry and isinstance(entry.get("quote"), dict):
                    vol = _non_neg_float(entry["quote"].get("volume"))
                    if vol is not None:
                        return vol
        except Exception:
            pass
    return _non_neg_float(getattr(alert, "last_eval_volume", None))


def rule_inputs(alert: Any, current_price: float, meta: Dict[str, Any],
                cond_type: str, pct: Optional[float], base_p: Optional[float]
                ) -> Tuple[float, str, Optional[float], Optional[float]]:
    """Return (price, cond_type, percent, base_price) as the checker should use them."""
    raw = getattr(alert, "raw_rule", None) or {}
    if raw.get("price_field") == "close":
        close = _pos(meta.get("close"))
        if close is not None:
            current_price = close

    yesterday = _pos(meta.get("prev_close"))
    if yesterday is not None:
        if cond_type == "absolutePriceChange":
            delta = _pos(getattr(alert, "delta_absolute", None))
            if delta is not None:
                return current_price, "percentChange", delta / yesterday * 100.0, yesterday
        elif cond_type == "percentChange":
            return current_price, cond_type, pct, yesterday
    return current_price, cond_type, pct, base_p
