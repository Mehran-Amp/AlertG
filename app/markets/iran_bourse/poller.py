# -*- coding: utf-8 -*-
"""
Iranian Bourse — demand-driven poller (IB-5).

* Exactly one gateway request in flight, one request per poll (rule N14): /v1/changes?since=<seq>.
* Polls only while demand exists: an active tsetmc alert, or an app screen touched
  an id within GRACE_SECONDS. Idle => zero requests.
* Errors: back-off 5/10/20/30 s added to the poll interval, never a retry storm.
* Singleton across workers via a file lock (same idea as the crypto poller, own lock file).
* Never started unless IRAN_BOURSE_ENABLED (see server.py hook). Imports nothing from other markets.
"""
import asyncio
import fcntl
import logging
import os
import time
from typing import Callable, Iterable, Optional, Set

import httpx

import app.config as config
from app.markets.iran_bourse.client import BourseClient, BourseError
from app.markets.iran_bourse.snapshot import BourseSnapshotStore

logger = logging.getLogger("signalalert.iran_bourse")

GRACE_SECONDS = 60.0
BACKOFF_STEPS = (5.0, 10.0, 20.0, 30.0)
BOURSE_EXCHANGE = "tsetmc"


def active_alert_ids() -> Set[str]:
    """Instrument ids of active tsetmc alerts (symbol is the id, kept as str)."""
    try:
        from app.storage import ALERTS_DB
        out = set()
        for a in ALERTS_DB:
            if getattr(a, "is_active", False) and (getattr(a, "exchange", "") or "").lower().strip() == BOURSE_EXCHANGE:
                sym = str(getattr(a, "symbol", "") or "").strip()
                if sym:
                    out.add(sym)
        return out
    except Exception as e:
        logger.debug(f"[IranBourse] alert scan failed: {e}")
        return set()


