# -*- coding: utf-8 -*-
"""
AlertG — Phase F-4 Unit & Integration Tests:
1. Daily Crypto Exchange Self-Test execution.
2. Degradation & Dropout detection.
3. Admin Telegram Alert dispatching on exchange degradation.
4. Admin REST API (/api/admin/crypto/selftest).
"""
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.markets.adapters.base import BatchPriceResult
from app.markets.crypto_selftest import (
    run_single_exchange_selftest,
    run_daily_crypto_selftest,
    get_latest_crypto_selftest
)


class TestCryptoSelfTestF4(unittest.IsolatedAsyncioTestCase):

    async def test_01_single_exchange_healthy(self):
        """Verify healthy exchange audit returns HEALTHY status with prices count."""
        mock_client = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.display_name = "Binance Spot"
        mock_adapter.fetch_batch_prices = AsyncMock(return_value=BatchPriceResult(
            prices={"BTCUSDT": 68000.0, "ETHUSDT": 2500.0},
            error_code="OK"
        ))

        with patch("app.markets.crypto_selftest.get_exchange_adapter", return_value=mock_adapter):
            res = await run_single_exchange_selftest("binance", mock_client)
            self.assertTrue(res["healthy"])
            self.assertEqual(res["status"], "HEALTHY")
            self.assertEqual(res["prices_count"], 2)
            self.assertIsNone(res["issue"])

    async def test_02_single_exchange_degraded_on_empty_prices(self):
        """Verify empty prices or provider block marks exchange as DEGRADED."""
        mock_client = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.display_name = "MEXC Global"
        mock_adapter.fetch_batch_prices = AsyncMock(return_value=BatchPriceResult(
            prices={},
            error="Cloudflare block HTTP 403",
            error_code="PROVIDER_BLOCKED",
            http_status=403
        ))

        with patch("app.markets.crypto_selftest.get_exchange_adapter", return_value=mock_adapter):
            res = await run_single_exchange_selftest("mexc", mock_client)
            self.assertFalse(res["healthy"])
            self.assertEqual(res["status"], "DEGRADED")
            self.assertEqual(res["prices_count"], 0)
            self.assertIn("Cloudflare", res["issue"])

    async def test_03_single_exchange_down_on_exception(self):
        """Verify network or runtime exception marks exchange as DOWN."""
        mock_client = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.display_name = "KuCoin Spot"
        mock_adapter.fetch_batch_prices = AsyncMock(side_effect=ConnectionResetError("Connection dropped"))

        with patch("app.markets.crypto_selftest.get_exchange_adapter", return_value=mock_adapter):
            res = await run_single_exchange_selftest("kucoin", mock_client)
            self.assertFalse(res["healthy"])
            self.assertEqual(res["status"], "DOWN")
            self.assertIn("Connection dropped", res["issue"])

    async def test_04_daily_selftest_dispatches_admin_telegram_alert(self):
        """Verify run_daily_crypto_selftest dispatches admin Telegram alert when exchanges degrade."""
        mock_client = MagicMock()

        # Mock adapter returns degraded for 1 exchange, healthy for others
        def mock_get_adapter(ex_id):
            adapter = MagicMock()
            adapter.display_name = ex_id.upper()
            if ex_id == "kraken":
                adapter.fetch_batch_prices = AsyncMock(return_value=BatchPriceResult(
                    prices={},
                    error="Timeout from Kraken Cloud",
                    error_code="TIMEOUT"
                ))
            else:
                adapter.fetch_batch_prices = AsyncMock(return_value=BatchPriceResult(
                    prices={"BTCUSDT": 68000.0},
                    error_code="OK"
                ))
            return adapter

        mock_notify = AsyncMock()

        with patch("app.markets.crypto_selftest.get_exchange_adapter", side_effect=mock_get_adapter), \
             patch("app.markets.crypto_selftest.notify_admin_telegram", mock_notify):

            report = await run_daily_crypto_selftest(client=mock_client, notify_admin=True)

            self.assertEqual(report["status"], "DEGRADED")
            self.assertGreater(report["total_exchanges"], 0)
            self.assertEqual(report["degraded_count"], 1)
            self.assertIn("kraken", report["results"])
            self.assertFalse(report["results"]["kraken"]["healthy"])

            # Verify admin Telegram alert was called with diagnostic info
            mock_notify.assert_called_once()
            called_msg = mock_notify.call_args[0][0]
            self.assertIn("Crypto Exchange Self-Test Warning", called_msg)
            self.assertIn("kraken", called_msg.lower())

    async def test_05_latest_selftest_accessor(self):
        """Verify get_latest_crypto_selftest returns stored report."""
        latest = get_latest_crypto_selftest()
        self.assertIsInstance(latest, dict)
        self.assertIn("status", latest)


if __name__ == "__main__":
    unittest.main()
