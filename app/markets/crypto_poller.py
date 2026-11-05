# -*- coding: utf-8 -*-
"""
AlertG — REST Bulk Poller for Crypto Exchanges (Phase 3 / Version 2).
Executes Stage A background bulk price polling for active crypto exchanges:
1. Demand-Driven: Only polls an exchange if there is at least one active alert
   for it, with a 60-second grace period after the last alert is removed.
2. In-Flight Protection: Strictly guarantees at most ONE in-flight HTTP request
   per exchange at any time (zero request storms, Rule R9).
3. Exponential Back-Off: On HTTP 429/418 or provider block, backs off (1s -> 2s -> 4s -> ...
   capped at 30s) and honors 'Retry-After' headers if provided.
4. Feeds the in-memory Price Snapshot Store with zero latency overhead.
"""

import os
import fcntl
import asyncio
import logging
import time
from collections import deque
from typing import Dict, Set, Optional, Any

import httpx

import app.config as config
from app.markets.crypto_registry import get_supported_exchange_ids, get_crypto_exchange
from app.markets.crypto_catalog import get_exchange_adapter
from app.markets.crypto_snapshot import update_exchange_snapshot
try:
    from app.markets.crypto_stream import is_stream_active_and_healthy
except ImportError:
    def is_stream_active_and_healthy(ex: str) -> bool: return False

logger = logging.getLogger("signalalert.crypto_poller")

# Configured default poll cadences (seconds per bulk fetch)
# Kept safely at or below 50% of each exchange's documented rate limits.
DEFAULT_POLL_CADENCES: Dict[str, float] = {
    "binance": 1.0,
    "mexc": 1.0,
    "kucoin": 1.0,
    "gateio": 1.0,
    "lbank": 1.5,
    "okx": 1.0,
    "bybit": 1.0,
    "bitget": 1.0,
    "kraken": 2.0,
    "htx": 1.0,
    "tabdeal": 2.0,
    "bingx": 1.0,
    "xt": 1.0,
    "toobit": 1.0,
    "poloniex": 1.5,
    "coinbase": 2.0,
    "bitfinex": 2.0,
}

GRACE_PERIOD_SECONDS = 60.0
MAX_BACKOFF_SECONDS = 30.0

# Rolling window of last 200 poll latencies for percentiles calculation (p50 / p95)
_POLL_LATENCY_HISTORY = deque(maxlen=200)


def record_poll_latency(latency_ms: float) -> None:
    """Records a single poll latency in milliseconds."""
    if latency_ms and latency_ms > 0:
        _POLL_LATENCY_HISTORY.append(float(latency_ms))


def get_crypto_latency_percentiles() -> Dict[str, Any]:
    """Calculates p50 and p95 latency percentiles from rolling window."""
    if not _POLL_LATENCY_HISTORY:
        return {
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "samples": 0,
            "active_pollers": len(CRYPTO_POLLER._tasks) if hasattr(CRYPTO_POLLER, "_tasks") else 0,
            "is_leader": getattr(CRYPTO_POLLER, "_is_leader", False)
        }
    sorted_samples = sorted(_POLL_LATENCY_HISTORY)
    n = len(sorted_samples)
    p50_idx = int(0.50 * n)
    p95_idx = min(int(0.95 * n), n - 1)
    return {
        "p50_ms": round(sorted_samples[p50_idx], 2),
        "p95_ms": round(sorted_samples[p95_idx], 2),
        "samples": n,
        "active_pollers": len(CRYPTO_POLLER._tasks) if hasattr(CRYPTO_POLLER, "_tasks") else 0,
        "is_leader": getattr(CRYPTO_POLLER, "_is_leader", False)
    }