class BoursePoller:
    def __init__(
        self,
        store: Optional[BourseSnapshotStore] = None,
        client: Optional[BourseClient] = None,
        demand_fn: Callable[[], Iterable[str]] = active_alert_ids,
        poll_seconds: Optional[float] = None,
        clock: Callable[[], float] = time.time,
    ):
        self.store = store or BourseSnapshotStore(
            stale_seconds=getattr(config, "IRAN_BOURSE_STALE_SECONDS", 60.0), clock=clock)
        self._client = client
        self._own_http: Optional[httpx.AsyncClient] = None
        self._demand_fn = demand_fn
        self._poll_seconds = max(3.0, float(poll_seconds if poll_seconds is not None
                                            else getattr(config, "IRAN_BOURSE_POLL_SECONDS", 5.0)))
        self._clock = clock
        self._last_touch: float = 0.0
        self._failures = 0
        self._in_flight = False
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._lock_file = None
        self.is_leader = False
        self.requests_made = 0

    # ---- demand ---------------------------------------------------------
    def touch(self, ids: Iterable[str]) -> None:
        """An app screen asked for these ids: keep them and start/continue polling."""
        self.store.touch(ids)
        self._last_touch = self._clock()

    def has_demand(self) -> bool:
        if set(self._demand_fn()):
            return True
        return self._last_touch > 0 and (self._clock() - self._last_touch) <= GRACE_SECONDS

    # ---- one poll -------------------------------------------------------
    def next_backoff(self) -> float:
        if self._failures <= 0:
            return 0.0
        return BACKOFF_STEPS[min(self._failures, len(BACKOFF_STEPS)) - 1]

    def _get_client(self) -> BourseClient:
        if self._client is None:
            self._own_http = httpx.AsyncClient()
            self._client = BourseClient(
                self._own_http,
                config.IRAN_BOURSE_GATEWAY_URL,
                config.IRAN_BOURSE_GATEWAY_KEY,
                timeout=httpx.Timeout(config.IRAN_BOURSE_HTTP_TIMEOUT, connect=3.0),
                allowed_versions=tuple(config.IRAN_BOURSE_ALLOWED_VERSIONS),
                verify_version_every=600.0,
            )
        return self._client

    async def poll_once(self) -> bool:
        """One /v1/changes request. Returns True on success. No-op if one is in flight."""
        if self._in_flight:
            return False
        self._in_flight = True
        try:
            self.store.set_watched(self._demand_fn())
            self.requests_made += 1
            since = self.store.seq
            quotes, meta = await self._get_client().changes(since)
            seq = meta.get("seq")
            if isinstance(seq, int) and seq < self.store.seq:
                # gateway restarted: our cursor is from the future. Refetch everything.
                logger.warning("[IranBourse] gateway seq went backwards (%s < %s): cursor reset",
                               seq, self.store.seq)
                self.store.reset_cursor()
                since = 0
                quotes, meta = await self._get_client().changes(0)
                self.requests_made += 1
            full_ids = {str(q.get("id")) for q in quotes} if since == 0 else None
            self.store.apply(quotes, meta)
            if full_ids is not None:
                await self._reconcile_instruments(full_ids)
            self._failures = 0
            return True
        except asyncio.CancelledError:
            raise
        except (BourseError, Exception) as e:
            self._failures += 1
            self.store.record_error(f"{type(e).__name__}: {e}")
            logger.warning("[IranBourse] poll failed (%s), back-off %.0fs", e, self.next_backoff())
            return False
        finally:
            self._in_flight = False

    async def _reconcile_instruments(self, present_ids: Set[str]) -> None:
        """A full snapshot (since=0) tells us which instruments exist: flag alerts on missing ones."""
        try:
            import app.storage as storage
            from app.markets.iran_bourse.lifecycle import reconcile_missing
            changed = reconcile_missing(storage.ALERTS_DB, present_ids)
            if changed:
                from app.markets.iran_bourse.messages import dispatch_missing_notifications
                import app.state as state
                await dispatch_missing_notifications(changed, client=state.http_client)
                await storage.save_alerts_to_disk_async(storage.ALERTS_DB)
        except Exception as e:
            logger.warning("[IranBourse] instrument reconcile failed: %s", e)

    # ---- loop / lifecycle -----------------------------------------------
    async def _loop(self) -> None:
        while self._running:
            try:
                if self.has_demand():
                    await self.poll_once()
                    delay = self._poll_seconds + self.next_backoff()
                else:
                    delay = 2.0
            except asyncio.CancelledError:
                raise
            except Exception as e:  # never let the loop die
                logger.error("[IranBourse] loop error: %s", e)
                delay = self._poll_seconds
            await asyncio.sleep(delay)

    def _acquire_leader_lock(self) -> bool:
        path = os.path.join(getattr(config, "DATA_DIR", "."), "iran_bourse_poller.lock")
        try:
            self._lock_file = open(path, "w")
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_file.write(f"{os.getpid()}\n")
            self._lock_file.flush()
            self.is_leader = True
            return True
        except (BlockingIOError, OSError):
            self.is_leader = False
            if self._lock_file:
                try:
                    self._lock_file.close()
                except Exception:
                    pass
                self._lock_file = None
            return False

    def _release_leader_lock(self) -> None:
        if self._lock_file:
            try:
                fcntl.flock(self._lock_file, fcntl.LOCK_UN)
                self._lock_file.close()
            except Exception:
                pass
            self._lock_file = None
        self.is_leader = False

    def start(self) -> bool:
        if self._running:
            return True
        if not self._acquire_leader_lock():
            logger.info("[IranBourse] standby worker: lock held by another process")
            return False
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("[IranBourse] poller started (every %.0fs while demand exists)", self._poll_seconds)
        return True

    async def stop(self) -> None:
        self._running = False
        task, self._task = self._task, None
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if self._own_http is not None:
            try:
                await self._own_http.aclose()
            except Exception:
                pass
            self._own_http = None
            self._client = None
        self._release_leader_lock()
        logger.info("[IranBourse] poller stopped")


BOURSE_POLLER: Optional[BoursePoller] = None


def get_poller() -> BoursePoller:
    global BOURSE_POLLER
    if BOURSE_POLLER is None:
        BOURSE_POLLER = BoursePoller()
    return BOURSE_POLLER


def start_bourse_poller() -> bool:
    if not getattr(config, "IRAN_BOURSE_ENABLED", False):
        return False
    return get_poller().start()


async def stop_bourse_poller() -> None:
    if BOURSE_POLLER is not None:
        await BOURSE_POLLER.stop()
