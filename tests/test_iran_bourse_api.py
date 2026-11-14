# -*- coding: utf-8 -*-
"""IB-9: Bourse routes, alert-creation validation, sync pre-validation, vanished instruments."""
import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import server as server_mod
import app.config as config
import app.storage as storage
from app.markets import limiter as limiter_mod
from app.markets.iran_bourse import directory as dmod, poller as pmod, session as session_mod
from app.markets.iran_bourse.client import BourseTimeout, BourseNotFound, BourseConnectionError
from app.markets.iran_bourse.directory import Directory
from app.markets.iran_bourse.lifecycle import reconcile_missing, MIN_FULL_SNAPSHOT
from app.markets.iran_bourse.poller import BoursePoller
from app.markets.iran_bourse.snapshot import BourseSnapshotStore
from app.models import Alert
from app.routes import alerts as alerts_routes
from app.routes.alerts import router as alerts_router
from app.routes.iran_bourse import router as bourse_router

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "iran_bourse")
AYAR = "34144395039913458"
UNKNOWN = "99999999999999999"
SAT = datetime(2026, 11, 14, 6, 30, tzinfo=timezone.utc)      # Saturday 10:00 Tehran
THU = datetime(2026, 11, 12, 6, 30, tzinfo=timezone.utc)
H = {"X-API-Key": "api-k"}
A = {"X-Admin-Key": "admin-k"}


def _q(**kw):
    q = dict(json.load(open(os.path.join(FIX, "changes.json")))["data"][0]); q.update(kw); return q


class FakeClient:
    def __init__(self):
        self.calls = []
        self.error = None
        self.quote_result = (_q(), {"seq": 7, "stale": False, "updated_at": datetime.now(timezone.utc).isoformat()})
    def _go(self, name, *a, **kw):
        self.calls.append((name, a, kw))
        if self.error:
            raise self.error
    async def symbols(self, q, limit=20, **filters):
        self._go("symbols", q, limit, **filters)
        return [{"id": AYAR, "ticker": "عیار", "name": "صندوق عیار"}][:limit], {"stale": False}
    async def classification(self):
        self._go("classification")
        return {"codes": {}, "observed": {}}, {"stale": False}
    async def quotes(self, ids):
        self._go("quotes", list(ids))
        found = [_q()] if AYAR in ids else []
        return found, [i for i in ids if i != AYAR], {"stale": False}
    async def quote(self, iid):
        self._go("quote", iid)
        if iid == UNKNOWN:
            raise BourseNotFound("unknown")
        return self.quote_result
    async def health(self):
        self._go("health")
        return {"status": "ok", "version": "0.2.2"}
    def names(self): return [c[0] for c in self.calls]


class Clock:
    t = 1000.0
    def __call__(self): return self.t


class Base(unittest.TestCase):
    def setUp(self):
        self.fc = FakeClient()
        self.clock = Clock()
        self.dir = Directory(self.clock)
        self.poller = BoursePoller(store=BourseSnapshotStore(60.0), client=self.fc, demand_fn=lambda: set(), poll_seconds=5.0)
        self.now = {"v": SAT}
        self.alerts_db = []
        app = FastAPI()
        app.include_router(bourse_router); app.include_router(alerts_router)
        self.http = TestClient(app)
        patches = [
            patch.object(config, "API_KEY", "api-k"), patch.object(config, "ADMIN_KEY", "admin-k"),
            patch.object(server_mod, "ADMIN_KEY", "admin-k"),
            patch.object(config, "IRAN_BOURSE_ENABLED", True),
            patch.object(config, "IRAN_BOURSE_ALLOWED_USER_IDS", []),
            patch.object(dmod, "DIRECTORY", self.dir),
            patch("app.routes.iran_bourse.DIRECTORY", self.dir),
            patch("app.markets.iran_bourse.validation.DIRECTORY", self.dir),
            patch.object(Directory, "_client", staticmethod(lambda: self.fc)),
            patch.object(pmod, "BOURSE_POLLER", self.poller),
            patch.object(session_mod, "_now", side_effect=lambda: self.now["v"]),
            patch.dict(limiter_mod.PROVIDER_LIMITERS, {"iran_bourse": limiter_mod.TokenBucketRateLimiter(1000.0, 1000.0)}),
            patch.object(storage, "ALERTS_DB", self.alerts_db),
            patch.object(alerts_routes, "save_alerts_to_disk_async", AsyncMock()),
            patch.object(storage, "save_alerts_to_disk_async", AsyncMock()),
        ]
        for p in patches:
            p.start(); self.addCleanup(p.stop)


