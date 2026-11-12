# -*- coding: utf-8 -*-
"""IB-8: alert semantics on Bourse data. Replayed sequences through the real checker."""
import json
import os
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import httpx

import app.config as config
from app.engine import checker
from app.markets import limiter as limiter_mod
from app.markets.iran_bourse import poller as pmod, session as session_mod
from app.markets.iran_bourse.alert_rules import rule_inputs, within_limits, meta_extras
from app.markets.iran_bourse.poller import BoursePoller
from app.markets.iran_bourse.snapshot import BourseSnapshotStore
from app.models import Alert
from app.state import PRICE_CACHE

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "iran_bourse")
AYAR = "34144395039913458"
KEY = f"tsetmc:{AYAR}"
SAT_1000 = datetime(2026, 11, 14, 6, 30, tzinfo=timezone.utc)      # Saturday 10:00 Tehran
THU_1000 = datetime(2026, 11, 12, 6, 30, tzinfo=timezone.utc)


def _q(**kw):
    q = dict(json.load(open(os.path.join(FIX, "changes.json")))["data"][0])
    q.update(kw)
    return q


def mk_alert(**kw):
    d = dict(id="a1", user_id="u1", exchange="tsetmc", symbol=AYAR, target_price=700000.0,
             condition="ABOVE", trigger_mode="oneShot", check_interval_seconds=30,
             is_active=True, last_checked_at=0.0)
    d.update(kw)
    return Alert(**d)


def trace(price, state="LIVE", asof=1000, **extra):
    t = {"source": "tsetmc-gateway", "url": "", "status_code": 200, "latency_ms": 1.0,
         "success": state == "LIVE", "currency": "IRR", "parsed_price": price, "asOf": asof,
         "state": state, "alert_eligible": state == "LIVE", "prev_close": 685477.0, "close": 693152.0,
         "lower_limit": 616930, "upper_limit": 754024}
    t.update(extra)
    return t


