# -*- coding: utf-8 -*-
"""IB-4a: gateway client, using httpx.MockTransport (no network)."""
import asyncio
import json
import os
import unittest

import httpx

from app.markets.iran_bourse.client import (
    BourseBadResponse, BourseBadVersion, BourseClient, BourseConnectionError,
    BourseNotFound, BourseNotReady, BourseTimeout, BourseUnauthorized,
)

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "iran_bourse")
AYAR_ID = "34144395039913458"
KEY = "test-key"


def load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


def make(handler, **kw):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return BourseClient(http, "http://gw.local:8080/", KEY, **kw), http


def json_response(body, status=200):
    return httpx.Response(status, content=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                          headers={"content-type": "application/json; charset=utf-8"})


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_quote_success_sends_key_and_keeps_persian_and_big_id(self):
        seen = {}

        def handler(req):
            seen["key"] = req.headers.get("x-api-key")
            seen["path"] = req.url.path
            return json_response(load("quote_ayar.json"))

        c, http = make(handler)
        async with http:
            quote, meta = await c.quote(AYAR_ID)
        self.assertEqual(seen["key"], KEY)
        self.assertEqual(seen["path"], "/v1/quote/" + AYAR_ID)
        self.assertEqual(quote["id"], AYAR_ID)
        self.assertIsInstance(quote["id"], str)
        self.assertEqual(quote["name"], "صندوق طلای عیار مفید")
        self.assertEqual(meta["unit"], "IRR")

    async def test_as_of_ignores_a_wrong_gateway_clock(self):
        """Real incident: gateway PC clock was 10.5 h ahead; asOf must follow OUR clock."""
        import time
        from datetime import datetime, timedelta, timezone
        wrong = (datetime.now(timezone.utc) + timedelta(hours=10, minutes=30)).isoformat()

        def handler(req):
            body = load("quote_ayar.json")
            body["meta"] = dict(body["meta"], updated_at=wrong, age_seconds=20.0)
            return json_response(body)

        c, http = make(handler)
        async with http:
            _, meta = await c.quote(AYAR_ID)
        self.assertLess(abs(meta["local_as_of"] - (time.time() - 20.0)), 3)
        self.assertEqual(meta["updated_at"], wrong)          # original field is left untouched

    async def test_as_of_without_or_with_bad_age_uses_receive_time(self):
        import time
        for bad in (None, "x", -5, 10 ** 9, True):
            def handler(req, bad=bad):
                body = load("quote_ayar.json")
                meta = dict(body["meta"])
                meta.pop("age_seconds", None)
                if bad is not None:
                    meta["age_seconds"] = bad
                body["meta"] = meta
                return json_response(body)

            c, http = make(handler)
            async with http:
                _, meta = await c.quote(AYAR_ID)
            self.assertLess(abs(meta["local_as_of"] - time.time()), 3, f"age={bad!r}")

    async def test_401(self):
        c, http = make(lambda r: json_response({"error": "x"}, 401))
        async with http:
            with self.assertRaises(BourseUnauthorized):
                await c.quote(AYAR_ID)

    async def test_503_not_ready(self):
        c, http = make(lambda r: json_response({"error": "x"}, 503))
        async with http:
            with self.assertRaises(BourseNotReady):
                await c.changes(0)

    async def test_404_unknown(self):
        c, http = make(lambda r: json_response({"error": "x"}, 404))
        async with http:
            with self.assertRaises(BourseNotFound):
                await c.quote("123")

    async def test_unexpected_status(self):
        c, http = make(lambda r: json_response({"error": "x"}, 500))
        async with http:
            with self.assertRaises(BourseBadResponse):
                await c.quote(AYAR_ID)

    async def test_timeout(self):
        def handler(req):
            raise httpx.ReadTimeout("slow", request=req)
        c, http = make(handler)
        async with http:
            with self.assertRaises(BourseTimeout):
                await c.quote(AYAR_ID)

    async def test_connection_error(self):
        def handler(req):
            raise httpx.ConnectError("down", request=req)
        c, http = make(handler)
        async with http:
            with self.assertRaises(BourseConnectionError):
                await c.quote(AYAR_ID)

    async def test_no_hidden_retry(self):
        calls = []

        def handler(req):
            calls.append(1)
            return json_response({"error": "x"}, 500)

        c, http = make(handler)
        async with http:
            with self.assertRaises(BourseBadResponse):
                await c.quote(AYAR_ID)
        self.assertEqual(len(calls), 1)

    async def test_malformed_json(self):
        c, http = make(lambda r: httpx.Response(200, content=b"{not json"))
        async with http:
            with self.assertRaises(BourseBadResponse):
                await c.quote(AYAR_ID)

    async def test_non_object_body(self):
        c, http = make(lambda r: httpx.Response(200, content=b"[1,2]"))
        async with http:
            with self.assertRaises(BourseBadResponse):
                await c.quote(AYAR_ID)

    async def test_missing_envelope(self):
        c, http = make(lambda r: json_response({"data": {}}))
        async with http:
            with self.assertRaises(BourseBadResponse):
                await c.quote(AYAR_ID)

    async def test_missing_quote_field(self):
        env = load("quote_ayar.json")
        del env["data"]["last"]
        c, http = make(lambda r: json_response(env))
        async with http:
            with self.assertRaises(BourseBadResponse):
                await c.quote(AYAR_ID)

    async def test_numeric_id_in_quote_is_rejected(self):
        env = load("quote_ayar.json")
        env["data"]["id"] = 34144395039913458
        c, http = make(lambda r: json_response(env))
        async with http:
            with self.assertRaises(BourseBadResponse):
                await c.quote(AYAR_ID)

    async def test_changes_returns_quotes_and_meta(self):
        seen = {}

        def handler(req):
            seen["since"] = req.url.params.get("since")
            return json_response(load("changes.json"))

        c, http = make(handler)
        async with http:
            data, meta = await c.changes(0)
        self.assertEqual(seen["since"], "0")
        self.assertEqual(len(data), 1)
        self.assertEqual(meta["seq"], 1)

    async def test_quotes_found_and_missing(self):
        c, http = make(lambda r: json_response(load("quotes_missing.json")))
        async with http:
            found, missing, meta = await c.quotes([AYAR_ID, "999"])
        self.assertEqual(len(found), 1)
        self.assertEqual(missing, ["999"])

    async def test_quotes_limits(self):
        c, http = make(lambda r: json_response({}))
        async with http:
            with self.assertRaises(ValueError):
                await c.quotes([])
            with self.assertRaises(ValueError):
                await c.quotes([str(i) for i in range(201)])

    async def test_symbols_params_and_limit_cap(self):
        seen = {}

        def handler(req):
            seen.update(dict(req.url.params))
            return json_response({"meta": {}, "data": []})

        c, http = make(handler)
        async with http:
            await c.symbols("عیار", limit=500, traded=1, market=None)
        self.assertEqual(seen["q"], "عیار")
        self.assertEqual(seen["limit"], "100")
        self.assertEqual(seen["traded"], "1")
        self.assertNotIn("market", seen)

    async def test_classification(self):
        c, http = make(lambda r: json_response({"meta": {}, "data": {"codes": {}, "observed": {}}}))
        async with http:
            data, _ = await c.classification()
        self.assertIn("codes", data)

    async def test_version_gate(self):
        health = load("health.json")
        c, http = make(lambda r: json_response(health))
        async with http:
            self.assertEqual((await c.check_version())["version"], "0.2.2")
        c2, http2 = make(lambda r: json_response(dict(health, version="9.9.9")))
        async with http2:
            with self.assertRaises(BourseBadVersion):
                await c2.check_version()
        c3, http3 = make(lambda r: json_response(dict(health, version="9.9.9")),
                         allowed_versions=("9.9.9",))
        async with http3:
            await c3.check_version()

    async def test_only_one_request_in_flight(self):
        state = {"now": 0, "max": 0}

        async def handler(req):
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
            await asyncio.sleep(0.02)
            state["now"] -= 1
            return json_response(load("quote_ayar.json"))

        c, http = make(handler)
        async with http:
            await asyncio.gather(*[c.quote(AYAR_ID) for _ in range(8)])
        self.assertEqual(state["max"], 1)


if __name__ == "__main__":
    unittest.main()
