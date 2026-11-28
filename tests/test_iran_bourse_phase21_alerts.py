# -*- coding: utf-8 -*-
"""Phase 21 (21c & 21e): Iranian Bourse queueBuy, queueSell, and volumeAbove tests."""
import asyncio
import json
import os
import types
import unittest
from unittest.mock import AsyncMock, patch

from app.markets.iran_bourse.alert_rules import (
    EXTRA_KEYS,
    evaluate_special_alert,
    is_bourse_special_alert,
    is_buy_queue,
    is_sell_queue,
    is_volume_above,
    meta_extras,
    min_queue_volume_of,
)
from app.markets.iran_bourse.mapping import quote_to_price_result
from app.markets.iran_bourse.messages import (
    alert_category_of,
    format_shares,
    telegram_registered,
    trigger_display,
    trigger_payload,
)

REAL_FIX = os.path.join(os.path.dirname(__file__), "fixtures", "iran_bourse", "real")


def _load_real(name):
    with open(os.path.join(REAL_FIX, name), encoding="utf-8") as f:
        return json.load(f)


def _alert(**kw):
    base = dict(
        id="p21-1",
        user_id="u1",
        exchange="tsetmc",
        symbol="37389789764168256",
        market_symbol="توریل",
        condition="ABOVE",
        condition_type="queueBuy",
        target_price=0.0,
        language="fa",
        note=None,
        raw_rule={},
        waiting_for_cross=False,
        last_eval_price=None,
        is_active=True,
        trigger_mode="oneShot",
    )
    base.update(kw)
    return types.SimpleNamespace(**base)


def _live_meta(**overrides):
    base = {
        "state": "LIVE",
        "alert_eligible": True,
        "traded_today": True,
        "is_stale": False,
        "upper_limit": 4210,
        "lower_limit": 3970,
        "best_bid": {"price": 4210, "volume": 3358402, "orders": 24},
        "best_ask": None,
        "queue": "buy",
        "volume": 37782645,
        "ticker": "توریل",
        "name": "توکاریل",
        "prev_close": 4090,
    }
    base.update(overrides)
    return base