class Replay(unittest.IsolatedAsyncioTestCase):
    """Feed (price, traces) tuples to the real get_cached_price/evaluate_ready_alerts."""
    def setUp(self):
        PRICE_CACHE.pop(KEY, None)
        self.push = AsyncMock()
        for p in (patch.object(checker, "enqueue_alert_push", self.push),
                  patch.object(checker, "save_alerts_to_disk_async", AsyncMock()),
                  patch.object(checker, "get_category_cache_ttl", return_value=0.0)):
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(lambda: PRICE_CACHE.pop(KEY, None))

    async def run_seq(self, alert, seq, step=60.0):
        """seq: list of (price, state). One evaluation per item, current_time advancing by step."""
        t = 10_000.0
        for i, item in enumerate(seq):
            price, state = item[0], item[1]
            extra = item[2] if len(item) > 2 else {}
            res = (price if state == "LIVE" else None, [trace(price, state, asof=1000 + i, **extra)])
            with patch.object(checker, "fetch_price_with_trace", new=AsyncMock(return_value=res)):
                alert.last_checked_at = 0.0
                await checker.evaluate_ready_alerts(None, [alert], t)
            t += step
        return self.push.await_count

    async def test_one_trigger_per_crossing_oneshot(self):
        a = mk_alert()
        n = await self.run_seq(a, [(690000, "LIVE"), (695000, "LIVE"), (701000, "LIVE"),
                                   (702000, "LIVE"), (699000, "LIVE"), (705000, "LIVE")])
        self.assertEqual(n, 1)
        self.assertFalse(a.is_active)

    async def test_below_crossing(self):
        a = mk_alert(condition="BELOW", target_price=690000.0)
        n = await self.run_seq(a, [(695000, "LIVE"), (691000, "LIVE"), (689000, "LIVE"), (688000, "LIVE")])
        self.assertEqual(n, 1)

    async def test_no_crossing_no_trigger(self):
        n = await self.run_seq(mk_alert(), [(690000, "LIVE"), (695000, "LIVE"), (699999, "LIVE")])
        self.assertEqual(n, 0)

    async def test_stale_closed_notrade_never_trigger(self):
        for st in ("STALE", "CLOSED", "NO_TRADE_TODAY", "no_data"):
            self.push.reset_mock(); PRICE_CACHE.pop(KEY, None)
            n = await self.run_seq(mk_alert(), [(690000, "LIVE"), (710000, st), (720000, st)])
            self.assertEqual(n, 0, st)

    async def test_recovers_after_stale_then_triggers_once(self):
        n = await self.run_seq(mk_alert(), [(690000, "LIVE"), (710000, "STALE"), (710000, "CLOSED"),
                                            (710000, "LIVE"), (712000, "LIVE")])
        self.assertEqual(n, 1)

    async def test_recurring_cooldown_unchanged(self):
        a = mk_alert(trigger_mode="recurring", check_interval_seconds=300)
        n = await self.run_seq(a, [(690000, "LIVE"), (701000, "LIVE"), (702000, "LIVE")], step=60.0)
        self.assertEqual(n, 1)                                    # 60 s later is inside the 300 s cooldown
        self.assertTrue(a.is_active)

    async def test_price_field_close(self):
        a = mk_alert(target_price=693000.0, raw_rule={"price_field": "close"})
        # last 692000 (below target) but close 693152 (above): close is what is compared
        n = await self.run_seq(a, [(690000, "LIVE", {"close": 690000.0}), (692000, "LIVE", {"close": 693152.0})])
        self.assertEqual(n, 1)
        PRICE_CACHE.pop(KEY, None); self.push.reset_mock()
        b = mk_alert(target_price=693000.0)                        # default 'last'
        self.assertEqual(await self.run_seq(b, [(690000, "LIVE"), (692000, "LIVE", {"close": 693152.0})]), 0)

    async def test_percent_change_uses_yesterday_vambat(self):
        # وبملت: yesterday 1393, last 1434 -> +2.94 %
        self.assertEqual(round((1434 - 1393) / 1393 * 100, 2), 2.94)
        ex = {"prev_close": 1393.0, "lower_limit": 1000, "upper_limit": 2000}
        hit = mk_alert(condition_type="percentChange", percent=2.9, base_price=999999.0, target_price=0.0)
        self.assertEqual(await self.run_seq(hit, [(1434, "LIVE", ex)]), 1)      # base_price is ignored
        PRICE_CACHE.pop(KEY, None); self.push.reset_mock()
        miss = mk_alert(condition_type="percentChange", percent=3.0, base_price=1.0, target_price=0.0)
        self.assertEqual(await self.run_seq(miss, [(1434, "LIVE", ex)]), 0)
        PRICE_CACHE.pop(KEY, None); self.push.reset_mock()
        down = mk_alert(condition_type="percentChange", condition="BELOW", percent=2.0, base_price=1.0, target_price=0.0)
        self.assertEqual(await self.run_seq(down, [(1393, "LIVE", ex), (1365, "LIVE", ex)]), 1)   # 1393*0.98=1365.14

    async def test_absolute_change_uses_yesterday(self):
        ex = {"prev_close": 1393.0, "lower_limit": 1000, "upper_limit": 2000}
        a = mk_alert(condition_type="absolutePriceChange", delta_absolute=40.0, base_price=5.0, target_price=0.0)
        self.assertEqual(await self.run_seq(a, [(1420, "LIVE", ex), (1425, "LIVE", ex)]), 0)   # +32 < +40
        PRICE_CACHE.pop(KEY, None); self.push.reset_mock()
        b = mk_alert(condition_type="absolutePriceChange", delta_absolute=40.0, base_price=5.0, target_price=0.0)
        self.assertEqual(await self.run_seq(b, [(1420, "LIVE", ex), (1434, "LIVE", ex)]), 1)   # 1393+40=1433

    async def test_other_markets_ignore_bourse_rules(self):
        # same fields on an alert of another market: base_price/percent behave exactly as before
        a = mk_alert(exchange="binance", symbol="BTCUSDT", condition_type="percentChange", percent=2.0,
                     base_price=100.0, target_price=0.0)
        a_key = "binance:BTCUSDT"; PRICE_CACHE.pop(a_key, None)
        tr = {"source": "binance", "success": True, "parsed_price": 103.0, "asOf": 5, "state": "LIVE",
              "currency": "USDT", "prev_close": 1.0}
        with patch.object(checker, "fetch_price_with_trace", new=AsyncMock(return_value=(103.0, [tr]))):
            await checker.evaluate_ready_alerts(None, [a], 10_000.0)
        self.assertEqual(self.push.await_count, 1)                 # base 100, +3 % >= +2 %
        PRICE_CACHE.pop(a_key, None)


