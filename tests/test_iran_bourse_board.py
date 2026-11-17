# -*- coding: utf-8 -*-
"""IB-16a: market board for the app's browse lists (grouping, filters, sort, paging, refresh, route)."""
import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.config as config
import server as server_mod
from app.markets.iran_bourse import board as bmod
from app.markets.iran_bourse.board import BourseBoard, group_of, price_of, norm
from app.markets.iran_bourse.client import BourseTimeout
from app.routes.iran_bourse import router as bourse_router

SAT_OPEN = datetime(2026, 11, 14, 6, 30, tzinfo=timezone.utc)    # Saturday 10:00 Tehran
SAT_CLOSED = datetime(2026, 11, 14, 17, 0, tzinfo=timezone.utc)  # Saturday 20:30 Tehran
H = {"X-API-Key": "api-k"}


def row(i, ticker, typ, **kw):
    r = {"id": str(10 ** 15 + i), "ticker": ticker, "name": "نام " + ticker, "last": 1000 + i, "close": 990 + i,
         "yesterday": 980 + i, "last_change_pct": float(i) - 5, "volume": 100 * i, "value": 1000 * i,
         "traded": True, "type": typ, "type_code": "T" + typ[:1], "market_code": "1", "sector_code": "27",
         "sector": "فلزات", "update_time": "12:00:00"}
    r.update(kw)
    return r


def market():
    return [
        row(1, "فولاد", "سهام"),
        row(2, "وبملت", "سهام"),
        row(3, "عیار", "صندوق کالایی", market_code="2"),
        row(4, "اهرم", "صندوق سرمایه‌گذاری در سهام"),
        row(5, "ضهرم8024", "اختیار خرید"),
        row(6, "طهرم8024", "اختیار فروش"),
        row(7, "فولاد ح", "حق تقدم سهام"),
        row(8, "اجاره۱", "اوراق اجاره"),
        row(9, "کدخدا", "نوع عجیب", traded=False, last=None, close=None),
    ]


class FakeClient:
    def __init__(self, rows=None):
        self.rows = rows if rows is not None else market()
        self.calls = []
        self.error = None
        self.seq = 5
        self.meta_override = None

    async def changes(self, since=0):
        self.calls.append(since)
        if self.error:
            raise self.error
        meta = {"seq": self.seq, "stale": False}
        if self.meta_override:
            meta.update(self.meta_override)
        return list(self.rows), meta


class Clock:
    t = 1000.0
    def __call__(self): return self.t


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestGrouping(unittest.TestCase):
    def test_groups_by_type_name(self):
        cases = {"سهام": "stocks", "حق تقدم سهام": "rights", "صندوق کالایی": "funds",
                 "صندوق سرمایه‌گذاری در سهام": "funds", "اختیار خرید": "derivatives",
                 "اختیار فروش": "derivatives", "آتی": "derivatives", "اوراق مشارکت": "bonds",
                 "صکوک اجاره": "bonds", "": "other", None: "other", "چیز دیگر": "other"}
        for typ, want in cases.items():
            self.assertEqual(group_of({"type": typ}), want, typ)

    def test_rows_without_a_type_name_use_code_sector_or_name(self):
        self.assertEqual(group_of({"type": None, "type_code": "315", "sector": "صندوق سرمایه‌گذاری قابل معامله"}), "funds")
        self.assertEqual(group_of({"type": None, "type_code": "206", "sector": None, "name": "گام بانک ملت0607"}), "bonds")
        self.assertEqual(group_of({"type": None, "type_code": 404, "name": "ح. پتروشیمی اصفهان"}), "rights")
        self.assertEqual(group_of({"type": None, "type_code": "999", "sector": "صندوق X"}), "funds")
        self.assertEqual(group_of({"type": None, "type_code": "999", "name": "ح. جهان فولاد"}), "rights")
        self.assertEqual(group_of({"type": None, "type_code": "999", "name": "چیز"}), "other")
        self.assertEqual(group_of({"type": "زعفران (کالا)", "type_code": "315"}), "other")   # a named type wins over the code

    def test_arabic_letters_and_half_space_are_normalized(self):
        self.assertEqual(norm("صندوق  كالايي"), "صندوق کالایی")
        self.assertEqual(group_of({"type": "اختيار خرید"}), "derivatives")  # Arabic yeh

    def test_price_falls_back_from_last_to_close_to_yesterday(self):
        self.assertEqual(price_of({"last": 5, "close": 4, "yesterday": 3}), (5.0, "last"))
        self.assertEqual(price_of({"last": 0, "close": 4, "yesterday": 3}), (4.0, "close"))
        self.assertEqual(price_of({"last": None, "close": None, "yesterday": 3}), (3.0, "yesterday"))
        self.assertEqual(price_of({}), (None, "none"))
        self.assertEqual(price_of({"last": True, "yesterday": "x"}), (None, "none"))


