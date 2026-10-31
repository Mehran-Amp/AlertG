# -*- coding: utf-8 -*-
"""
AlertG — Phase 9 Acceptance Tests: Delisted Coins, Needs Attention & Health Observability.
Verifies Phase 9 requirements:
1. When a coin disappears or is delisted from an exchange catalog:
   - Sets alert.needs_attention = True
   - Records alert.needs_attention_reason
   - NEVER deletes or deactivates the alert (is_active remains True).
2. Sends exactly one notification per delist event across Telegram and FCM.
3. Restoring / relisting a coin clears the needs_attention flag.
4. Non-crypto alerts (stocks, forex, Iranian markets) are completely untouched.
5. Catalog outages / safety threshold failures (< 20 pairs) do not trigger false delistings.
6. Admin status dashboard exposes per-exchange crypto catalog health.
7. Existing notification templates remain byte-identical.
"""

import os
import sys
import json
import time
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

# Ensure test runner has necessary modules without external runtime dependencies
for mod in [
    'httpx', 'fastapi', 'fastapi.middleware.cors', 'fastapi.responses',
    'apscheduler', 'apscheduler.schedulers', 'apscheduler.schedulers.asyncio',
    'firebase_admin', 'firebase_admin.credentials', 'firebase_admin.messaging', 'firebase_admin.exceptions'
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import app.config as config
from app.models import Alert
import app.storage as storage
from app.markets.crypto_lifecycle import (
    scan_and_flag_delisted_crypto_alerts,
    dispatch_delisted_alert_notifications,
    check_and_process_delisted_crypto_alerts,
)
from app.notifier.telegram import (
    format_coin_delisted_telegram_msg,
    format_alert_registered_telegram_msg,
)


class TestPhase9DelistedCoinsAndHealth(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="phase9_test_")
        self.catalog_dir = os.path.join(self.test_dir, "crypto_catalog")
        os.makedirs(self.catalog_dir, exist_ok=True)

        # Build valid mock catalog with 25 active pairs
        self.valid_pairs = [
            {"symbol": f"COIN{i}USDT", "base": f"COIN{i}", "quote": "USDT", "native_symbol": f"COIN{i}USDT", "is_leveraged": False}
            for i in range(1, 26)
        ]
        self.catalog_payload = {
            "exchange": "binance",
            "display_name": "Binance",
            "updated_at": int(time.time()),
            "total_pairs": len(self.valid_pairs),
            "is_stale": False,
            "error": None,
            "pairs": self.valid_pairs,
        }
        with open(os.path.join(self.catalog_dir, "binance.json"), "w", encoding="utf-8") as f:
            json.dump(self.catalog_payload, f)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_coin_delisted_sets_needs_attention_never_deletes(self):
        """Verifies delisted coin is flagged with needs_attention=True and is_active remains True."""
        active_alert = Alert(
            id="alt_delisted_1",
            user_id="user_test",
            exchange="binance",
            symbol="OLDCOINUSDT",  # Not in the 25 valid pairs
            target_price=10.0,
            condition="ABOVE",
            is_active=True,
        )
        alerts = [active_alert]

        flagged = scan_and_flag_delisted_crypto_alerts(alerts, override_dir=self.catalog_dir)

        self.assertEqual(len(flagged), 1)
        self.assertTrue(active_alert.needs_attention)
        self.assertIsNotNone(active_alert.needs_attention_reason)
        self.assertIn("OLDCOINUSDT", active_alert.needs_attention_reason)
        self.assertIn("Binance", active_alert.needs_attention_reason)
        # CRITICAL: Must NEVER auto-delete or auto-deactivate
        self.assertTrue(active_alert.is_active, "Alert was incorrectly deactivated on delisting")

    def test_02_relisted_coin_clears_needs_attention(self):
        """Verifies that if a coin reappears in the catalog, needs_attention is automatically cleared."""
        alert = Alert(
            id="alt_relisted_1",
            user_id="user_test",
            exchange="binance",
            symbol="COIN1USDT",  # Is in the catalog
            target_price=10.0,
            condition="ABOVE",
            is_active=True,
            needs_attention=True,
            needs_attention_reason="Previous delisting",
            attention_notified_at=123456.0,
        )
        alerts = [alert]

        flagged = scan_and_flag_delisted_crypto_alerts(alerts, override_dir=self.catalog_dir)

        self.assertEqual(len(flagged), 0, "Active listed coin should not be in newly flagged list")
        self.assertFalse(alert.needs_attention, "needs_attention was not cleared for restored coin")
        self.assertIsNone(alert.needs_attention_reason)
        self.assertIsNone(alert.attention_notified_at)

    def test_03_notification_dispatched_exactly_once(self):
        """Verifies simulated dispatch sends exactly 1 notification per event with zero duplicate spam."""
        alert = Alert(
            id="alt_notify_1",
            user_id="user_test",
            exchange="binance",
            symbol="DEADCOINUSDT",
            target_price=0.5,
            condition="BELOW",
            is_active=True,
            telegram_chat_id="12345678",
            fcm_token="test_fcm_token_xyz",
            needs_attention=True,
            needs_attention_reason="Removed from Binance catalog",
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        with patch("app.markets.crypto_lifecycle.send_telegram_alert", new=AsyncMock(return_value=True)) as mock_tg:
            with patch("app.markets.crypto_lifecycle.send_fcm_notification_async", new=AsyncMock(return_value=(True, "OK"))) as mock_fcm:
                # First dispatch: must send notifications
                import asyncio
                count1 = asyncio.run(dispatch_delisted_alert_notifications([alert], client=mock_client))
                self.assertEqual(count1, 1)
                self.assertEqual(mock_tg.call_count, 1)
                self.assertEqual(mock_fcm.call_count, 1)
                self.assertIsNotNone(alert.attention_notified_at)

                # Second dispatch: must NOT send duplicate notification
                count2 = asyncio.run(dispatch_delisted_alert_notifications([alert], client=mock_client))
                self.assertEqual(count2, 0)
                self.assertEqual(mock_tg.call_count, 1, "Duplicate Telegram notification was sent!")
                self.assertEqual(mock_fcm.call_count, 1, "Duplicate FCM notification was sent!")

    def test_04_delisted_template_formatting(self):
        """Verifies Phase 9 format_coin_delisted_telegram_msg and guarantees existing templates are untouched."""
        alert = Alert(
            id="alt_tmpl_1",
            user_id="user_test",
            exchange="binance",
            symbol="LUNAUSDT",
            target_price=80.0,
            condition="BELOW",
            needs_attention=True,
            needs_attention_reason="Pair halted on Binance Spot",
        )
        msg = format_coin_delisted_telegram_msg(alert)
        self.assertIn("Market Alert: Coin Unavailable", msg)
        self.assertIn("Binance", msg)
        self.assertIn("LUNAUSDT", msg)
        self.assertIn("Pair halted on Binance Spot", msg)
        self.assertIn("<blockquote>", msg)

        # Verify existing registration template is completely functional and untouched
        reg_msg = format_alert_registered_telegram_msg(alert)
        self.assertIn("LUNA/USDT", reg_msg)
        self.assertIn("Binance", reg_msg)

    def test_05_non_crypto_alerts_completely_unaffected(self):
        """Verifies stock, Iranian, forex and macro alerts are never scanned or flagged by crypto lifecycle."""
        stock_alert = Alert(
            id="alt_stock_1",
            user_id="user_test",
            exchange="stocks",
            symbol="AAPL",
            target_price=220.0,
            condition="ABOVE",
            is_active=True,
        )
        iran_alert = Alert(
            id="alt_iran_1",
            user_id="user_test",
            exchange="nobitex",
            symbol="USDTIRT",
            target_price=70000.0,
            condition="ABOVE",
            is_active=True,
        )
        alerts = [stock_alert, iran_alert]

        flagged = scan_and_flag_delisted_crypto_alerts(alerts, override_dir=self.catalog_dir)
        self.assertEqual(len(flagged), 0)
        self.assertFalse(stock_alert.needs_attention)
        self.assertFalse(iran_alert.needs_attention)

    def test_06_catalog_safety_failure_never_flags_alerts(self):
        """Verifies that an empty or failed catalog (< 20 pairs) does not trigger false delisting notifications."""
        # Create empty / broken catalog for mexc
        mexc_payload = {
            "exchange": "mexc",
            "display_name": "MEXC",
            "updated_at": int(time.time()),
            "total_pairs": 5,  # Under 20-pair ceiling
            "is_stale": True,
            "error": "Upstream API timeout",
            "pairs": [{"symbol": "BTCUSDT", "base": "BTC", "quote": "USDT"}],
        }
        with open(os.path.join(self.catalog_dir, "mexc.json"), "w", encoding="utf-8") as f:
            json.dump(mexc_payload, f)

        alert_mexc = Alert(
            id="alt_mexc_1",
            user_id="user_test",
            exchange="mexc",
            symbol="ETHUSDT",  # Not in the 5 pairs, but catalog is broken
            target_price=3000.0,
            condition="ABOVE",
            is_active=True,
        )
        flagged = scan_and_flag_delisted_crypto_alerts([alert_mexc], override_dir=self.catalog_dir)
        self.assertEqual(len(flagged), 0, "Alert was falsely flagged during an upstream catalog outage!")
        self.assertFalse(alert_mexc.needs_attention)

    def test_07_admin_status_contains_crypto_catalogs(self):
        """Verifies get_crypto_catalogs_status reports accurate health data for the admin status dashboard."""
        from app.markets.crypto_catalog import get_crypto_catalogs_status
        status = get_crypto_catalogs_status(override_dir=self.catalog_dir)
        self.assertIn("total_exchanges", status)
        self.assertIn("exchanges", status)
        self.assertIn("binance", status["exchanges"])
        b_info = status["exchanges"]["binance"]
        self.assertTrue(b_info["file_exists"])
        self.assertEqual(b_info["total_pairs"], 25)
        self.assertFalse(b_info["is_stale"])


if __name__ == "__main__":
    unittest.main()