class Outlier(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        PRICE_CACHE.clear()
        for p in (patch.object(checker, "get_category_cache_ttl", return_value=0.0),
                  patch.object(checker, "get_category_outlier_threshold", return_value=0.01)):
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(PRICE_CACHE.clear)

    async def two(self, ex, sym, p1, p2, extra):
        calls = [(p1, [trace(p1, **extra)]), (p2, [trace(p2, **extra)])]
        with patch.object(checker, "fetch_price_with_trace", new=AsyncMock(side_effect=calls)):
            await checker.get_cached_price(None, ex, sym)
            return await checker.get_cached_price(None, ex, sym)

    async def test_inside_limits_never_held(self):
        out = await self.two("tsetmc", AYAR, 693000.0, 740000.0, {})   # +6.8 % > 1 %, but inside limits
        self.assertEqual(out, 740000.0)

    async def test_outside_limits_held_until_confirmed(self):
        out = await self.two("tsetmc", AYAR, 693000.0, 800000.0, {})   # above upper_limit 754024
        self.assertEqual(out, 693000.0)

    async def test_other_market_still_filtered(self):
        extra = {"lower_limit": 1, "upper_limit": 10**9}                 # limits present but market is not Bourse
        out = await self.two("stocks", "AAPL", 100.0, 200.0, extra)
        self.assertEqual(out, 100.0)


class Helpers(unittest.TestCase):
    def test_within_limits(self):
        self.assertTrue(within_limits(700000, [trace(700000)]))
        self.assertFalse(within_limits(800000, [trace(800000)]))
        self.assertFalse(within_limits(700000, [trace(700000, lower_limit=None)]))
        self.assertFalse(within_limits(700000, []))

    def test_rule_inputs_defaults_untouched(self):
        a = mk_alert()
        self.assertEqual(rule_inputs(a, 5.0, {}, "priceThreshold", None, None), (5.0, "priceThreshold", None, None))

    def test_meta_extras(self):
        self.assertEqual(set(meta_extras(trace(1))) - {"alert_eligible"},
                         {"prev_close", "close", "lower_limit", "upper_limit"})


class AsOfAndNoTrade(unittest.IsolatedAsyncioTestCase):
    """Full real chain: poller snapshot -> price.py -> checker. A stock with no trade for 2 h is evaluated."""
    def setUp(self):
        PRICE_CACHE.pop(KEY, None)
        class FC:
            async def quote(s, iid):
                now = datetime.now(timezone.utc)
                q = _q(update_time="08:40:00", last=701000, traded=True)   # last trade ~2 h ago
                return q, {"seq": 7, "stale": False, "updated_at": now.isoformat()}
        self.poller = BoursePoller(store=BourseSnapshotStore(60.0), client=FC(), demand_fn=lambda: set(), poll_seconds=5.0)
        self.push = AsyncMock()
        self.now = {"v": SAT_1000}
        for p in (patch.object(config, "IRAN_BOURSE_ENABLED", True),
                  patch.object(pmod, "BOURSE_POLLER", self.poller),
                  patch.object(session_mod, "_now", side_effect=lambda: self.now["v"]),
                  patch.dict(limiter_mod.PROVIDER_LIMITERS, {"iran_bourse": limiter_mod.TokenBucketRateLimiter(1000.0, 1000.0)}),
                  patch.object(checker, "enqueue_alert_push", self.push),
                  patch.object(checker, "save_alerts_to_disk_async", AsyncMock()),
                  patch.object(checker, "get_category_cache_ttl", return_value=0.0)):
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(lambda: PRICE_CACHE.pop(KEY, None))

    async def test_asof_is_fetch_time_not_trade_time_and_still_evaluated(self):
        import time
        async with httpx.AsyncClient() as c:
            price, traces = await checker.fetch_price_with_trace(c, "tsetmc", AYAR)
        tr = traces[0]
        self.assertEqual(price, 701000.0)
        self.assertLess(abs(tr["asOf"] - time.time()), 5)              # gateway fetch time
        self.assertEqual(tr["last_trade_time"], "08:40:00")            # separate field
        self.assertFalse(checker.is_data_stale(tr["asOf"], None, time.time()))
        a = mk_alert(target_price=700000.0)
        a.last_eval_price = 690000.0                                   # previously below: a real crossing
        async with httpx.AsyncClient() as c:
            await checker.evaluate_ready_alerts(c, [a], time.time())
        self.assertEqual(self.push.await_count, 1)

    async def test_closed_session_blocks_trigger_in_real_chain(self):
        import time
        self.now["v"] = THU_1000
        a = mk_alert(target_price=700000.0); a.last_eval_price = 690000.0
        async with httpx.AsyncClient() as c:
            await checker.evaluate_ready_alerts(c, [a], time.time())
        self.assertEqual(self.push.await_count, 0)


if __name__ == "__main__":
    unittest.main()
