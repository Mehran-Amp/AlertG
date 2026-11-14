# -*- coding: utf-8 -*-
"""IB-10: Bourse notification text/payloads (golden strings) + proof other markets are unchanged."""
import importlib.util
import re
import subprocess
import sys
import unittest
from unittest.mock import AsyncMock, patch

from app.engine import checker
from app.markets.iran_bourse import messages as M
from app.models import Alert
from app.notifier import telegram as tg
from app.state import PRICE_CACHE

AYAR = "34144395039913458"
NAME = "صندوق طلای عیار مفید"
TICKER = "عیار"


def mk(**kw):
    d = dict(id="a1", user_id="u1", exchange="tsetmc", symbol=AYAR, market_symbol=TICKER, target_price=700000.0,
             condition="ABOVE", trigger_mode="oneShot", check_interval_seconds=30, is_active=True,
             last_checked_at=0.0, telegram_chat_id="555", webhook_url=None)
    d.update(kw)
    return Alert(**d)


def trace(price, **extra):
    t = {"source": "tsetmc-gateway", "url": "", "status_code": 200, "latency_ms": 1.0, "success": True,
         "currency": "IRR", "parsed_price": price, "asOf": 1000, "state": "LIVE", "alert_eligible": True,
         "prev_close": 685477.0, "name": NAME, "ticker": TICKER}
    t.update(extra)
    return t


class TestFormat(unittest.TestCase):
    def test_rial_golden(self):
        self.assertEqual(M.format_rial(693731), "693,731 ریال")
        self.assertEqual(M.format_rial(1434.0), "1,434 ریال")
        self.assertEqual(M.format_rial(1234567890), "1,234,567,890 ریال")
        self.assertEqual(M.format_rial(0), "0 ریال")
        self.assertEqual(M.format_rial(None), "-")
        self.assertEqual(M.format_rial(693731, "en"), "693,731 IRR")
        self.assertEqual(M.format_rial(1.5), "1.50 ریال")

    def test_name_fallback_chain(self):
        a = mk()
        self.assertEqual(M.name_of(a, {"name": NAME}), NAME)
        self.assertEqual(M.name_of(a, {}), TICKER)                      # no name -> ticker
        self.assertEqual(M.name_of(mk(market_symbol=None), {}), AYAR)   # last resort: id

    def test_payload_schema(self):
        p = M.trigger_payload(mk(), {"name": NAME, "ticker": TICKER})
        self.assertEqual(p, {"exchange": "tsetmc", "symbol": AYAR, "ticker": TICKER, "name": NAME, "unit": "IRR"})
        self.assertTrue(all(isinstance(v, str) for v in p.values()))     # FCM data values are strings


class TestRegistered(unittest.TestCase):
    def test_registered_message(self):
        m = tg.format_alert_registered_telegram_msg(mk())
        self.assertIn("700,000 ریال", m)
        self.assertIn("بورس ایران", m)
        self.assertIn(TICKER, m)
        self.assertNotIn("$", m)
        self.assertNotIn(AYAR, m)
        self.assertIn("▲", m)

    def test_registered_percent_and_absolute(self):
        self.assertIn("2.5%", tg.format_alert_registered_telegram_msg(mk(condition_type="percentChange", percent=2.5)))
        self.assertIn("40 ریال", tg.format_alert_registered_telegram_msg(mk(condition_type="absolutePriceChange", delta_absolute=40.0)))