class Phase21MappingAndPureRulesTests(unittest.TestCase):
    def test_mapping_passes_best_bid_and_best_ask_and_meta_extras_keeps_them(self):
        env = _load_real("quote_ayar.json")
        res = quote_to_price_result(env["data"], env["meta"])
        self.assertIn("best_bid", res)
        self.assertIn("best_ask", res)
        self.assertEqual(res["best_bid"], env["data"]["best_bid"])
        self.assertEqual(res["best_ask"], env["data"]["best_ask"])
        for k in ("queue", "best_bid", "best_ask", "volume", "traded_today"):
            self.assertIn(k, EXTRA_KEYS)
        extras = meta_extras(res)
        self.assertEqual(extras["best_bid"], env["data"]["best_bid"])
        self.assertEqual(extras["volume"], env["data"]["volume"])
        self.assertEqual(extras["traded_today"], env["data"]["traded"])

    def test_real_gateway_captures_buy_sell_and_false_positives(self):
        changes = _load_real("changes_reload_trimmed.json")["data"]
        by_ticker = {q["ticker"]: q for q in changes}
        symbols = _load_real("symbols.json")["data"]
        for q in symbols:
            if q.get("ticker") == "معیار":
                by_ticker["معیار"] = q
                break

        def to_live(ticker):
            q = by_ticker[ticker]
            r = quote_to_price_result(q, {"stale": False, "local_as_of": 1795000000})
            r["alert_eligible"] = r["state"] == "LIVE"
            return r

        # Real buy queues (both best_ask=None and out-of-band best_ask > upper_limit)
        for t in ("خگلپا", "توریل", "ثمسکن", "زبینا", "وسپهر"):
            m = to_live(t)
            self.assertTrue(is_buy_queue(m), msg=f"expected buy queue for {t}")
            self.assertFalse(is_sell_queue(m), msg=f"unexpected sell queue for {t}")

        # Real sell queues (traded today)
        for t in ("فجهانح", "ضخود9058", "ضسپا8088", "ضسپا8089"):
            m = to_live(t)
            self.assertTrue(is_sell_queue(m), msg=f"expected sell queue for {t}")
            self.assertFalse(is_buy_queue(m), msg=f"unexpected buy queue for {t}")

        # Untraded symbol with gateway queue="sell" MUST NOT fire
        untraded = to_live("ضسپا8090")
        self.assertFalse(is_sell_queue(untraded))
        self.assertFalse(is_buy_queue(untraded))

        # Traded at upper_limit (last == 2590) with ask still at 2590 MUST NOT fire
        meyar = to_live("معیار")
        self.assertEqual(meyar["price"], meyar["upper_limit"])
        self.assertFalse(is_buy_queue(meyar))
        self.assertFalse(is_sell_queue(meyar))

    def test_buy_queue_min_volume_and_guards(self):
        m = _live_meta()
        self.assertTrue(is_buy_queue(m, min_queue_volume=3_000_000))
        self.assertFalse(is_buy_queue(m, min_queue_volume=4_000_000))
        # Closed / stale / untraded / missing limits never fire
        self.assertFalse(is_buy_queue(_live_meta(state="CLOSED")))
        self.assertFalse(is_buy_queue(_live_meta(state="STALE")))
        self.assertFalse(is_buy_queue(_live_meta(alert_eligible=False)))
        self.assertFalse(is_buy_queue(_live_meta(traded_today=False)))
        self.assertFalse(is_buy_queue(_live_meta(upper_limit=None)))
        self.assertFalse(is_buy_queue(_live_meta(best_bid=None)))
        # Fillable ask at upper_limit disqualifies buy queue
        self.assertFalse(is_buy_queue(_live_meta(best_ask={"price": 4210, "volume": 100, "orders": 1})))
        # Out-of-band ask above upper_limit is allowed
        self.assertTrue(is_buy_queue(_live_meta(best_ask={"price": 4250, "volume": 100, "orders": 1})))

    def test_sell_queue_min_volume_and_guards(self):
        m = _live_meta(
            upper_limit=2966,
            lower_limit=2794,
            best_bid=None,
            best_ask={"price": 2794, "volume": 4_930_693, "orders": 1},
            queue="sell",
        )
        self.assertTrue(is_sell_queue(m))
        self.assertTrue(is_sell_queue(m, min_queue_volume=4_000_000))
        self.assertFalse(is_sell_queue(m, min_queue_volume=5_000_000))
        # Out-of-band bid below lower_limit is allowed
        self.assertTrue(is_sell_queue({**m, "best_bid": {"price": 2750, "volume": 500, "orders": 1}}))
        # Fillable bid at lower_limit disqualifies sell queue
        self.assertFalse(is_sell_queue({**m, "best_bid": {"price": 2794, "volume": 500, "orders": 1}}))
        self.assertFalse(is_sell_queue({**m, "state": "CLOSED"}))
        self.assertFalse(is_sell_queue({**m, "lower_limit": 0}))

    def test_volume_above_rules_and_guards(self):
        m = _live_meta(volume=5_000_000)
        self.assertTrue(is_volume_above(m, 5_000_000))
        self.assertTrue(is_volume_above(m, 4_500_000))
        self.assertFalse(is_volume_above(m, 5_000_001))
        self.assertFalse(is_volume_above(m, 0))
        self.assertFalse(is_volume_above(m, -10))
        self.assertFalse(is_volume_above(_live_meta(volume=5_000_000, state="CLOSED"), 1_000_000))
        self.assertFalse(is_volume_above(_live_meta(volume=5_000_000, traded_today=False), 1_000_000))

    def test_edge_triggered_queue_replay_entering_staying_leaving_reentering(self):
        alert = _alert(condition_type="queueBuy", trigger_mode="recurring")
        normal = _live_meta(
            best_bid={"price": 4100, "volume": 1000, "orders": 1},
            best_ask={"price": 4120, "volume": 1000, "orders": 1},
            queue=None,
        )
        in_queue = _live_meta()

        # 1. Not in queue yet -> no trigger
        trig, _, _ = evaluate_special_alert(alert, 4100, normal)
        self.assertFalse(trig)
        self.assertFalse(alert.waiting_for_cross)

        # 2. Enters buy queue -> fires once and arms edge guard
        trig, is_above, target = evaluate_special_alert(alert, 4210, in_queue)
        self.assertTrue(trig)
        self.assertTrue(is_above)
        self.assertEqual(target, 4210.0)
        self.assertTrue(alert.waiting_for_cross)

        # 3. Stays in buy queue -> MUST NOT fire again
        trig, _, _ = evaluate_special_alert(alert, 4210, in_queue)
        self.assertFalse(trig)
        self.assertTrue(alert.waiting_for_cross)

        # 4. Leaves buy queue -> re-arms without firing
        trig, _, _ = evaluate_special_alert(alert, 4150, normal)
        self.assertFalse(trig)
        self.assertFalse(alert.waiting_for_cross)

        # 5. Re-enters buy queue -> fires again
        trig, is_above, _ = evaluate_special_alert(alert, 4210, in_queue)
        self.assertTrue(trig)
        self.assertTrue(is_above)
        self.assertTrue(alert.waiting_for_cross)

    def test_edge_triggered_volume_above_fires_once_until_reset(self):
        alert = _alert(condition_type="volumeAbove", target_price=10_000_000, trigger_mode="recurring")
        trig, _, _ = evaluate_special_alert(alert, 4200, _live_meta(volume=9_000_000))
        self.assertFalse(trig)

        trig, is_above, target = evaluate_special_alert(alert, 4200, _live_meta(volume=10_500_000))
        self.assertTrue(trig)
        self.assertTrue(is_above)
        self.assertIsNone(target)
        self.assertTrue(alert.waiting_for_cross)

        # Still above threshold -> no repeat fire
        trig, _, _ = evaluate_special_alert(alert, 4205, _live_meta(volume=12_000_000))
        self.assertFalse(trig)

        # Next trading day volume resets below threshold -> re-arms
        trig, _, _ = evaluate_special_alert(alert, 4190, _live_meta(volume=500_000))
        self.assertFalse(trig)
        self.assertFalse(alert.waiting_for_cross)

    def test_special_alert_guard_ignores_other_exchanges(self):
        self.assertTrue(is_bourse_special_alert(_alert(exchange="tsetmc", condition_type="queueBuy")))
        self.assertTrue(is_bourse_special_alert(_alert(exchange="tsetmc", condition_type="queueSell")))
        self.assertTrue(is_bourse_special_alert(_alert(exchange="tsetmc", condition_type="volumeAbove")))
        self.assertFalse(is_bourse_special_alert(_alert(exchange="binance", condition_type="queueBuy")))
        self.assertFalse(is_bourse_special_alert(_alert(exchange="tsetmc", condition_type="priceThreshold")))
        self.assertEqual(min_queue_volume_of(_alert(raw_rule={"min_queue_volume": 250000})), 250000.0)
        self.assertIsNone(min_queue_volume_of(_alert(raw_rule={"min_queue_volume": 0})))

    def test_messages_formatting_for_queue_and_volume(self):
        self.assertEqual(format_shares(5_000_000, "fa"), "5,000,000 سهم")
        self.assertEqual(format_shares(5_000_000, "en"), "5,000,000 shares")

        a_buy = _alert(condition_type="queueBuy", raw_rule={"min_queue_volume": 2_000_000})
        reg_buy = telegram_registered(a_buy)
        self.assertIn("صف خرید", reg_buy)
        self.assertIn("2,000,000 سهم", reg_buy)
        _, disp_buy = trigger_display(a_buy, _live_meta(), 4210)
        self.assertIn("صف خرید", disp_buy)
        self.assertIn("4,210 ریال", disp_buy)

        a_sell = _alert(condition_type="queueSell")
        self.assertIn("صف فروش", telegram_registered(a_sell))
        _, disp_sell = trigger_display(a_sell, _live_meta(), 3970)
        self.assertIn("صف فروش", disp_sell)

        a_vol = _alert(condition_type="volumeAbove", target_price=15_000_000)
        self.assertIn("15,000,000 سهم", telegram_registered(a_vol))
        _, disp_vol = trigger_display(a_vol, _live_meta(volume=16_200_000), 4200)
        self.assertIn("16,200,000 سهم", disp_vol)

    def test_phase24d_payload_category_and_sound_fields_for_queue_and_volume(self):
        self.assertEqual(alert_category_of("queueBuy"), "queue")
        self.assertEqual(alert_category_of("queueSell"), "queue")
        self.assertEqual(alert_category_of("volumeAbove"), "volume")
        self.assertEqual(alert_category_of("priceThreshold"), "price")

        p_buy = trigger_payload(_alert(condition_type="queueBuy"), _live_meta())
        self.assertEqual(p_buy["condition_type"], "queueBuy")
        self.assertEqual(p_buy["alert_category"], "queue")
        self.assertTrue(all(isinstance(v, str) for v in p_buy.values()))

        p_sell = trigger_payload(_alert(condition_type="queueSell"), _live_meta(queue="sell"))
        self.assertEqual(p_sell["condition_type"], "queueSell")
        self.assertEqual(p_sell["alert_category"], "queue")

        p_vol = trigger_payload(_alert(condition_type="volumeAbove", target_price=10_000_000), _live_meta(volume=16_200_000))
        self.assertEqual(p_vol["condition_type"], "volumeAbove")
        self.assertEqual(p_vol["alert_category"], "volume")
        self.assertEqual(p_vol["volume"], "16200000")
        self.assertTrue(all(isinstance(v, str) for v in p_vol.values()))

        # Standard priceThreshold keeps legacy 5-key schema untouched
        p_price = trigger_payload(_alert(condition_type="priceThreshold"), _live_meta())
        self.assertNotIn("alert_category", p_price)
        self.assertNotIn("condition_type", p_price)

    def test_phase24c_fresh_queue_alert_on_active_queue_fires_immediately(self):
        # Decision 24c Option A: a freshly created queue alert on an already-queued symbol
        # fires immediately on first evaluation, then arms waiting_for_cross until exit.
        buy_alert = _alert(condition_type="queueBuy", trigger_mode="recurring")
        self.assertFalse(buy_alert.waiting_for_cross)
        trig, is_above, target = evaluate_special_alert(buy_alert, 4210, _live_meta(queue="buy"))
        self.assertTrue(trig)
        self.assertTrue(is_above)
        self.assertEqual(target, 4210.0)
        self.assertTrue(buy_alert.waiting_for_cross)

        sell_meta = _live_meta(
            queue="sell",
            best_bid=None,
            best_ask={"price": 3970, "volume": 4_000_000, "orders": 15},
        )
        sell_alert = _alert(condition_type="queueSell", trigger_mode="oneShot")
        self.assertFalse(sell_alert.waiting_for_cross)
        trig, is_above, target = evaluate_special_alert(sell_alert, 3970, sell_meta)
        self.assertTrue(trig)
        self.assertFalse(is_above)
        self.assertEqual(target, 3970.0)
        self.assertTrue(sell_alert.waiting_for_cross)



