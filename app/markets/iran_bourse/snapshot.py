# -*- coding: utf-8 -*-
"""
Iranian Bourse — in-memory snapshot store (IB-5).

Holds the latest validated gateway quote per instrument id, only for ids somebody
cares about: "watched" ids (active alerts) are always kept; "recent" ids (an app
screen asked) live in an LRU of RECENT_LIMIT entries. Everything else the gateway
sends is dropped. Instrument ids are always strings (rule N6). Prices are untouched
(rule N7, Rial). This module imports nothing from other markets.
"""
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, Iterable, Optional, Set

RECENT_LIMIT = 500


class BourseSnapshotStore:
    def __init__(self, stale_seconds: float = 60.0, clock: Callable[[], float] = time.time):
        self._stale_seconds = float(stale_seconds)
        self._clock = clock
        self._quotes: Dict[str, Dict[str, Any]] = {}
        self._recent: "OrderedDict[str, None]" = OrderedDict()
        self._watched: Set[str] = set()
        self.seq: int = 0                      # last gateway seq we consumed
        self.last_success_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.gateway_stale: bool = False       # meta.stale of the last response
        self.resets: int = 0                   # gateway-reload resets seen

    # ---- interest -------------------------------------------------------
    def set_watched(self, ids: Iterable[str]) -> None:
        self._watched = {str(i) for i in ids}
        self._evict()

    def touch(self, ids: Iterable[str]) -> None:
        for i in ids:
            i = str(i)
            self._recent.pop(i, None)
            self._recent[i] = None
        while len(self._recent) > RECENT_LIMIT:
            self._recent.popitem(last=False)
        self._evict()

    def wanted(self) -> Set[str]:
        return self._watched | set(self._recent)

    def _evict(self) -> None:
        keep = self.wanted()
        for i in [k for k in self._quotes if k not in keep]:
            del self._quotes[i]

    # ---- updates --------------------------------------------------------
    def apply(self, quotes: Iterable[Dict[str, Any]], meta: Dict[str, Any]) -> int:
        """Store quotes for wanted ids. Returns how many were kept."""
        keep = self.wanted()
        now = self._clock()
        n = 0
        for q in quotes:
            qid = str(q.get("id", ""))
            if qid in keep:
                self._quotes[qid] = {"quote": q, "meta": dict(meta), "fetched_at": now}
                n += 1
        seq = meta.get("seq")
        if isinstance(seq, int):
            self.seq = seq
        self.gateway_stale = bool(meta.get("stale", False))
        self.last_success_at = now
        self.last_error = None
        return n

    def put(self, quote: Dict[str, Any], meta: Dict[str, Any]) -> None:
        """Store one on-demand quote WITHOUT moving the /v1/changes cursor."""
        qid = str(quote.get("id", ""))
        self._recent.pop(qid, None)
        self._recent[qid] = None
        while len(self._recent) > RECENT_LIMIT:
            self._recent.popitem(last=False)
        self._evict()
        now = self._clock()
        self._quotes[qid] = {"quote": quote, "meta": dict(meta), "fetched_at": now}
        self.gateway_stale = bool(meta.get("stale", False))
        self.last_success_at = now
        self.last_error = None

    def record_error(self, message: str) -> None:
        self.last_error = message

    def reset_cursor(self) -> None:
        """Gateway restarted (seq went backwards): refetch everything next poll."""
        self.seq = 0
        self.resets += 1

    # ---- reads ----------------------------------------------------------
    def is_stale(self) -> bool:
        if self.last_success_at is None:
            return True
        if self.gateway_stale:
            return True
        return (self._clock() - self.last_success_at) > self._stale_seconds

    def get(self, instrument_id: str) -> Optional[Dict[str, Any]]:
        """Return {quote, meta, fetched_at, stale} or None if never seen."""
        entry = self._quotes.get(str(instrument_id))
        if entry is None:
            return None
        out = dict(entry)
        out["stale"] = self.is_stale()
        return out

    def stats(self) -> Dict[str, Any]:
        return {
            "stored": len(self._quotes),
            "watched": len(self._watched),
            "recent": len(self._recent),
            "seq": self.seq,
            "stale": self.is_stale(),
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
            "resets": self.resets,
        }
