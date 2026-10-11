#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 9: Observability, Health & Quotas, Kill Switch and Telegram Alerts Unit Tests.
Verifies:
  1. /status & /api/admin/probe include provider health & quota, last sync info, and failing symbols.
  2. Provider and Category Kill Switches from env variables.
  3. Automatic Admin Telegram Alerts for outage, >80% quota usage, and failed sync.
"""

import os
import unittest
import asyncio
from unittest.mock import patch, AsyncMock

from app.state import METRICS, FAILED_SYMBOLS
from app.markets.limiter import (
    record_provider_metric, get_all_providers_status,
    _QUOTA_ALERTED_PROVIDERS, _OUTAGE_ALERTED_PROVIDERS
)
from app.markets.kill_switch import (
    is_provider_killed, is_category_killed, get_active_kill_switches
)
from app.engine.sync import get_last_sync_info, check_sync_safety, CatalogSafetyCeilingExceededError
from app.routes.admin import get_status_dashboard, admin_probe_market_sources
import app.state as state


class TestPhase9Observability(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Reset alert tracking sets for clean test runs
        _QUOTA_ALERTED_PROVIDERS.clear()
        _OUTAGE_ALERTED_PROVIDERS.clear()
        FAILED_SYMBOLS.clear()

    def tearDown(self):
        # Clean up any kill switch env variables
        for k in list(os.environ.keys()):
            if k.startswith("KILL_SWITCH_"):
                del os.environ[k]

    def test_01_kill_switch_provider_and_category(self):
        """Test Kill Switch resolution via list and per-item env variables"""
        self.assertFalse(is_provider_killed("yahoo"))
        self.assertFalse(is_category_killed("iran"))

        # Test global comma-separated lists
        os.environ["KILL_SWITCH_PROVIDERS"] = "yahoo, twelvedata"
        os.environ["KILL_SWITCH_CATEGORIES"] = "iran, macro"

        self.assertTrue(is_provider_killed("yahoo"))
        self.assertTrue(is_provider_killed("twelvedata"))
        self.assertFalse(is_provider_killed("nobitex"))

        self.assertTrue(is_category_killed("iran"))
        self.assertTrue(is_category_killed("macro"))
        self.assertFalse(is_category_killed("crypto"))

        # Test specific per-provider and per-category env flags
        os.environ["KILL_SWITCH_PROVIDER_NOBITEX"] = "1"
        os.environ["KILL_SWITCH_CATEGORY_CRYPTO"] = "true"

        self.assertTrue(is_provider_killed("nobitex"))
        self.assertTrue(is_category_killed("crypto"))

        status = get_active_kill_switches()
        self.assertTrue(status["any_active"])
        self.assertIn("yahoo", status["providers_killed"])
        self.assertIn("nobitex", status["providers_killed"])
        self.assertIn("iran", status["categories_killed"])
        self.assertIn("crypto", status["categories_killed"])

    async def test_02_price_fetch_blocked_by_kill_switch(self):
        """Verify fetch_price_with_trace respects category and provider kill switches"""
        from app.markets.base import fetch_price_with_trace

        os.environ["KILL_SWITCH_CATEGORIES"] = "macro"
        dummy_client = AsyncMock()

        # Macro symbol should fast-fail without calling outbound network
        price, traces = await fetch_price_with_trace(dummy_client, "macro", "US10Y")
        self.assertIsNone(price)
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0]["source"], "kill_switch")
        self.assertIn("disabled by kill switch", traces[0]["error"].lower())
        dummy_client.get.assert_not_called()

    async def test_03_provider_quota_alert_dispatched_at_80_percent(self):
        """Verify Telegram admin alert is fired when provider reaches >=80% quota"""
        with patch("app.notifier.telegram.send_telegram_alert", new_callable=AsyncMock) as mock_tg:
            with patch("app.config.TELEGRAM_ADMIN_CHAT_ID", "12345678"):
                # Twelve data limit is 800 req/day in PROVIDER_QUOTAS
                # Send 640 requests (exactly 80%)
                prov_metrics = METRICS.setdefault("providers", {})
                prov_metrics["twelvedata"] = {"requests": 639, "success": 639, "errors": 0, "rate_limits_429": 0}

                # 640th request triggers >=80%
                record_provider_metric("twelvedata", "requests")
                await asyncio.sleep(0.05)

                self.assertIn("twelvedata", _QUOTA_ALERTED_PROVIDERS)
                mock_tg.assert_called_once()
                call_args = mock_tg.call_args[0]
                message_sent = call_args[2]
                self.assertIn("سهمیه بالای ۸۰٪", message_sent)
                self.assertIn("Twelve Data", message_sent)

                # Subsequent requests should not spam alerts again
                record_provider_metric("twelvedata", "requests")
                await asyncio.sleep(0.05)
                self.assertEqual(mock_tg.call_count, 1)

    async def test_04_provider_outage_alert_dispatched(self):
        """Verify Telegram admin alert is fired on provider outage / error threshold"""
        with patch("app.notifier.telegram.send_telegram_alert", new_callable=AsyncMock) as mock_tg:
            with patch("app.config.TELEGRAM_ADMIN_CHAT_ID", "12345678"):
                # Nobitex enters OUTAGE_OR_BLOCKED on 6 rate limits 429
                for _ in range(6):
                    record_provider_metric("nobitex", "rate_limits_429", status_code=429)

                await asyncio.sleep(0.05)
                self.assertIn("nobitex", _OUTAGE_ALERTED_PROVIDERS)
                mock_tg.assert_called_once()
                call_args = mock_tg.call_args[0]
                message_sent = call_args[2]
                self.assertIn("قطعی سرویس‌دهنده", message_sent)
                self.assertIn("OUTAGE_OR_BLOCKED", message_sent)

    def test_05_catalog_sync_safety_admin_alert_on_halt(self):
        """Verify emergency halt of catalog sync triggers admin alert"""
        with patch("app.notifier.telegram.send_telegram_alert", new_callable=AsyncMock) as mock_tg:
            with patch("app.config.TELEGRAM_ADMIN_CHAT_ID", "12345678"):
                # Safety ceiling exceeded (>5% delisted)
                bad_stats = {"candidate_count": 94, "current_active_count": 100, "added_count": 0, "delisted_count": 6}
                with self.assertRaises(CatalogSafetyCeilingExceededError):
                    check_sync_safety(bad_stats)

                self.assertGreater(METRICS.get("catalog_sync_admin_alerts", 0), 0)
                self.assertIn("exceeds 5.0% threshold", METRICS.get("last_catalog_sync_error", ""))

    def test_06_last_sync_info_summary(self):
        """Verify get_last_sync_info provides comprehensive metadata"""
        info = get_last_sync_info()
        self.assertIn("version", info)
        self.assertIn("last_sync_at", info)
        self.assertIn("total_symbols", info)
        self.assertIn("active_symbols", info)
        self.assertIn("delisted_symbols", info)
        self.assertIn("status", info)

    def test_07_failing_symbols_tracking(self):
        """Verify FAILED_SYMBOLS correctly populates in status dashboard"""
        FAILED_SYMBOLS["binance:INVALID_COIN"] = {
            "symbol": "INVALID_COIN",
            "exchange": "binance",
            "category": "crypto",
            "error": "Symbol not found or 0 price",
            "attempts": 3,
            "failed_at": 1700000000.0
        }

        # JSON status response
        res = get_status_dashboard(format="json")
        import json
        body = json.loads(res.body.decode("utf-8"))

        self.assertIn("providers", body)
        self.assertIn("last_catalog_sync", body)
        self.assertIn("failing_symbols", body)
        self.assertEqual(body["failing_symbols"]["count"], 1)
        self.assertEqual(body["failing_symbols"]["items"][0]["symbol"], "INVALID_COIN")
        self.assertIn("kill_switches", body)

        # HTML status response
        html_res = get_status_dashboard(format="html")
        html_text = html_res.body.decode("utf-8")
        self.assertIn("INVALID_COIN", html_text)
        self.assertIn("Provider Health & Quotas", html_text)
        self.assertIn("Weekly Catalog Sync Status", html_text)

    async def test_08_admin_probe_includes_observability_matrix(self):
        """Verify /api/admin/probe returns providers, last_sync, failing_symbols, and respects kill switches"""
        os.environ["KILL_SWITCH_PROVIDERS"] = "binance"
        state.http_client = AsyncMock()

        report = await admin_probe_market_sources(format="json")

        self.assertIn("summary", report)
        self.assertIn("providers", report)
        self.assertIn("last_catalog_sync", report)
        self.assertIn("failing_symbols", report)
        self.assertIn("kill_switches", report)

        # Binance spot probe should have been aborted via kill switch with 0 latency
        binance_result = next((r for r in report["results"] if r["id"] == "binance"), None)
        self.assertIsNotNone(binance_result)
        self.assertEqual(binance_result["status"], "KILLED")
        self.assertEqual(binance_result["latency_ms"], 0.0)
        self.assertEqual(binance_result["error"], "Disabled by Kill Switch")


if __name__ == '__main__':
    unittest.main()