class TestBoard(unittest.TestCase):
    def setUp(self):
        self.fc = FakeClient()
        self.clock = Clock()
        self.board = BourseBoard(lambda: self.fc, clock=self.clock, refresh_seconds=15.0)
        run(self.board.ensure_fresh())

    def ids(self, **kw):
        return [i["ticker"] for i in self.board.query(**kw)["items"]]

    def test_default_list_hides_derivatives_but_counts_them(self):
        out = self.board.query()
        self.assertEqual(out["total"], 7)
        self.assertNotIn("اختیار", " ".join(i["type"] for i in out["items"]))
        self.assertEqual(out["groups"]["derivatives"], 2)
        self.assertEqual(out["groups"]["stocks"], 2)
        self.assertEqual(out["unit"], "IRR")

    def test_group_filter_and_derivatives_tab(self):
        self.assertCountEqual(self.ids(group="funds"), ["عیار", "اهرم"])
        self.assertCountEqual(self.ids(group="derivatives"), ["ضهرم8024", "طهرم8024"])
        self.assertEqual(self.ids(group="rights"), ["فولاد ح"])

    def test_market_sector_type_traded_filters(self):
        self.assertEqual(self.ids(market="2"), ["عیار"])
        self.assertEqual(self.ids(sector="27", group="bonds"), ["اجاره۱"])
        self.assertCountEqual(self.ids(type_code="Tس"), ["فولاد", "وبملت"])
        self.assertNotIn("کدخدا", self.ids(traded=True))
        self.assertIn("کدخدا", self.ids())

    def test_search_inside_the_board(self):
        self.assertCountEqual(self.ids(q="فولاد"), ["فولاد", "فولاد ح"])
        self.assertEqual(self.ids(q="وبملت"), ["وبملت"])
        self.assertEqual(self.ids(q="كدخدا"), ["کدخدا"])      # Arabic kaf in the query still matches
        self.assertEqual(self.ids(q="وبملت"), ["وبملت"])
        self.assertEqual(self.ids(q="نام عیار"), ["عیار"])

    def test_sort_orders_and_missing_values_go_last(self):
        self.assertEqual(self.ids(sort="price")[0], "اجاره۱")                 # highest price first (desc)
        self.assertEqual(self.ids(sort="price")[-1], "کدخدا")                 # no last/close: yesterday's price (989)
        self.assertEqual(self.ids(sort="price", order="asc")[0], "کدخدا")
        self.assertEqual(self.ids(sort="price", order="asc")[1], "فولاد")
        self.assertEqual(self.ids(sort="change")[0], "کدخدا")                # change +4 is the highest
        self.assertEqual(self.ids(sort="volume", order="asc")[0], "فولاد")
        names = self.ids(sort="name")
        self.assertEqual(names, sorted(names, key=norm))                       # name defaults to ascending
        self.assertEqual(self.ids(sort="bogus")[0], self.ids(sort="value")[0])

    def test_rows_without_any_price_go_last_in_both_directions(self):
        self.fc.rows = [row(20, "بدون", "سهام", last=None, close=None, yesterday=None, value=None)]
        self.fc.seq = 6
        self.clock.t += 16
        run(self.board.ensure_fresh())
        self.assertEqual(self.ids(sort="price")[-1], "بدون")
        self.assertEqual(self.ids(sort="price", order="asc")[-1], "بدون")
        self.assertEqual(self.ids(sort="value")[-1], "بدون")

    def test_paging(self):
        a = self.board.query(limit=3, offset=0)
        b = self.board.query(limit=3, offset=3)
        c = self.board.query(limit=3, offset=6)
        self.assertEqual((len(a["items"]), len(b["items"]), len(c["items"])), (3, 3, 1))
        seen = [i["id"] for p in (a, b, c) for i in p["items"]]
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(a["total"], 7)
        self.assertEqual(self.board.query(offset=99)["items"], [])
        self.assertEqual(len(self.board.query(limit=10000)["items"]), 7)       # limit is capped
        self.assertEqual(self.board.query(limit=10000)["limit"], bmod.MAX_LIMIT)

    def test_item_shape_keeps_ids_as_strings_and_rial_untouched(self):
        it = self.board.query(group="stocks", sort="name")["items"][0]
        self.assertIsInstance(it["id"], str)
        self.assertEqual(it["price"], it["last"])
        self.assertEqual(it["price_source"], "last")
        for k in ("ticker", "name", "change_pct", "volume", "value", "traded", "group", "update_time"):
            self.assertIn(k, it)
        self.assertNotIn("best_bid", it)

    def test_unclassified_types_are_reported_for_tuning(self):
        self.assertEqual(self.board.query()["other_types"], {"نوع عجیب": 1})

    def test_session_open_closed_stale(self):
        self.assertEqual(self.board.session(SAT_OPEN), "OPEN")
        self.assertEqual(self.board.session(SAT_CLOSED), "CLOSED")
        self.board.gateway_stale = True
        self.assertEqual(self.board.session(SAT_OPEN), "STALE")


