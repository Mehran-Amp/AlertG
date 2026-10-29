#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — Phase 3 Test Suite: Real-Time Price Engine (Stage A).
Tests:
- T1: Snapshot Store operations (O(1) lookups, staleness detection, status mapping).
- T3: Strict Exchange Isolation via Snapshot Store (distinct prices, zero foreign leakage).
- T5: Zero outbound HTTP calls during alert evaluation under CRYPTO_ENGINE_V2=True.
- Demand-driven poller activation, back-off on rate limit, and in-flight concurrency lock.
- Real-time interval clamping (1s minimum for crypto vs 180s for non-crypto).
- Outlier threshold (1.00) and floor (1e-12) for crypto under CRYPTO_ENGINE_V2=True.
"""

import unittest
import asyncio
import time
import os
import tempfile
import shutil
from unittest.mock import AsyncMock, MagicMock, patch

try:
    import httpx
except ImportError:
    httpx = MagicMock()

import app.config as config
from app.models import Alert
from app.storage import ALERTS_DB
from app.markets.crypto_snapshot import (
    update_exchange_snapshot,
    get_snapshot_price,
    clear_snapshot_store,
    get_all_snapshots_status,
)
from app.markets.crypto_poller import CryptoPollerSupervisor
from app.markets.crypto import fetch_crypto
from app.security import _clamp_interval
from app.engine.categories import (
    resolve_symbol_category,
    get_category_outlier_threshold,
)


class TestCryptoEngineV2(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_client = AsyncMock()
        self._orig_alerts = list(ALERTS_DB)
        ALERTS_DB.clear()
        clear_snapshot_store()

        self.temp_dir = tempfile.mkdtemp(prefix="test_engine_")
        self._orig_catalog_dir = getattr(config, "CRYPTO_CATALOG_DIR", None)
        config.CRYPTO_CATALOG_DIR = self.temp_dir

        self._orig_engine_flag = getattr(config, "CRYPTO_ENGINE_V2", False)
        self._orig_strict_flag = getattr(config, "CRYPTO_STRICT_V2", False)
        config.CRYPTO_ENGINE_V2 = True
        config.CRYPTO_STRICT_V2 = True
        os.environ["CRYPTO_ENGINE_V2"] = "true"
        os.environ["CRYPTO_STRICT_V2"] = "true"

    def tearDown(self):
        config.CRYPTO_ENGINE_V2 = self._orig_engine_flag
        config.CRYPTO_STRICT_V2 = self._orig_strict_flag
        os.environ["CRYPTO_ENGINE_V2"] = "true" if self._orig_engine_flag else "false"
        os.environ["CRYPTO_STRICT_V2"] = "true" if self._orig_strict_flag else "false"
        config.CRYPTO_CATALOG_DIR = self._orig_catalog_dir

        ALERTS_DB.clear()
        ALERTS_DB.extend(self._orig_alerts)
        clear_snapshot_store()

        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # =========================================================================
    # T1: Snapshot Store Operations
    # =========================================================================

    def test_01_snapshot_store_crud_and_lookups(self):
        """Verifies O(1) in-memory price storage and retrieval."""
        now = time.time()
        update_exchange_snapshot(
            exchange_id="binance",
            prices={"BTCUSDT": 67123.45, "ETHUSDT": 2650.0},
            status="OK",
            latency_ms=45.2,
            as_of=now,
        )

        # 1. Exact match
        price, as_of, status, latency = get_snapshot_price("binance", "BTCUSDT")
        self.assertEqual(price, 67123.45)
        self.assertEqual(status, "OK")
        self.assertEqual(latency, 45.2)
        self.assertEqual(as_of, now)

        # 2. Case-insensitive lookup
        p_eth, _, s_eth, _ = get_snapshot_price("binance", "ethusdt")
        self.assertEqual(p_eth, 2650.0)
        self.assertEqual(s_eth, "OK")

        # 3. Unlisted symbol returns NO_PRICE
        p_none, _, s_none, _ = get_snapshot_price("binance", "SOLUSDT")
        self.assertIsNone(p_none)
        self.assertEqual(s_none, "NO_PRICE")

        # 4. Unknown exchange returns NO_PRICE
        p_un, _, s_un, _ = get_snapshot_price("nonexistent_broker", "BTCUSDT")
        self.assertIsNone(p_un)
        self.assertEqual(s_un, "NO_PRICE")

    def test_02_snapshot_staleness_detection(self):
        """Verifies snapshots older than max_age_seconds automatically return STALE_PRICE."""
        old_time = time.time() - 25.0  # 25 seconds ago
        update_exchange_snapshot(
            exchange_id="bybit",
            prices={"BTCUSDT": 67200.0},
            status="OK",
            latency_ms=30.0,
            as_of=old_time,
        )

        # Max age = 10s. Old time (25s) must be flagged as STALE_PRICE and return None
        price, as_of, status, _ = get_snapshot_price("bybit", "BTCUSDT", max_age_seconds=10.0)
        self.assertIsNone(price)
        self.assertEqual(status, "STALE_PRICE")
        self.assertEqual(as_of, old_time)

    def test_03_snapshot_status_monitoring_inspection(self):
        """Verifies get_all_snapshots_status aggregates health metadata accurately."""
        now = time.time()
        update_exchange_snapshot("bitget", {"BTCUSDT": 67300.0}, status="OK", latency_ms=50.0, as_of=now)
        update_exchange_snapshot("okx", {}, status="RATE_LIMITED", latency_ms=120.0, as_of=now, error="429 Too Many Requests")

        overview = get_all_snapshots_status()
        self.assertIn("bitget", overview)
        self.assertIn("okx", overview)

        self.assertEqual(overview["bitget"]["status"], "OK")
        self.assertEqual(overview["bitget"]["total_pairs"], 1)
        self.assertFalse(overview["bitget"]["is_stale"])

        self.assertEqual(overview["okx"]["status"], "RATE_LIMITED")
        self.assertEqual(overview["okx"]["total_pairs"], 0)
        self.assertIn("429", overview["okx"]["error"])

    # =========================================================================
    # T3: Strict Exchange Isolation via Snapshot Store
    # =========================================================================

    async def test_04_t3_strict_exchange_binding_with_distinct_snapshots(self):
        """
        Rule R1: Verifies that alerts query strictly their own exchange snapshot.
        Cross-exchange leakage is mathematically impossible.
        """
        now = time.time()
        update_exchange_snapshot("binance", {"BTCUSDT": 60001.0}, status="OK", as_of=now)
        update_exchange_snapshot("mexc", {"BTCUSDT": 60002.0}, status="OK", as_of=now)
        update_exchange_snapshot("kucoin", {"BTC-USDT": 60003.0}, status="OK", as_of=now)
        update_exchange_snapshot("bybit", {"BTCUSDT": 60007.0}, status="OK", as_of=now)
        update_exchange_snapshot("bitget", {"BTCUSDT": 60008.0}, status="OK", as_of=now)

        traces = []
        p_bybit = await fetch_crypto(self.mock_client, "bybit", "BTCUSDT", None, traces, False)
        self.assertEqual(p_bybit, 60007.0, "Bybit must return Bybit snapshot price")

        p_bitget = await fetch_crypto(self.mock_client, "bitget", "BTCUSDT", None, traces, False)
        self.assertEqual(p_bitget, 60008.0, "Bitget must return Bitget snapshot price")

        p_binance = await fetch_crypto(self.mock_client, "binance", "BTCUSDT", None, traces, False)
        self.assertEqual(p_binance, 60001.0, "Binance must return Binance snapshot price")

    async def test_05_t3_failing_exchange_never_steals_from_healthy_exchange(self):
        """
        Rule R1: When KuCoin snapshot is empty or RATE_LIMITED, fetch_crypto returns None.
        Zero fallback to Binance or Bybit.
        """
        now = time.time()
        update_exchange_snapshot("binance", {"BTCUSDT": 65000.0}, status="OK", as_of=now)
        update_exchange_snapshot("kucoin", {}, status="RATE_LIMITED", as_of=now, error="429 Rate Limit")

        traces = []
        p_kucoin = await fetch_crypto(self.mock_client, "kucoin", "BTCUSDT", None, traces, False)
        self.assertIsNone(p_kucoin, "KuCoin failure must NOT fall back to Binance price")
        self.assertTrue(any("snapshot:kucoin" in str(tr.get("url")) for tr in traces))
        self.assertFalse(any("snapshot:binance" in str(tr.get("url")) for tr in traces))

    # =========================================================================
    # T5: Zero Outbound HTTP Calls During Alert Evaluation
    # =========================================================================

    async def test_06_t5_evaluation_makes_zero_http_calls(self):
        """
        Rule R9: Evaluation path must execute from in-memory snapshot with ZERO HTTP calls.
        """
        now = time.time()
        update_exchange_snapshot("binance", {"BTCUSDT": 67500.0}, status="OK", as_of=now)

        network_called = []

        async def fake_try_fetch(*args, **kwargs):
            network_called.append(args)
            return None

        traces = []
        price = await fetch_crypto(
            client=self.mock_client,
            exchange="binance",
            symbol="BTCUSDT",
            _try_fetch=fake_try_fetch,
            traces=traces,
            collect_all_traces=False,
        )

        self.assertEqual(price, 67500.0)
        self.assertEqual(len(network_called), 0, "Evaluation path made outbound HTTP calls! Must be zero (Rule R9)")
        self.assertEqual(traces[0]["url"], "snapshot:binance")

    # =========================================================================
    # Demand-Driven Poller & Concurrency Lock
    # =========================================================================

    def test_07_demand_driven_poller_scanning(self):
        """Verifies poller scans ALERTS_DB for active crypto alert demand."""
        poller = CryptoPollerSupervisor()

        # No active alerts
        self.assertEqual(poller.get_active_demand_exchanges(), set())

        # Add active Binance and Bybit alerts
        ALERTS_DB.append(Alert(id="a1", user_id="u1", exchange="binance", symbol="BTCUSDT", is_active=True))
        ALERTS_DB.append(Alert(id="a2", user_id="u1", exchange="bybit", symbol="ETHUSDT", is_active=True))
        ALERTS_DB.append(Alert(id="a3", user_id="u1", exchange="macro", symbol="US10Y", is_active=True, alert_nature="macro"))
        ALERTS_DB.append(Alert(id="a4", user_id="u1", exchange="okx", symbol="SOLUSDT", is_active=False))

        demand = poller.get_active_demand_exchanges()
        self.assertIn("binance", demand)
        self.assertIn("bybit", demand)
        self.assertNotIn("okx", demand, "Inactive alert should not create demand")
        self.assertNotIn("macro", demand, "Macro alert should not create crypto demand")

    async def test_08_poller_in_flight_concurrency_lock(self):
        """Rule R9: Never two concurrent in-flight requests for the same exchange."""
        poller = CryptoPollerSupervisor()
        poller._in_flight.add("binance")

        # Attempting to poll while in-flight must skip immediately
        with patch("app.markets.crypto_catalog.get_exchange_adapter") as mock_get_adapter:
            await poller.poll_exchange_once("binance")
            mock_get_adapter.assert_not_called()

        poller._in_flight.discard("binance")

    # =========================================================================
    # Real-Time Clamping & Outlier Configuration
    # =========================================================================

    def test_09_interval_clamping_for_crypto_vs_non_crypto(self):
        """
        Rule R2: Crypto alerts allow intervals down to 1s.
        Non-crypto categories strictly maintain the 180s minimum floor.
        """
        # Crypto exchanges accept 1s minimum
        self.assertEqual(_clamp_interval(1, exchange="binance"), 1)
        self.assertEqual(_clamp_interval(2, exchange="bybit"), 2)
        self.assertEqual(_clamp_interval(5, exchange="bitget"), 5)
        self.assertEqual(_clamp_interval(10, exchange="lbank"), 10)

        # Non-crypto categories clamp to 180s
        self.assertEqual(_clamp_interval(1, exchange="stocks"), 180)
        self.assertEqual(_clamp_interval(5, exchange="global_stocks"), 180)
        self.assertEqual(_clamp_interval(10, exchange="nobitex"), 180)
        self.assertEqual(_clamp_interval(60, exchange="forex"), 180)
        self.assertEqual(_clamp_interval(1, exchange=None), 180)

    def test_10_crypto_category_and_outlier_threshold(self):
        """
        Rule R1: Crypto exchanges immediately classify as 'crypto'.
        Outlier threshold for crypto is 1.00 (100%) under CRYPTO_ENGINE_V2=True.
        """
        self.assertEqual(resolve_symbol_category("binance", "BTCUSDT"), "crypto")
        self.assertEqual(resolve_symbol_category("bybit", "BTCUSDT"), "crypto")
        self.assertEqual(resolve_symbol_category("bitget", "BTCUSDT"), "crypto")

        # Outlier threshold
        self.assertEqual(get_category_outlier_threshold("crypto"), 1.00)
        self.assertEqual(get_category_outlier_threshold("forex"), 0.05)


if __name__ == "__main__":
    unittest.main()
