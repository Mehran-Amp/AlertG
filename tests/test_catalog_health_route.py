#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — Crypto Catalog Health Route Visibility Tests (Phase CS4).
Validates:
1. Dynamic crypto catalog health summary on /status, /api/status, and /api/health.
2. Total active exchanges = 18 (16 Global + 2 Iran).
3. Per-exchange metrics:
   - total_pairs (int)
   - updated_at (canonical ISO timestamp string)
   - age_seconds (elapsed seconds from update)
   - is_stale (boolean staleness evaluation)
   - last_error (error message or reason for staleness)
4. Summary statistics:
   - total_active == 18
   - total_global == 16
   - total_iran == 2
   - healthy_count
   - stale_count
   - oldest_catalog_age_minutes
5. Isolation: strictly non-destructive and independent of network.
"""

import unittest
import os
import sys
import json
import time
import shutil
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# Safe module mocks for isolated testing environments
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

try:
    import fastapi
except ImportError:
    fastapi = MagicMock()
    class APIRouter:
        def get(self, *a, **kw):
            return lambda fn: fn
        def post(self, *a, **kw):
            return lambda fn: fn
        def delete(self, *a, **kw):
            return lambda fn: fn
        def put(self, *a, **kw):
            return lambda fn: fn
        def patch(self, *a, **kw):
            return lambda fn: fn
        def include_router(self, *a, **kw): pass

    class HTTPException(Exception):
        def __init__(self, status_code=500, detail="", **kw):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class Response:
        def __init__(self, content=b"", status_code=200, headers=None, media_type=None, **kwargs):
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
    fastapi.__path__ = []
    sys.modules['fastapi'] = fastapi

    import types
    resp_mod = types.ModuleType('fastapi.responses')
    class JSONResponse(Response):
        def __init__(self, content=None, status_code=200, headers=None, **kwargs):
            self._json_data = content
            b = json.dumps(content).encode("utf-8") if isinstance(content, (dict, list)) else (content or b"")
            super().__init__(content=b, status_code=status_code, headers=headers or {})
        def json(self):
            return self._json_data if self._json_data is not None else json.loads(self.content.decode("utf-8"))

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


from app.markets.crypto_catalog import (
    get_crypto_catalogs_status,
    save_exchange_catalog_atomic,
    get_supported_crypto_exchanges,
)
from app.markets.crypto_registry import get_supported_exchange_ids


class TestCatalogHealthRoute(unittest.TestCase):
    """Tests for Phase CS4: Dynamic Crypto Catalog Health Visibility."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="alertg_health_test_")
        self.now_ts = int(time.time())

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_health_status_structure_and_counts(self):
        """1. Verifies get_crypto_catalogs_status returns all 18 active exchanges (16 global, 2 Iran) and summary."""
        # Seed fresh catalog for Binance (global)
        save_exchange_catalog_atomic(
            "binance",
            {
                "exchange": "binance",
                "total_pairs": 518,
                "updated_at": self.now_ts - 300,  # 5 min ago
                "is_stale": False,
                "error": None,
                "pairs": [{"base": "BTC", "quote": "USDT"}],
            },
            override_dir=self.test_dir
        )

        # Seed fresh catalog for Tabdeal (Iran)
        save_exchange_catalog_atomic(
            "tabdeal",
            {
                "exchange": "tabdeal",
                "total_pairs": 110,
                "updated_at": self.now_ts - 600,  # 10 min ago
                "is_stale": False,
                "error": None,
                "pairs": [{"base": "BTC", "quote": "USDT"}],
            },
            override_dir=self.test_dir
        )

        # Seed stale catalog for MEXC (global) by age (> 4h)
        save_exchange_catalog_atomic(
            "mexc",
            {
                "exchange": "mexc",
                "total_pairs": 1200,
                "updated_at": self.now_ts - (5 * 3600),  # 5 hours ago
                "is_stale": False,
                "error": None,
                "pairs": [{"base": "BTC", "quote": "USDT"}],
            },
            override_dir=self.test_dir
        )

        status = get_crypto_catalogs_status(override_dir=self.test_dir)

        # Assert exchange counts
        self.assertEqual(status["total_active_exchanges"], 18)
        self.assertEqual(status["total_global_exchanges"], 16)
        self.assertEqual(status["total_iran_exchanges"], 2)
        self.assertEqual(status["total_exchanges"], 16)  # backward compatibility

        # Assert summary object
        self.assertIn("summary", status)
        summary = status["summary"]
        self.assertEqual(summary["total_active"], 18)
        self.assertEqual(summary["total_global"], 16)
        self.assertEqual(summary["total_iran"], 2)

        # 2 healthy (binance, tabdeal), 16 stale/missing (15 missing + 1 stale MEXC)
        self.assertEqual(summary["healthy_count"], 2)
        self.assertEqual(summary["stale_count"], 16)
        self.assertIsNotNone(summary["oldest_catalog_age_minutes"])
        self.assertAlmostEqual(summary["oldest_catalog_age_minutes"], 300.0, delta=2.0)

        # Assert all 18 exchanges exist in exchanges dictionary
        exchanges = status["exchanges"]
        self.assertEqual(len(exchanges), 18)
        for expected_id in [
            "binance", "mexc", "kucoin", "gateio", "lbank", "okx", "kraken",
            "bybit", "bitget", "htx", "bingx", "xt", "toobit", "poloniex",
            "coinbase", "bitfinex", "tabdeal", "kifpool"
        ]:
            self.assertIn(expected_id, exchanges, f"Missing exchange {expected_id} in exchanges map")

    def test_02_per_exchange_schema_and_iso_timestamp(self):
        """2. Verifies per-exchange schema: total_pairs, updated_at (ISO), age_seconds, is_stale, last_error."""
        known_ts = 1731320000
        save_exchange_catalog_atomic(
            "gateio",
            {
                "exchange": "gateio",
                "total_pairs": 2038,
                "updated_at": known_ts,
                "is_stale": False,
                "error": None,
                "pairs": [{"base": "BTC", "quote": "USDT"}],
            },
            override_dir=self.test_dir
        )

        status = get_crypto_catalogs_status(override_dir=self.test_dir)
        gate_info = status["exchanges"]["gateio"]

        self.assertTrue(gate_info["file_exists"])
        self.assertEqual(gate_info["total_pairs"], 2038)
        self.assertEqual(gate_info["category"], "tier1")

        # ISO timestamp check
        expected_iso = datetime.fromtimestamp(known_ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertEqual(gate_info["updated_at"], expected_iso)
        self.assertEqual(gate_info["updated_at_iso"], expected_iso)
        self.assertEqual(gate_info["updated_at_raw"], known_ts)

        # Age seconds check
        expected_age = max(0, int(time.time() - known_ts))
        self.assertAlmostEqual(gate_info["age_seconds"], expected_age, delta=5)

        # Missing exchange check (Kifpool unseeded)
        kifpool_info = status["exchanges"]["kifpool"]
        self.assertFalse(kifpool_info["file_exists"])
        self.assertEqual(kifpool_info["total_pairs"], 0)
        self.assertIsNone(kifpool_info["updated_at"])
        self.assertIsNone(kifpool_info["age_seconds"])
        self.assertTrue(kifpool_info["is_stale"])
        self.assertEqual(kifpool_info["last_error"], "Catalog file does not exist yet")
        self.assertEqual(kifpool_info["category"], "iran_crypto")

    def test_03_admin_status_json_dashboard_contains_catalog_health(self):
        """3. Verifies GET /status?format=json exposes crypto_catalogs and crypto_catalog_health."""
        from app.routes.admin import get_status_dashboard

        # Seed one catalog in test_dir
        save_exchange_catalog_atomic(
            "binance",
            {
                "exchange": "binance",
                "total_pairs": 518,
                "updated_at": self.now_ts,
                "is_stale": False,
                "error": None,
            },
            override_dir=self.test_dir
        )

        with patch("app.markets.crypto_catalog.get_catalog_dir", return_value=self.test_dir):
            response = get_status_dashboard(format="json")

            # Extract content from JSONResponse
            if hasattr(response, "json"):
                data = response.json()
            else:
                data = json.loads(response.body.decode("utf-8") if hasattr(response, "body") else response.content.decode("utf-8"))

            self.assertIn("crypto_catalogs", data)
            self.assertIn("crypto_catalog_health", data)

            cat_data = data["crypto_catalogs"]
            self.assertEqual(cat_data["total_active_exchanges"], 18)
            self.assertEqual(cat_data["total_global_exchanges"], 16)
            self.assertEqual(cat_data["total_iran_exchanges"], 2)

            health_summary = data["crypto_catalog_health"]
            self.assertEqual(health_summary["total_active"], 18)
            self.assertEqual(health_summary["total_global"], 16)
            self.assertEqual(health_summary["total_iran"], 2)
            self.assertIn("healthy_count", health_summary)
            self.assertIn("stale_count", health_summary)

    def test_04_admin_crypto_catalog_status_and_health_endpoints(self):
        """4. Verifies dedicated admin and health endpoints return accurate crypto catalog health."""
        from app.routes.admin import get_admin_crypto_catalog_status, get_health_summary

        with patch("app.markets.crypto_catalog.get_catalog_dir", return_value=self.test_dir):
            admin_status = get_admin_crypto_catalog_status()
            self.assertEqual(admin_status["total_active_exchanges"], 18)
            self.assertIn("summary", admin_status)
            self.assertIn("exchanges", admin_status)

            health_resp = get_health_summary()
            self.assertIn("crypto_catalogs", health_resp)
            self.assertIn("crypto_catalog_health", health_resp)
            self.assertEqual(health_resp["crypto_catalog_health"]["total_active"], 18)


if __name__ == "__main__":
    unittest.main()
