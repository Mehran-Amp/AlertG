# -*- coding: utf-8 -*-
"""
Phase H2 Test:
Validates that an aborted or closed-client sync never marks a good catalog as stale,
never overwrites the file on disk (bytes and mtime intact), and never notifies admin.
A normal error still sets is_stale=True.
"""

import os
import sys
import time
import json
import tempfile
import shutil
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

from app.markets.crypto_catalog import (
    sync_exchange_catalog,
    save_exchange_catalog_atomic,
    load_exchange_catalog,
)


class FakeCatalogAdapter:
    def __init__(self, symbols=None, err_code=None, err_msg=None, raise_exc=None):
        self.symbols = symbols or []
        self.err_code = err_code
        self.err_msg = err_msg
        self.raise_exc = raise_exc

    async def fetch_symbols(self, client=None):
        if self.raise_exc:
            raise self.raise_exc
        return self.symbols, self.err_code, self.err_msg


class TestCatalogAbortNoWrite(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_catalog_h2_")
        # Seed a valid catalog on disk
        self.seed_payload = {
            "exchange": "binance",
            "display_name": "Binance",
            "updated_at": int(time.time()),
            "total_pairs": 2,
            "is_stale": False,
            "error": None,
            "pairs": [
                {"symbol": "BTCUSDT", "base": "BTC", "quote": "USDT", "native_symbol": "BTCUSDT"},
                {"symbol": "ETHUSDT", "base": "ETH", "quote": "USDT", "native_symbol": "ETHUSDT"},
            ],
        }
        self.saved_path = save_exchange_catalog_atomic("binance", self.seed_payload, override_dir=self.temp_dir)
        self.initial_bytes = open(self.saved_path, "rb").read()
        self.initial_mtime = os.path.getmtime(self.saved_path)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_01_client_closed_error_leaves_catalog_untouched(self):
        """1. When adapter reports 'Cannot send a request, as the client has been closed', file is untouched."""
        fake = FakeCatalogAdapter(
            symbols=[],
            err_code="INVALID_RESPONSE",
            err_msg="Binance symbols request failed: Cannot send a request, as the client has been closed."
        )
        mock_notify = AsyncMock()

        with patch("app.markets.crypto_catalog.get_exchange_adapter", return_value=fake), \
             patch("app.markets.crypto_catalog._safe_notify_admin", mock_notify):
            res = await sync_exchange_catalog("binance", override_dir=self.temp_dir)

            self.assertFalse(res.get("success"))
            self.assertEqual(res.get("error_code"), "ABORTED")
            self.assertFalse(res.get("is_stale"))  # remained unchanged (False)

            # Assert file was NOT overwritten
            current_bytes = open(self.saved_path, "rb").read()
            self.assertEqual(current_bytes, self.initial_bytes)
            self.assertEqual(os.path.getmtime(self.saved_path), self.initial_mtime)

            # Assert Telegram admin was NOT notified
            mock_notify.assert_not_called()

            # Assert load_exchange_catalog still returns is_stale=False and error=None
            disk_cat = load_exchange_catalog("binance", override_dir=self.temp_dir)
            self.assertFalse(disk_cat.get("is_stale"))
            self.assertIsNone(disk_cat.get("error"))

    async def test_02_normal_error_still_marks_stale(self):
        """2. When adapter reports a normal upstream error (e.g. 500 / RATE_LIMITED), catalog is marked stale."""
        fake = FakeCatalogAdapter(
            symbols=[],
            err_code="RATE_LIMITED",
            err_msg="HTTP 429 Too Many Requests"
        )
        mock_notify = AsyncMock()

        with patch("app.markets.crypto_catalog.get_exchange_adapter", return_value=fake), \
             patch("app.markets.crypto_catalog._safe_notify_admin", mock_notify):
            res = await sync_exchange_catalog("binance", override_dir=self.temp_dir)

            self.assertFalse(res.get("success"))
            self.assertEqual(res.get("error_code"), "RATE_LIMITED")
            self.assertTrue(res.get("is_stale"))

            # Assert file was updated with is_stale=True
            disk_cat = load_exchange_catalog("binance", override_dir=self.temp_dir)
            self.assertTrue(disk_cat.get("is_stale"))
            self.assertIn("RATE_LIMITED", disk_cat.get("error", ""))

            # Assert Telegram admin WAS notified for real outage
            mock_notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
