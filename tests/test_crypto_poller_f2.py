# -*- coding: utf-8 -*-
"""
AlertG — Phase F-2 Unit & Integration Tests:
1. Exponential back-off on rate limits / provider blocks.
2. Honor Retry-After headers in crypto poller.
3. Singleton Poller Guard (Rule R9) preventing concurrent multi-process pollers.
4. Percentile calculations (p50 / p95) and exposure in /status.
"""
import os
import sys
import time
import shutil
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.markets.adapters.base import BatchPriceResult
from app.markets.crypto_poller import (
    CryptoPollerSupervisor,
    record_poll_latency,
    get_crypto_latency_percentiles,
    _POLL_LATENCY_HISTORY,
    MAX_BACKOFF_SECONDS
)


class TestCryptoPollerF2(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_poller_f2_")
        self.orig_data_dir = getattr(sys.modules["app.config"], "DATA_DIR", ".")
        setattr(sys.modules["app.config"], "DATA_DIR", self.test_dir)
        _POLL_LATENCY_HISTORY.clear()

    def tearDown(self):
        setattr(sys.modules["app.config"], "DATA_DIR", self.orig_data_dir)
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)
        _POLL_LATENCY_HISTORY.clear()

    async def test_01_exponential_backoff_on_consecutive_errors(self):
        """Verify backoff doubles on repeated failures and caps at MAX_BACKOFF_SECONDS."""
        supervisor = CryptoPollerSupervisor()
        supervisor._client = MagicMock()

        mock_adapter = MagicMock()
        mock_adapter.fetch_batch_prices = AsyncMock(return_value=BatchPriceResult(
            prices={},
            error="Rate limit reached",
            error_code="RATE_LIMITED",
            http_status=429
        ))

        with patch("app.markets.crypto_poller.get_exchange_adapter", return_value=mock_adapter):
            # Pass 1: backoff starts at 1.0
            await supervisor.poll_exchange_once("binance")
            self.assertEqual(supervisor._backoff.get("binance"), 1.0)

            # Pass 2: doubles to 2.0
            await supervisor.poll_exchange_once("binance")
            self.assertEqual(supervisor._backoff.get("binance"), 2.0)

            # Pass 3: doubles to 4.0
            await supervisor.poll_exchange_once("binance")
            self.assertEqual(supervisor._backoff.get("binance"), 4.0)

            # Pass 4: doubles to 8.0
            await supervisor.poll_exchange_once("binance")
            self.assertEqual(supervisor._backoff.get("binance"), 8.0)

            # Repeated failures cap at MAX_BACKOFF_SECONDS (30.0)
            for _ in range(5):
                await supervisor.poll_exchange_once("binance")
            self.assertEqual(supervisor._backoff.get("binance"), MAX_BACKOFF_SECONDS)

            # Success resets backoff to 0.0
            mock_adapter.fetch_batch_prices = AsyncMock(return_value=BatchPriceResult(
                prices={"BTCUSDT": 68000.0},
                error_code="OK"
            ))
            await supervisor.poll_exchange_once("binance")
            self.assertEqual(supervisor._backoff.get("binance"), 0.0)

    async def test_02_retry_after_header_override(self):
        """Verify poller sets backoff directly from Retry-After header."""
        supervisor = CryptoPollerSupervisor()
        supervisor._client = MagicMock()

        mock_adapter = MagicMock()
        mock_adapter.fetch_batch_prices = AsyncMock(return_value=BatchPriceResult(
            prices={},
            error="Too Many Requests",
            error_code="RATE_LIMITED",
            http_status=429,
            retry_after=12.0
        ))

        with patch("app.markets.crypto_poller.get_exchange_adapter", return_value=mock_adapter):
            await supervisor.poll_exchange_once("kraken")
            self.assertEqual(supervisor._backoff.get("kraken"), 12.0)

    def test_03_singleton_poller_guard_prevents_duplicate_processes(self):
        """Verify Rule R9: only one poller supervisor can be leader per DATA_DIR."""
        s1 = CryptoPollerSupervisor()
        s2 = CryptoPollerSupervisor()

        # s1 acquires lock first -> leader
        self.assertTrue(s1._acquire_leader_lock())
        self.assertTrue(s1._is_leader)

        # s2 attempts lock on same DATA_DIR -> standby
        self.assertFalse(s2._acquire_leader_lock())
        self.assertFalse(s2._is_leader)

        # s1 releases lock
        s1._release_leader_lock()
        self.assertFalse(s1._is_leader)

        # s2 can now acquire lock -> becomes leader
        self.assertTrue(s2._acquire_leader_lock())
        self.assertTrue(s2._is_leader)
        s2._release_leader_lock()

    def test_04_latency_percentiles_calculation(self):
        """Verify p50 (median) and p95 calculations over rolling poll latency window."""
        # Empty case
        res_empty = get_crypto_latency_percentiles()
        self.assertEqual(res_empty["p50_ms"], 0.0)
        self.assertEqual(res_empty["p95_ms"], 0.0)
        self.assertEqual(res_empty["samples"], 0)

        # Feed 100 samples from 1ms to 100ms
        for i in range(1, 101):
            record_poll_latency(float(i))

        res = get_crypto_latency_percentiles()
        self.assertEqual(res["samples"], 100)
        # Median of 1..100 at index 50 is 51.0
        self.assertAlmostEqual(res["p50_ms"], 51.0, delta=1.0)
        # p95 at index 95 is 96.0
        self.assertAlmostEqual(res["p95_ms"], 96.0, delta=1.0)


if __name__ == "__main__":
    unittest.main()
