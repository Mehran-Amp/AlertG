# -*- coding: utf-8 -*-
"""
IB-2: gateway contract, locked on REAL captures (tests/fixtures/iran_bourse/real/, taken 2026-11-14 from
tsetmc-gateway 0.2.2 on a Tehran-IP host). A gateway change that drops or retypes a field AlertG relies on
must fail here, not in production.
"""
import copy
import json
import os
import re
import unittest
from datetime import datetime

import httpx

from app.markets.iran_bourse.client import (
    BourseBadVersion, BourseClient, BourseUnauthorized,
)
from app.markets.iran_bourse.mapping import (
    MappingError, REQUIRED_QUOTE_FIELDS, meta_as_of, quote_to_price_result, validate_quote,
)
from app.markets.iran_bourse.price import MAX_ID_LEN, MIN_ID_LEN, valid_instrument_id

REAL = os.path.join(os.path.dirname(__file__), "fixtures", "iran_bourse", "real")
AYAR = "34144395039913458"


def load(name):
    with open(os.path.join(REAL, name), encoding="utf-8") as f:
        return json.load(f)


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


STR_FIELDS = ("id", "isin", "ticker", "name", "update_time", "market_code", "board_code", "type_code", "sector_code")
NUM_FIELDS = ("last", "close", "first", "low", "high", "yesterday", "trades", "volume", "value",
              "upper_limit", "lower_limit")
NULLABLE_NUM = ("last_change_pct", "close_change_pct", "nav")
NULLABLE_STR = ("market", "board", "type", "sector")


def check_quote(tc, q):
    """Appendix C: required fields and types."""
    for f in REQUIRED_QUOTE_FIELDS:
        tc.assertIn(f, q, f"missing {f}")
    for f in STR_FIELDS:
        tc.assertIsInstance(q[f], str, f)
    for f in NUM_FIELDS:
        tc.assertTrue(is_num(q[f]), f"{f}={q[f]!r}")
    for f in NULLABLE_NUM:
        tc.assertTrue(q[f] is None or is_num(q[f]), f"{f}={q[f]!r}")
    for f in NULLABLE_STR:
        tc.assertTrue(q[f] is None or isinstance(q[f], str), f)
    tc.assertIsInstance(q["traded"], bool)
    tc.assertIsInstance(q["rev"], int)
    tc.assertIn(q["queue"], (None, "buy", "sell"))
    for side in ("best_bid", "best_ask"):
        v = q[side]
        if v is not None:
            tc.assertEqual(set(v) >= {"price", "volume", "orders"}, True, side)
    tc.assertRegex(q["update_time"], r"^\d{2}:\d{2}:\d{2}$")
    tc.assertTrue(q["id"].isdigit() and q["id"].isascii(), "id must be a digit string (N6)")
    tc.assertTrue(MIN_ID_LEN <= len(q["id"]) <= MAX_ID_LEN, f"id length {len(q['id'])}")
    tc.assertTrue(q["lower_limit"] <= q["upper_limit"], "limits order")


def check_meta(tc, meta):
    tc.assertEqual(meta["unit"], "IRR")                         # D1: Rial, no conversion
    tc.assertIsInstance(meta["seq"], int)
    tc.assertIsInstance(meta["stale"], bool)
    tc.assertTrue(is_num(meta["age_seconds"]))
    datetime.fromisoformat(meta["updated_at"])
    tc.assertIsNotNone(meta_as_of(meta))


