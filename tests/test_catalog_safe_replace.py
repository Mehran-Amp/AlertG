# -*- coding: utf-8 -*-
"""
Phase CS2 Unit Tests: Shrink guard & safe replace.
Verifies that:
1. Empty new catalogs are rejected and old file is preserved.
2. Catalogs shrinking below CRYPTO_CATALOG_MIN_RATIO (default 0.7) are rejected and old file is preserved.
3. [CatalogSync] ex=<id> REJECTED old=<n> new=<n> is logged on rejection.
4. Normal fluctuation >= 0.7 is accepted and saves new file atomically.
5. [CatalogSync] ex=<id> total=<n> +<added> -<removed> is logged on accept.
6. All tests run in isolated temp dir and clean up properly.
"""

import os
import sys
import time
import json
import shutil
import logging
import tempfile
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

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

import app.config as config
from app.markets.adapters.base import MarketSymbol
from app.markets.crypto_catalog import (
    sync_exchange_catalog,
    save_exchange_catalog_atomic,
    load_exchange_catalog,
    validate_catalog_safety,
)


class FakeShrinkAdapter:
    def __init__(self, symbols=None, err_code=None, err_msg=None, display_name="Binance"):
        self.symbols = symbols if symbols is not None else []
        self.err_code = err_code
        self.err_msg = err_msg
        self.display_name = display_name

    async def fetch_symbols(self, client=None):
        return self.symbols, self.err_code, self.err_msg


