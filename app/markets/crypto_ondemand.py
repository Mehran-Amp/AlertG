# -*- coding: utf-8 -*-
"""
AlertG — On-Demand Crypto Snapshot Refresh Helper (Phase S1).
Provides single-flight on-demand snapshot refresh for crypto price reads
under CRYPTO_ENGINE_V2 when an exchange has no background alerts polling it.
"""

import time
import asyncio
import logging
from typing import Dict, Optional, Any

try:
    import httpx
except ImportError:
    from unittest.mock import MagicMock
    httpx = MagicMock()

import app.config as config
from app.markets.crypto_registry import is_supported_crypto_exchange
from app.markets.crypto_catalog import get_exchange_adapter
from app.markets.crypto_snapshot import update_exchange_snapshot, get_exchange_snapshot_detail

logger = logging.getLogger("signalalert.crypto_ondemand")

# Single-flight mapping per canonical exchange ID
_in_flight: Dict[str, asyncio.Task] = {}
_default_client: Optional[httpx.AsyncClient] = None


async def _perform_fetch(exchange_id: str, adapter: Any, passed_client: Optional[httpx.AsyncClient] = None) -> None:
    """Internal runner that executes the batch price fetch under timeout and updates snapshot."""
    global _default_client
    timeout_sec = float(getattr(config, "CRYPTO_ONDEMAND_TIMEOUT_SECONDS", 6.0))
    t_start = time.perf_counter()
    now_ts = time.time()

    # Client resolution (passed client -> app.state.http_client -> lazy default AsyncClient)
    client = passed_client
    if client is None:
        try:
            import app.state as state
            client = getattr(state, "http_client", None)
        except Exception:
            client = None

    if client is None:
        if _default_client is None or getattr(_default_client, "is_closed", False):
            _default_client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=3.0),
                headers={"User-Agent": "AlertG/3.0.0 (CryptoOnDemand)"}
            )
        client = _default_client

    final_status = "PROVIDER_ERROR"
    final_prices: Dict[str, float] = {}

    try:
        batch_res = await asyncio.wait_for(adapter.fetch_batch_prices(client), timeout=timeout_sec)
        latency_ms = (time.perf_counter() - t_start) * 1000.0

        if getattr(batch_res, "prices", None) and getattr(batch_res, "error_code", None) in ("OK", None):
            final_status = "OK"
            final_prices = dict(batch_res.prices)
            update_exchange_snapshot(
                exchange_id=exchange_id,
                prices=final_prices,
                status="OK",
                latency_ms=latency_ms,
                as_of=batch_res.as_of or now_ts,
                error=None,
                source="rest",
            )
        else:
            err_code = getattr(batch_res, "error_code", None) or "NO_PRICE"
            final_status = "PROVIDER_BLOCKED" if "BLOCK" in str(err_code) else str(err_code)
            err_msg = getattr(batch_res, "error", None) or f"HTTP error {getattr(batch_res, 'http_status', 'unknown')}"
            update_exchange_snapshot(
                exchange_id=exchange_id,
                prices={},
                status=final_status,
                latency_ms=latency_ms,
                as_of=now_ts,
                error=err_msg,
                source="rest",
            )
    except asyncio.TimeoutError:
        latency_ms = (time.perf_counter() - t_start) * 1000.0
        final_status = "TIMEOUT"
        update_exchange_snapshot(
            exchange_id=exchange_id,
            prices={},
            status="TIMEOUT",
            latency_ms=latency_ms,
            as_of=now_ts,
            error=f"Timeout after {timeout_sec}s",
            source="rest",
        )
    except Exception as e:
        latency_ms = (time.perf_counter() - t_start) * 1000.0
        final_status = "PROVIDER_ERROR"
        update_exchange_snapshot(
            exchange_id=exchange_id,
            prices={},
            status="PROVIDER_ERROR",
            latency_ms=latency_ms,
            as_of=now_ts,
            error=str(e),
            source="rest",
        )

    # One log line per real fetch (Requirement 7)
    log_msg = f"[OnDemand] ex={exchange_id} status={final_status} pairs={len(final_prices)} ms={round(latency_ms, 1)}"
    logger.info(log_msg)
    print(log_msg)


async def _execute_wrapped(exchange_id: str, adapter: Any, client: Optional[httpx.AsyncClient] = None) -> None:
    """Wraps fetch with guaranteed in-flight task cleanup."""
    try:
        await _perform_fetch(exchange_id, adapter, client)
    finally:
        _in_flight.pop(exchange_id, None)


async def ensure_fresh_snapshot(exchange_id: str, client: Optional[httpx.AsyncClient] = None) -> str:
    """
    Ensures an in-memory snapshot exists for exchange_id.
    Returns the final snapshot status string ('OK', 'PROVIDER_BLOCKED', etc.).
    Never raises exceptions to the caller.
    """
    clean_id = (exchange_id or "").strip().lower()

    # 2. Reject unsupported IDs or missing adapter
    if not is_supported_crypto_exchange(clean_id):
        return "UNKNOWN_EXCHANGE"

    adapter = get_exchange_adapter(clean_id)
    if adapter is None:
        return "UNKNOWN_EXCHANGE"

    detail = get_exchange_snapshot_detail(clean_id)
    current_status = (detail.get("raw_status") or detail.get("status") or "NO_PRICE") if detail else "NO_PRICE"

    # 1. If CRYPTO_ONDEMAND_ENABLED is false: return current status, no fetch
    if not getattr(config, "CRYPTO_ONDEMAND_ENABLED", True):
        return current_status

    # 3. Skip fetch if snapshot exists and age < NEG_TTL (negative cache) or is fresh OK
    neg_ttl = float(getattr(config, "CRYPTO_ONDEMAND_NEG_TTL_SECONDS", 5.0))
    if detail and detail.get("age_seconds") is not None:
        if detail["age_seconds"] < neg_ttl or (detail.get("raw_status") == "OK" and not detail.get("is_stale", False)):
            return detail.get("raw_status") or detail.get("status") or "OK"

    # 4. Single-flight per exchange
    task = _in_flight.get(clean_id)
    if task is None or task.done():
        task = asyncio.create_task(_execute_wrapped(clean_id, adapter, client))
        _in_flight[clean_id] = task

    try:
        await asyncio.shield(task)
    except Exception:
        pass

    after = get_exchange_snapshot_detail(clean_id)
    return (after.get("raw_status") or after.get("status") or "NO_PRICE") if after else "NO_PRICE"
