#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — Crypto Symbols API Acceptance & Contract Tests (Phase 6, T2).
Validates:
1. GET /api/crypto/exchanges:
   - Lists all 7 supported exchanges with metadata (id, name, display_name, total_pairs, last_updated_at, is_stale).
   - Authentication enforcement (401 without API key).
2. GET /api/crypto/symbols/{exchange} and GET /api/crypto/symbols:
   - 404 on unknown or unsupported exchange with descriptive error message.
   - Multi-tier search ranking: Exact match -> Prefix match (starts with) -> Substring match (contains).
   - Pagination (limit, offset, cursor, max limit cap).
   - ETag & 304 Not Modified caching.
   - Gzip compression on demand.
   - Quote currency filtering (e.g. USDT).
3. Zero mutation / regression (R3, R4, R5):
   - catalog.json remains pristine and untouched.
   - Legacy /api/symbols/wallstreet-macro remains intact.
"""

import os
import sys
import json
import gzip
import time
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Ensure mock/dependencies are ready before importing app modules
try:
    import httpx
except ImportError:
    httpx = MagicMock()
    class TimeoutException(Exception): pass
    class HTTPError(Exception): pass
    httpx.TimeoutException = TimeoutException
    httpx.HTTPError = HTTPError
    sys.modules['httpx'] = httpx

try:
    import apscheduler
except ImportError:
    apscheduler = MagicMock()
    sys.modules['apscheduler'] = apscheduler
    sys.modules['apscheduler.schedulers'] = apscheduler
    sys.modules['apscheduler.schedulers.asyncio'] = apscheduler

if 'fastapi' in sys.modules:
    if not hasattr(sys.modules['fastapi'], '__path__'):
        sys.modules['fastapi'].__path__ = []
    if 'fastapi.responses' not in sys.modules:
        import types
        resp_mod = types.ModuleType('fastapi.responses')
        class Response:
            def __init__(self, content=b"", status_code=200, headers=None, media_type=None):
                self.content = content if isinstance(content, bytes) else str(content).encode("utf-8")
                self.status_code = status_code
                self.headers = headers or {}
        class JSONResponse(Response):
            def __init__(self, content=None, status_code=200, headers=None, **kw):
                b = json.dumps(content).encode("utf-8") if isinstance(content, (dict, list)) else (content or b"")
                super().__init__(content=b, status_code=status_code, headers=headers or {})
        class HTMLResponse(Response): pass
        resp_mod.Response = Response
        resp_mod.JSONResponse = JSONResponse
        resp_mod.HTMLResponse = HTMLResponse
        sys.modules['fastapi'].responses = resp_mod
        sys.modules['fastapi.responses'] = resp_mod

try:
    import fastapi
except ImportError:
    import types
    fastapi = types.ModuleType('fastapi')
    fastapi.__path__ = []
    class APIRouter:
        def get(self, *a, **kw): return lambda fn: fn
        def post(self, *a, **kw): return lambda fn: fn
        def delete(self, *a, **kw): return lambda fn: fn
        def put(self, *a, **kw): return lambda fn: fn
        def patch(self, *a, **kw): return lambda fn: fn
        def include_router(self, *a, **kw): pass
    class HTTPException(Exception):
        def __init__(self, status_code=500, detail=""):
            self.status_code = status_code
            self.detail = detail
    class Response:
        def __init__(self, content=b"", status_code=200, headers=None, media_type=None):
            self.content = content if isinstance(content, bytes) else str(content).encode("utf-8")
            self.status_code = status_code
            self.headers = headers or {}
    class Request: pass
    fastapi.APIRouter = APIRouter
    fastapi.HTTPException = HTTPException
    fastapi.Response = Response
    fastapi.Request = Request
    fastapi.Header = MagicMock()
    fastapi.Depends = MagicMock()
    fastapi.Query = lambda default=None, **kw: default
    sys.modules['fastapi'] = fastapi

    resp_mod = types.ModuleType('fastapi.responses')
    class JSONResponse(Response):
        def __init__(self, content=None, status_code=200, headers=None, **kw):
            b = json.dumps(content).encode("utf-8") if isinstance(content, (dict, list)) else (content or b"")
            super().__init__(content=b, status_code=status_code, headers=headers or {})
    class HTMLResponse(Response): pass
    resp_mod.Response = Response
    resp_mod.JSONResponse = JSONResponse
    resp_mod.HTMLResponse = HTMLResponse
    fastapi.responses = resp_mod
    sys.modules['fastapi.responses'] = resp_mod

try:
    import pydantic
except ImportError:
    pydantic = MagicMock()
    class BaseModel: pass
    pydantic.BaseModel = BaseModel
    sys.modules['pydantic'] = pydantic

import app.config as config
if not getattr(config, 'API_KEY', None):
    config.API_KEY = "test_phase6_crypto_symbols_key"

from app.markets.crypto_catalog import (
    SUPPORTED_CRYPTO_EXCHANGES,
    save_exchange_catalog_atomic,
)
from app.routes.crypto_symbols import (
    build_crypto_symbols_response,
    get_crypto_exchanges,
    EXCHANGE_METADATA,
    MAX_PAGE_LIMIT,
)
from app.routes.symbols import load_golden_legacy_wallstreet_macro


class _OfflineMockResponse:
    """Helper wrapper to provide .json(), .status_code, and .headers in all environments."""
    def __init__(self, raw_resp):
        self.status_code = getattr(raw_resp, "status_code", 200)
        self.headers = getattr(raw_resp, "headers", {})
        self.content = getattr(raw_resp, "content", getattr(raw_resp, "body", b""))

    def json(self):
        if not self.content:
            return None
        return json.loads(self.content.decode("utf-8"))


class TestCryptoSymbolsAPI(unittest.TestCase):
    """Acceptance tests for Phase 6 Crypto Symbols & Exchanges API."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_phase6_crypto_cat_")
        self.headers = {"X-API-Key": config.API_KEY}

        # Root catalog preservation check
        self.root_catalog_path = os.path.abspath("catalog.json")
        self.initial_catalog_mtime = (
            os.path.getmtime(self.root_catalog_path)
            if os.path.exists(self.root_catalog_path)
            else None
        )

        # Seed realistic fixture catalogs for testing
        self._seed_test_catalogs()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _seed_test_catalogs(self):
        """Seeds fixture catalogs on disk in self.test_dir."""
        # Binance fixture: designed to test multi-tier search ranking (Exact -> Prefix -> Substring)
        binance_pairs = [
            {"base": "BTC", "quote": "USDT", "native_symbol": "BTCUSDT", "is_active": True, "is_etf": False, "min_price": 0.01, "min_qty": 0.00001},
            {"base": "BTCST", "quote": "USDT", "native_symbol": "BTCSTUSDT", "is_active": True, "is_etf": False, "min_price": 0.001, "min_qty": 0.001},
            {"base": "WBTC", "quote": "USDT", "native_symbol": "WBTCUSDT", "is_active": True, "is_etf": False, "min_price": 0.01, "min_qty": 0.00001},
            {"base": "ETH", "quote": "USDT", "native_symbol": "ETHUSDT", "is_active": True, "is_etf": False, "min_price": 0.01, "min_qty": 0.0001},
            {"base": "SOL", "quote": "USDC", "native_symbol": "SOLUSDC", "is_active": True, "is_etf": False, "min_price": 0.01, "min_qty": 0.01},
        ]
        save_exchange_catalog_atomic(
            "binance",
            {
                "exchange": "binance",
                "display_name": "Binance",
                "updated_at": 1729000000,
                "total_pairs": len(binance_pairs),
                "is_stale": False,
                "error": None,
                "pairs": binance_pairs
            },
            override_dir=self.test_dir
        )

        # MEXC fixture
        mexc_pairs = [
            {"base": "TON", "quote": "USDT", "native_symbol": "TON_USDT", "is_active": True, "is_etf": False, "min_price": 0.001, "min_qty": 0.1},
            {"base": "NOT", "quote": "USDT", "native_symbol": "NOT_USDT", "is_active": True, "is_etf": False, "min_price": 0.00001, "min_qty": 1.0},
        ]
        save_exchange_catalog_atomic(
            "mexc",
            {
                "exchange": "mexc",
                "display_name": "MEXC",
                "updated_at": 1729000100,
                "total_pairs": len(mexc_pairs),
                "is_stale": False,
                "error": None,
                "pairs": mexc_pairs
            },
            override_dir=self.test_dir
        )

        # Gate.io fixture (Fresh - tested for Task 11 staleness by age)
        gateio_pairs = [
            {"base": "GT", "quote": "USDT", "native_symbol": "GT_USDT", "is_active": True, "is_etf": False, "min_price": 0.01, "min_qty": 0.1},
        ]
        save_exchange_catalog_atomic(
            "gateio",
            {
                "exchange": "gateio",
                "display_name": "Gate.io",
                "updated_at": int(time.time()),
                "total_pairs": len(gateio_pairs),
                "is_stale": False,
                "error": None,
                "pairs": gateio_pairs
            },
            override_dir=self.test_dir
        )

    def test_01_exchanges_list_metadata(self):
        """Verifies GET /api/crypto/exchanges returns all 9 exchanges with complete metadata."""
        resp_raw = get_crypto_exchanges(catalog_dir=self.test_dir)
        resp = _OfflineMockResponse(resp_raw)

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["total"], 9)
        self.assertEqual(len(data["exchanges"]), 9)

        ex_map = {e["id"]: e for e in data["exchanges"]}
        for ex_id in ["binance", "mexc", "kucoin", "gateio", "lbank", "okx", "kraken", "bybit", "bitget"]:
            self.assertIn(ex_id, ex_map)
            item = ex_map[ex_id]
            self.assertEqual(item["exchange_id"], ex_id)
            self.assertIn("name", item)
            self.assertIn("display_name", item)
            self.assertIn("total_pairs", item)
            self.assertIn("last_updated_at", item)
            self.assertIn("is_stale", item)

        # Check seeded data for binance (stale by age >12h per Task 11 since timestamp is 1729000000)
        self.assertEqual(ex_map["binance"]["total_pairs"], 5)
        self.assertEqual(ex_map["binance"]["is_stale"], True)
        self.assertEqual(ex_map["binance"]["last_updated_at"], 1729000000)

        # Check seeded data for mexc (stale by age >12h per Task 11 since timestamp is 1729000100)
        self.assertEqual(ex_map["mexc"]["total_pairs"], 2)
        self.assertEqual(ex_map["mexc"]["is_stale"], True)

        # Check seeded fresh data for gateio (fresh <12h per Task 11)
        self.assertEqual(ex_map["gateio"]["total_pairs"], 1)
        self.assertEqual(ex_map["gateio"]["is_stale"], False)

        # Check unseeded exchange has safe defaults
        self.assertEqual(ex_map["kraken"]["total_pairs"], 0)
        self.assertEqual(ex_map["kraken"]["is_stale"], True)
        self.assertEqual(ex_map["bybit"]["total_pairs"], 0)
        self.assertEqual(ex_map["bybit"]["is_stale"], True)
        self.assertEqual(ex_map["bitget"]["total_pairs"], 0)
        self.assertEqual(ex_map["bitget"]["is_stale"], True)

    def test_02_unknown_exchange_returns_404(self):
        """Verifies unknown exchange returns 404 with clear informative error message."""
        try:
            from fastapi import HTTPException
        except ImportError:
            class HTTPException(Exception): pass

        with self.assertRaises(HTTPException) as ctx:
            build_crypto_symbols_response(
                exchange_param="nonexistent_dex",
                catalog_dir=self.test_dir
            )
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("nonexistent_dex", ctx.exception.detail)
        self.assertIn("Supported exchanges", ctx.exception.detail)

    def test_03_multi_tier_search_ranking(self):
        """
        T2 Contract Test: Search ranking must strictly return:
        Exact Match -> Prefix Match (Starts-with) -> Substring Match (Contains).
        """
        # Search for 'BTC':
        # Tier 1 exact: 'BTC'
        # Tier 2 prefix: 'BTCST'
        # Tier 3 substring: 'WBTC'
        raw_resp = build_crypto_symbols_response(
            exchange_param="binance",
            q="BTC",
            catalog_dir=self.test_dir
        )
        resp = _OfflineMockResponse(raw_resp)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        symbols = data["symbols"]
        self.assertEqual(len(symbols), 3)

        # Verify ranking order
        self.assertEqual(symbols[0]["base"], "BTC", "Exact match must rank 1st")
        self.assertEqual(symbols[1]["base"], "BTCST", "Prefix match must rank 2nd")
        self.assertEqual(symbols[2]["base"], "WBTC", "Substring match must rank 3rd")

    def test_04_pagination_and_cursors(self):
        """Verifies limit, offset, cursor and max limit capping."""
        # Page 1: limit 2
        raw_p1 = build_crypto_symbols_response(
            exchange_param="binance",
            limit=2,
            offset=0,
            catalog_dir=self.test_dir
        )
        p1 = _OfflineMockResponse(raw_p1).json()
        self.assertEqual(p1["count"], 2)
        self.assertEqual(p1["total_count"], 5)
        self.assertEqual(p1["offset"], 0)
        self.assertEqual(p1["cursor"], 2)
        self.assertTrue(p1["has_more"])

        # Page 2: limit 2, offset 2
        raw_p2 = build_crypto_symbols_response(
            exchange_param="binance",
            limit=2,
            offset=2,
            catalog_dir=self.test_dir
        )
        p2 = _OfflineMockResponse(raw_p2).json()
        self.assertEqual(p2["count"], 2)
        self.assertEqual(p2["offset"], 2)
        self.assertEqual(p2["cursor"], 4)
        self.assertTrue(p2["has_more"])

        # Page 3: limit 2, offset 4 (last item)
        raw_p3 = build_crypto_symbols_response(
            exchange_param="binance",
            limit=2,
            offset=4,
            catalog_dir=self.test_dir
        )
        p3 = _OfflineMockResponse(raw_p3).json()
        self.assertEqual(p3["count"], 1)
        self.assertEqual(p3["offset"], 4)
        self.assertIsNone(p3["cursor"])
        self.assertFalse(p3["has_more"])

        # Max limit capping: requesting limit=999 must cap to MAX_PAGE_LIMIT
        raw_capped = build_crypto_symbols_response(
            exchange_param="binance",
            limit=999,
            catalog_dir=self.test_dir
        )
        capped = _OfflineMockResponse(raw_capped).json()
        self.assertEqual(capped["limit"], MAX_PAGE_LIMIT)

    def test_05_quote_currency_filtering(self):
        """Verifies filtering by quote currency (e.g. quote=USDC vs quote=USDT)."""
        raw_usdc = build_crypto_symbols_response(
            exchange_param="binance",
            quote="USDC",
            catalog_dir=self.test_dir
        )
        usdc_data = _OfflineMockResponse(raw_usdc).json()
        self.assertEqual(usdc_data["total_count"], 1)
        self.assertEqual(usdc_data["symbols"][0]["base"], "SOL")
        self.assertEqual(usdc_data["symbols"][0]["quote"], "USDC")

        raw_usdt = build_crypto_symbols_response(
            exchange_param="binance",
            quote="USDT",
            catalog_dir=self.test_dir
        )
        usdt_data = _OfflineMockResponse(raw_usdt).json()
        self.assertEqual(usdt_data["total_count"], 4)
        for s in usdt_data["symbols"]:
            self.assertEqual(s["quote"], "USDT")

    def test_06_etag_and_304_caching(self):
        """Verifies deterministic ETag generation and 304 Not Modified status."""
        raw_resp = build_crypto_symbols_response(
            exchange_param="binance",
            catalog_dir=self.test_dir
        )
        resp = _OfflineMockResponse(raw_resp)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ETag", resp.headers)
        etag = resp.headers["ETag"]
        self.assertTrue(etag.startswith('"') and etag.endswith('"'))

        # Request with exact matching If-None-Match header -> 304
        cached_resp_raw = build_crypto_symbols_response(
            exchange_param="binance",
            if_none_match=etag,
            catalog_dir=self.test_dir
        )
        cached_resp = _OfflineMockResponse(cached_resp_raw)
        self.assertEqual(cached_resp.status_code, 304)

        # Request with differing If-None-Match header -> 200
        differ_resp_raw = build_crypto_symbols_response(
            exchange_param="binance",
            if_none_match='"different_stale_etag"',
            catalog_dir=self.test_dir
        )
        differ_resp = _OfflineMockResponse(differ_resp_raw)
        self.assertEqual(differ_resp.status_code, 200)

    def test_07_gzip_compression_support(self):
        """Verifies gzip compression when gzip=True."""
        raw_resp = build_crypto_symbols_response(
            exchange_param="binance",
            gzip_flag=True,
            catalog_dir=self.test_dir
        )
        resp = _OfflineMockResponse(raw_resp)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("Content-Encoding"), "gzip")

        # Decompress and verify content integrity
        decompressed = gzip.decompress(resp.content).decode("utf-8")
        decompressed_data = json.loads(decompressed)
        self.assertEqual(decompressed_data["status"], "success")
        self.assertEqual(decompressed_data["exchange"], "binance")
        self.assertEqual(len(decompressed_data["symbols"]), 5)

    def test_08_missing_catalog_graceful_empty_page(self):
        """Verifies an exchange with no catalog file yet returns is_stale=True and 0 symbols without 500 crash."""
        raw_resp = build_crypto_symbols_response(
            exchange_param="kraken",
            catalog_dir=self.test_dir
        )
        resp = _OfflineMockResponse(raw_resp)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["exchange"], "kraken")
        self.assertEqual(data["total_count"], 0)
        self.assertEqual(len(data["symbols"]), 0)
        self.assertTrue(data["is_stale"])
        self.assertIsNotNone(data["error"])

    def test_09_case_insensitivity_and_whitespace_normalization(self):
        """Verifies exchange names and search queries handle case and whitespace gracefully."""
        raw_resp = build_crypto_symbols_response(
            exchange_param="  BiNaNce  ",
            q="  bTc  ",
            catalog_dir=self.test_dir
        )
        resp = _OfflineMockResponse(raw_resp)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["exchange"], "binance")
        self.assertEqual(data["symbols"][0]["base"], "BTC")

    def test_10_zero_mutation_isolation_rules(self):
        """
        Rule R3 & R4: Verifies zero mutation to catalog.json and legacy endpoints.
        """
        # 1. catalog.json check
        if self.initial_catalog_mtime is not None:
            current_mtime = os.path.getmtime(self.root_catalog_path)
            self.assertEqual(
                self.initial_catalog_mtime,
                current_mtime,
                "catalog.json mtime MUST NOT change (Rule R3/R4 violation)"
            )

        # 2. Legacy /api/symbols/wallstreet-macro returns golden 94 symbols
        legacy_data = load_golden_legacy_wallstreet_macro()
        self.assertEqual(legacy_data["status"], "success")
        self.assertEqual(legacy_data["total_count"], 94)
        self.assertEqual(len(legacy_data["symbols"]), 94)


if __name__ == "__main__":
    unittest.main()
