#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — Phase 4 Test Suite: Crypto Alert Validation & Resolution Engine.
Tests:
- Rejection of discontinued exchange 'coinex' with 'EXCHANGE_NOT_SUPPORTED'.
- Rejection of unknown/unsupported crypto exchanges with 'EXCHANGE_NOT_SUPPORTED'.
- Rejection of non-USDT crypto quotes with 'INVALID_QUOTE_CURRENCY'.
- Listing verification: listed symbols pass, unlisted symbols return 'SYMBOL_NOT_LISTED'.
- Non-crypto markets (Iranian, global stocks, forex, macro) pass validation untouched.
- Two-way alias resolution using base_currency + counter_currency + market_symbol.
- API validation enforcement under config.CRYPTO_VALIDATE_ALERTS ('enforce' vs 'false').
"""

import os
import sys
import json
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

# Mock optional dependencies for test runners
try:
    import httpx
except ImportError:
    httpx = MagicMock()
    sys.modules['httpx'] = httpx

try:
    import apscheduler
except ImportError:
    apscheduler = MagicMock()
    sys.modules['apscheduler'] = apscheduler
    sys.modules['apscheduler.schedulers'] = apscheduler
    sys.modules['apscheduler.schedulers.asyncio'] = apscheduler

class BaseModel:
    def __init__(self, **kwargs):
        for cls in reversed(self.__class__.__mro__):
            for k in getattr(cls, '__annotations__', {}):
                if hasattr(cls, k):
                    setattr(self, k, getattr(cls, k))
                else:
                    setattr(self, k, None)
        for k, v in kwargs.items():
            setattr(self, k, v)
    def dict(self, *args, **kwargs):
        return self.__dict__.copy()
    def model_dump(self, *args, **kwargs):
        return self.__dict__.copy()

try:
    import pydantic
except ImportError:
    pydantic = MagicMock()
    pydantic.BaseModel = BaseModel
    pydantic.Field = lambda *args, **kwargs: kwargs.get('default', None)
    sys.modules['pydantic'] = pydantic


import types

if 'fastapi' in sys.modules:
    if not hasattr(sys.modules['fastapi'], '__path__'):
        sys.modules['fastapi'].__path__ = []
    if 'fastapi.responses' not in sys.modules:
        resp_mod = types.ModuleType('fastapi.responses')
        class Response:
            def __init__(self, content=b"", status_code=200, headers=None, media_type=None, **kw):
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
    fastapi = types.ModuleType('fastapi')
    fastapi.__path__ = []
    class APIRouter:
        def get(self, *a, **kw): return lambda fn: fn
        def post(self, *a, **kw): return lambda fn: fn
        def delete(self, *a, **kw): return lambda fn: fn
        def put(self, *a, **kw): return lambda fn: fn
        def patch(self, *a, **kw): return lambda fn: fn
        def include_router(self, *a, **kw): pass
    class Response:
        def __init__(self, content=b"", status_code=200, headers=None, media_type=None, **kwargs):
            self.content = content if isinstance(content, bytes) else str(content).encode("utf-8")
            self.status_code = status_code
            self.headers = headers or {}
    class Request: pass
    class HTTPException(Exception):
        def __init__(self, status_code=500, detail="", **kwargs):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail
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


import app.config as config
from app.markets.crypto_validation import (
    validate_crypto_alert,
    is_crypto_exchange_candidate,
)
from app.markets.crypto_catalog import (
    resolve_pair,
    save_exchange_catalog_atomic,
)
from app.models import AlertCreate, Alert, AlertPublic
from app.storage import ALERTS_DB
from app.routes.alerts import create_alert, sync_user_alerts
from fastapi import HTTPException

for model_cls in (AlertCreate, Alert, AlertPublic):
    try:
        model_cls()
    except TypeError:
        model_cls.__init__ = BaseModel.__init__
        model_cls.dict = BaseModel.dict
        model_cls.model_dump = BaseModel.model_dump




class TestCryptoValidationEngine(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_val_catalog_")
        self._orig_catalog_dir = getattr(config, "CRYPTO_CATALOG_DIR", None)
        config.CRYPTO_CATALOG_DIR = self.temp_dir

        self._orig_val_flag = getattr(config, "CRYPTO_VALIDATE_ALERTS", "false")
        self._orig_alerts = list(ALERTS_DB)
        ALERTS_DB.clear()

        # Seed sample catalog for binance and kraken
        binance_catalog = {
            "exchange": "binance",
            "updated_at": 1700000000,
            "total_pairs": 3,
            "is_stale": False,
            "pairs": [
                {
                    "symbol": "BTCUSDT",
                    "base": "BTC",
                    "quote": "USDT",
                    "native_symbol": "BTCUSDT",
                    "aliases": ["BTC-USDT", "BTC_USDT"],
                },
                {
                    "symbol": "ETHUSDT",
                    "base": "ETH",
                    "quote": "USDT",
                    "native_symbol": "ETHUSDT",
                    "aliases": ["ETH-USDT"],
                },
                {
                    "symbol": "PEPEUSDT",
                    "base": "PEPE",
                    "quote": "USDT",
                    "native_symbol": "PEPEUSDT",
                    "aliases": [],
                },
            ],
        }
        kraken_catalog = {
            "exchange": "kraken",
            "updated_at": 1700000000,
            "total_pairs": 2,
            "is_stale": False,
            "pairs": [
                {
                    "symbol": "BTCUSDT",
                    "base": "BTC",
                    "quote": "USDT",
                    "native_symbol": "XBTUSDT",
                    "aliases": ["BTCUSDT", "XBT/USDT"],
                },
                {
                    "symbol": "ETHUSDT",
                    "base": "ETH",
                    "quote": "USDT",
                    "native_symbol": "ETHUSDT",
                    "aliases": [],
                },
            ],
        }
        save_exchange_catalog_atomic("binance", binance_catalog, self.temp_dir)
        save_exchange_catalog_atomic("kraken", kraken_catalog, self.temp_dir)

    def tearDown(self):
        ALERTS_DB.clear()
        ALERTS_DB.extend(self._orig_alerts)
        config.CRYPTO_CATALOG_DIR = self._orig_catalog_dir
        config.CRYPTO_VALIDATE_ALERTS = self._orig_val_flag
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_coinex_discontinued_rejection(self):
        """Owner Decision E1.2: CoinEx is permanently discontinued and rejected with EXCHANGE_NOT_SUPPORTED."""
        is_val, code, msg = validate_crypto_alert("coinex", "BTCUSDT", override_dir=self.temp_dir)
        self.assertFalse(is_val)
        self.assertEqual(code, "EXCHANGE_NOT_SUPPORTED")
        self.assertIn("discontinued", msg.lower())

    def test_02_unknown_exchange_rejection(self):
        """Unrecognized crypto exchange must be rejected with EXCHANGE_NOT_SUPPORTED."""
        is_val, code, msg = validate_crypto_alert("unknown_dex_exchange", "BTCUSDT", override_dir=self.temp_dir)
        self.assertFalse(is_val)
        self.assertEqual(code, "EXCHANGE_NOT_SUPPORTED")

    def test_03_non_crypto_exchanges_pass_untouched(self):
        """Iranian exchanges, global stocks, and macro bypass crypto validation untouched."""
        for ex in ["nobitex", "wallex", "tabdeal", "stocks", "global_stocks", "macro", "forex"]:
            is_val, code, msg = validate_crypto_alert(ex, "USDTIRT", override_dir=self.temp_dir)
            self.assertTrue(is_val, f"Failed for {ex}")
            self.assertIsNone(code)
            self.assertIsNone(msg)

    def test_04_invalid_quote_currency_rejected(self):
        """Spot crypto alerts must use USDT quote currency; non-USDT must be rejected."""
        is_val, code, msg = validate_crypto_alert(
            exchange="binance",
            symbol="BTCEUR",
            counter_currency="EUR",
            override_dir=self.temp_dir,
        )
        self.assertFalse(is_val)
        self.assertEqual(code, "INVALID_QUOTE_CURRENCY")
        self.assertIn("USDT", msg)

    def test_05_listed_symbol_passes(self):
        """Symbol present in the exchange catalog must pass validation."""
        is_val, code, msg = validate_crypto_alert(
            exchange="binance",
            symbol="BTCUSDT",
            override_dir=self.temp_dir,
        )
        self.assertTrue(is_val)
        self.assertIsNone(code)

    def test_06_unlisted_symbol_rejected(self):
        """Symbol absent from the exchange catalog must be rejected with SYMBOL_NOT_LISTED."""
        is_val, code, msg = validate_crypto_alert(
            exchange="binance",
            symbol="FAKECOIN999USDT",
            override_dir=self.temp_dir,
        )
        self.assertFalse(is_val)
        self.assertEqual(code, "SYMBOL_NOT_LISTED")

    def test_07_kraken_alias_resolution(self):
        """Kraken uses native symbol XBTUSDT while canonical symbol is BTCUSDT."""
        # Query using canonical base and market_symbol
        status, pair = resolve_pair(
            exchange_id="kraken",
            symbol_or_base="BTCUSDT",
            market_symbol="XBTUSDT",
            override_dir=self.temp_dir,
        )
        self.assertEqual(status, "OK")
        self.assertIsNotNone(pair)
        self.assertEqual(pair["native_symbol"], "XBTUSDT")
        self.assertEqual(pair["base"], "BTC")

        # Query using only base_currency="BTC"
        status2, pair2 = resolve_pair(
            exchange_id="kraken",
            symbol_or_base="BTC",
            base_currency="BTC",
            override_dir=self.temp_dir,
        )
        self.assertEqual(status2, "OK")
        self.assertEqual(pair2["native_symbol"], "XBTUSDT")

    async def test_08_api_create_alert_enforce_mode(self):
        """create_alert route rejects invalid crypto requests when CRYPTO_VALIDATE_ALERTS=enforce."""
        config.CRYPTO_VALIDATE_ALERTS = "enforce"

        # 1. CoinEx rejection
        bad_alert = AlertCreate(
            user_id="user_test_val",
            exchange="coinex",
            symbol="BTCUSDT",
            target_price=65000.0,
        )
        with self.assertRaises(HTTPException) as ctx:
            await create_alert(bad_alert)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("EXCHANGE_NOT_SUPPORTED", ctx.exception.detail)

        # 2. Non-USDT quote rejection
        bad_quote_alert = AlertCreate(
            user_id="user_test_val",
            exchange="binance",
            symbol="BTCEUR",
            counter_currency="EUR",
            target_price=65000.0,
        )
        with self.assertRaises(HTTPException) as ctx:
            await create_alert(bad_quote_alert)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("INVALID_QUOTE_CURRENCY", ctx.exception.detail)

        # 3. Non-crypto alert (nobitex) passes through cleanly
        nobitex_alert = AlertCreate(
            user_id="user_test_val",
            exchange="nobitex",
            symbol="USDTIRT",
            target_price=90000.0,
        )
        res = await create_alert(nobitex_alert)
        self.assertEqual(res.exchange, "nobitex")
        self.assertEqual(res.symbol, "USDTIRT")

    async def test_09_api_create_alert_disabled_mode(self):
        """When CRYPTO_VALIDATE_ALERTS=false, existing behavior is completely preserved."""
        config.CRYPTO_VALIDATE_ALERTS = "false"

        alert = AlertCreate(
            user_id="user_test_val",
            exchange="coinex",
            symbol="BTCUSDT",
            target_price=65000.0,
        )
        # Should NOT raise HTTPException with EXCHANGE_NOT_SUPPORTED
        res = await create_alert(alert)
        self.assertEqual(res.exchange, "coinex")

    async def test_10_api_sync_alerts_enforce_mode_per_item(self):
        """Under enforce mode, one bad item is rejected while valid items sync successfully."""
        config.CRYPTO_VALIDATE_ALERTS = "enforce"

        payload = {
            "user_id": "user_sync_test",
            "fcm_token": "token_12345678901",
            "sync_mode": "mirror",
            "alerts": [
                {
                    "id": "valid_binance_1",
                    "exchange": "binance",
                    "symbol": "BTCUSDT",
                    "target_price": 60000.0,
                },
                {
                    "id": "invalid_coinex_1",
                    "exchange": "coinex",
                    "symbol": "BTCUSDT",
                    "target_price": 60000.0,
                },
            ],
        }
        res = await sync_user_alerts(payload)
        self.assertEqual(res["status"], "synced")
        self.assertEqual(res["count"], 1)
        self.assertIn("warnings", res)
        self.assertEqual(len(res["warnings"]), 1)
        self.assertEqual(res["warnings"][0]["id"], "invalid_coinex_1")
        self.assertEqual(res["warnings"][0]["error_code"], "EXCHANGE_NOT_SUPPORTED")

        # Verify only the valid alert is in ALERTS_DB
        active_ids = [a.id for a in ALERTS_DB]
        self.assertIn("valid_binance_1", active_ids)
        self.assertNotIn("invalid_coinex_1", active_ids)

    async def test_11_existing_server_alerts_pass_untouched(self):
        """Alerts already on the server pass through sync untouched even under enforce mode."""
        config.CRYPTO_VALIDATE_ALERTS = "enforce"

        # Seed an alert directly in DB as if created previously
        existing_alert = AlertCreate(
            id="legacy_coinex_alert",
            user_id="user_sync_test",
            exchange="coinex",
            symbol="BTCUSDT",
            target_price=50000.0,
        )
        from app.models import Alert
        ALERTS_DB.append(Alert(
            id="legacy_coinex_alert",
            user_id="user_sync_test",
            exchange="coinex",
            symbol="BTCUSDT",
            target_price=50000.0,
            condition="ABOVE",
            created_at="2026-01-01T00:00:00Z",
        ))

        # Client syncs back the exact same alert
        payload = {
            "user_id": "user_sync_test",
            "fcm_token": "token_12345678901",
            "sync_mode": "mirror",
            "alerts": [
                {
                    "id": "legacy_coinex_alert",
                    "exchange": "coinex",
                    "symbol": "BTCUSDT",
                    "target_price": 50000.0,
                    "condition": "ABOVE",
                }
            ],
        }
        res = await sync_user_alerts(payload)
        self.assertEqual(res["status"], "synced")
        self.assertEqual(res["count"], 1)
        # Passed untouched, no warnings
        self.assertNotIn("warnings", res)
        self.assertEqual(ALERTS_DB[0].id, "legacy_coinex_alert")

    async def test_12_warn_mode_returns_warning(self):
        """Under warn mode, invalid alerts are allowed but warning is returned."""
        config.CRYPTO_VALIDATE_ALERTS = "warn"

        payload = {
            "user_id": "user_sync_test",
            "fcm_token": "token_12345678901",
            "sync_mode": "mirror",
            "alerts": [
                {
                    "id": "warn_coinex_1",
                    "exchange": "coinex",
                    "symbol": "BTCUSDT",
                    "target_price": 60000.0,
                }
            ],
        }
        res = await sync_user_alerts(payload)
        self.assertEqual(res["status"], "synced")
        self.assertEqual(res["count"], 1)
        self.assertIn("warnings", res)
        self.assertEqual(res["warnings"][0]["id"], "warn_coinex_1")
        self.assertEqual(res["warnings"][0]["error_code"], "EXCHANGE_NOT_SUPPORTED")

        # Verify alert was saved and has warning attached
        self.assertEqual(len(ALERTS_DB), 1)
        self.assertEqual(ALERTS_DB[0].id, "warn_coinex_1")
        self.assertIsNotNone(ALERTS_DB[0].warning)

    def test_13_interval_clamping_guarded_by_engine_flag(self):
        """When CRYPTO_ENGINE_V2=False, crypto interval cannot be clamped below 180s."""
        from app.security import _clamp_interval

        config.CRYPTO_ENGINE_V2 = False
        self.assertEqual(_clamp_interval(1, exchange="binance"), 180)
        self.assertEqual(_clamp_interval(10, exchange="binance"), 180)

        config.CRYPTO_ENGINE_V2 = True
        self.assertEqual(_clamp_interval(1, exchange="binance"), 1)
        self.assertEqual(_clamp_interval(5, exchange="binance"), 5)
        # Non-crypto always clamped to 180
        self.assertEqual(_clamp_interval(1, exchange="nobitex"), 180)


if __name__ == "__main__":
    unittest.main()
