# -*- coding: utf-8 -*-
"""
Iranian Bourse — alert semantics (IB-8). Pure helpers, no I/O, nothing from other markets.

* price_field: raw_rule.price_field is 'last' (default) or 'close'.
* percent change: the daily base is the instrument's `yesterday` (prev_close), re-read every
  evaluation. absolutePriceChange is turned into the same percent rule (delta / yesterday).
* outlier filter: a price inside the instrument's own [lower_limit, upper_limit] is never held back.
* asOf (set in price.py/mapping.py) is the gateway fetch time; last_trade_time is a separate field.
"""
from typing import Any, Dict, Optional, Tuple

EXTRA_KEYS = ("last_trade_time", "prev_close", "close", "lower_limit", "upper_limit",
              "change_pct", "ticker", "name", "alert_eligible")


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
    return float(x) if isinstance(x, (int, float)) and x > 0 else None


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