try:
    import fastapi  # noqa: F401
    _HAS_FASTAPI = True
except ModuleNotFoundError:
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "fastapi not installed in minimal sandbox")
class Phase21ValidationTests(unittest.TestCase):
    def _run(self, coro):
        return asyncio.run(coro)

    def test_validation_accepts_and_rejects_phase21_types(self):
        import app.config as config
        from app.markets.iran_bourse.validation import BourseAlertError, check_bourse_alert

        fake_info = {"ticker": "توریل", "name": "توکاریل", "yesterday": 4090}
        with patch.object(config, "IRAN_BOURSE_ENABLED", True), \
             patch.object(config, "IRAN_BOURSE_ALLOWED_USER_IDS", []), \
             patch("app.markets.iran_bourse.validation.DIRECTORY.lookup", new=AsyncMock(return_value=fake_info)):
            # Valid queueBuy with and without min_queue_volume
            self._run(check_bourse_alert({
                "user_id": "u1", "exchange": "tsetmc", "symbol": "37389789764168256",
                "condition_type": "queueBuy", "target_price": 0, "raw_rule": {},
            }))
            self._run(check_bourse_alert({
                "user_id": "u1", "exchange": "tsetmc", "symbol": "37389789764168256",
                "condition_type": "queueSell", "target_price": 0, "raw_rule": {"min_queue_volume": 500000},
            }))
            # Invalid negative min_queue_volume
            with self.assertRaises(BourseAlertError):
                self._run(check_bourse_alert({
                    "user_id": "u1", "exchange": "tsetmc", "symbol": "37389789764168256",
                    "condition_type": "queueBuy", "target_price": 0, "raw_rule": {"min_queue_volume": -5},
                }))
            # Valid volumeAbove
            self._run(check_bourse_alert({
                "user_id": "u1", "exchange": "tsetmc", "symbol": "37389789764168256",
                "condition_type": "volumeAbove", "target_price": 10_000_000, "raw_rule": {},
            }))
            # Invalid volumeAbove with zero target
            with self.assertRaises(BourseAlertError):
                self._run(check_bourse_alert({
                    "user_id": "u1", "exchange": "tsetmc", "symbol": "37389789764168256",
                    "condition_type": "volumeAbove", "target_price": 0, "raw_rule": {},
                }))

    def test_phase24d_checker_preserves_sound_flags_and_category_for_queue_and_volume(self):
        from app.engine import checker
        from app.models import Alert
        from app.state import PRICE_CACHE

        cases = [
            ("queueBuy", 0.0, "radar_pulse", True, False, True, True, "queue",
             {"queue": "buy", "upper_limit": 4210, "lower_limit": 3970,
              "best_bid": {"price": 4210, "volume": 3_000_000, "orders": 12}, "best_ask": None,
              "volume": 5_000_000}),
            ("queueSell", 0.0, "alert_horn", False, True, False, False, "queue",
             {"queue": "sell", "upper_limit": 4210, "lower_limit": 3970,
              "best_bid": None, "best_ask": {"price": 3970, "volume": 4_000_000, "orders": 15},
              "volume": 6_000_000}),
            ("volumeAbove", 10_000_000.0, "cyber_chime", True, True, True, False, "volume",
             {"queue": None, "upper_limit": 4210, "lower_limit": 3970,
              "best_bid": {"price": 4100, "volume": 1000, "orders": 1},
              "best_ask": {"price": 4110, "volume": 1000, "orders": 1},
              "volume": 12_500_000}),
        ]

        async def run_cases():
            for ctype, target, sound, s_en, v_en, f_en, t_en, expected_cat, extra in cases:
                PRICE_CACHE.pop("tsetmc:37389789764168256", None)
                push = AsyncMock()
                alert = Alert(
                    id=f"p24d-{ctype}",
                    user_id="u1",
                    exchange="tsetmc",
                    symbol="37389789764168256",
                    market_symbol="توریل",
                    condition="BELOW" if ctype == "queueSell" else "ABOVE",
                    condition_type=ctype,
                    target_price=target,
                    trigger_mode="oneShot",
                    check_interval_seconds=180,
                    is_active=True,
                    last_checked_at=0.0,
                    sound=sound,
                    sound_enabled=s_en,
                    vibration_enabled=v_en,
                    flash_enabled=f_en,
                    tts_enabled=t_en,
                )
                tr = {
                    "source": "iran_bourse",
                    "success": True,
                    "parsed_price": 4210.0 if ctype != "queueSell" else 3970.0,
                    "asOf": 10,
                    "state": "LIVE",
                    "alert_eligible": True,
                    "traded_today": True,
                    "ticker": "توریل",
                    "name": "توکاریل",
                    "prev_close": 4090.0,
                    "currency": "IRR",
                    **extra,
                }
                with patch.object(checker, "enqueue_alert_push", push), \
                     patch.object(checker, "save_alerts_to_disk_async", AsyncMock()), \
                     patch.object(checker, "get_category_cache_ttl", return_value=0.0), \
                     patch.object(checker, "fetch_price_with_trace", new=AsyncMock(return_value=(tr["parsed_price"], [tr]))):
                    await checker.evaluate_ready_alerts(None, [alert], 10_000.0)

                self.assertEqual(push.await_count, 1, f"{ctype} did not trigger push")
                _a, _title, _body, data = push.await_args.args[:4]
                self.assertEqual(data["sound"], sound)
                self.assertEqual(data["sound_enabled"], "true" if s_en else "false")
                self.assertEqual(data["vibration_enabled"], "true" if v_en else "false")
                self.assertEqual(data["flash_enabled"], "true" if f_en else "false")
                self.assertEqual(data["tts_enabled"], "true" if t_en else "false")
                self.assertEqual(data["condition_type"], ctype)
                self.assertEqual(data["alert_category"], expected_cat)
                if ctype == "volumeAbove":
                    self.assertEqual(data["volume"], "12500000")

        self._run(run_cases())


if __name__ == "__main__":
    unittest.main()
