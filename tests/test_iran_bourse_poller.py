# -*- coding: utf-8 -*-
"""IB-5: Bourse snapshot store + poller. Fake client/clock, no network."""
import asyncio
import json
import os
import unittest
from unittest.mock import patch, AsyncMock

from app.markets.iran_bourse import poller as pmod
from app.markets.iran_bourse.client import BourseTimeout, BourseConnectionError
from app.markets.iran_bourse.poller import BoursePoller
from app.markets.iran_bourse.snapshot import BourseSnapshotStore, RECENT_LIMIT

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "iran_bourse")
AYAR = "34144395039913458"


def _quote(i=AYAR):
    q = json.load(open(os.path.join(FIX, "changes.json")))["data"][0]
    q = dict(q)
    q["id"] = str(i)
    return q


class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


class FakeClient:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])
        self.gate = None
    async def changes(self, since=0):
        self.calls.append(since)
        if self.gate:
            await self.gate.wait()
        r = self.responses.pop(0) if self.responses else ([_quote()], {"seq": 5, "stale": False})
        if isinstance(r, Exception):
            raise r
        return r


def mk(demand, client=None, clock=None):
    clock = clock or Clock()
    store = BourseSnapshotStore(60.0, clock)
    return BoursePoller(store=store, client=client or FakeClient(), demand_fn=lambda: demand,
                        poll_seconds=5.0, clock=clock), clock


class TestSnapshot(unittest.TestCase):
    def test_only_wanted_ids_kept(self):
        s = BourseSnapshotStore(60, Clock())
        s.set_watched([AYAR])
        n = s.apply([_quote(), _quote("111111111111111")], {"seq": 3})
        self.assertEqual(n, 1)
        self.assertIsNotNone(s.get(AYAR))
        self.assertIsNone(s.get("111111111111111"))
        self.assertEqual(s.seq, 3)

    def test_stale_by_age_and_by_gateway(self):
        c = Clock(); s = BourseSnapshotStore(60, c)
        self.assertTrue(s.is_stale())  # never succeeded
        s.set_watched([AYAR]); s.apply([_quote()], {"seq": 1})
        self.assertFalse(s.is_stale())
        c.t += 61
        self.assertTrue(s.is_stale())
        self.assertTrue(s.get(AYAR)["stale"])
        s.apply([_quote()], {"seq": 2, "stale": True})
        self.assertTrue(s.is_stale())

    def test_lru_limit(self):
        s = BourseSnapshotStore(60, Clock())
        s.touch([str(10**15 + i) for i in range(RECENT_LIMIT + 50)])
        self.assertEqual(s.stats()["recent"], RECENT_LIMIT)
        self.assertNotIn(str(10**15), s.wanted())            # oldest evicted
        self.assertIn(str(10**15 + RECENT_LIMIT + 49), s.wanted())

    def test_watched_never_evicted_by_lru(self):
        s = BourseSnapshotStore(60, Clock())
        s.set_watched([AYAR]); s.apply([_quote()], {"seq": 1})
        s.touch([str(10**15 + i) for i in range(RECENT_LIMIT + 5)])
        self.assertIsNotNone(s.get(AYAR))

    def test_ids_are_strings(self):
        s = BourseSnapshotStore(60, Clock())
        s.set_watched([int(AYAR)])
        s.apply([_quote()], {"seq": 1})
        self.assertIsNotNone(s.get(AYAR))

    def test_reset_cursor(self):
        s = BourseSnapshotStore(60, Clock()); s.apply([], {"seq": 9})
        s.reset_cursor()
        self.assertEqual((s.seq, s.resets), (0, 1))


