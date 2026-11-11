#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — Crypto Catalog Staleness Telegram Alert Tests (Phase CS5).
Validates:
1. Operational alert is triggered if any active exchange catalog remains stale > 6h.
2. Alert includes exchange display name, canonical ID, catalog age, and pairs count.
3. Per-exchange cooldown suppresses duplicate spam within the cooldown window.
4. Fresh catalogs (< 6h) never trigger stale alerts.
"""

import unittest
import os
import sys
import time
import shutil
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

# Safe module mocks for isolated test runner
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

from app.markets.crypto_catalog import (
    check_and_alert_stale_catalogs,
    save_exchange_catalog_atomic,
    _STALE_ALERT_COOLDOWN,
    get_supported_crypto_exchanges,
)


class TestCatalogStalenessAlert(unittest.IsolatedAsyncioTestCase):
    """Phase CS5 Unit Tests: Staleness Telegram Alerts."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="alertg_staleness_test_")
        self.now_ts = int(time.time())
        _STALE_ALERT_COOLDOWN.clear()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)
        _STALE_ALERT_COOLDOWN.clear()

    async def test_01_stale_catalog_triggers_telegram_alert(self):
        """1. Trigger Telegram alert for catalog older than 6 hours."""
        # Binance: Fresh (10 min ago)
        save_exchange_catalog_atomic(
            "binance",
            {
                "exchange": "binance",
                "total_pairs": 518,
                "updated_at": self.now_ts - 600,
                "is_stale": False,
                "error": None,
                "pairs": [{"base": "BTC", "quote": "USDT"}],
            },
            override_dir=self.test_dir
        )

        # OKX: Stale > 6h (7.5 hours ago)
        save_exchange_catalog_atomic(
            "okx",
            {
                "exchange": "okx",
                "total_pairs": 474,
                "updated_at": self.now_ts - int(7.5 * 3600),
                "is_stale": True,
                "error": "Upstream timeout",
                "pairs": [{"base": "ETH", "quote": "USDT"}],
            },
            override_dir=self.test_dir
        )

        # Mock the admin notifier
        mock_notify = AsyncMock()
        with patch("app.markets.crypto_catalog._safe_notify_admin", mock_notify), \
             patch("app.markets.crypto_catalog.get_supported_crypto_exchanges", return_value=["binance", "okx"]):

            alerted = await check_and_alert_stale_catalogs(
                override_dir=self.test_dir,
                max_stale_hours=6.0
            )

            # Binance should NOT be alerted
            self.assertNotIn("binance", alerted)

            # OKX should be alerted
            self.assertIn("okx", alerted)
            mock_notify.assert_awaited()

            # Verify message contents
            sent_msg = mock_notify.await_args[0][0]
            self.assertIn("OKX", sent_msg)
            self.assertIn("okx", sent_msg)
            self.assertIn("474", sent_msg)
            self.assertIn("Upstream timeout", sent_msg)

    async def test_02_alert_cooldown_prevents_duplicate_spam(self):
        """2. Verifies that duplicate alerts within cooldown window are suppressed."""
        save_exchange_catalog_atomic(
            "mexc",
            {
                "exchange": "mexc",
                "total_pairs": 1353,
                "updated_at": self.now_ts - int(8.0 * 3600),
                "is_stale": True,
                "error": None,
            },
            override_dir=self.test_dir
        )

        mock_notify = AsyncMock()
        with patch("app.markets.crypto_catalog._safe_notify_admin", mock_notify), \
             patch("app.markets.crypto_catalog.get_supported_crypto_exchanges", return_value=["mexc"]):

            # First check: triggers alert
            first_alerted = await check_and_alert_stale_catalogs(
                override_dir=self.test_dir,
                max_stale_hours=6.0,
                cooldown_seconds=3600.0
            )
            self.assertEqual(first_alerted, ["mexc"])
            self.assertEqual(mock_notify.await_count, 1)

            # Immediate second check: suppressed by cooldown
            second_alerted = await check_and_alert_stale_catalogs(
                override_dir=self.test_dir,
                max_stale_hours=6.0,
                cooldown_seconds=3600.0
            )
            self.assertEqual(second_alerted, [])
            self.assertEqual(mock_notify.await_count, 1)

            # Force alert: bypasses cooldown
            forced_alerted = await check_and_alert_stale_catalogs(
                override_dir=self.test_dir,
                max_stale_hours=6.0,
                cooldown_seconds=3600.0,
                force_alert=True
            )
            self.assertEqual(forced_alerted, ["mexc"])
            self.assertEqual(mock_notify.await_count, 2)


if __name__ == "__main__":
    unittest.main()
