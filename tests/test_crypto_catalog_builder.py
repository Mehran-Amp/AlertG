#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — Crypto Dynamic Catalog Builder & Safety Engine Tests (Phase 5).
Validates:
1. Per-exchange catalog isolation: One file per exchange in crypto_catalogs/, completely separate from catalog.json.
2. Zero mutation of catalog.json or catalog_version.
3. Safety Engine:
   - Rejects catalogs below 20 pairs (MIN_PAIRS_CEILING).
   - Rejects catalogs dropping >50% compared to previous valid version (MAX_DROP_RATIO).
   - Preserves previous valid catalog on disk, marks it 'is_stale=True'.
4. Atomic write & crash recovery (no corrupted files on disk).
5. Isolated multi-exchange sync (failure of one exchange never stops others).
6. Admin endpoints for status inspection and on-demand synchronization.
"""

import unittest
import os
import sys
import json
import shutil
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

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

    class HTTPException(Exception):
        def __init__(self, status_code=500, detail=""):
            self.status_code = status_code
            self.detail = detail
    fastapi.APIRouter = APIRouter
    fastapi.HTTPException = HTTPException
    fastapi.Header = MagicMock()
    fastapi.Depends = MagicMock()
    sys.modules['fastapi'] = fastapi

try:
    import pydantic
except ImportError:
    pydantic = MagicMock()
    class BaseModel: pass
    pydantic.BaseModel = BaseModel
    sys.modules['pydantic'] = pydantic


from app.markets.crypto_catalog import (
    SUPPORTED_CRYPTO_EXCHANGES,
    get_exchange_adapter,
    get_catalog_path,
    load_exchange_catalog,
    save_exchange_catalog_atomic,
    validate_catalog_safety,
    sync_exchange_catalog,
    sync_all_crypto_catalogs,
    get_crypto_catalogs_status,
)
from app.markets.adapters.base import SymbolInfo


class TestCryptoCatalogBuilder(unittest.IsolatedAsyncioTestCase):
    """Unit and contract tests for Dynamic Crypto Catalog Service."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_crypto_catalogs_")
        # Ensure root catalog.json remains untouched
        self.root_catalog_path = os.path.abspath("catalog.json")
        self.initial_catalog_mtime = (
            os.path.getmtime(self.root_catalog_path)
            if os.path.exists(self.root_catalog_path)
            else None
        )

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_supported_exchanges_and_adapters(self):
        """Verifies all 7 supported exchanges instantiate their isolated adapters."""
        self.assertEqual(len(SUPPORTED_CRYPTO_EXCHANGES), 7)
        for ex_id in ["binance", "mexc", "kucoin", "gateio", "lbank", "okx", "kraken"]:
            self.assertIn(ex_id, SUPPORTED_CRYPTO_EXCHANGES)
            adapter = get_exchange_adapter(ex_id)
            self.assertIsNotNone(adapter, f"Adapter for {ex_id} should not be None")
            self.assertEqual(adapter.exchange_id, ex_id)

    def test_02_atomic_write_and_read(self):
        """Verifies atomic write and read with utf-8 encoding."""
        sample_data = {
            "exchange": "binance",
            "updated_at": 1729000000,
            "total_pairs": 2,
            "is_stale": False,
            "error": None,
            "pairs": [
                {
                    "base": "BTC",
                    "quote": "USDT",
                    "native_symbol": "BTCUSDT",
                    "is_active": True,
                    "is_etf": False,
                    "min_price": 0.01,
                    "min_qty": 0.00001
                },
                {
                    "base": "ETH",
                    "quote": "USDT",
                    "native_symbol": "ETHUSDT",
                    "is_active": True,
                    "is_etf": False,
                    "min_price": 0.01,
                    "min_qty": 0.0001
                }
            ]
        }
        saved_path = save_exchange_catalog_atomic("binance", sample_data, override_dir=self.test_dir)
        self.assertTrue(os.path.exists(saved_path))
        self.assertTrue(saved_path.endswith("binance.json"))

        loaded = load_exchange_catalog("binance", override_dir=self.test_dir)
        self.assertEqual(loaded["exchange"], "binance")
        self.assertEqual(loaded["total_pairs"], 2)
        self.assertEqual(len(loaded["pairs"]), 2)
        self.assertEqual(loaded["pairs"][0]["base"], "BTC")

    def test_03_zero_mutation_of_root_catalog_json(self):
        """
        Crucial Safety Rule: Verifies catalog.json is completely untouched.
        Crypto catalogs reside strictly in their own directory.
        """
        if self.initial_catalog_mtime is not None:
            sample_data = {"exchange": "mexc", "pairs": []}
            save_exchange_catalog_atomic("mexc", sample_data, override_dir=self.test_dir)
            current_mtime = os.path.getmtime(self.root_catalog_path)
            self.assertEqual(
                self.initial_catalog_mtime,
                current_mtime,
                "Violation of R3/R4: root catalog.json modified by crypto catalog builder!"
            )

    def test_04_safety_rejects_empty_and_below_minimum(self):
        """Verifies safety engine rejects catalogs with fewer than 20 pairs."""
        existing = {}
        # 1. Empty pairs list
        is_safe, reason = validate_catalog_safety("binance", [], existing)
        self.assertFalse(is_safe)
        self.assertIn("below minimum ceiling", reason)

        # 2. 15 pairs (below 20 threshold)
        few_pairs = [{"base": f"COIN{i}", "quote": "USDT"} for i in range(15)]
        is_safe, reason = validate_catalog_safety("binance", few_pairs, existing)
        self.assertFalse(is_safe)
        self.assertIn("below minimum ceiling", reason)

    def test_05_safety_rejects_drop_over_50_percent(self):
        """Verifies safety engine rejects drop > 50% from previous valid catalog."""
        existing = {
            "exchange": "gateio",
            "pairs": [{"base": f"COIN{i}", "quote": "USDT"} for i in range(100)]
        }
        # Incoming catalog has 40 pairs (60% drop -> exceeds 50% ceiling)
        incoming_40 = [{"base": f"COIN{i}", "quote": "USDT"} for i in range(40)]
        is_safe, reason = validate_catalog_safety("gateio", incoming_40, existing)
        self.assertFalse(is_safe)
        self.assertIn("dropped by 60%", reason)

    def test_06_safety_allows_safe_update_or_ignore_flag(self):
        """Verifies safety engine allows normal updates and respects ignore_safety flag."""
        existing = {
            "exchange": "kucoin",
            "pairs": [{"base": f"COIN{i}", "quote": "USDT"} for i in range(100)]
        }
        # 1. 95 pairs (5% drop -> completely safe)
        incoming_95 = [{"base": f"COIN{i}", "quote": "USDT"} for i in range(95)]
        is_safe, reason = validate_catalog_safety("kucoin", incoming_95, existing)
        self.assertTrue(is_safe)
        self.assertIsNone(reason)

        # 2. Ignored safety flag allows even small catalogs
        is_safe, reason = validate_catalog_safety("kucoin", incoming_95[:10], existing, ignore_safety=True)
        self.assertTrue(is_safe)
        self.assertIsNone(reason)

    async def test_07_sync_single_exchange_with_mock_adapter(self):
        """Verifies sync_exchange_catalog executes end-to-end and creates valid file."""
        mock_symbols = [
            SymbolInfo(
                base=f"COIN{i}",
                quote="USDT",
                market_symbol=f"COIN{i}USDT",
                is_active=True,
                is_etf=(i % 5 == 0),
                min_price=0.01,
                min_qty=1.0,
                raw={}
            )
            for i in range(30)
        ]

        mock_adapter = MagicMock()
        mock_adapter.display_name = "Binance"
        mock_adapter.fetch_symbols = AsyncMock(return_value=(mock_symbols, None, None))

        with patch("app.markets.crypto_catalog.get_exchange_adapter", return_value=mock_adapter):
            result = await sync_exchange_catalog("binance", override_dir=self.test_dir)

        self.assertTrue(result["success"])
        self.assertEqual(result["total_pairs"], 30)
        self.assertFalse(result["is_stale"])

        # Check saved file on disk
        saved = load_exchange_catalog("binance", override_dir=self.test_dir)
        self.assertEqual(saved["exchange"], "binance")
        self.assertEqual(saved["total_pairs"], 30)
        self.assertEqual(len(saved["pairs"]), 30)
        self.assertEqual(saved["pairs"][0]["base"], "COIN0")
        self.assertTrue(saved["pairs"][0]["is_etf"])
        self.assertFalse(saved["pairs"][1]["is_etf"])

    async def test_08_failure_isolation_between_exchanges(self):
        """
        Acceptance R8: Failure of one exchange catalog query NEVER blocks other exchanges.
        """
        def fake_get_adapter(ex_id):
            adapter = MagicMock()
            adapter.display_name = ex_id.upper()
            if ex_id == "lbank":
                # LBank raises or fails with 429
                adapter.fetch_symbols = AsyncMock(return_value=([], "RATE_LIMITED", "429 Too Many Requests"))
            else:
                # All other exchanges return 25 valid pairs
                symbols = [
                    SymbolInfo(
                        base=f"{ex_id.upper()}_{i}",
                        quote="USDT",
                        market_symbol=f"{ex_id.upper()}_{i}-USDT",
                        is_active=True,
                        is_etf=False,
                        min_price=0.01,
                        min_qty=1.0,
                        raw={}
                    )
                    for i in range(25)
                ]
                adapter.fetch_symbols = AsyncMock(return_value=(symbols, None, None))
            return adapter

        with patch("app.markets.crypto_catalog.get_exchange_adapter", side_effect=fake_get_adapter):
            report = await sync_all_crypto_catalogs(override_dir=self.test_dir)

        self.assertEqual(report["total_exchanges"], 7)
        self.assertEqual(report["success_count"], 6)

        # LBank failed gracefully
        self.assertFalse(report["results"]["lbank"]["success"])
        self.assertEqual(report["results"]["lbank"]["error_code"], "RATE_LIMITED")

        # Other 6 exchanges succeeded
        for ex in ["binance", "mexc", "kucoin", "gateio", "okx", "kraken"]:
            self.assertTrue(report["results"][ex]["success"])
            self.assertEqual(report["results"][ex]["total_pairs"], 25)

    async def test_09_stale_flagging_on_error_preserves_previous(self):
        """Verifies that an error marks previous catalog stale without deleting pairs."""
        # 1. First write a valid catalog with 40 pairs
        valid_catalog = {
            "exchange": "okx",
            "display_name": "OKX",
            "updated_at": 1729000000,
            "total_pairs": 40,
            "is_stale": False,
            "error": None,
            "pairs": [{"base": f"T{i}", "quote": "USDT"} for i in range(40)]
        }
        save_exchange_catalog_atomic("okx", valid_catalog, override_dir=self.test_dir)

        # 2. Now simulate a fetch failure
        mock_adapter = MagicMock()
        mock_adapter.display_name = "OKX"
        mock_adapter.fetch_symbols = AsyncMock(return_value=([], "GEO_BLOCKED", "Forbidden 403"))

        with patch("app.markets.crypto_catalog.get_exchange_adapter", return_value=mock_adapter):
            res = await sync_exchange_catalog("okx", override_dir=self.test_dir)

        self.assertFalse(res["success"])
        self.assertTrue(res["is_stale"])

        # Check on-disk catalog: 40 pairs MUST STILL BE INTACT, but flagged is_stale
        on_disk = load_exchange_catalog("okx", override_dir=self.test_dir)
        self.assertEqual(len(on_disk["pairs"]), 40)
        self.assertTrue(on_disk["is_stale"])
        self.assertIn("Forbidden 403", on_disk.get("error", ""))

    def test_10_crash_recovery_atomic_write(self):
        """Verifies that if writing fails midway, original catalog remains uncorrupted."""
        orig_data = {"exchange": "kraken", "total_pairs": 50, "pairs": [{"base": "BTC"}]}
        save_exchange_catalog_atomic("kraken", orig_data, override_dir=self.test_dir)

        # Simulate exception during atomic write (e.g. disk write error)
        with patch("json.dump", side_effect=IOError("Simulated disk full")):
            with self.assertRaises(IOError):
                save_exchange_catalog_atomic(
                    "kraken",
                    {"exchange": "kraken", "total_pairs": 0, "pairs": []},
                    override_dir=self.test_dir
                )

        # Original file must be completely intact and valid
        recovered = load_exchange_catalog("kraken", override_dir=self.test_dir)
        self.assertEqual(recovered["total_pairs"], 50)
        self.assertEqual(len(recovered["pairs"]), 1)

    def test_11_status_inspection(self):
        """Verifies get_crypto_catalogs_status reports accurate summary for all exchanges."""
        # Save dummy catalog for binance
        save_exchange_catalog_atomic(
            "binance",
            {"exchange": "binance", "total_pairs": 150, "is_stale": False, "error": None},
            override_dir=self.test_dir
        )

        status = get_crypto_catalogs_status(override_dir=self.test_dir)
        self.assertEqual(status["total_exchanges"], 7)
        self.assertTrue(status["exchanges"]["binance"]["file_exists"])
        self.assertEqual(status["exchanges"]["binance"]["total_pairs"], 150)
        self.assertFalse(status["exchanges"]["binance"]["is_stale"])

        # mexc does not exist yet
        self.assertFalse(status["exchanges"]["mexc"]["file_exists"])
        self.assertTrue(status["exchanges"]["mexc"]["is_stale"])

    async def test_12_admin_endpoint_handlers(self):
        """Verifies admin endpoint handlers return valid structures."""
        try:
            from app.routes.admin import get_admin_crypto_catalog_status, trigger_admin_crypto_catalog_sync
            status_res = get_admin_crypto_catalog_status()
            self.assertIn("total_exchanges", status_res)
            self.assertEqual(status_res["total_exchanges"], 7)
            self.assertIn("exchanges", status_res)

            mock_sync_result = {
                "exchange": "binance",
                "success": True,
                "total_pairs": 50,
                "is_stale": False
            }
            with patch("app.markets.crypto_catalog.sync_single_exchange_catalog", new=AsyncMock(return_value=mock_sync_result)):
                sync_res = await trigger_admin_crypto_catalog_sync(exchange="binance")
                self.assertEqual(sync_res["sync_mode"], "single")
                self.assertTrue(sync_res["result"]["success"])
        except ImportError:
            # When FastAPI is not in container python, test directly through the service functions
            from app.markets.crypto_catalog import get_crypto_catalogs_status
            status_res = get_crypto_catalogs_status()
            self.assertIn("total_exchanges", status_res)
            self.assertEqual(status_res["total_exchanges"], 7)


if __name__ == '__main__':
    unittest.main()


