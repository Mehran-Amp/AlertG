# -*- coding: utf-8 -*-
"""IB-7: Bourse session, states and eligibility (fake clock) + proof other markets are unchanged."""
import unittest
from datetime import datetime, timezone, timedelta

from app.engine import calendar as cal
from app.markets.iran_bourse import session as sess
from app.markets.iran_bourse.snapshot import BourseSnapshotStore

TEH = timezone(timedelta(hours=3, minutes=30))


def teh(y, m, d, hh, mm):       # Tehran wall time
    return datetime(y, m, d, hh, mm, tzinfo=TEH)

# 2026-11-14 is a Saturday
SAT = (2026, 11, 14); THU = (2026, 11, 12); WED = (2026, 11, 11); FRI = (2026, 11, 13)


class TestOpen(unittest.TestCase):
    def test_schedule(self):
        self.assertEqual(cal.is_iran_bourse_open(teh(*SAT, 10, 0)), (True, "OPEN"))
        self.assertEqual(cal.is_iran_bourse_open(teh(*THU, 10, 0)), (False, "CLOSED"))
        self.assertEqual(cal.is_iran_bourse_open(teh(*FRI, 10, 0)), (False, "CLOSED"))
        self.assertEqual(cal.is_iran_bourse_open(teh(*WED, 12, 45)), (True, "OPEN"))   # after TSE close
        self.assertEqual(cal.is_iran_bourse_open(teh(*WED, 19, 30)), (False, "CLOSED"))
        self.assertEqual(cal.is_iran_bourse_open(teh(*SAT, 8, 29))[0], False)
        self.assertEqual(cal.is_iran_bourse_open(teh(*SAT, 8, 30))[0], True)
        self.assertEqual(cal.is_iran_bourse_open(teh(*SAT, 19, 0))[0], False)

    def test_stale_and_quiet_seq(self):
        t = teh(*SAT, 10, 0)
        self.assertEqual(cal.is_iran_bourse_open(t, feed_fresh=False), (False, "STALE"))
        self.assertEqual(cal.is_iran_bourse_open(t, True, 179), (True, "OPEN"))
        self.assertEqual(cal.is_iran_bourse_open(t, True, 181), (False, "CLOSED"))   # holiday: no changes
        self.assertEqual(cal.is_iran_bourse_open(t, True, None), (True, "OPEN"))     # unknown -> schedule only

    def test_closed_beats_stale_outside_session(self):
        self.assertEqual(cal.is_iran_bourse_open(teh(*THU, 10, 0), feed_fresh=False), (False, "CLOSED"))

    def test_polling_gate_is_schedule_only(self):
        self.assertTrue(cal.is_market_open("tsetmc", "34144395039913458", teh(*SAT, 10, 0)))
        self.assertFalse(cal.is_market_open("tsetmc", "34144395039913458", teh(*THU, 10, 0)))
        self.assertFalse(cal.is_market_open("tsetmc", "34144395039913458", teh(*WED, 19, 30)))