class CryptoPollerSupervisor:
    """
    Supervises background polling tasks for all active crypto exchanges.
    Ensures demand-driven execution, rate-limiting, and error isolation.
    Enforces Singleton Poller Guard across worker processes (Rule R9).
    """

    def __init__(self):
        self._running = False
        self._is_leader = False
        self._lock_file = None
        self._tasks: Dict[str, asyncio.Task] = {}
        self._in_flight: Set[str] = set()
        self._last_needed_at: Dict[str, float] = {}
        self._backoff: Dict[str, float] = {}
        self._client: Optional[httpx.AsyncClient] = None
        self._supervisor_task: Optional[asyncio.Task] = None

    def get_active_demand_exchanges(self) -> Set[str]:
        """
        Scans current alerts to determine which crypto exchanges have active alerts.
        """
        try:
            from app.storage import ALERTS_DB
            active_exchanges = set()
            for alert in ALERTS_DB:
                if getattr(alert, "is_active", False):
                    nature = getattr(alert, "alert_nature", "price")
                    if nature != "macro":
                        ex = (getattr(alert, "exchange", "") or "").lower().strip()
                        if ex:
                            active_exchanges.add(ex)
            return active_exchanges
        except Exception as e:
            logger.debug(f"Failed to scan ALERTS_DB for demand: {e}")
            return set()

    async def poll_exchange_once(self, exchange_id: str) -> None:
        """
        Executes exactly one bulk price poll for the given exchange.
        Protected by in-flight concurrency lock.
        """
        ex = exchange_id.lower().strip()
        if ex in self._in_flight:
            return

        # Phase 7 (Stage C): If WebSocket stream is active and healthy for this exchange,
        # yield to WebSocket stream to conserve network budget and avoid duplicate updates.
        if is_stream_active_and_healthy(ex):
            return

        adapter = get_exchange_adapter(ex)
        if not adapter:
            return

        self._in_flight.add(ex)
        t_start = time.perf_counter()
        now_ts = time.time()

        try:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(
                    timeout=httpx.Timeout(10.0, connect=3.0),
                    headers={"User-Agent": "AlertG/3.0.0 (CryptoPoller)"}
                )

            batch_res = await adapter.fetch_batch_prices(self._client)
            latency_ms = (time.perf_counter() - t_start) * 1000.0

            if batch_res.prices and batch_res.error_code in ("OK", None):
                # Reset backoff on success
                self._backoff[ex] = 0.0
                record_poll_latency(latency_ms)
                update_exchange_snapshot(
                    exchange_id=ex,
                    prices=batch_res.prices,
                    status="OK",
                    latency_ms=latency_ms,
                    as_of=batch_res.as_of or now_ts,
                    error=None,
                )
            else:
                # Handle error and apply backoff (honoring Retry-After if provided)
                err_code = batch_res.error_code or "NO_PRICE"
                status = "PROVIDER_BLOCKED" if "BLOCK" in err_code else err_code
                if getattr(batch_res, "retry_after", None) and batch_res.retry_after > 0:
                    next_backoff = min(MAX_BACKOFF_SECONDS, max(1.0, float(batch_res.retry_after)))
                else:
                    cur_backoff = self._backoff.get(ex, 0.0)
                    next_backoff = min(MAX_BACKOFF_SECONDS, max(1.0, cur_backoff * 2.0))
                self._backoff[ex] = next_backoff

                update_exchange_snapshot(
                    exchange_id=ex,
                    prices={},
                    status=status,
                    latency_ms=latency_ms,
                    as_of=now_ts,
                    error=batch_res.error or f"HTTP error {batch_res.http_status}",
                )

        except Exception as e:
            latency_ms = (time.perf_counter() - t_start) * 1000.0
            cur_backoff = self._backoff.get(ex, 0.0)
            next_backoff = min(MAX_BACKOFF_SECONDS, max(1.0, cur_backoff * 2.0))
            self._backoff[ex] = next_backoff

            update_exchange_snapshot(
                exchange_id=ex,
                prices={},
                status="PROVIDER_ERROR",
                latency_ms=latency_ms,
                as_of=now_ts,
                error=str(e),
            )
        finally:
            self._in_flight.discard(ex)

    async def _exchange_poll_loop(self, exchange_id: str) -> None:
        """Dedicated asyncio polling loop for a single exchange."""
        cadence = DEFAULT_POLL_CADENCES.get(exchange_id, 1.0)
        logger.info(f"🚀 [Crypto Poller] Started dedicated poll loop for {exchange_id} (cadence: {cadence}s)")

        while self._running:
            # Check demand: only poll if active within grace period
            now = time.time()
            last_needed = self._last_needed_at.get(exchange_id, 0.0)
            if (now - last_needed) > GRACE_PERIOD_SECONDS:
                # Idle: wait longer before re-checking demand
                await asyncio.sleep(2.0)
                continue

            # Poll once
            await self.poll_exchange_once(exchange_id)

            # Sleep base cadence + any active back-off delay
            backoff_delay = self._backoff.get(exchange_id, 0.0)
            sleep_duration = cadence + backoff_delay
            await asyncio.sleep(sleep_duration)

    async def _supervisor_loop(self) -> None:
        """Main loop that discovers active exchange demand and manages worker tasks."""
        while self._running:
            try:
                active_demand = self.get_active_demand_exchanges()
                now = time.time()

                for ex in active_demand:
                    self._last_needed_at[ex] = now
                    if ex not in self._tasks or self._tasks[ex].done():
                        # Launch dedicated task
                        self._tasks[ex] = asyncio.create_task(self._exchange_poll_loop(ex))

            except Exception as e:
                logger.error(f"Error in crypto poller supervisor loop: {e}")

            await asyncio.sleep(2.0)

    def _acquire_leader_lock(self) -> bool:
        """Acquires exclusive non-blocking file lock to enforce Singleton Poller (Rule R9)."""
        data_dir = getattr(config, "DATA_DIR", ".")
        lock_path = os.path.join(data_dir, "crypto_poller.lock")
        try:
            self._lock_file = open(lock_path, "w")
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_file.write(f"{os.getpid()}\n")
            self._lock_file.flush()
            self._is_leader = True
            return True
        except (BlockingIOError, OSError):
            self._is_leader = False
            if self._lock_file:
                try:
                    self._lock_file.close()
                except Exception:
                    pass
                self._lock_file = None
            return False

    def _release_leader_lock(self) -> None:
        """Releases the leader lock and closes lock file."""
        if self._lock_file:
            try:
                fcntl.flock(self._lock_file, fcntl.LOCK_UN)
                self._lock_file.close()
            except Exception:
                pass
            self._lock_file = None
        self._is_leader = False

    def start(self) -> None:
        """Starts the background poller supervisor if this worker is leader."""
        if self._running:
            return
        if not self._acquire_leader_lock():
            logger.info("🟡 [Crypto Poller] Standby worker: lock held by another process (Singleton R9).")
            return
        self._running = True
        self._supervisor_task = asyncio.create_task(self._supervisor_loop())
        logger.info("🟢 [Crypto Poller Supervisor] Started (Leader).")

    def stop(self) -> None:
        """Gracefully stops all background polling tasks and releases leader lock."""
        self._running = False
        if self._supervisor_task and not self._supervisor_task.done():
            self._supervisor_task.cancel()
        for ex, task in self._tasks.items():
            if not task.done():
                task.cancel()
        self._tasks.clear()
        self._in_flight.clear()
        self._release_leader_lock()
        logger.info("🔴 [Crypto Poller Supervisor] Stopped.")


# Global singleton supervisor instance
CRYPTO_POLLER = CryptoPollerSupervisor()


def start_crypto_poller() -> None:
    """Entry point to start crypto poller."""
    CRYPTO_POLLER.start()


def stop_crypto_poller() -> None:
    """Entry point to stop crypto poller."""
    CRYPTO_POLLER.stop()