class TestRealFixtures(unittest.TestCase):
    def test_health(self):
        for name in ("health.json", "health_t30.json"):
            h = load(name)
            self.assertEqual(h["version"], "0.2.2")
            self.assertIn(h["status"], ("ok", "degraded"))
            for k, t in (("ready", bool), ("stale", bool), ("instruments", int), ("seq", int), ("active_window", bool)):
                self.assertIsInstance(h[k], t, k)
            self.assertTrue(is_num(h["age_seconds"]))
            self.assertGreater(h["instruments"], 3000)
            self.assertEqual(h["stats"]["bad_rows"], 0)

    def test_quote_ayar(self):
        body = load("quote_ayar.json")
        check_meta(self, body["meta"])
        q = body["data"]
        check_quote(self, q)
        self.assertEqual((q["id"], q["ticker"], q["name"]), (AYAR, "عیار", "صندوق طلای عیار مفید"))
        self.assertEqual(q["isin"], "IRTKMOFD0001")

    def test_quotes_missing(self):
        body = load("quotes_missing.json")
        check_meta(self, body["meta"])
        self.assertIsInstance(body["data"], list)
        self.assertIsInstance(body["missing"], list)
        for q in body["data"]:
            check_quote(self, q)
        self.assertEqual([q["id"] for q in body["data"]], [AYAR])
        self.assertEqual(body["missing"], ["99999999999999999"])    # strings, never numbers

    def test_symbols(self):
        body = load("symbols.json")
        check_meta(self, body["meta"])
        self.assertLessEqual(len(body["data"]), 5)
        self.assertEqual(body["data"][0]["id"], AYAR)
        for q in body["data"]:
            check_quote(self, q)

    def test_classification(self):
        body = load("classification.json")
        check_meta(self, body["meta"])
        self.assertEqual(set(body["data"]), {"codes", "observed"})
        self.assertIsInstance(body["data"]["codes"], dict)
        self.assertIsInstance(body["data"]["observed"], dict)

    def test_changes_reload_every_row(self):
        body = load("changes_reload_trimmed.json")
        check_meta(self, body["meta"])
        rows = body["data"]
        self.assertGreater(len(rows), 30)
        for q in rows:
            check_quote(self, q)
            validate_quote(q)                                   # AlertG's own gate agrees
            r = quote_to_price_result(q, body["meta"])
            self.assertEqual(r["currency"], "IRR")
            self.assertIn(r["state"], ("LIVE", "NO_TRADE_TODAY", "STALE"))
            self.assertEqual(r["price"], q["last"] if q["last"] > 0 else None)
            self.assertIsInstance(r["asOf"], int)

    def test_real_edge_cases_are_covered(self):
        rows = load("changes_reload_trimmed.json")["data"]
        self.assertTrue(any(len(q["id"]) == 14 for q in rows), "14-digit ids exist in real data")
        self.assertTrue({15, 16, 17} <= {len(q["id"]) for q in rows})
        self.assertTrue(any(q["best_bid"] is None for q in rows))
        self.assertTrue(any(q["type"] is None for q in rows))
        self.assertTrue(any(q["queue"] == "buy" for q in rows) and any(q["queue"] == "sell" for q in rows))
        self.assertTrue(any(q["traded"] for q in rows) and any(not q["traded"] for q in rows))
        for q in rows:
            self.assertTrue(valid_instrument_id(q["id"]), q["id"])   # AlertG accepts every real id

    def test_ids_above_2_pow_53_stay_strings(self):
        raw = open(os.path.join(REAL, "quote_ayar.json"), encoding="utf-8").read()
        self.assertRegex(raw, r'"id":\s*"34144395039913458"')       # quoted in the wire format


class TestContractBreaks(unittest.TestCase):
    """The contract must FAIL when the gateway changes shape."""
    def quote(self):
        return copy.deepcopy(load("quote_ayar.json")["data"])

    def test_every_required_field_is_enforced(self):
        for f in REQUIRED_QUOTE_FIELDS:
            q = self.quote(); del q[f]
            with self.assertRaises(MappingError, msg=f):
                validate_quote(q)
            with self.assertRaises(AssertionError, msg=f):
                check_quote(self, q)

    def test_numeric_id_rejected(self):
        q = self.quote(); q["id"] = int(q["id"])
        with self.assertRaises(MappingError):
            validate_quote(q)
        with self.assertRaises(AssertionError):
            check_quote(self, q)

    def test_retyped_price_detected(self):
        q = self.quote(); q["last"] = "671609"
        with self.assertRaises(AssertionError):
            check_quote(self, q)

    def test_unit_change_detected(self):
        meta = copy.deepcopy(load("quote_ayar.json")["meta"]); meta["unit"] = "IRT"
        with self.assertRaises(AssertionError):
            check_meta(self, meta)


def real_transport(version="0.2.2", log=None):
    """A fake gateway that serves the real captures."""
    def handler(req: httpx.Request) -> httpx.Response:
        if log is not None:
            log.append(req.url.path)
        p = req.url.path
        if p == "/health":
            h = load("health.json"); h["version"] = version
            return httpx.Response(200, json=h)
        if req.headers.get("x-api-key") != "k":
            return httpx.Response(401, json={"error": "unauthorized"})
        table = {"/v1/classification": "classification.json", "/v1/symbols": "symbols.json",
                 "/v1/quotes": "quotes_missing.json", "/v1/changes": "changes_reload_trimmed.json"}
        if p == "/v1/quote/" + AYAR:
            return httpx.Response(200, content=open(os.path.join(REAL, "quote_ayar.json"), "rb").read())
        if p in table:
            return httpx.Response(200, content=open(os.path.join(REAL, table[p]), "rb").read())
        return httpx.Response(404, json={"error": "not found"})
    return httpx.MockTransport(handler)