class TestRefresh(unittest.TestCase):
    def setUp(self):
        self.fc = FakeClient()
        self.clock = Clock()
        self.board = BourseBoard(lambda: self.fc, clock=self.clock, refresh_seconds=15.0)

    def test_first_call_loads_everything_then_waits(self):
        run(self.board.ensure_fresh())
        run(self.board.ensure_fresh())
        self.assertEqual(self.fc.calls, [0])
        self.assertEqual(len(self.board), 9)
        self.clock.t += 16
        run(self.board.ensure_fresh())
        self.assertEqual(self.fc.calls, [0, 5])            # only the changes since the last seq

    def test_concurrent_requests_make_one_gateway_call(self):
        async def go():
            await asyncio.gather(*[self.board.ensure_fresh() for _ in range(10)])
        run(go())
        self.assertEqual(self.fc.calls, [0])

    def test_changes_update_rows_in_place(self):
        run(self.board.ensure_fresh())
        self.fc.rows = [row(1, "فولاد", "سهام", last=5000)]
        self.fc.seq = 6
        self.clock.t += 16
        run(self.board.ensure_fresh())
        self.assertEqual(len(self.board), 9)
        top = [i for i in self.board.query(group="stocks")["items"] if i["ticker"] == "فولاد"][0]
        self.assertEqual(top["price"], 5000.0)

    def test_gateway_restart_reloads_everything(self):
        run(self.board.ensure_fresh())
        self.fc.seq = 1                                      # went backwards
        self.fc.rows = [row(1, "فولاد", "سهام")]
        self.clock.t += 16
        run(self.board.ensure_fresh())
        self.assertEqual(self.fc.calls, [0, 5, 0])
        self.assertEqual(len(self.board), 1)                 # stale rows are dropped
        self.assertEqual(self.board.full_loads, 2)

    def test_failed_refresh_keeps_old_rows_and_retries_soon(self):
        run(self.board.ensure_fresh())
        self.fc.error = BourseTimeout("slow")
        self.clock.t += 16
        run(self.board.ensure_fresh())                       # no exception, old rows kept
        self.assertEqual(len(self.board), 9)
        self.assertIn("BourseTimeout", self.board.last_error)
        n = len(self.fc.calls)
        run(self.board.ensure_fresh())
        self.assertEqual(len(self.fc.calls), n)              # not retried immediately
        self.clock.t += 6
        self.fc.error = None
        run(self.board.ensure_fresh())
        self.assertEqual(len(self.fc.calls), n + 1)
        self.assertIsNone(self.board.last_error)

    def test_failure_with_nothing_to_show_raises(self):
        self.fc.error = BourseTimeout("slow")
        with self.assertRaises(BourseTimeout):
            run(self.board.ensure_fresh())

    def test_rows_without_an_id_are_skipped(self):
        self.fc.rows = [{"ticker": "x"}, row(1, "فولاد", "سهام")]
        run(self.board.ensure_fresh())
        self.assertEqual(len(self.board), 1)

    def test_as_of_prefers_local_as_of(self):
        self.fc.meta_override = {"local_as_of": 1794726798}
        run(self.board.ensure_fresh())
        self.assertEqual(self.board.query()["as_of"], 1794726798)