class TestClassify(unittest.TestCase):
    def setUp(self):
        self.t = [1000.0]
        self.store = BourseSnapshotStore(60.0, lambda: self.t[0])
        self.store.apply([], {"seq": 1})            # fresh, seq moved now
        self.q = {"state": "LIVE", "traded_today": True}

    def test_live(self):
        self.assertEqual(sess.classify(self.q, self.store, teh(*SAT, 10, 0)), ("LIVE", True))

    def test_fund_wednesday_1245_live_while_seq_advances(self):
        for i in range(2, 6):
            self.t[0] += 30
            self.store.apply([], {"seq": i})
        self.assertEqual(sess.classify(self.q, self.store, teh(*WED, 12, 45)), ("LIVE", True))

    def test_1930_closed(self):
        self.assertEqual(sess.classify(self.q, self.store, teh(*WED, 19, 30)), ("CLOSED", False))

    def test_holiday_no_changes_closed(self):
        self.t[0] += 120; self.store.apply([], {"seq": 1})   # poll ok, seq unchanged
        self.t[0] += 61; self.store.apply([], {"seq": 1})
        self.assertEqual(sess.classify(self.q, self.store, teh(*SAT, 10, 0)), ("CLOSED", False))

    def test_stale_feed(self):
        self.t[0] += 61
        self.assertEqual(sess.classify(self.q, self.store, teh(*SAT, 10, 0)), ("STALE", False))

    def test_gateway_stale_flag(self):
        self.store.apply([], {"seq": 2, "stale": True})
        self.assertEqual(sess.classify(self.q, self.store, teh(*SAT, 10, 0)), ("STALE", False))

    def test_quote_stale(self):
        self.assertEqual(sess.classify({"state": "STALE", "traded_today": True}, self.store, teh(*SAT, 10, 0)), ("STALE", False))

    def test_no_trade_today(self):
        self.assertEqual(sess.classify({"state": "LIVE", "traded_today": False}, self.store, teh(*SAT, 10, 0)), ("NO_TRADE_TODAY", False))

    def test_only_live_is_eligible(self):
        for now in (teh(*SAT, 10, 0), teh(*THU, 10, 0), teh(*WED, 19, 30)):
            for q in (self.q, {"state": "STALE", "traded_today": True}, {"state": "LIVE", "traded_today": False}):
                st, el = sess.classify(q, self.store, now)
                self.assertEqual(el, st == "LIVE")

    def test_never_polled_unknown_seq_age(self):
        s = BourseSnapshotStore(60.0, lambda: 1000.0)
        self.assertEqual(sess.classify(self.q, s, teh(*SAT, 10, 0)), ("STALE", False))   # never succeeded


class TestStatusAndIsolation(unittest.TestCase):
    def test_status_has_new_key_old_keys_unchanged(self):
        st = cal.get_all_markets_status(teh(*SAT, 10, 0))
        self.assertEqual(set(st), {"us_stocks", "forex", "commodities", "crypto", "tse", "iran_bourse"})
        self.assertEqual(st["tse"], {
            "name": "بورس اوراق بهادار تهران (TSE)", "status": "open", "status_fa": "باز", "state": "OPEN",
            "state_fa": "باز", "is_open": True, "schedule": "Saturday-Wednesday 09:00-12:30 IRST",
            "schedule_fa": "شنبه تا چهارشنبه ۰۹:۰۰ تا ۱۲:۳۰", "source": "Tehran Stock Exchange Official Schedule"})
        self.assertEqual(st["crypto"]["state"], "OPEN")
        self.assertTrue(st["iran_bourse"]["is_open"])
        self.assertFalse(st["iran_bourse"]["enabled"])           # flag default off
        self.assertFalse(cal.get_all_markets_status(teh(*THU, 10, 0))["iran_bourse"]["is_open"])

    def test_old_tse_untouched(self):
        self.assertEqual(cal.is_tse_market_open(teh(*WED, 12, 45)), (False, "CLOSED"))   # TSE closed, Bourse open
        self.assertEqual(cal.is_tse_market_open(teh(*SAT, 10, 0)), (True, "OPEN"))
        self.assertEqual(cal.is_tse_market_open(teh(*SAT, 12, 30)), (False, "CLOSED"))
        self.assertEqual(cal.is_tse_market_open(teh(*THU, 10, 0)), (False, "CLOSED"))

    def test_other_markets_unchanged(self):
        sat = teh(*SAT, 10, 0)
        self.assertTrue(cal.is_market_open("binance", "BTCUSDT", sat))
        self.assertTrue(cal.is_market_open("nobitex", "USDTIRT", teh(*THU, 3, 0)))     # crypto-like iran 24/7
        self.assertEqual(cal.is_market_open("tse", "FOLD", teh(*WED, 12, 45)), False)   # old TSE hours
        self.assertEqual(cal.is_market_open("tse", "FOLD", sat), True)
        wed_us_open = datetime(2026, 11, 11, 15, 0, tzinfo=timezone.utc)                # 10:00 NY
        self.assertTrue(cal.is_market_open("stocks", "AAPL", wed_us_open))
        sat_us = datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc)
        self.assertFalse(cal.is_market_open("stocks", "AAPL", sat_us))


if __name__ == "__main__":
    unittest.main()
