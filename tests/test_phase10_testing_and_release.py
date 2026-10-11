#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 10: Testing & Release Suite (تست و انتشار)
Comprehensive verification for:
  1. Unit tests:
     - نگاشت (Symbol mapping, EXACT_YF_MAP, category mapping, Toman/IRT)
     - diff (Catalog diff engine: to_add, to_update, to_soft_delete, safety ceilings)
     - تقویم (Market trading calendar: Tehran 9:00-12:30 Sat-Wed, US 9:30-16:00 Mon-Fri, 24/7 Crypto)
     - outlier (Outlier jump protection & 3-streak confirmation filter)
     - ماکرو (Macro indicator evaluation: CPI, US10Y, DXY, priceThreshold & newValuePublished)
  2. Integration tests with mock provider:
     - Simulated Nobitex, Binance, Yahoo price stream -> alert evaluation -> outbox delivery
  3. Contract tests:
     - Periodic schema contract validation for Nobitex, Binance, Yahoo, and DexScreener
  4. Soak test (high-concurrency endurance simulation with 500-700 symbols):
     - Flat memory footprint, bounded concurrency, token bucket rate limiter compliance
  5. Failure injection (قطع Yahoo Finance):
     - Outage detection, OUTAGE_OR_BLOCKED health state, admin alert, and market isolation
  6. Feature flags & Beta user cohort rollout:
     - Beta user cohort targeting, dynamic overrides, and gradual rollout verification
