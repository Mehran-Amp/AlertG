# -*- coding: utf-8 -*-
"""
Iranian Bourse — instruments that disappear (IB-9). Uses the existing alert fields
needs_attention / needs_attention_reason. Only tsetmc alerts are touched.
Called with a FULL gateway snapshot (changes?since=0), never with a partial one.
"""
import logging
from typing import Any, Iterable, List, Set

logger = logging.getLogger("signalalert.iran_bourse")

MIN_FULL_SNAPSHOT = 500          # a "full" list smaller than this is treated as a broken reload


def reconcile_missing(alerts: Iterable[Any], present_ids: Set[str]) -> List[Any]:
    """Flag tsetmc alerts whose id is absent from a full snapshot; clear the flag when it is back.
    Returns the alerts whose flag changed."""
    if len(present_ids) < MIN_FULL_SNAPSHOT:
        return []
    changed = []
    for a in alerts:
        if (getattr(a, "exchange", "") or "").lower().strip() != "tsetmc":
            continue
        iid = str(getattr(a, "symbol", "") or "")
        flagged = bool(getattr(a, "needs_attention", False))
        if iid not in present_ids and not flagged:
            a.needs_attention = True
            a.needs_attention_reason = f"Instrument {getattr(a, 'market_symbol', None) or iid} is no longer listed by the Bourse data feed."
            changed.append(a)
            logger.warning("[IranBourse] alert %s flagged needs_attention (instrument %s missing)", a.id, iid)
        elif iid in present_ids and flagged and "Bourse" in (getattr(a, "needs_attention_reason", "") or ""):
            a.needs_attention = False
            a.needs_attention_reason = None
            a.attention_notified_at = None
            changed.append(a)
    return changed