class TestRoutes(Base):
    def test_auth(self):
        for path in ("/api/iran-bourse/symbols?q=a", "/api/iran-bourse/classification", f"/api/iran-bourse/quote/{AYAR}"):
            self.assertEqual(self.http.get(path).status_code, 401)
            self.assertEqual(self.http.get(path, headers={"X-API-Key": "bad"}).status_code, 401)
            self.assertEqual(self.http.get(path, headers=H).status_code, 200)
        self.assertEqual(self.http.get("/api/iran-bourse/status").status_code, 401)
        self.assertEqual(self.http.get("/api/iran-bourse/status", headers=H).status_code, 401)   # api key is not admin
        self.assertEqual(self.http.get("/api/iran-bourse/status", headers=A).status_code, 200)

    def test_flag_off_503_and_zero_requests(self):
        with patch.object(config, "IRAN_BOURSE_ENABLED", False):
            for path in ("/api/iran-bourse/symbols?q=a", "/api/iran-bourse/classification", f"/api/iran-bourse/quote/{AYAR}"):
                r = self.http.get(path, headers=H)
                self.assertEqual(r.status_code, 503)
                self.assertIn("not enabled", r.json()["detail"])
        self.assertEqual(self.fc.calls, [])

    def test_symbols_filters_and_shape(self):
        r = self.http.get("/api/iran-bourse/symbols", headers=H,
                          params={"q": "عیار", "market": "7", "board": "QS", "type": "FUND", "sector": "68", "traded": "true", "limit": 5})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual((j["count"], j["unit"], j["items"][0]["id"]), (1, "IRR", AYAR))
        name, args, kw = self.fc.calls[0]
        self.assertEqual(args, ("عیار", 5))
        self.assertEqual(kw, {"market": "7", "board": "QS", "type": "FUND", "sector": "68", "traded": "1"})

    def test_persian_query_with_arabic_letters(self):
        self.http.get("/api/iran-bourse/symbols", headers=H, params={"q": "فيلم كاسپين"})   # Arabic ي and ك
        self.assertEqual(self.fc.calls[0][1][0], "فیلم کاسپین")
        n = len(self.fc.calls)
        self.http.get("/api/iran-bourse/symbols", headers=H, params={"q": "فیلم کاسپین"})   # same query, Persian letters
        self.assertEqual(len(self.fc.calls), n)                                              # one cache entry

    def test_limit_cap_and_validation(self):
        self.http.get("/api/iran-bourse/symbols?q=a&limit=500", headers=H)
        self.assertEqual(self.fc.calls[0][1][1], 50)
        self.assertEqual(self.http.get("/api/iran-bourse/symbols?q=a&limit=0", headers=H).status_code, 422)
        self.assertEqual(self.http.get("/api/iran-bourse/symbols", headers=H).status_code, 422)
        self.assertEqual(self.http.get("/api/iran-bourse/symbols?q=%20%20", headers=H).status_code, 400)

    def test_gateway_down_is_clear_503(self):
        for err in (BourseTimeout("t"), BourseConnectionError("c")):
            self.fc.error = err; self.dir.cache.clear()
            r = self.http.get("/api/iran-bourse/symbols?q=a", headers=H)
            self.assertEqual(r.status_code, 503)
            self.assertIn("unavailable", r.json()["detail"])
            self.assertEqual(self.http.get("/api/iran-bourse/classification", headers=H).status_code, 503)

    def test_search_cache_30s_and_classification_6h(self):
        self.http.get("/api/iran-bourse/symbols?q=a", headers=H)
        self.http.get("/api/iran-bourse/symbols?q=a", headers=H)
        self.assertEqual(self.fc.names().count("symbols"), 1)
        self.http.get("/api/iran-bourse/symbols?q=b", headers=H)                       # different key
        self.assertEqual(self.fc.names().count("symbols"), 2)
        self.clock.t += 31
        self.http.get("/api/iran-bourse/symbols?q=a", headers=H)
        self.assertEqual(self.fc.names().count("symbols"), 3)                          # expired
        self.http.get("/api/iran-bourse/classification", headers=H)
        self.clock.t += 6 * 3600 - 10
        self.http.get("/api/iran-bourse/classification", headers=H)
        self.assertEqual(self.fc.names().count("classification"), 1)
        self.clock.t += 20
        self.http.get("/api/iran-bourse/classification", headers=H)
        self.assertEqual(self.fc.names().count("classification"), 2)

    def test_quote(self):
        r = self.http.get(f"/api/iran-bourse/quote/{AYAR}", headers=H)
        j = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual((j["price"], j["currency"], j["unit"], j["state"], j["alert_eligible"]),
                         (693731, "IRR", "IRR", "LIVE", True))
        self.assertEqual(j["symbol"], AYAR)

    def test_quote_closed_still_shows_price_with_state(self):
        self.now["v"] = THU
        j = self.http.get(f"/api/iran-bourse/quote/{AYAR}", headers=H).json()
        self.assertEqual((j["state"], j["alert_eligible"], j["price"]), ("CLOSED", False, 693731))

    def test_quote_errors(self):
        for bad in ("FOLD", "123", "1" * 21, "abc123456789012345"):
            self.assertEqual(self.http.get(f"/api/iran-bourse/quote/{bad}", headers=H).status_code, 400)
        self.assertEqual(self.http.get(f"/api/iran-bourse/quote/{UNKNOWN}", headers=H).status_code, 404)
        self.fc.error = BourseTimeout("t")
        self.assertEqual(self.http.get(f"/api/iran-bourse/quote/{AYAR}", headers=H).status_code, 503)

    def test_status_makes_no_request_unless_probe(self):
        j = self.http.get("/api/iran-bourse/status", headers=A).json()
        self.assertTrue(j["enabled"])
        self.assertEqual(self.fc.calls, [])
        self.assertIn("seq", j["poller"])
        j = self.http.get("/api/iran-bourse/status?probe=true", headers=A).json()
        self.assertEqual(j["gateway"]["version"], "0.2.2")
        self.assertEqual(self.fc.names(), ["health"])


