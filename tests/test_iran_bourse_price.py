# -*- coding: utf-8 -*-
"""IB-6: Bourse price path through fetch_price_with_trace. Fake poller client, no network."""
import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock

import httpx

import app.config as config
from app.markets import base
from app.markets.iran_bourse import poller as pmod, price as price_mod, session as session_mod
from app.markets.iran_bourse.client import BourseTimeout
from app.markets.iran_bourse.poller import BoursePoller
from app.markets import limiter as limiter_mod
from app.markets.iran_bourse.snapshot import BourseSnapshotStore

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "iran_bourse")
AYAR = "34144395039913458"


def _q(**kw):
    q = dict(json.load(open(os.path.join(FIX, "changes.json")))["data"][0])
    q.update(kw)
    return q


class Clock:
    t = 1000.0
    def __call__(self): return self.t


class FakeClient:
    def __init__(self, result=None):
        self.result = result if result is not None else (_q(), {"seq": 7, "stale": False})
        self.calls = []
    async def quote(self, iid):
        self.calls.append(iid)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class Base(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.clock = Clock()
        self.fc = FakeClient()
        store = BourseSnapshotStore(60.0, self.clock)
        self.poller = BoursePoller(store=store, client=self.fc, demand_fn=lambda: set(),
                                   poll_seconds=5.0, clock=self.clock)
        sat_1000 = datetime(2026, 11, 14, 6, 30, tzinfo=timezone.utc)   # Saturday 10:00 Tehran
        for p in (patch.object(config, "IRAN_BOURSE_ENABLED", True),
                  patch.object(session_mod, "_now", return_value=sat_1000),
                  patch.dict(limiter_mod.PROVIDER_LIMITERS,
                             {"iran_bourse": limiter_mod.TokenBucketRateLimiter(1000.0, 1000.0)}),
                  patch.object(pmod, "BOURSE_POLLER", self.poller)):
            p.start(); self.addCleanup(p.stop)

    async def call(self, sym=AYAR, ex="tsetmc"):
        async with httpx.AsyncClient() as c:
            return await base.fetch_price_with_trace(c, ex, sym)


class TestPricePath(Base):
    async def test_miss_does_one_on_demand_quote_in_rial(self):
        price, traces = await self.call()
        self.assertEqual(price, 693731.0)               # Rial, untouched (N7)
        self.assertEqual(self.fc.calls, [AYAR])
        t = traces[0]
        self.assertEqual((t["state"], t["currency"], t["source"], t["success"]), ("LIVE", "IRR", "tsetmc-gateway", True))

    async def test_second_call_served_from_snapshot(self):
        await self.call()
        price, traces = await self.call()
        self.assertEqual(price, 693731.0)
        self.assertEqual(len(self.fc.calls), 1)          # no new request
        self.assertTrue(traces[0]["cached_bulk"])

    async def test_on_demand_does_not_move_poll_cursor(self):
        await self.call()
        self.assertEqual(self.poller.store.seq, 0)

    async def test_stale_snapshot_refetches(self):
        await self.call()
        self.clock.t += 61
        await self.call()
        self.assertEqual(len(self.fc.calls), 2)

    async def test_error_without_snapshot_returns_none(self):
        self.fc.result = BourseTimeout("slow")
        price, traces = await self.call()
        self.assertIsNone(price)
        self.assertIn("BourseTimeout", traces[0]["error"])

    async def test_error_with_old_snapshot_never_returns_live_price(self):
        await self.call()
        self.clock.t += 61
        self.fc.result = BourseTimeout("slow")
        price, traces = await self.call()
        self.assertIsNone(price)                          # stale is not a live price
        self.assertEqual(traces[0]["state"], "STALE")

    async def test_gateway_stale_flag_gives_none(self):
        self.fc.result = (_q(), {"seq": 7, "stale": True})
        price, traces = await self.call()
        self.assertIsNone(price)
        self.assertEqual(traces[0]["state"], "STALE")

    async def test_not_traded_today(self):
        self.fc.result = (_q(traded=False), {"seq": 7, "stale": False})
        price, traces = await self.call()
        self.assertIsNone(price)
        self.assertEqual(traces[0]["state"], "NO_TRADE_TODAY")

    async def test_invalid_ids_never_hit_gateway(self):
        for bad in ("", "abc", "123", "1" * 19, "../v1/health"):
            price, traces = await self.call(bad)
            self.assertIsNone(price)
        self.assertEqual(self.fc.calls, [])

    async def test_rate_limited_returns_none_without_request(self):
        with patch("app.markets.limiter.acquire_provider_slot", new=AsyncMock(return_value=False)):
            price, traces = await self.call()
        self.assertIsNone(price)
        self.assertEqual(self.fc.calls, [])

    async def test_provider_kill_switch_blocks_request(self):
        with patch("app.markets.kill_switch.is_provider_killed", return_value=True):
            price, _ = await self.call()
        self.assertIsNone(price)
        self.assertEqual(self.fc.calls, [])

    async def test_category_kill_switch_blocks(self):
        with patch("app.markets.kill_switch.is_category_killed", side_effect=lambda c: c == "iran_bourse"):
            price, traces = await self.call()
        self.assertIsNone(price)
        self.assertEqual(traces[0]["source"], "kill_switch")
        self.assertEqual(self.fc.calls, [])

    async def test_call_touches_poller_demand(self):
        self.assertFalse(self.poller.has_demand())
        await self.call()
        self.assertTrue(self.poller.has_demand())


class TestFlagOffAndIsolation(unittest.IsolatedAsyncioTestCase):
    async def test_flag_off_no_client_no_poller_no_fallthrough(self):
        with patch.object(config, "IRAN_BOURSE_ENABLED", False), \
             patch.object(pmod, "BOURSE_POLLER", None), \
             patch("app.markets.base.fetch_crypto", new=AsyncMock()) as crypto, \
             patch("app.markets.base.fetch_iran", new=AsyncMock()) as iran, \
             patch("app.markets.base.fetch_global_stocks", new=AsyncMock()) as stocks:
            async with httpx.AsyncClient() as c:
                price, traces = await base.fetch_price_with_trace(c, "tsetmc", AYAR)
            self.assertIsNone(price)
            self.assertEqual(traces[0]["state"], "disabled")
            self.assertIsNone(pmod.BOURSE_POLLER)
            for m in (crypto, iran, stocks):
                m.assert_not_called()

    async def test_bourse_never_reaches_other_markets(self):
        poller = BoursePoller(client=FakeClient(), demand_fn=lambda: set())
        with patch.object(config, "IRAN_BOURSE_ENABLED", True), \
             patch.object(pmod, "BOURSE_POLLER", poller), \
             patch("app.markets.base.fetch_crypto", new=AsyncMock()) as crypto, \
             patch("app.markets.base.fetch_iran", new=AsyncMock()) as iran, \
             patch("app.markets.base.fetch_global_stocks", new=AsyncMock()) as stocks:
            async with httpx.AsyncClient() as c:
                await base.fetch_price_with_trace(c, "tsetmc", AYAR)
            for m in (crypto, iran, stocks):
                m.assert_not_called()

    async def test_other_markets_do_not_touch_bourse(self):
        with patch.object(config, "IRAN_BOURSE_ENABLED", True), \
             patch.object(price_mod, "fetch_bourse_price", new=AsyncMock()) as fb, \
             patch("app.markets.base.fetch_crypto", new=AsyncMock(return_value=None)), \
             patch("app.markets.base.fetch_iran", new=AsyncMock(return_value=None)), \
             patch("app.markets.base.fetch_global_stocks", new=AsyncMock(return_value=None)):
            async with httpx.AsyncClient() as c:
                for ex, sym in [("binance", "BTCUSDT"), ("nobitex", "USDTIRT"), ("stocks", "AAPL"),
                                ("tse", "FOLD"), ("bonbast", "USD"), ("okx", "BTCUSDT")]:
                    await base.fetch_price_with_trace(c, ex, sym)
            fb.assert_not_called()


if __name__ == "__main__":
    unittest.main()
