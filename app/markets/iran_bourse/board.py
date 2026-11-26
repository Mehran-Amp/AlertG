# -*- coding: utf-8 -*-
"""
Iranian Bourse — market board for the app's browse lists (IB-16a).

The gateway can only *search*. To show every symbol in categorized lists (like a stock
app) the server keeps one compact in-memory table of the whole market, fed by the
gateway's /v1/changes feed:

* Request-driven: the table is refreshed only while someone asks for it (at most once per
  REFRESH_SECONDS, one request in flight). Nobody viewing => zero gateway requests.
* First refresh pulls the whole market (about 2.5 MB); later refreshes only the changes.
* The gateway restarting (seq goes backwards) triggers one full reload.
* Instrument ids are Strings (rule N6). Prices are Rial and untouched (rules D1, N7).
* Imports nothing from other markets. Calls go through the poller's single client.
"""
import asyncio
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.engine.calendar import is_iran_bourse_open
from app.markets.iran_bourse.client import BourseError

REFRESH_SECONDS = 15.0
MAX_LIMIT = 100
DEFAULT_LIMIT = 50

# Category groups shown as tabs. Options and futures are kept out of the default list.
GROUP_STOCKS = "stocks"
GROUP_FUNDS = "funds"
GROUP_BONDS = "bonds"
GROUP_RIGHTS = "rights"
GROUP_COMMODITIES = "commodities"
GROUP_DERIVATIVES = "derivatives"
GROUP_OTHER = "other"
GROUPS = (
    GROUP_STOCKS,
    GROUP_FUNDS,
    GROUP_BONDS,
    GROUP_RIGHTS,
    GROUP_COMMODITIES,
    GROUP_DERIVATIVES,
    GROUP_OTHER,
)

SORT_KEYS = ("value", "volume", "change", "price", "name")

_LETTERS = str.maketrans({"ي": "ی", "ك": "ک", "ى": "ی", "‌": " "})

# Fields kept per instrument (everything else the gateway sends is dropped).
KEEP = ("id", "isin", "ticker", "name", "last", "close", "yesterday", "last_change_pct",
        "close_change_pct", "high", "low", "volume", "value", "trades", "traded", "upper_limit",
        "lower_limit", "nav", "queue", "update_time", "market_code", "market", "board_code", "board",
        "type_code", "type", "sector_code", "sector")


def norm(text: Any) -> str:
    """Arabic Yeh/Kaf to Persian, half-space to space, single spaces."""
    return " ".join(str(text or "").translate(_LETTERS).split())


# Type codes seen on the live feed for rows that arrive WITHOUT a type name (IB-16a2, Phase 20).
CODE_GROUPS = {
    "313": GROUP_STOCKS,        # base/small market equities (e.g., رهیاب)
    "315": GROUP_FUNDS,         # commodity-backed / project funds (sector: tradable fund)
    "206": GROUP_BONDS,         # bank "gam" securities
    "307": GROUP_BONDS,         # housing facility certificates (تسهیلات مسکن)
    "403": GROUP_RIGHTS,
    "404": GROUP_RIGHTS,        # rights issues (tickers start with "ح.")
    "701": GROUP_COMMODITIES,   # saffron & commodity deposit certificates
    "201": GROUP_COMMODITIES,   # electricity capacity certificates (گواهی ظرفیت)
    "801": GROUP_COMMODITIES,   # energy exchange base-load daily contracts
    "802": GROUP_COMMODITIES,   # energy exchange base-load weekly contracts
    "803": GROUP_COMMODITIES,   # energy exchange base-load monthly contracts
    "804": GROUP_COMMODITIES,   # energy exchange base-load seasonal contracts
}