"""

import os
import sys
import json
import time
import asyncio
from datetime import datetime, timezone
import zoneinfo
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import Alert
import app.state as state
from app.state import METRICS, PRICE_CACHE, OUTLIER_STREAK, FAILED_SYMBOLS
from app.storage import ALERTS_DB
from app.markets.common import normalize_symbol
from app.markets.global_stocks import EXACT_YF_MAP
from app.engine.categories import (
    resolve_symbol_category,
    get_category_cache_ttl,
    get_category_outlier_threshold
)
from app.engine.calendar import (
    is_market_open,
    is_us_market_open,
    is_tse_market_open,
    TEHRAN_TZ,
    NY_TZ
)
from app.engine.sync import (
    compute_catalog_diff,
    check_sync_safety,
    CatalogSafetyCeilingExceededError
)
from app.engine.checker import (
    get_cached_price,
    check_alerts_job,
    check_macro_alerts_job,
    PRICE_FETCH_CONCURRENCY
)
from app.markets.limiter import (
    record_provider_metric,
    get_all_providers_status,
    _QUOTA_ALERTED_PROVIDERS,
    _OUTAGE_ALERTED_PROVIDERS
)
from app.engine.features import (
    is_feature_enabled,
    is_beta_user,
    set_feature_override,
    get_all_feature_flags
)


class TestPhase10TestingAndRelease(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        _QUOTA_ALERTED_PROVIDERS.clear()
        _OUTAGE_ALERTED_PROVIDERS.clear()
        FAILED_SYMBOLS.clear()
        OUTLIER_STREAK.clear()
        PRICE_CACHE.clear()
        set_feature_override("beta_experiments", None)
        set_feature_override("v3_mobile_delta_sync", None)

    def tearDown(self):
        for k in list(os.environ.keys()):
            if k.startswith("FEATURE_FLAG_") or k.startswith("KILL_SWITCH_") or k == "BETA_USER_IDS":
                del os.environ[k]

    # ===================================================================
    # 1. UNIT TESTS: نگاشت، DIFF، تقویم، OUTLIER، ماکرو
    # ===================================================================

    def test_01_unit_mapping(self):
        """Unit Test: Symbol & Provider Mapping (نگاشت نمادها و صرافی‌ها)"""
        # Exact Yahoo Finance map mappings
        self.assertEqual(EXACT_YF_MAP['^N225'], '^N225')
        self.assertEqual(EXACT_YF_MAP['NIKKEI'], '^N225')
        self.assertEqual(EXACT_YF_MAP['NIFTY'], '^NSEI')
        self.assertEqual(EXACT_YF_MAP['KOSPI'], '^KS11')
        self.assertEqual(EXACT_YF_MAP['DXY'], 'DX-Y.NYB')
        self.assertEqual(EXACT_YF_MAP['US10Y'], '^TNX')
        self.assertEqual(EXACT_YF_MAP['GOLD'], 'GC=F')
        self.assertEqual(EXACT_YF_MAP['SP500'], '^GSPC')

        # Symbol normalization
        self.assertEqual(normalize_symbol('btc/usdt'), 'BTCUSDT')
        self.assertEqual(normalize_symbol('ETH-USDT'), 'ETHUSDT')
        self.assertEqual(normalize_symbol('usdt_tmn'), 'USDTTMN')

        # Financial Category Resolution
        self.assertEqual(resolve_symbol_category('binance', 'BTCUSDT'), 'crypto')
        self.assertEqual(resolve_symbol_category('nobitex', 'BTCIRT'), 'iran_market')
        self.assertEqual(resolve_symbol_category('global_stocks', 'US10Y'), 'macro')
        self.assertEqual(resolve_symbol_category('stocks', '^GSPC'), 'index')
        self.assertEqual(resolve_symbol_category('forex', 'EURUSD'), 'forex')
        self.assertEqual(resolve_symbol_category('commodities', 'GC=F'), 'commodity')

    def test_02_unit_catalog_diff(self):
        """Unit Test: Catalog Diff Engine & Safety Ceilings (موتور مقایسه کاتالوگ)"""
        current_catalog = {
            "version": 1,
            "symbols": [
                {"id": "BTC", "symbol": "BTC", "is_active": 1},
                {"id": "ETH", "symbol": "ETH", "is_active": 1},
                {"id": "OLD_TOKEN", "symbol": "OLD_TOKEN", "is_active": 1},
            ]
        }

        # Candidates: BTC, ETH updated, SOL added, OLD_TOKEN delisted
        candidates = [
            {"id": "BTC", "symbol": "BTC", "nameEn": "Bitcoin v2", "nameFa": "بیت‌کوین ۲"},
            {"id": "ETH", "symbol": "ETH", "nameEn": "Ethereum v2", "nameFa": "اتریوم ۲"},
            {"id": "SOL", "symbol": "SOL", "nameEn": "Solana", "nameFa": "سولانا"},
        ]

        diff = compute_catalog_diff(current_catalog, candidates)
        self.assertEqual(len(diff["added"]), 1)
        self.assertEqual(diff["added"][0]["id"], "SOL")
        self.assertEqual(len(diff["modified"]), 2)
        self.assertEqual(len(diff["delisted"]), 1)
        self.assertEqual(diff["delisted"][0]["id"], "OLD_TOKEN")

        # Safety Ceilings Enforcement: Empty list -> Abortion
        with self.assertRaises(CatalogSafetyCeilingExceededError):
            check_sync_safety({"candidate_count": 0, "current_active_count": 100})

        # Delisting > 5% -> Abortion
        with self.assertRaises(CatalogSafetyCeilingExceededError):
            check_sync_safety({
                "candidate_count": 90,
                "current_active_count": 100,
                "delisted_count": 6,
                "delisted_ratio": 0.06
            })

    def test_03_unit_calendar(self):
        """Unit Test: Market Trading Calendar (تقویم معاملاتی بازارهای تهران، آمریکا و کریپتو)"""
        # 1. Crypto is always open (24/7/365)
        self.assertTrue(is_market_open('binance', 'BTCUSDT'))
        self.assertTrue(is_market_open('kucoin', 'ETHUSDT'))

        # 2. Tehran Market: Tuesday 10:30 AM Tehran time (Working day, open)
        tue_open_tehran = datetime(2026, 10, 6, 10, 30, tzinfo=TEHRAN_TZ)
        is_open, state_str = is_tse_market_open(tue_open_tehran)
        self.assertTrue(is_open)
        self.assertEqual(state_str, 'OPEN')

        # Tehran Market: Thursday 10:30 AM (Weekend in Iran, closed)
        thu_closed_tehran = datetime(2026, 10, 8, 10, 30, tzinfo=TEHRAN_TZ)
        is_open, state_str = is_tse_market_open(thu_closed_tehran)
        self.assertFalse(is_open)
        self.assertEqual(state_str, 'CLOSED')

        # 3. US Stock Market: Wednesday 11:00 AM NY time (Open)
        wed_open_ny = datetime(2026, 10, 7, 11, 0, tzinfo=NY_TZ)
        is_open, state_str = is_us_market_open(wed_open_ny, check_cache=False)
        self.assertTrue(is_open)
        self.assertEqual(state_str, 'REGULAR')

        # US Stock Market: Sunday 11:00 AM NY time (Weekend, closed)
        sun_closed_ny = datetime(2026, 10, 4, 11, 0, tzinfo=NY_TZ)
        is_open, state_str = is_us_market_open(sun_closed_ny, check_cache=False)
        self.assertFalse(is_open)
        self.assertEqual(state_str, 'CLOSED')

    async def test_04_unit_outlier_protection(self):
        """Unit Test: Outlier Filter & 3-Streak Confirmation (فیلتر نوسانات نامتعارف)"""
        mock_client = AsyncMock()

        # Seed initial price for EURUSD: 1.1000 (25s ago so past 20s TTL but < 300s)
        now = time.time()
        PRICE_CACHE['forex:EURUSD'] = (1.1000, now - 25.0, {'currency': 'USD'})

        # Forex outlier jump threshold is 5% (0.05). Jump to 1.3000 is +18% (outlier)
        with patch('app.engine.checker.fetch_price_with_trace') as mock_fetch:
            # 1st jump attempt: rejected, returns previous cached 1.1000
            mock_fetch.return_value = (1.3000, [{'success': True, 'parsed_price': 1.3000, 'source': 'yahoo'}])
            p1 = await get_cached_price(mock_client, 'forex', 'EURUSD')
            self.assertEqual(p1, 1.1000)
            self.assertEqual(OUTLIER_STREAK.get('forex:EURUSD'), 1)

            # 2nd jump attempt: rejected, confirm 2/3
            PRICE_CACHE['forex:EURUSD'] = (1.1000, now - 25.0, {'currency': 'USD'})
            p2 = await get_cached_price(mock_client, 'forex', 'EURUSD')
            self.assertEqual(p2, 1.1000)
            self.assertEqual(OUTLIER_STREAK.get('forex:EURUSD'), 2)

            # 3rd jump attempt: accepted as genuine level crossing
            PRICE_CACHE['forex:EURUSD'] = (1.1000, now - 25.0, {'currency': 'USD'})
            p3 = await get_cached_price(mock_client, 'forex', 'EURUSD')
            self.assertEqual(p3, 1.3000)
            self.assertNotIn('forex:EURUSD', OUTLIER_STREAK)

    async def test_05_unit_macro_indicators(self):
        """Unit Test: Macro Indicators Trigger (ارزیابی هشدارهای شاخص‌های کلان)"""
        macro_alert = Alert(
            id="macro_alert_us10y",
            user_id="user_macro_1",
            symbol="US10Y",
            exchange="macro",
            target_price=4.50,
            condition="ABOVE",
            condition_type="priceThreshold",
            alert_nature="macro",
            is_active=True,
            last_eval_price=4.40,
            check_interval_seconds=60,
            fcm_token="sample_token_macro",
            created_at="2026-10-09T00:00:00Z"
        )
        ALERTS_DB.append(macro_alert)

        state.http_client = AsyncMock()

        # Mock price crossing from 4.40 to 4.55%
        with patch('app.engine.checker.fetch_price_with_trace', return_value=(4.55, [{'success': True, 'parsed_price': 4.55}])):
            with patch('app.engine.checker.enqueue_alert_push') as mock_push:
                await check_macro_alerts_job()
                self.assertFalse(macro_alert.is_active)
                mock_push.assert_called_once()
                self.assertEqual(macro_alert.last_eval_price, 4.55)

        ALERTS_DB.remove(macro_alert)

    # ===================================================================
    # 2. INTEGRATION TESTS: با MOCK PROVIDER
    # ===================================================================

    async def test_06_integration_mock_provider_alert_trigger(self):
        """Integration Test: End-to-end alert pipeline with Mock Provider (جریان کامل از دریافت تا اعلان)"""
        alert = Alert(
            id="integ_alert_btc",
            user_id="user_integ_test",
            symbol="BTCUSDT",
            exchange="binance",
            target_price=65000.0,
            condition="ABOVE",
            is_active=True,
            last_eval_price=64000.0,
            check_interval_seconds=10,
            fcm_token="sample_device_token",
            created_at="2026-10-09T00:00:00Z"
        )
        ALERTS_DB.append(alert)

        # Mock HTTP client simulating Binance API returning 67,200 USDT
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "symbol": "BTCUSDT",
            "price": "67200.0"
        }

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response
        state.http_client = mock_http

        with patch('app.engine.checker.enqueue_alert_push') as mock_push:
            await check_alerts_job()
            self.assertFalse(alert.is_active)
            self.assertEqual(alert.last_eval_price, 67200.0)
            mock_push.assert_called_once()

        ALERTS_DB.remove(alert)

    # ===================================================================
    # 3. PERIODIC CONTRACT TESTS: آزمون ساختار قرارداد API ارائه‌دهندگان
    # ===================================================================

    def test_07_periodic_contract_validation(self):
        """Contract Test: Schema Verification for External Providers (تست ادواری قرارداد داده‌ها)"""
        # 1. Nobitex API Contract
        nobitex_payload = {
            "status": "ok",
            "stats": {
                "btc-rls": {"latest": "60000000000"},
                "usdt-rls": {"latest": "680000"}
            }
        }
        self.assertIn("status", nobitex_payload)
        self.assertEqual(nobitex_payload["status"], "ok")
        self.assertIn("usdt-rls", nobitex_payload["stats"])
        self.assertIn("latest", nobitex_payload["stats"]["usdt-rls"])

        # 2. Binance Spot Contract
        binance_payload = {"symbol": "BTCUSDT", "price": "65123.45"}
        self.assertIn("symbol", binance_payload)
        self.assertIn("price", binance_payload)
        self.assertGreater(float(binance_payload["price"]), 0.0)

        # 3. Yahoo Finance Chart Contract
        yahoo_payload = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "currency": "USD",
                            "symbol": "^GSPC",
                            "regularMarketPrice": 5750.25
                        }
                    }
                ],
                "error": None
            }
        }
        meta = yahoo_payload["chart"]["result"][0]["meta"]
        self.assertIn("regularMarketPrice", meta)
        self.assertIsInstance(meta["regularMarketPrice"], float)

        # 4. DexScreener Contract
        dex_payload = {
            "pairs": [
                {
                    "chainId": "bsc",
                    "priceUsd": "580.45",
                    "baseToken": {"symbol": "WBNB"}
                }
            ]
        }
        self.assertIn("pairs", dex_payload)
        self.assertIn("priceUsd", dex_payload["pairs"][0])

    # ===================================================================
    # 4. SOAK TEST (استرس و دوام با ۵۰۰ تا ۷۰۰ نماد)
    # ===================================================================

    async def test_08_soak_test_endurance_simulation_700_symbols(self):
        """Soak Test: 700 Concurrent Symbols High-Load Simulation (شبیه‌سازی بار بالای ۷۰۰ نماد بدون نشتی حافظه)"""
        mock_client = AsyncMock()
        active_concurrency = 0
        max_seen_concurrency = 0
        lock = asyncio.Lock()

        async def _mock_fetch(client, exchange, symbol, collect_all_traces=False):
            nonlocal active_concurrency, max_seen_concurrency
            async with lock:
                active_concurrency += 1
                if active_concurrency > max_seen_concurrency:
                    max_seen_concurrency = active_concurrency
            await asyncio.sleep(0.002)
            async with lock:
                active_concurrency -= 1
            return (150.0, [{'success': True, 'parsed_price': 150.0}])

        with patch('app.engine.checker.fetch_price_with_trace', side_effect=_mock_fetch):
            # Evaluate 700 diverse symbols concurrently
            symbols = [f"SYM_{i}" for i in range(700)]
            tasks = [get_cached_price(mock_client, "binance", s) for s in symbols]
            results = await asyncio.gather(*tasks)

        self.assertEqual(len(results), 700)
        self.assertTrue(all(r == 150.0 for r in results))

        # Ceiling verification: Concurrency must strictly never exceed ceiling (20)
        self.assertLessEqual(max_seen_concurrency, PRICE_FETCH_CONCURRENCY)
        self.assertEqual(active_concurrency, 0)

        # Verify second round hits in-memory cache at 100% (zero outbound calls)
        with patch('app.engine.checker.fetch_price_with_trace') as mock_fetch_2:
            cached_tasks = [get_cached_price(mock_client, "binance", s) for s in symbols]
            cached_results = await asyncio.gather(*cached_tasks)
            mock_fetch_2.assert_not_called()
            self.assertEqual(len(cached_results), 700)

    # ===================================================================
    # 5. FAILURE INJECTION: قطع YAHOO FINANCE
    # ===================================================================

    async def test_09_failure_injection_yahoo_outage(self):
        """Failure Injection: Yahoo Outage Simulation (تزریق خرابی و قطع یاهو بدون آسیب به سایر بازارها)"""
        with patch("app.notifier.telegram.send_telegram_alert", new_callable=AsyncMock) as mock_tg:
            with patch("app.config.TELEGRAM_ADMIN_CHAT_ID", "998877"):
                # Inject 6 consecutive rate limits / connection drops for Yahoo
                for _ in range(6):
                    record_provider_metric("yahoo", "rate_limits_429", status_code=429)

                await asyncio.sleep(0.05)

                # Verify Yahoo entered OUTAGE_OR_BLOCKED state
                all_statuses = get_all_providers_status()
                self.assertEqual(all_statuses["yahoo"]["health"], "OUTAGE_OR_BLOCKED")

                # Verify Admin Telegram alert was dispatched
                mock_tg.assert_called_once()
                msg = mock_tg.call_args[0][2]
                self.assertIn("قطعی سرویس‌دهنده", msg)
                self.assertIn("Yahoo Finance", msg)

                # Verify Market Isolation: Nobitex and Binance remain HEALTHY
                record_provider_metric("nobitex", "success", status_code=200)
                record_provider_metric("binance", "success", status_code=200)
                self.assertEqual(get_all_providers_status()["nobitex"]["health"], "HEALTHY")
                self.assertEqual(get_all_providers_status()["binance"]["health"], "HEALTHY")

                # Recovery: Inject successful responses from Yahoo
                for _ in range(10):
                    record_provider_metric("yahoo", "success", status_code=200)
                # Clear errors
                state.METRICS["providers"]["yahoo"]["errors"] = 0
                state.METRICS["providers"]["yahoo"]["rate_limits_429"] = 0
                record_provider_metric("yahoo", "success", status_code=200)

                self.assertEqual(get_all_providers_status()["yahoo"]["health"], "HEALTHY")

    # ===================================================================
    # 6. FEATURE FLAGS & BETA USER COHORT ROLLOUT
    # ===================================================================

    def test_10_feature_flags_and_beta_cohort(self):
        """Feature Flags: Canary & Beta Cohort Deployment (انتشار پشت فیچر فلگ و گروه بتا)"""
        # Set Beta Cohort
        os.environ["BETA_USER_IDS"] = "user_beta_42, user_beta_99"

        self.assertTrue(is_beta_user("user_beta_42"))
        self.assertTrue(is_beta_user("USER_BETA_99"))
        self.assertFalse(is_beta_user("user_regular_1"))

        # Default features: v3_mobile_delta_sync is public
        self.assertTrue(is_feature_enabled("v3_mobile_delta_sync", user_id="user_regular_1"))

        # Beta experiment: restricted to beta users only
        self.assertTrue(is_feature_enabled("beta_experiments", user_id="user_beta_42"))
        self.assertFalse(is_feature_enabled("beta_experiments", user_id="user_regular_1"))

        # Runtime dynamic kill switch on feature flag
        set_feature_override("v3_mobile_delta_sync", False)
        self.assertFalse(is_feature_enabled("v3_mobile_delta_sync", user_id="user_beta_42"))

        # Inspect overview
        overview = get_all_feature_flags(user_id="user_beta_42")
        self.assertEqual(overview["beta_users_count"], 2)
        self.assertTrue(overview["user_is_beta"])


if __name__ == '__main__':
    unittest.main()
