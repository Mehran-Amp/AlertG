# -*- coding: utf-8 -*-
"""
Iranian Bourse — instrument directory for the app API (IB-9).

Search is cached 30 s, classification 6 h, instrument lookups 6 h (unknown ids 60 s).
All gateway calls go through the poller's single client (one request in flight, no retries).
Errors are raised as BourseError; callers map them to a clear 503.
"""
import time
from typing import Any, Callable, Dict, Optional, Tuple

SEARCH_TTL = 30.0
CLASSIFICATION_TTL = 6 * 3600.0
LOOKUP_TTL = 6 * 3600.0
UNKNOWN_TTL = 60.0
MAX_ENTRIES = 500

_LETTERS = str.maketrans({"ي": "ی", "ك": "ک", "ى": "ی"})  # ي ك ى -> ی ک ی


def normalize_query(q: str) -> str:
    """Arabic Yeh/Kaf to Persian, trimmed. (The gateway also normalizes; this keeps cache keys equal.)"""
    return " ".join((q or "").translate(_LETTERS).split())


class _TTL:
    def __init__(self, clock: Callable[[], float]):
        self._clock = clock
        self._d: Dict[Any, Tuple[float, Any]] = {}

    def get(self, key):
        item = self._d.get(key)
        if item and item[0] > self._clock():
            return item[1], True
        self._d.pop(key, None)
        return None, False

    def put(self, key, value, ttl: float):
        if len(self._d) >= MAX_ENTRIES:
            now = self._clock()
            for k in [k for k, v in self._d.items() if v[0] <= now] or [next(iter(self._d))]:
                self._d.pop(k, None)
        self._d[key] = (self._clock() + ttl, value)

    def clear(self):
        self._d.clear()

    def __len__(self):
        return len(self._d)


class Directory:
    def __init__(self, clock: Callable[[], float] = time.time):
        self.cache = _TTL(clock)
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _client():
        from app.markets.iran_bourse.poller import get_poller
        return get_poller()._get_client()

    async def search(self, q: str, limit: int = 20, market: str = "", board: str = "",
                     type_: str = "", sector: str = "", traded: Optional[bool] = None):
        limit = max(1, min(50, int(limit)))
        nq = normalize_query(q)
        key = ("s", nq, limit, market, board, type_, sector, traded)
        hit, ok = self.cache.get(key)
        if ok:
            self.hits += 1
            return hit
        self.misses += 1
        filters = {"market": market, "board": board, "type": type_, "sector": sector}
        if traded:
            filters["traded"] = "1"
        rows, meta = await self._client().symbols(nq, limit, **filters)
        value = (rows, meta)
        self.cache.put(key, value, SEARCH_TTL)
        return value

    async def classification(self):
        hit, ok = self.cache.get(("c",))
        if ok:
            self.hits += 1
            return hit
        self.misses += 1
        value = await self._client().classification()
        self.cache.put(("c",), value, CLASSIFICATION_TTL)
        return value

    async def lookup(self, instrument_id: str) -> Optional[Dict[str, Any]]:
        """{'id','ticker','name','yesterday'} for a known id, None for an unknown one."""
        key = ("i", instrument_id)
        hit, ok = self.cache.get(key)
        if ok:
            self.hits += 1
            return hit
        self.misses += 1
        found, _missing, _meta = await self._client().quotes([instrument_id])
        info = None
        for q in found:
            if str(q.get("id")) == instrument_id:
                info = {"id": instrument_id, "ticker": q.get("ticker"), "name": q.get("name"),
                        "yesterday": q.get("yesterday")}
        self.cache.put(key, info, LOOKUP_TTL if info else UNKNOWN_TTL)
        return info


DIRECTORY = Directory()