def group_of(row: Dict[str, Any]) -> str:
    """Category group from the instrument type name (the gateway's own Persian label).
    Rows without a type name fall back to the type code, then to the sector / name."""
    t = norm(row.get("type"))
    if not t:
        by_code = CODE_GROUPS.get(str(row.get("type_code") or "").strip())
        if by_code:
            return by_code
        if "صندوق" in norm(row.get("sector")):
            return GROUP_FUNDS
        n = norm(row.get("name"))
        if n.startswith("ح."):
            return GROUP_RIGHTS
        if "تسهیلات مسکن" in n:
            return GROUP_BONDS
        if any(k in n for k in ("زعفران", "گواهی سپرده", "گواهی ظرفیت", "بار پایه")):
            return GROUP_COMMODITIES
    if "اختیار" in t or "آتی" in t:
        return GROUP_DERIVATIVES
    if "حق تقدم" in t:
        return GROUP_RIGHTS
    if "صندوق" in t:
        return GROUP_FUNDS
    if any(k in t for k in ("اوراق", "صکوک", "مرابحه", "اجاره", "مشارکت", "سلف", "منفعت", "تسهیلات")):
        return GROUP_BONDS
    if any(k in t for k in ("زعفران", "گواهی سپرده", "گواهی ظرفیت", "کالا", "بار پایه")):
        return GROUP_COMMODITIES
    if "سهام" in t or "سهم" in t:
        return GROUP_STOCKS
    return GROUP_OTHER


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def price_of(row: Dict[str, Any]) -> Tuple[Optional[float], str]:
    """The price to show, and where it came from: last trade, else closing price, else yesterday."""
    for key, label in (("last", "last"), ("close", "close"), ("yesterday", "yesterday")):
        v = _num(row.get(key))
        if v is not None and v > 0:
            return v, label
    return None, "none"


def project(row: Dict[str, Any]) -> Dict[str, Any]:
    price, source = price_of(row)
    return {
        "id": str(row.get("id")),
        "ticker": row.get("ticker"),
        "name": row.get("name"),
        "price": price,
        "price_source": source,
        "last": row.get("last"),
        "close": row.get("close"),
        "yesterday": row.get("yesterday"),
        "change_pct": row.get("last_change_pct"),
        "volume": row.get("volume"),
        "value": row.get("value"),
        "traded": bool(row.get("traded")),
        "queue": row.get("queue"),
        "group": group_of(row),
        "market_code": row.get("market_code"),
        "type_code": row.get("type_code"),
        "type": row.get("type"),
        "sector_code": row.get("sector_code"),
        "sector": row.get("sector"),
        "update_time": row.get("update_time"),
    }


def _sort_value(item: Dict[str, Any], key: str):
    if key == "name":
        return norm(item.get("ticker") or item.get("name"))
    field = {"value": "value", "volume": "volume", "change": "change_pct", "price": "price"}[key]
    return _num(item.get(field))