class TestClientOnRealCaptures(unittest.IsolatedAsyncioTestCase):
    async def client(self, **kw):
        http = httpx.AsyncClient(transport=real_transport(kw.pop("version", "0.2.2"), kw.pop("log", None)))
        self.addAsyncCleanup(http.aclose)
        return BourseClient(http, "http://gw", "k", **kw)

    async def test_every_call_parses_real_bytes(self):
        c = await self.client()
        self.assertEqual((await c.health())["version"], "0.2.2")
        q, meta = await c.quote(AYAR)
        self.assertEqual(q["id"], AYAR); check_meta(self, meta)
        found, missing, _ = await c.quotes([AYAR, "99999999999999999"])
        self.assertEqual(([x["id"] for x in found], missing), ([AYAR], ["99999999999999999"]))
        rows, _ = await c.symbols("عیار", 5)
        self.assertEqual(rows[0]["id"], AYAR)
        cls, _ = await c.classification()
        self.assertIn("codes", cls)
        changes, meta = await c.changes(0)
        self.assertGreater(len(changes), 30)

    async def test_wrong_key_is_401(self):
        http = httpx.AsyncClient(transport=real_transport())
        self.addAsyncCleanup(http.aclose)
        with self.assertRaises(BourseUnauthorized):
            await BourseClient(http, "http://gw", "wrong").quote(AYAR)


class TestVersionGate(unittest.IsolatedAsyncioTestCase):
    async def mk(self, version, log, clock=None):
        http = httpx.AsyncClient(transport=real_transport(version, log))
        self.addAsyncCleanup(http.aclose)
        kw = {"clock": clock} if clock else {}
        return BourseClient(http, "http://gw", "k", verify_version_every=600.0, **kw)

    async def test_allowed_version_passes_and_is_checked_once(self):
        log = []
        c = await self.mk("0.2.2", log)
        await c.quote(AYAR); await c.quote(AYAR); await c.changes(0)
        self.assertEqual(log.count("/health"), 1)                  # not on every call
        self.assertTrue(c.version_state()["ok"])

    async def test_unlisted_version_blocks_every_data_call(self):
        log = []
        c = await self.mk("0.3.0", log)
        for call in (lambda: c.quote(AYAR), lambda: c.quotes([AYAR]), lambda: c.changes(0),
                     lambda: c.symbols("x", 5), lambda: c.classification()):
            with self.assertRaises(BourseBadVersion):
                await call()
        self.assertEqual([p for p in log if p != "/health"], [])   # no data request ever left
        self.assertFalse(c.version_state()["ok"])
        self.assertIn("0.3.0", c.version_state()["error"])

    async def test_bad_version_not_rechecked_for_60s_then_recovers(self):
        t = [1000.0]
        log = []
        http = httpx.AsyncClient(transport=real_transport("0.3.0", log)); self.addAsyncCleanup(http.aclose)
        c = BourseClient(http, "http://gw", "k", verify_version_every=600.0, clock=lambda: t[0])
        for _ in range(3):
            with self.assertRaises(BourseBadVersion):
                await c.quote(AYAR)
        self.assertEqual(log.count("/health"), 1)
        t[0] += 61
        with self.assertRaises(BourseBadVersion):
            await c.quote(AYAR)
        self.assertEqual(log.count("/health"), 2)                  # re-checked after 60 s
        http2 = httpx.AsyncClient(transport=real_transport("0.2.2", log)); self.addAsyncCleanup(http2.aclose)
        c._http = http2                                            # operator fixed the gateway
        t[0] += 61
        q, _ = await c.quote(AYAR)
        self.assertEqual(q["id"], AYAR)

    async def test_recheck_after_ttl(self):
        t = [1000.0]; log = []
        c = await self.mk("0.2.2", log, clock=lambda: t[0])
        await c.quote(AYAR); t[0] += 599; await c.quote(AYAR)
        self.assertEqual(log.count("/health"), 1)
        t[0] += 2; await c.quote(AYAR)
        self.assertEqual(log.count("/health"), 2)

    async def test_gate_off_by_default(self):
        log = []
        http = httpx.AsyncClient(transport=real_transport("9.9.9", log)); self.addAsyncCleanup(http.aclose)
        await BourseClient(http, "http://gw", "k").quote(AYAR)     # existing behaviour unchanged
        self.assertEqual(log.count("/health"), 0)

    async def test_poller_builds_gated_client(self):
        import app.config as config
        from unittest.mock import patch
        from app.markets.iran_bourse.poller import BoursePoller
        with patch.object(config, "IRAN_BOURSE_GATEWAY_URL", "http://gw"), patch.object(config, "IRAN_BOURSE_GATEWAY_KEY", "k"):
            p = BoursePoller(demand_fn=lambda: set())
            c = p._get_client()
            self.assertTrue(c.version_state()["gate"])
            await p.stop()


if __name__ == "__main__":
    unittest.main()