class TestRoute(unittest.TestCase):
    def setUp(self):
        self.fc = FakeClient()
        self.board = BourseBoard(lambda: self.fc, clock=Clock(), refresh_seconds=15.0)
        app = FastAPI()
        app.include_router(bourse_router)
        self.http = TestClient(app)
        for p in (patch.object(config, "API_KEY", "api-k"), patch.object(config, "ADMIN_KEY", "admin-k"),
                  patch.object(server_mod, "ADMIN_KEY", "admin-k"),
                  patch.object(config, "IRAN_BOURSE_ENABLED", True),
                  patch("app.routes.iran_bourse.get_board", return_value=self.board)):
            p.start(); self.addCleanup(p.stop)

    def test_auth_and_flag(self):
        self.assertEqual(self.http.get("/api/iran-bourse/board").status_code, 401)
        self.assertEqual(self.http.get("/api/iran-bourse/board", headers={"X-API-Key": "bad"}).status_code, 401)
        with patch.object(config, "IRAN_BOURSE_ENABLED", False):
            r = self.http.get("/api/iran-bourse/board", headers=H)
            self.assertEqual(r.status_code, 503)
            self.assertIn("not enabled", r.json()["detail"])
        self.assertEqual(self.fc.calls, [])                  # switched off => no gateway request

    def test_shape_and_paging(self):
        r = self.http.get("/api/iran-bourse/board", headers=H, params={"limit": 3, "sort": "value"})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual((j["unit"], j["total"], len(j["items"])), ("IRR", 7, 3))
        self.assertIn(j["session"], ("OPEN", "CLOSED", "STALE"))
        self.assertEqual(set(j["groups"]), set(bmod.GROUPS))
        j2 = self.http.get("/api/iran-bourse/board", headers=H, params={"limit": 3, "offset": 3}).json()
        self.assertFalse({i["id"] for i in j["items"]} & {i["id"] for i in j2["items"]})

    def test_bad_parameters_are_400_or_422(self):
        self.assertEqual(self.http.get("/api/iran-bourse/board", headers=H, params={"group": "x"}).status_code, 400)
        self.assertEqual(self.http.get("/api/iran-bourse/board", headers=H, params={"sort": "x"}).status_code, 400)
        self.assertEqual(self.http.get("/api/iran-bourse/board", headers=H, params={"order": "up"}).status_code, 400)
        self.assertEqual(self.http.get("/api/iran-bourse/board", headers=H, params={"limit": 0}).status_code, 422)
        self.assertEqual(self.http.get("/api/iran-bourse/board", headers=H, params={"limit": 101}).status_code, 422)
        self.assertEqual(self.http.get("/api/iran-bourse/board", headers=H, params={"offset": -1}).status_code, 422)

    def test_derivatives_tab(self):
        j = self.http.get("/api/iran-bourse/board", headers=H, params={"group": "derivatives"}).json()
        self.assertEqual(j["total"], 2)

    def test_gateway_down_with_empty_board_is_503(self):
        self.fc.error = BourseTimeout("slow")
        r = self.http.get("/api/iran-bourse/board", headers=H)
        self.assertEqual(r.status_code, 503)
        self.assertIn("unavailable", r.json()["detail"])


if __name__ == "__main__":
    unittest.main()