class TestPoller(unittest.IsolatedAsyncioTestCase):
    async def test_poll_stores_and_advances_cursor(self):
        p, _ = mk({AYAR})
        self.assertTrue(await p.poll_once())
        self.assertEqual(p._client.calls, [0])
        self.assertEqual(p.store.seq, 5)
        self.assertIsNotNone(p.store.get(AYAR))
        await p.poll_once()
        self.assertEqual(p._client.calls, [0, 5])  # since=<seq>

    async def test_one_request_per_poll_and_single_flight(self):
        fc = FakeClient(); fc.gate = asyncio.Event()
        p, _ = mk({AYAR}, fc)
        t1 = asyncio.create_task(p.poll_once())
        await asyncio.sleep(0)
        self.assertFalse(await p.poll_once())      # second caller refused while first in flight
        fc.gate.set()
        self.assertTrue(await t1)
        self.assertEqual(len(fc.calls), 1)

    async def test_backoff_timeline_and_reset(self):
        errs = [BourseTimeout("t"), BourseConnectionError("c"), BourseTimeout("t"),
                BourseTimeout("t"), BourseTimeout("t")]
        p, _ = mk({AYAR}, FakeClient(errs))
        seen = []
        for _ in range(5):
            self.assertFalse(await p.poll_once())
            seen.append(p.next_backoff())
        self.assertEqual(seen, [5.0, 10.0, 20.0, 30.0, 30.0])   # capped at 30
        self.assertIn("BourseTimeout", p.store.stats()["last_error"])
        self.assertTrue(await p.poll_once())
        self.assertEqual(p.next_backoff(), 0.0)

    async def test_failure_keeps_old_quote_and_goes_stale(self):
        p, c = mk({AYAR}, FakeClient([([_quote()], {"seq": 1}), BourseTimeout("x")]))
        await p.poll_once(); await p.poll_once()
        c.t += 61
        got = p.store.get(AYAR)
        self.assertIsNotNone(got)
        self.assertTrue(got["stale"])

    async def test_gateway_reload_resets_cursor(self):
        fc = FakeClient([([_quote()], {"seq": 100}), ([], {"seq": 3}), ([_quote()], {"seq": 3})])
        p, _ = mk({AYAR}, fc)
        await p.poll_once()
        await p.poll_once()           # seq 3 < 100 -> reset, immediate full refetch
        self.assertEqual(fc.calls, [0, 100, 0])
        self.assertEqual(p.store.resets, 1)
        self.assertEqual(p.store.seq, 3)

    async def test_demand_alert_touch_grace(self):
        demand = set()
        p, c = mk(demand)
        self.assertFalse(p.has_demand())
        demand.add(AYAR); self.assertTrue(p.has_demand())
        demand.clear(); self.assertFalse(p.has_demand())
        p.touch([AYAR]); self.assertTrue(p.has_demand())
        c.t += 59; self.assertTrue(p.has_demand())
        c.t += 2;  self.assertFalse(p.has_demand())       # 60 s grace over

    async def test_idle_loop_makes_zero_requests(self):
        fc = FakeClient()
        p, _ = mk(set(), fc)
        p._running = True
        with patch.object(pmod.asyncio, "sleep", new=AsyncMock(side_effect=[None, asyncio.CancelledError()])):
            with self.assertRaises(asyncio.CancelledError):
                await p._loop()
        self.assertEqual(fc.calls, [])

    async def test_loop_polls_with_demand_and_survives_errors(self):
        fc = FakeClient([BourseTimeout("x"), ([_quote()], {"seq": 2})])
        p, _ = mk({AYAR}, fc)
        p._running = True
        sleeps = []
        async def fake_sleep(d):
            sleeps.append(d)
            if len(sleeps) == 2:
                raise asyncio.CancelledError()
        with patch.object(pmod.asyncio, "sleep", new=fake_sleep):
            with self.assertRaises(asyncio.CancelledError):
                await p._loop()
        self.assertEqual(sleeps, [5.0 + 5.0, 5.0])   # first failed (+5 s back-off), then ok
        self.assertEqual(len(fc.calls), 2)

    async def test_poll_seconds_floor(self):
        p = BoursePoller(demand_fn=lambda: set(), poll_seconds=1.0)
        self.assertEqual(p._poll_seconds, 3.0)

    async def test_start_stop_leader_lock_and_cancel(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d, patch.object(pmod.config, "DATA_DIR", d):
            a = BoursePoller(demand_fn=lambda: set()); b = BoursePoller(demand_fn=lambda: set())
            self.assertTrue(a.start())
            self.assertFalse(b.start())                      # standby: lock held
            self.assertIsNone(b._task)
            task = a._task
            await a.stop()
            self.assertTrue(task.done())
            self.assertFalse(a.is_leader)
            self.assertTrue(b.start())                       # lock free again
            await b.stop()

    async def test_flag_off_means_no_task_no_poller(self):
        with patch.object(pmod.config, "IRAN_BOURSE_ENABLED", False), \
             patch.object(pmod, "BOURSE_POLLER", None):
            self.assertFalse(pmod.start_bourse_poller())
            self.assertIsNone(pmod.BOURSE_POLLER)


class TestLifespanHook(unittest.IsolatedAsyncioTestCase):
    async def _run(self, flag):
        import server
        from server import app, lifespan
        stopped = AsyncMock()
        with patch("server._run_background_crypto_catalog_sync", new_callable=AsyncMock), \
             patch("server._run_background_market_refresh", new_callable=AsyncMock), \
             patch("server.outbox_worker_loop", new_callable=AsyncMock), \
             patch.object(server.config, "IRAN_BOURSE_ENABLED", flag), \
             patch.object(pmod, "start_bourse_poller", return_value=True) as st, \
             patch.object(pmod, "stop_bourse_poller", new=stopped):
            async with lifespan(app):
                pass
        return st.call_count, stopped.await_count

    async def test_flag_off_not_started(self):
        self.assertEqual(await self._run(False), (0, 0))

    async def test_flag_on_started_and_stopped(self):
        self.assertEqual(await self._run(True), (1, 1))


if __name__ == "__main__":
    unittest.main()