def body(**kw):
    d = dict(user_id="u1", exchange="tsetmc", symbol=AYAR, target_price=700000.0, condition="ABOVE")
    d.update(kw); return d


class TestAlertCreate(Base):
    def post(self, **kw):
        return self.http.post("/api/alerts", headers=H, json=body(**kw))

    def test_valid_creates_with_ticker(self):
        r = self.post(market_symbol="whatever")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["market_symbol"], "عیار")          # stored from the gateway, not the client
        self.assertEqual(len(self.alerts_db), 1)

    def test_rejection_matrix(self):
        cases = [
            (dict(symbol="FOLD"), 400, "numeric"),
            (dict(symbol="123456"), 400, "numeric"),
            (dict(symbol="1" * 21), 400, "numeric"),
            (dict(symbol=UNKNOWN), 400, "Unknown"),
            (dict(condition_type="volumeChange"), 400, "not supported"),
            (dict(alert_nature="timer"), 400, "price alerts only"),
            (dict(raw_rule={"price_field": "open"}), 400, "price_field"),
            (dict(condition_type="percentChange"), 400, "percent"),
            (dict(condition_type="absolutePriceChange"), 400, "delta_absolute"),
        ]
        for extra, code, word in cases:
            r = self.post(**extra)
            self.assertEqual(r.status_code, code, (extra, r.text))
            self.assertIn(word, r.text, extra)
        self.assertEqual(self.alerts_db, [])

    def test_persian_ticker_as_symbol_rejected(self):
        self.assertEqual(self.post(symbol="عیار").status_code, 400)

    def test_flag_off_and_user_gate_and_gateway_down(self):
        with patch.object(config, "IRAN_BOURSE_ENABLED", False):
            self.assertEqual(self.post().status_code, 503)
        with patch.object(config, "IRAN_BOURSE_ALLOWED_USER_IDS", ["vip"]):
            self.assertEqual(self.post().status_code, 403)
            self.assertEqual(self.post(user_id="vip").status_code, 200)
        self.fc.error = BourseTimeout("t"); self.dir.cache.clear()
        r = self.post(id="new")
        self.assertEqual(r.status_code, 503)
        self.assertIn("unavailable", r.json()["detail"])

    def test_percent_and_absolute_get_daily_base(self):
        r = self.post(condition_type="percentChange", percent=2.0, target_price=0.0, base_price=1.0)
        self.assertEqual(r.json()["base_price"], 685477.0)
        r = self.post(id="abs", condition_type="absolutePriceChange", delta_absolute=6854.77, target_price=0.0)
        j = r.json()
        self.assertEqual(j["base_price"], 685477.0)
        self.assertAlmostEqual(j["percent"], 1.0, places=6)

    def test_price_field_close_accepted(self):
        self.assertEqual(self.post(raw_rule={"price_field": "close"}).status_code, 200)

    def test_other_markets_unaffected_zero_gateway_calls(self):
        r = self.http.post("/api/alerts", headers=H, json=body(exchange="binance", symbol="BTCUSDT", target_price=50000.0))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(r.json()["market_symbol"])
        self.assertEqual(self.fc.calls, [])
        with patch.object(config, "IRAN_BOURSE_ENABLED", False):       # flag off does not block other markets
            r = self.http.post("/api/alerts", headers=H, json=body(exchange="nobitex", symbol="USDTIRT", target_price=100000.0, id="n2"))
            self.assertEqual(r.status_code, 200)