class BourseBoard:
    def __init__(self, client_fn: Callable[[], Any], clock: Callable[[], float] = time.time,
                 refresh_seconds: float = REFRESH_SECONDS):
        self._client_fn = client_fn
        self._clock = clock
        self._refresh_seconds = float(refresh_seconds)
        self._rows: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self.seq = 0
        self.last_refresh: float = 0.0
        self.last_success_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.gateway_stale = False
        self.as_of: Optional[int] = None
        self.requests_made = 0
        self.full_loads = 0

    def __len__(self) -> int:
        return len(self._rows)

    # ---- refresh ---------------------------------------------------------
    def apply(self, quotes: List[Dict[str, Any]], meta: Dict[str, Any], full: bool) -> None:
        if full:
            self._rows = {}
            self.full_loads += 1
        for q in quotes:
            qid = str(q.get("id", "")).strip()
            if not qid:
                continue
            row = {k: q.get(k) for k in KEEP}
            row["id"] = qid
            self._rows[qid] = row
        seq = meta.get("seq")
        if isinstance(seq, int):
            self.seq = seq
        self.gateway_stale = bool(meta.get("stale", False))
        local = meta.get("local_as_of")
        self.as_of = int(local) if isinstance(local, (int, float)) and not isinstance(local, bool) else int(self._clock())
        self.last_success_at = self._clock()
        self.last_error = None

    async def ensure_fresh(self) -> None:
        """Refresh if the table is older than the refresh interval. Raises BourseError only
        when there is nothing to show; otherwise a failed refresh keeps the old rows."""
        if self._rows and (self._clock() - self.last_refresh) < self._refresh_seconds:
            return
        async with self._lock:
            if self._rows and (self._clock() - self.last_refresh) < self._refresh_seconds:
                return  # someone else refreshed while we waited
            try:
                client = self._client_fn()
                since = self.seq if self._rows else 0
                self.requests_made += 1
                quotes, meta = await client.changes(since)
                seq = meta.get("seq")
                if since and isinstance(seq, int) and seq < since:
                    self.requests_made += 1
                    quotes, meta = await client.changes(0)
                    since = 0
                self.apply(quotes, meta, full=(since == 0))
                self.last_refresh = self._clock()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.last_error = f"{type(e).__name__}: {e}"
                self.last_refresh = self._clock() - self._refresh_seconds + 5.0  # retry in ~5 s, no storm
                if not self._rows:
                    if isinstance(e, BourseError):
                        raise
                    raise BourseError(str(e)) from e

    # ---- reads -----------------------------------------------------------
    def stale(self) -> bool:
        if self.last_success_at is None or self.gateway_stale:
            return True
        return (self._clock() - self.last_success_at) > 3 * self._refresh_seconds + 30.0

    def session(self, now_dt=None) -> str:
        """OPEN / CLOSED / STALE by the Tehran schedule and feed freshness."""
        return is_iran_bourse_open(now_dt, not self.stale())[1]

    def query(self, group: str = "", market: str = "", sector: str = "", type_code: str = "",
              traded: Optional[bool] = None, q: str = "", sort: str = "value", order: str = "",
              offset: int = 0, limit: int = DEFAULT_LIMIT) -> Dict[str, Any]:
        sort = sort if sort in SORT_KEYS else "value"
        desc = (order or ("asc" if sort == "name" else "desc")).lower() != "asc"
        limit = max(1, min(MAX_LIMIT, int(limit)))
        offset = max(0, int(offset))
        nq = norm(q).lower()

        items = [project(r) for r in self._rows.values()]
        counts = {g: 0 for g in GROUPS}
        other_types: Dict[str, int] = {}
        for it in items:
            counts[it["group"]] += 1
            if it["group"] == GROUP_OTHER:
                label = norm(it.get("type")) or "?"
                other_types[label] = other_types.get(label, 0) + 1

        def keep(it: Dict[str, Any]) -> bool:
            if group:
                if it["group"] != group:
                    return False
            elif it["group"] == GROUP_DERIVATIVES:
                return False  # default list: options and futures live in their own category
            if market and str(it.get("market_code")) != market:
                return False
            if sector and str(it.get("sector_code")) != sector:
                return False
            if type_code and str(it.get("type_code")) != type_code:
                return False
            if traded is True and not it["traded"]:
                return False
            if nq and nq not in norm(it.get("ticker")).lower() and nq not in norm(it.get("name")).lower():
                return False
            return True

        rows = [it for it in items if keep(it)]
        present = [it for it in rows if _sort_value(it, sort) is not None]
        missing = [it for it in rows if _sort_value(it, sort) is None]  # always last
        present.sort(key=lambda it: (_sort_value(it, sort), it["id"]), reverse=desc)
        ordered = present + missing
        page = ordered[offset:offset + limit]
        return {
            "unit": "IRR",
            "session": self.session(),
            "stale": self.stale(),
            "as_of": self.as_of,
            "total": len(ordered),
            "offset": offset,
            "limit": limit,
            "sort": sort,
            "order": "desc" if desc else "asc",
            "groups": counts,
            "other_types": dict(sorted(other_types.items(), key=lambda kv: -kv[1])[:20]),
            "items": page,
        }

    def catalog_snapshot(self) -> Dict[str, Any]:
        """Full market snapshot for mobile local caching (refreshed once daily after market close)."""
        items = [project(r) for r in self._rows.values()]
        counts = {g: 0 for g in GROUPS}
        for it in items:
            counts[it["group"]] += 1
        items.sort(key=lambda it: (-(_num(it.get("value")) or -1.0), it["id"]))
        return {
            "unit": "IRR",
            "session": self.session(),
            "stale": self.stale(),
            "as_of": self.as_of,
            "total": len(items),
            "groups": counts,
            "items": items,
        }

    def stats(self) -> Dict[str, Any]:
        return {"rows": len(self._rows), "seq": self.seq, "stale": self.stale(),
                "requests": self.requests_made, "full_loads": self.full_loads,
                "last_error": self.last_error}


BOARD: Optional[BourseBoard] = None


def get_board() -> BourseBoard:
    global BOARD
    if BOARD is None:
        from app.markets.iran_bourse.poller import get_poller
        BOARD = BourseBoard(lambda: get_poller()._get_client())
    return BOARD
