# -*- coding: utf-8 -*-
"""
Iranian Bourse — session state and alert eligibility (IB-7). Appendix D.

States: LIVE (fresh + open + traded), CLOSED, NO_TRADE_TODAY, STALE, no_data.
Order: outside session -> CLOSED; stale feed -> STALE; seq quiet >180 s -> CLOSED;
then not traded -> NO_TRADE_TODAY; else LIVE. alert_eligible is True only for LIVE.
"""
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from app.engine.calendar import is_iran_bourse_open


def _now() -> datetime:
    return datetime.now().astimezone()


def feed_health() -> Tuple[Optional[bool], Optional[float]]:
    """(feed_fresh, seq_age_seconds) from the running poller; (None, None) if there is none."""
    from app.markets.iran_bourse import poller as pmod
    p = pmod.BOURSE_POLLER
    if p is None:
        return None, None
    return p.store.feed_health()


def classify(result: Dict[str, Any], store=None, now_dt: Optional[datetime] = None) -> Tuple[str, bool]:
    """Return (state, alert_eligible) for a mapped quote result."""
    fresh, seq_age = store.feed_health() if store is not None else feed_health()
    is_open, why = is_iran_bourse_open(now_dt or _now(), fresh, seq_age)
    if not is_open:
        state = why                                   # CLOSED or STALE
    elif result.get("state") == "STALE":
        state = "STALE"                               # gateway said stale for this quote
    elif not result.get("traded_today"):
        state = "NO_TRADE_TODAY"
    else:
        state = "LIVE"
    return state, state == "LIVE"