class TestCatalogSafeReplace(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_cs2_shrink_guard_")
        self.mock_notify = AsyncMock()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _seed_catalog(self, exchange_id: str, count: int, prefix: str = "COIN"):
        pairs = [
            {
                "symbol": f"{prefix}{i}USDT",
                "base": f"{prefix}{i}",
                "quote": "USDT",
                "native_symbol": f"{prefix}{i}USDT",
                "is_active": True,
            }
            for i in range(count)
        ]
        payload = {
            "exchange": exchange_id,
            "display_name": exchange_id.upper(),
            "updated_at": int(time.time()),
            "total_pairs": len(pairs),
            "is_stale": False,
            "error": None,
            "pairs": pairs,
        }
        return save_exchange_catalog_atomic(exchange_id, payload, override_dir=self.temp_dir)

    def _make_symbols(self, count: int, prefix: str = "COIN"):
        return [
            MarketSymbol(
                base=f"{prefix}{i}",
                quote="USDT",
                market_symbol=f"{prefix}{i}USDT",
                is_active=True,
                is_etf=False,
                min_price=0.01,
                min_qty=0.001
            )
            for i in range(count)
        ]

    async def test_01_empty_catalog_rejected_and_old_file_intact(self):
        """1. Empty new catalog is rejected, old file kept, REJECTED logged."""
        self._seed_catalog("binance", 50)
        fake = FakeShrinkAdapter(symbols=[])

        with patch("app.markets.crypto_catalog.get_exchange_adapter", return_value=fake), \
             patch("app.markets.crypto_catalog._safe_notify_admin", self.mock_notify), \
             self.assertLogs("signalalert.crypto_catalog", level="WARNING") as cm:
            res = await sync_exchange_catalog("binance", override_dir=self.temp_dir)

            self.assertFalse(res.get("success"))
            self.assertTrue(res.get("safety_rejected"))

            # Assert log format: [CatalogSync] ex=binance REJECTED old=50 new=0
            log_found = any("[CatalogSync] ex=binance REJECTED old=50 new=0" in log for log in cm.output)
            self.assertTrue(log_found, f"Expected REJECTED log not found in {cm.output}")

            # Assert old file is kept on disk with all 50 pairs
            disk_cat = load_exchange_catalog("binance", override_dir=self.temp_dir)
            self.assertEqual(len(disk_cat["pairs"]), 50)
            self.assertTrue(disk_cat["is_stale"])
            self.assertIn("empty", disk_cat["error"].lower())

    async def test_02_shrink_below_min_ratio_rejected_and_old_file_intact(self):
        """2. 40% shrink (100 -> 60, ratio 0.60 < 0.70) rejected, old file intact."""
        self._seed_catalog("binance", 100)
        # Incoming only 60 pairs
        fake = FakeShrinkAdapter(symbols=self._make_symbols(60))

        with patch("app.markets.crypto_catalog.get_exchange_adapter", return_value=fake), \
             patch("app.markets.crypto_catalog._safe_notify_admin", self.mock_notify), \
             self.assertLogs("signalalert.crypto_catalog", level="WARNING") as cm:
            res = await sync_exchange_catalog("binance", override_dir=self.temp_dir)

            self.assertFalse(res.get("success"))
            self.assertTrue(res.get("safety_rejected"))

            # Assert log format: [CatalogSync] ex=binance REJECTED old=100 new=60
            log_found = any("[CatalogSync] ex=binance REJECTED old=100 new=60" in log for log in cm.output)
            self.assertTrue(log_found, f"Expected REJECTED log not found in {cm.output}")

            # Assert old file on disk still has all 100 pairs
            disk_cat = load_exchange_catalog("binance", override_dir=self.temp_dir)
            self.assertEqual(len(disk_cat["pairs"]), 100)
            self.assertTrue(disk_cat["is_stale"])
            self.assertIn("Below CRYPTO_CATALOG_MIN_RATIO", disk_cat["error"])

    async def test_03_acceptable_shrink_and_diff_logging(self):
        """3. 15% shrink (100 -> 85, ratio 0.85 >= 0.70) accepted, diff logged."""
        self._seed_catalog("binance", 100, prefix="OLD")
        # 80 old retained (OLD0..79), 5 new added (NEW0..4) -> total 85 pairs
        new_symbols = self._make_symbols(80, prefix="OLD") + self._make_symbols(5, prefix="NEW")
        fake = FakeShrinkAdapter(symbols=new_symbols)

        with patch("app.markets.crypto_catalog.get_exchange_adapter", return_value=fake), \
             patch("app.markets.crypto_catalog._safe_notify_admin", self.mock_notify), \
             self.assertLogs("signalalert.crypto_catalog", level="INFO") as cm:
            res = await sync_exchange_catalog("binance", override_dir=self.temp_dir)

            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("total_pairs"), 85)
            self.assertFalse(res.get("is_stale"))

            # Assert diff log: total=85 +5 -20
            diff_log_found = any("[CatalogSync] ex=binance total=85 +5 -20" in log for log in cm.output)
            self.assertTrue(diff_log_found, f"Expected diff log not found in {cm.output}")

            # Assert file was updated with 85 pairs
            disk_cat = load_exchange_catalog("binance", override_dir=self.temp_dir)
            self.assertEqual(len(disk_cat["pairs"]), 85)
            self.assertFalse(disk_cat["is_stale"])

    async def test_04_growth_accepted_and_diff_logged(self):
        """4. 10% growth (100 -> 110) accepted, diff logged."""
        self._seed_catalog("binance", 100, prefix="COIN")
        fake = FakeShrinkAdapter(symbols=self._make_symbols(110, prefix="COIN"))

        with patch("app.markets.crypto_catalog.get_exchange_adapter", return_value=fake), \
             patch("app.markets.crypto_catalog._safe_notify_admin", self.mock_notify), \
             self.assertLogs("signalalert.crypto_catalog", level="INFO") as cm:
            res = await sync_exchange_catalog("binance", override_dir=self.temp_dir)

            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("total_pairs"), 110)

            # Assert diff log: total=110 +10 -0
            diff_log_found = any("[CatalogSync] ex=binance total=110 +10 -0" in log for log in cm.output)
            self.assertTrue(diff_log_found, f"Expected diff log not found in {cm.output}")

    async def test_05_first_sync_without_old_file_accepted(self):
        """5. First sync with no old file on disk is accepted."""
        fake = FakeShrinkAdapter(symbols=self._make_symbols(30, prefix="INITIAL"))

        with patch("app.markets.crypto_catalog.get_exchange_adapter", return_value=fake), \
             patch("app.markets.crypto_catalog._safe_notify_admin", self.mock_notify), \
             self.assertLogs("signalalert.crypto_catalog", level="INFO") as cm:
            res = await sync_exchange_catalog("binance", override_dir=self.temp_dir)

            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("total_pairs"), 30)

            diff_log_found = any("[CatalogSync] ex=binance total=30 +30 -0" in log for log in cm.output)
            self.assertTrue(diff_log_found, f"Expected diff log not found in {cm.output}")


if __name__ == "__main__":
    unittest.main()