class TestTrigger(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        key = f"tsetmc:{AYAR}"
        PRICE_CACHE.pop(key, None)
        self.push = AsyncMock(); self.tg_send = AsyncMock(); self.hook = AsyncMock(); self.spawned = []
        def spawn(coro):
            self.spawned.append(coro)
        for p in (patch.object(checker, "enqueue_alert_push", self.push),
                  patch.object(checker, "send_telegram_alert", self.tg_send),
                  patch.object(checker, "send_webhook_alert", self.hook),
                  patch.object(checker, "_spawn", spawn),
                  patch.object(checker, "save_alerts_to_disk_async", AsyncMock()),
                  patch.object(checker, "get_category_cache_ttl", return_value=0.0)):
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(PRICE_CACHE.clear)      # also drops entries other markets' alerts left behind

    async def fire(self, alert, price, tr, key=None):
        PRICE_CACHE.pop(key or f"{alert.exchange}:{alert.symbol}", None)
        with patch.object(checker, "fetch_price_with_trace", new=AsyncMock(return_value=(price, [tr]))):
            await checker.evaluate_ready_alerts(None, [alert], 10_000.0)
        for c in self.spawned:
            await c
        self.spawned.clear()

    async def test_bourse_trigger_text_and_payload(self):
        a = mk(webhook_url="https://example.com/h")
        await self.fire(a, 701000.0, trace(701000.0))
        _alert, title, body, data = self.push.await_args.args[:4]
        self.assertEqual(title, f"🟢 {NAME} +0.14% 701,000 ریال ▲")        # golden
        self.assertEqual(body, "🏛️ بورس ایران")
        self.assertNotIn("$", title + body)
        self.assertNotIn(AYAR, title + body)
        self.assertEqual((data["exchange"], data["symbol"], data["ticker"], data["name"], data["unit"]),
                         ("tsetmc", AYAR, TICKER, NAME, "IRR"))           # symbol is the id, not the name
        self.assertEqual(data["price"], "701000")                        # raw, machine readable
        self.assertEqual(data["tts_enabled"], "true")
        self.assertEqual(data["alert_id"], "a1")
        # Telegram
        msg = self.tg_send.await_args.args[2]
        self.assertIn(NAME, msg); self.assertIn("701,000 ریال", msg); self.assertIn("700,000 ریال", msg)
        self.assertIn("هشدار فعال شد", msg); self.assertNotIn("$", msg); self.assertNotIn(AYAR, msg)
        # Webhook
        hook = self.hook.await_args.args[2]
        self.assertEqual((hook["exchange"], hook["symbol"], hook["ticker"], hook["name"]), ("tsetmc", AYAR, TICKER, NAME))
        self.assertEqual(hook["price"], 701000.0)

    async def test_missing_name_uses_ticker_then_id(self):
        a = mk()
        await self.fire(a, 701000.0, trace(701000.0, name=None))
        title = self.push.await_args.args[1]
        self.assertIn(TICKER, title)
        self.assertNotIn(AYAR, title)

    async def test_english_language_alert(self):
        a = mk(language="en")
        await self.fire(a, 701000.0, trace(701000.0))
        self.assertIn("701,000 IRR", self.push.await_args.args[1])
        self.assertIn("ALERT TRIGGERED", self.tg_send.await_args.args[2])

    async def test_percent_alert_text(self):
        a = mk(condition_type="percentChange", percent=2.9, base_price=1.0, target_price=0.0)
        await self.fire(a, 1434.0, trace(1434.0, prev_close=1393.0, name="وبملت", ticker="وبملت"))
        self.assertIn("1,434 ریال", self.push.await_args.args[1])
        self.assertIn("1,393 ریال", self.tg_send.await_args.args[2])      # yesterday close shown

    async def test_other_markets_payload_and_title_unchanged(self):
        b = Alert(id="b1", user_id="u1", exchange="binance", symbol="BTCUSDT", target_price=50000.0,
                  condition="ABOVE", trigger_mode="oneShot", check_interval_seconds=30, is_active=True,
                  last_checked_at=0.0, telegram_chat_id="555", webhook_url="https://example.com/h")
        tr = {"source": "binance", "success": True, "parsed_price": 51000.0, "asOf": 5, "state": "LIVE", "currency": "USDT"}
        await self.fire(b, 51000.0, tr)
        _a, title, body, data = self.push.await_args.args[:4]
        self.assertEqual(title, "🟢 BTC/USDT +2.00% $51,000.00 ▲")
        self.assertEqual(set(data), {"alert_id", "symbol", "price", "note", "sound_enabled", "vibration_enabled",
                                     "flash_enabled", "tts_enabled", "sound"})             # no Bourse keys
        self.assertEqual(data["symbol"], "BTC/USDT")
        self.assertEqual(set(self.hook.await_args.args[2]),
                         {"event", "alert_id", "symbol", "price", "target_price", "condition", "timestamp"})

    async def test_tse_still_toman(self):
        t = Alert(id="t1", user_id="u1", exchange="tse", symbol="FOLD", target_price=1000.0, condition="ABOVE",
                  trigger_mode="oneShot", check_interval_seconds=30, is_active=True, last_checked_at=0.0)
        await self.fire(t, 1100.0, {"source": "tse", "success": True, "parsed_price": 1100.0, "asOf": 5, "state": "LIVE", "currency": "IRT"})
        self.assertIn("1,100 تومان", self.push.await_args.args[1])


def _load_head_telegram():
    """The committed (pre-IB-10) telegram.py, to prove other markets' messages are byte-identical."""
    src = subprocess.check_output(["git", "show", "e9d7c34:app/notifier/telegram.py"], text=True)
    spec = importlib.util.spec_from_loader("telegram_head", loader=None)
    mod = importlib.util.module_from_spec(spec)
    exec(compile(src, "telegram_head.py", "exec"), mod.__dict__)
    return mod


class TestOtherMarketsIdentical(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.old = _load_head_telegram()
        except Exception as e:          # not a git checkout: skip rather than fail
            raise unittest.SkipTest(f"HEAD telegram.py unavailable: {e}")

    def alerts(self):
        base = dict(user_id="u", target_price=50000.0, condition="ABOVE", trigger_mode="oneShot")
        return [Alert(id="1", exchange="binance", symbol="BTCUSDT", **base),
                Alert(id="2", exchange="nobitex", symbol="USDTIRT", **base),
                Alert(id="3", exchange="tse", symbol="FOLD", **base),
                Alert(id="4", exchange="stocks", symbol="AAPL", **base),
                Alert(id="5", exchange="forex", symbol="EURUSD", **base),
                Alert(id="6", exchange="okx", symbol="ETHUSDT", condition_type="percentChange", percent=3.0, **{k: v for k, v in base.items() if k != "target_price"})]

    @staticmethod
    def strip_time(s):
        return re.sub(r"🕒 <b>Time:</b> <code>[^<]*</code>", "T", s)

    def test_registered_identical(self):
        for a in self.alerts():
            self.assertEqual(tg.format_alert_registered_telegram_msg(a), self.old.format_alert_registered_telegram_msg(a))

    def test_history_card_identical(self):
        for a in self.alerts():
            new = tg.format_telegram_history_card(a, 51000.0, 50000.0, 49000.0, {"source": "x"}, "note")
            old = self.old.format_telegram_history_card(a, 51000.0, 50000.0, 49000.0, {"source": "x"}, "note")
            self.assertEqual(self.strip_time(new), self.strip_time(old))

    def test_exchange_names_identical_except_tsetmc(self):
        for ex in ("binance", "nobitex", "tse", "stocks", "forex", "okx", "iran_market", "unknown_x"):
            self.assertEqual(tg.get_exchange_display_name(ex), self.old.get_exchange_display_name(ex))
        self.assertEqual(tg.get_exchange_display_name("tsetmc"), "بورس ایران")


class TestMissingNotification(unittest.IsolatedAsyncioTestCase):
    async def test_one_message_per_vanished_instrument(self):
        a = mk(fcm_token="tok" * 10)
        a.needs_attention = True
        tgs = AsyncMock(); fcm = AsyncMock()
        with patch("app.notifier.telegram.send_telegram_alert", tgs), patch("app.notifier.send_fcm_notification_async", fcm):
            self.assertEqual(await M.dispatch_missing_notifications([a], client=object()), 1)
            self.assertEqual(await M.dispatch_missing_notifications([a], client=object()), 0)   # no repeat
        self.assertEqual((tgs.await_count, fcm.await_count), (1, 1))
        self.assertIn(TICKER, tgs.await_args.args[2])
        self.assertNotIn(AYAR, tgs.await_args.args[2])
        kw = fcm.await_args.kwargs
        self.assertEqual((kw["data_payload"]["type"], kw["data_payload"]["symbol"], kw["data_payload"]["exchange"]),
                         ("instrument_missing", AYAR, "tsetmc"))
        self.assertIsNotNone(a.attention_notified_at)

    async def test_not_flagged_not_sent(self):
        tgs = AsyncMock()
        with patch("app.notifier.telegram.send_telegram_alert", tgs):
            self.assertEqual(await M.dispatch_missing_notifications([mk()], client=object()), 0)
        tgs.assert_not_awaited()

    def test_missing_text_languages(self):
        self.assertIn("دیگر در دسترس نیست", M.missing_text(mk())[0])
        self.assertIn("no longer listed", M.missing_text(mk(language="en"))[0])


if __name__ == "__main__":
    unittest.main()
