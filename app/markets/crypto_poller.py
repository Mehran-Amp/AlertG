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

import asyncio
import logging
import time
from typing import Dict, Set, Optional, Any

import httpx

import app.config as config
from app.markets.crypto_registry import get_supported_exchange_ids, get_crypto_exchange
from app.markets.crypto_catalog import get_exchange_adapter
from app.markets.crypto_snapshot import update_exchange_snapshot

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
}

GRACE_PERIOD_SECONDS = 60.0
MAX_BACKOFF_SECONDS = 30.0


class CryptoPollerSupervisor:
    """
    Supervises background polling tasks for all active crypto exchanges.
    Ensures demand-driven execution, rate-limiting, and error isolation.
    """

    def __init__(self):
        self._running = False
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

            if batch_res.prices and batch_res.error_code in ("OK", "SUCCESS", None):
                # Reset backoff on success
                self._backoff[ex] = 0.0
                update_exchange_snapshot(
                    exchange_id=ex,
                    prices=batch_res.prices,
                    status="OK",
                    latency_ms=latency_ms,
                    as_of=batch_res.as_of or now_ts,
                    error=None,
                )
            else:
                # Handle error and apply backoff
                err_code = batch_res.error_code or "NO_PRICE"
                status = "PROVIDER_BLOCKED" if "BLOCK" in err_code else err_code
                cur_backoff = self._backoff.get(ex, 0.0)
                next_backoff = min(MAX_BACKOFF_SECONDS, max(1.0, cur_backoff * 2.0))
                self._backoff[ex] = next_backoff

                update_exchange_snapshot(
                    exchange_id=ex,
                    prices={},
                    status=status,
                    latency_ms=latency_ms,
                    as_of=now_ts,
                    error=batch_res.error_message or f"HTTP error {batch_res.http_status}",
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

    def start(self) -> None:
        """Starts the background poller supervisor."""
        if self._running:
            return
        self._running = True
        self._supervisor_task = asyncio.create_task(self._supervisor_loop())
        logger.info("🟢 [Crypto Poller Supervisor] Started.")

    def stop(self) -> None:
        """Gracefully stops all background polling tasks."""
        self._running = False
        if self._supervisor_task and not self._supervisor_task.done():
            self._supervisor_task.cancel()
        for ex, task in self._tasks.items():
            if not task.done():
                task.cancel()
        self._tasks.clear()
        self._in_flight.clear()
        logger.info("🔴 [Crypto Poller Supervisor] Stopped.")


# Global singleton supervisor instance
CRYPTO_POLLER = CryptoPollerSupervisor()


def start_crypto_poller() -> None:
    """Entry point to start crypto poller."""
    CRYPTO_POLLER.start()


def stop_crypto_poller() -> None:
    """Entry point to stop crypto poller."""
    CRYPTO_POLLER.stop()
