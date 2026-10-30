# -*- coding: utf-8 -*-
"""
AlertG — Crypto Price Snapshot Store (Phase 3 / Version 2).
In-memory, thread-safe O(1) price snapshot store for crypto exchanges.

Architecture (Rule R1, R2, R9):
1. Per exchange:
   - native_symbol -> price mapping
   - as_of timestamp (exact moment response was received)
   - poll latency in ms
   - poll status: 'OK' | 'NO_PRICE' | 'STALE_PRICE' | 'RATE_LIMITED' | 'PROVIDER_BLOCKED' | 'TIMEOUT' | 'PROVIDER_ERROR'
2. The evaluation path reads from this store in O(1) time with ZERO outbound HTTP requests.
3. Automatically flags data older than CRYPTO_SNAPSHOT_MAX_AGE_SECONDS (default 10s) as STALE_PRICE.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Any

import app.config as config


@dataclass
class ExchangeSnapshot:
    exchange_id: str
    prices: Dict[str, float] = field(default_factory=dict)
    as_of: float = 0.0
    latency_ms: float = 0.0
    status: str = "NO_PRICE"
    error_detail: Optional[str] = None
    updated_at: float = field(default_factory=time.time)


# In-memory single-process snapshot store
_SNAPSHOT_STORE: Dict[str, ExchangeSnapshot] = {}


def update_exchange_snapshot(
    exchange_id: str,
    prices: Dict[str, float],
    status: str = "OK",
    latency_ms: float = 0.0,
    as_of: Optional[float] = None,
    error: Optional[str] = None,
) -> ExchangeSnapshot:
    """
    Updates the in-memory snapshot for a given exchange.
    Called exclusively by the background poller or WebSocket stream.
    """
    ex_clean = (exchange_id or "").lower().strip()
    now_ts = time.time()
    receive_ts = as_of if as_of is not None else now_ts

    snap = ExchangeSnapshot(
        exchange_id=ex_clean,
        prices=dict(prices) if prices else {},
        as_of=receive_ts,
        latency_ms=max(0.0, float(latency_ms)),
        status=status,
        error_detail=error,
        updated_at=now_ts,
    )
    _SNAPSHOT_STORE[ex_clean] = snap
    return snap


def get_snapshot_price(
    exchange_id: str,
    native_symbol: str,
    max_age_seconds: Optional[float] = None,
) -> Tuple[Optional[float], Optional[float], str, float]:
    """
    O(1) read function for alert evaluation.
    Zero network I/O.

    Returns:
        (price, as_of, status, latency_ms)
        - price: float or None
        - as_of: epoch float timestamp or None
        - status: 'OK' | 'NO_PRICE' | 'STALE_PRICE' | 'RATE_LIMITED' | 'PROVIDER_BLOCKED'
        - latency_ms: float
    """
    ex_clean = (exchange_id or "").lower().strip()
    sym_clean = (native_symbol or "").strip()

    snap = _SNAPSHOT_STORE.get(ex_clean)
    if not snap:
        return None, None, "NO_PRICE", 0.0

    max_age = max_age_seconds if max_age_seconds is not None else getattr(config, "CRYPTO_SNAPSHOT_MAX_AGE_SECONDS", 10.0)
    now_ts = time.time()

    # Staleness check
    if snap.as_of <= 0 or (now_ts - snap.as_of) > max_age:
        return None, snap.as_of, "STALE_PRICE", snap.latency_ms

    if snap.status not in ("OK", "SUCCESS"):
        return None, snap.as_of, snap.status, snap.latency_ms

    if not snap.prices:
        return None, snap.as_of, "NO_PRICE", snap.latency_ms

    # Lookup native symbol or normalized fallback
    price = snap.prices.get(sym_clean)
    if price is None:
        price = snap.prices.get(sym_clean.upper())
    if price is None:
        price = snap.prices.get(sym_clean.lower())

    if price is not None and price > 0:
        return float(price), snap.as_of, "OK", snap.latency_ms

    return None, snap.as_of, "NO_PRICE", snap.latency_ms


def clear_snapshot_store() -> None:
    """Clears all in-memory snapshots (used primarily for test isolation)."""
    _SNAPSHOT_STORE.clear()


def get_all_snapshots_status() -> Dict[str, Any]:
    """Returns high-level status summary of all active snapshots for monitoring/status."""
    now_ts = time.time()
    max_age = getattr(config, "CRYPTO_SNAPSHOT_MAX_AGE_SECONDS", 10.0)
    out = {}
    for ex_id, snap in _SNAPSHOT_STORE.items():
        age = now_ts - snap.as_of if snap.as_of > 0 else None
        is_stale = (age is None) or (age > max_age)
        out[ex_id] = {
            "status": "STALE_PRICE" if is_stale and snap.status == "OK" else snap.status,
            "raw_status": snap.status,
            "as_of": snap.as_of,
            "age_seconds": round(age, 2) if age is not None else None,
            "latency_ms": round(snap.latency_ms, 2),
            "total_pairs": len(snap.prices),
            "is_stale": is_stale,
            "error": snap.error_detail,
        }
    return out


def get_exchange_snapshot_detail(exchange_id: str, sample_limit: int = 20) -> Optional[Dict[str, Any]]:
    """Returns detailed information for a specific exchange's in-memory snapshot."""
    ex_clean = (exchange_id or "").lower().strip()
    snap = _SNAPSHOT_STORE.get(ex_clean)
    if not snap:
        return None
    now_ts = time.time()
    max_age = getattr(config, "CRYPTO_SNAPSHOT_MAX_AGE_SECONDS", 10.0)
    age = now_ts - snap.as_of if snap.as_of > 0 else None
    is_stale = (age is None) or (age > max_age)

    # Sample pairs
    sample_pairs = {}
    for i, (sym, p) in enumerate(snap.prices.items()):
        if i >= sample_limit:
            break
        sample_pairs[sym] = p

    return {
        "exchange": ex_clean,
        "status": "STALE_PRICE" if is_stale and snap.status == "OK" else snap.status,
        "raw_status": snap.status,
        "as_of": snap.as_of,
        "age_seconds": round(age, 2) if age is not None else None,
        "latency_ms": round(snap.latency_ms, 2),
        "total_pairs": len(snap.prices),
        "is_stale": is_stale,
        "error": snap.error_detail,
        "sample_prices": sample_pairs,
    }

