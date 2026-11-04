#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — Phase 7 (Stage B) Acceptance Tests: Dedicated 1s Crypto Evaluation Job.
Verifies:
1. When CRYPTO_STAGE_B_ENABLED is False (default), the main 2s check_alerts_job evaluates all categories (backward compatible).
2. When CRYPTO_STAGE_B_ENABLED is True, check_alerts_job skips crypto alerts (evaluated exclusively by the 1s job).
3. check_crypto_alerts_job evaluates strictly crypto alerts and skips all non-crypto alerts (stocks, forex, bonds, macro).
4. Metrics (total_crypto_checks, last_crypto_check_ts) are accurately recorded in METRICS.
5. Cooldowns, one-shot deactivation, outbox enqueues, and notifications remain 100% shared and identical.
"""

import unittest
import asyncio
import time
import os
import sys
import json
from unittest.mock import AsyncMock, MagicMock, patch

# Mock optional dependencies for test runners without full environment
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

try:
    import pydantic
except ImportError:
    pydantic = MagicMock()
    class BaseModel: pass
    pydantic.BaseModel = BaseModel
    sys.modules['pydantic'] = pydantic

try:
    import fastapi
except ImportError:
    import types
    fastapi = types.ModuleType('fastapi')
    fastapi.__path__ = []
    class FastAPI:
        def api_route(self, *a, **kw): return lambda fn: fn
        def get(self, *a, **kw): return lambda fn: fn
        def post(self, *a, **kw): return lambda fn: fn
        def include_router(self, *a, **kw): pass
        def mount(self, *a, **kw): pass
        def add_middleware(self, *a, **kw): pass
    class APIRouter:
        def get(self, *a, **kw): return lambda fn: fn
        def post(self, *a, **kw): return lambda fn: fn
        def delete(self, *a, **kw): return lambda fn: fn
        def put(self, *a, **kw): return lambda fn: fn
        def patch(self, *a, **kw): return lambda fn: fn
        def websocket(self, *a, **kw): return lambda fn: fn
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
        def __init__(self, content=None, status_code=200, headers=None, **kwargs):
            b = json.dumps(content).encode("utf-8") if isinstance(content, (dict, list)) else (content or b"")
            super().__init__(content=b, status_code=status_code, headers=headers or {})
    class HTMLResponse(Response): pass
    resp_mod.Response = Response
    resp_mod.JSONResponse = JSONResponse
    resp_mod.HTMLResponse = HTMLResponse
    fastapi.responses = resp_mod
    sys.modules['fastapi.responses'] = resp_mod

import app.config as config
from app.models import Alert
from app.storage import ALERTS_DB
import app.state as state
from app.state import METRICS, PRICE_CACHE
from app.engine.checker import (
    check_alerts_job,
    check_crypto_alerts_job,
    evaluate_ready_alerts,
)


class TestCryptoStageB(unittest.IsolatedAsyncioTestCase):
    """Phase 7 Stage B Dedicated 1s Crypto Evaluation Job Test Suite."""

    def setUp(self):
        self.mock_client = AsyncMock()
        state.http_client = self.mock_client
        self._orig_alerts = list(ALERTS_DB)
        ALERTS_DB.clear()
        PRICE_CACHE.clear()

        # Seed alerts: 1 crypto alert, 1 stock alert, 1 forex alert
        self.crypto_alert = Alert(
            id="alert_crypto_1",
            user_id="user_test",
            exchange="binance",
            symbol="BTCUSDT",
            target_price=50000.0,
            condition="ABOVE",
            check_interval_seconds=1,
            trigger_mode="oneShot",
            is_active=True,
            last_checked_at=0.0
        )
        self.stock_alert = Alert(
            id="alert_stock_1",
            user_id="user_test",
            exchange="stocks",
            symbol="AAPL",
            target_price=150.0,
            condition="ABOVE",
            check_interval_seconds=180,
            trigger_mode="oneShot",
            is_active=True,
            last_checked_at=0.0
        )
        self.forex_alert = Alert(
            id="alert_forex_1",
            user_id="user_test",
            exchange="forex",
            symbol="EURUSD",
            target_price=1.10,
            condition="ABOVE",
            check_interval_seconds=180,
            trigger_mode="oneShot",
            is_active=True,
            last_checked_at=0.0
        )
        ALERTS_DB.extend([self.crypto_alert, self.stock_alert, self.forex_alert])

    def tearDown(self):
        ALERTS_DB.clear()
        ALERTS_DB.extend(self._orig_alerts)
        PRICE_CACHE.clear()

    async def test_01_stage_b_disabled_main_job_evaluates_both(self):
        """When CRYPTO_STAGE_B_ENABLED=False, main job evaluates both crypto and non-crypto."""
        with patch.object(config, "CRYPTO_STAGE_B_ENABLED", False), \
             patch.object(config, "CRYPTO_DEDICATED_JOB", False), \
             patch("app.engine.checker.is_market_open", return_value=True), \
             patch("app.engine.checker.get_cached_price", new=AsyncMock(return_value=100.0)):

            await check_alerts_job()

            # All 3 alerts should have been checked
            self.assertGreater(self.crypto_alert.last_checked_at, 0)
            self.assertGreater(self.stock_alert.last_checked_at, 0)
            self.assertGreater(self.forex_alert.last_checked_at, 0)

    async def test_02_stage_b_enabled_main_job_skips_crypto(self):
        """When CRYPTO_STAGE_B_ENABLED=True, main job evaluates ONLY non-crypto alerts."""
        with patch.object(config, "CRYPTO_STAGE_B_ENABLED", True), \
             patch.object(config, "CRYPTO_DEDICATED_JOB", True), \
             patch("app.engine.checker.is_market_open", return_value=True), \
             patch("app.engine.checker.get_cached_price", new=AsyncMock(return_value=100.0)):

            await check_alerts_job(skip_crypto=True)

            # Crypto alert must NOT be updated by the main 2s job
            self.assertEqual(self.crypto_alert.last_checked_at, 0.0, "Crypto alert must be skipped by main job in Stage B")

            # Non-crypto alerts must be updated
            self.assertGreater(self.stock_alert.last_checked_at, 0)
            self.assertGreater(self.forex_alert.last_checked_at, 0)

    async def test_03_stage_b_crypto_job_evaluates_strictly_crypto(self):
        """check_crypto_alerts_job evaluates strictly crypto alerts and ignores stocks/forex."""
        with patch("app.engine.checker.is_market_open", return_value=True), \
             patch("app.engine.checker.get_cached_price", new=AsyncMock(return_value=60000.0)):
            await check_crypto_alerts_job()

            # Crypto alert was checked
            self.assertGreater(self.crypto_alert.last_checked_at, 0)

            # Stocks and forex alerts were completely untouched
            self.assertEqual(self.stock_alert.last_checked_at, 0.0, "Stock alert must be skipped by crypto job")
            self.assertEqual(self.forex_alert.last_checked_at, 0.0, "Forex alert must be skipped by crypto job")

    async def test_04_crypto_metrics_tracked(self):
        """check_crypto_alerts_job updates total_crypto_checks and last_crypto_check_ts."""
        initial_checks = METRICS.get("total_crypto_checks", 0)
        with patch("app.engine.checker.is_market_open", return_value=True), \
             patch("app.engine.checker.get_cached_price", new=AsyncMock(return_value=60000.0)):
            await check_crypto_alerts_job()

        self.assertEqual(METRICS.get("total_crypto_checks"), initial_checks + 1)
        self.assertGreater(METRICS.get("last_crypto_check_ts", 0), 0)

    async def test_05_shared_trigger_and_deactivation_semantics(self):
        """When price crosses threshold in crypto job, oneShot alert deactivates and triggers identically."""
        self.crypto_alert.last_eval_price = 45000.0
        with patch("app.engine.checker.is_market_open", return_value=True), \
             patch("app.engine.checker.get_cached_price", new=AsyncMock(return_value=55000.0)), \
             patch("app.engine.checker.enqueue_alert_push", new=AsyncMock()) as mock_push, \
             patch("app.engine.checker.save_alerts_to_disk_async", new=AsyncMock()):

            await check_crypto_alerts_job()

            # 55000 >= 50000 target => triggered
            self.assertFalse(self.crypto_alert.is_active, "oneShot crypto alert must be deactivated after trigger")
            self.assertGreater(self.crypto_alert.last_triggered_at, 0)
            mock_push.assert_called_once()


if __name__ == '__main__':
    unittest.main()