class TestSync(Base):
    def sync(self, items, user="u1"):
        return self.http.post("/api/alerts/sync", headers=H,
                              json={"user_id": user, "fcm_token": "x" * 20, "sync_mode": "merge", "alerts": items})

    def test_invalid_bourse_item_dropped_others_kept(self):
        good = body(id="g1", exchange="binance", symbol="BTCUSDT", target_price=50000.0)
        bad = body(id="b1", symbol=UNKNOWN)
        ticker = body(id="b2", symbol="FOLD")
        ok = body(id="ok1")
        r = self.sync([good, bad, ticker, ok])
        self.assertEqual(r.status_code, 200, r.text)
        ids = sorted(a.id for a in self.alerts_db)
        self.assertEqual(ids, ["g1", "ok1"])
        w = {x["id"]: x for x in r.json()["warnings"]}
        self.assertEqual(set(w), {"b1", "b2"})
        self.assertTrue(w["b1"]["error_code"].startswith("BOURSE_"))
        self.assertEqual([a for a in self.alerts_db if a.id == "ok1"][0].market_symbol, "عیار")

    def test_existing_unchanged_item_skips_gateway(self):
        self.assertEqual(self.sync([body(id="ok1")]).status_code, 200)
        self.fc.calls.clear()
        with patch.object(config, "IRAN_BOURSE_ENABLED", False):        # even with the flag off it is untouched
            r = self.sync([body(id="ok1")])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.fc.calls, [])
        self.assertEqual([a.id for a in self.alerts_db], ["ok1"])
        self.assertNotIn("warnings", r.json())

    def test_flag_off_new_bourse_item_dropped(self):
        with patch.object(config, "IRAN_BOURSE_ENABLED", False):
            r = self.sync([body(id="n1"), body(id="n2", exchange="binance", symbol="BTCUSDT", target_price=5.0)])
        self.assertEqual([a.id for a in self.alerts_db], ["n2"])
        self.assertEqual(r.json()["warnings"][0]["error_code"], "BOURSE_503")

    def test_sync_without_bourse_items_unchanged(self):
        r = self.sync([body(id="g1", exchange="binance", symbol="BTCUSDT", target_price=50000.0)])
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("warnings", r.json())
        self.assertEqual(self.fc.calls, [])


class TestLifecycle(unittest.IsolatedAsyncioTestCase):
    def mk(self, ex="tsetmc", sym=AYAR):
        return Alert(id="a1", user_id="u", exchange=ex, symbol=sym, target_price=1.0, market_symbol="عیار")

    def ids(self, n=MIN_FULL_SNAPSHOT + 10):
        return {str(10**16 + i) for i in range(n)}

    def test_flag_and_clear(self):
        a = self.mk()
        self.assertEqual(reconcile_missing([a], self.ids()), [a])
        self.assertTrue(a.needs_attention)
        self.assertIn("no longer listed", a.needs_attention_reason)
        self.assertEqual(reconcile_missing([a], self.ids()), [])               # not flagged twice
        back = self.ids() | {AYAR}
        self.assertEqual(reconcile_missing([a], back), [a])
        self.assertFalse(a.needs_attention)
        self.assertIsNone(a.needs_attention_reason)

    def test_small_snapshot_never_flags(self):
        a = self.mk()
        self.assertEqual(reconcile_missing([a], {"1"}), [])
        self.assertEqual(reconcile_missing([a], self.ids(MIN_FULL_SNAPSHOT - 1)), [])
        self.assertFalse(a.needs_attention)

    def test_other_markets_never_touched(self):
        others = [self.mk("binance", "BTCUSDT"), self.mk("nobitex", "USDTIRT"), self.mk("tse", "FOLD")]
        self.assertEqual(reconcile_missing(others, self.ids()), [])
        self.assertTrue(all(not getattr(o, "needs_attention", False) for o in others))

    def test_crypto_flag_not_cleared_by_bourse(self):
        a = self.mk(); a.needs_attention = True; a.needs_attention_reason = "something else"
        reconcile_missing([a], self.ids() | {AYAR})
        self.assertTrue(a.needs_attention)                                      # not ours to clear

    async def test_poller_reconciles_on_full_snapshot_only(self):
        a = self.mk()
        full = [dict(_q(), id=i) for i in self.ids()]
        class FC:
            def __init__(s): s.n = 0
            async def changes(s, since=0):
                s.n += 1
                return (full if since == 0 else []), {"seq": 5, "stale": False}
        db = [a]; save = AsyncMock()
        with patch.object(storage, "ALERTS_DB", db), patch.object(storage, "save_alerts_to_disk_async", save):
            p = BoursePoller(client=FC(), demand_fn=lambda: {AYAR}, poll_seconds=5.0)
            await p.poll_once()
            self.assertTrue(a.needs_attention)
            self.assertEqual(save.await_count, 1)
            a.needs_attention = False
            await p.poll_once()                                                  # since=5: partial, no reconcile
            self.assertFalse(a.needs_attention)
            self.assertEqual(save.await_count, 1)


if __name__ == "__main__":
    unittest.main()
