# -*- coding: utf-8 -*-
"""
Phase S2 Acceptance Tests:
Validates app/markets/crypto_ondemand.py behavior:
1. miss_then_fetch
2. single_flight
3. negative_cache
4. exception_and_timeout
5. unknown_exchange
6. flag_off
7. fresh_snapshot_skips
8. single_flight_cleanup
"""

import sys
import time
import asyncio
import unittest
from unittest.mock import patch, MagicMock

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

import app.config as config
from app.markets.adapters.base import BatchPriceResult
from app.markets.crypto_snapshot import (
    clear_snapshot_store,
    get_snapshot_price,
    update_exchange_snapshot,
)
from app.markets.crypto_ondemand import ensure_fresh_snapshot


class FakeAdapter:
    def __init__(self, prices=None, error_code="OK", error=None, sleep_seconds=0.0, raise_exception=None):
        self.prices = prices or {}
        self.error_code = error_code
        self.error = error
        self.sleep_seconds = sleep_seconds
        self.raise_exception = raise_exception
        self.call_count = 0

    async def fetch_batch_prices(self, client=None):
        self.call_count += 1
        if self.sleep_seconds > 0:
            await asyncio.sleep(self.sleep_seconds)
        if self.raise_exception:
            raise self.raise_exception
        return BatchPriceResult(
            prices=dict(self.prices),
            as_of=int(time.time()),
            source="fake",
            error=self.error,
            error_code=self.error_code,
            http_status=200 if self.error_code == "OK" else 500,
        )


class TestCryptoOnDemand(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        clear_snapshot_store()
        self._orig_enabled = getattr(config, "CRYPTO_ONDEMAND_ENABLED", True)
        self._orig_timeout = getattr(config, "CRYPTO_ONDEMAND_TIMEOUT_SECONDS", 6.0)
        self._orig_neg_ttl = getattr(config, "CRYPTO_ONDEMAND_NEG_TTL_SECONDS", 5.0)
        config.CRYPTO_ONDEMAND_ENABLED = True
        config.CRYPTO_ONDEMAND_TIMEOUT_SECONDS = 6.0
        config.CRYPTO_ONDEMAND_NEG_TTL_SECONDS = 5.0

    def tearDown(self):
        clear_snapshot_store()
        config.CRYPTO_ONDEMAND_ENABLED = self._orig_enabled
        config.CRYPTO_ONDEMAND_TIMEOUT_SECONDS = self._orig_timeout
        config.CRYPTO_ONDEMAND_NEG_TTL_SECONDS = self._orig_neg_ttl

    async def test_01_miss_then_fetch(self):
        """1. Empty store, fake returns 3 prices -> status OK and price returned. Adapter called once."""
        fake = FakeAdapter(prices={"BTCUSDT": 75000.0, "ETHUSDT": 3500.0, "SOLUSDT": 180.0})
        with patch("app.markets.crypto_ondemand.get_exchange_adapter", return_value=fake):
            status = await ensure_fresh_snapshot("binance")
            self.assertEqual(status, "OK")
            self.assertEqual(fake.call_count, 1)

            price, as_of, p_status, latency = get_snapshot_price("binance", "BTCUSDT")
            self.assertEqual(price, 75000.0)
            self.assertEqual(p_status, "OK")

    async def test_02_single_flight(self):
        """2. 20 concurrent ensure_fresh_snapshot calls -> adapter called once, all return OK."""
        fake = FakeAdapter(prices={"BTCUSDT": 75000.0}, sleep_seconds=0.05)
        with patch("app.markets.crypto_ondemand.get_exchange_adapter", return_value=fake):
            results = await asyncio.gather(*[ensure_fresh_snapshot("binance") for _ in range(20)])
            self.assertEqual(len(results), 20)
            for r in results:
                self.assertEqual(r, "OK")
            self.assertEqual(fake.call_count, 1)

    async def test_03_negative_cache(self):
        """3. Fake returns error -> status is error. Immediate second call skipped. Retried after NEG_TTL."""
        fake = FakeAdapter(error_code="PROVIDER_BLOCKED", error="Blocked by Cloudflare")
        config.CRYPTO_ONDEMAND_NEG_TTL_SECONDS = 0.05
        with patch("app.markets.crypto_ondemand.get_exchange_adapter", return_value=fake):
            status1 = await ensure_fresh_snapshot("binance")
            self.assertEqual(status1, "PROVIDER_BLOCKED")
            self.assertEqual(fake.call_count, 1)

            # Immediate second call within NEG_TTL -> negative cache skips
            status2 = await ensure_fresh_snapshot("binance")
            self.assertEqual(status2, "PROVIDER_BLOCKED")
            self.assertEqual(fake.call_count, 1)

            # Wait for NEG_TTL to pass
            await asyncio.sleep(0.08)
            status3 = await ensure_fresh_snapshot("binance")
            self.assertEqual(fake.call_count, 2)

    async def test_04_exception_and_timeout(self):
        """4. Fake raises or times out -> no exception escapes, status is PROVIDER_ERROR or TIMEOUT."""
        # Exception case
        fake_err = FakeAdapter(raise_exception=RuntimeError("Connection reset"))
        with patch("app.markets.crypto_ondemand.get_exchange_adapter", return_value=fake_err):
            status_err = await ensure_fresh_snapshot("binance")
            self.assertEqual(status_err, "PROVIDER_ERROR")

        # Timeout case
        clear_snapshot_store()
        config.CRYPTO_ONDEMAND_TIMEOUT_SECONDS = 0.05
        fake_timeout = FakeAdapter(sleep_seconds=0.2)
        with patch("app.markets.crypto_ondemand.get_exchange_adapter", return_value=fake_timeout):
            status_timeout = await ensure_fresh_snapshot("mexc")
            self.assertEqual(status_timeout, "TIMEOUT")

    async def test_05_unknown_exchange(self):
        """5. Unsupported id -> UNKNOWN_EXCHANGE, adapter never called."""
        fake = FakeAdapter(prices={"BTCUSDT": 75000.0})
        with patch("app.markets.crypto_ondemand.get_exchange_adapter", return_value=fake):
            status = await ensure_fresh_snapshot("nonexistent_dex_xyz")
            self.assertEqual(status, "UNKNOWN_EXCHANGE")
            self.assertEqual(fake.call_count, 0)

    async def test_06_flag_off(self):
        """6. CRYPTO_ONDEMAND_ENABLED=false -> adapter never called."""
        fake = FakeAdapter(prices={"BTCUSDT": 75000.0})
        config.CRYPTO_ONDEMAND_ENABLED = False
        with patch("app.markets.crypto_ondemand.get_exchange_adapter", return_value=fake):
            status = await ensure_fresh_snapshot("binance")
            self.assertEqual(fake.call_count, 0)

    async def test_07_fresh_snapshot_skips(self):
        """7. Pre-fill a fresh OK snapshot -> adapter never called."""
        fake = FakeAdapter(prices={"BTCUSDT": 75000.0})
        update_exchange_snapshot("binance", {"BTCUSDT": 74000.0}, status="OK")
        with patch("app.markets.crypto_ondemand.get_exchange_adapter", return_value=fake):
            status = await ensure_fresh_snapshot("binance")
            self.assertEqual(status, "OK")
            self.assertEqual(fake.call_count, 0)

    async def test_08_single_flight_cleanup(self):
        """8. After a failing fetch, a later call can fetch again (in-flight entry does not leak)."""
        fake = FakeAdapter(raise_exception=RuntimeError("Transient failure"))
        config.CRYPTO_ONDEMAND_NEG_TTL_SECONDS = 0.0
        with patch("app.markets.crypto_ondemand.get_exchange_adapter", return_value=fake):
            status1 = await ensure_fresh_snapshot("binance")
            self.assertEqual(status1, "PROVIDER_ERROR")
            self.assertEqual(fake.call_count, 1)

            # Recover adapter
            fake.raise_exception = None
            fake.prices = {"BTCUSDT": 76000.0}
            fake.error_code = "OK"

            status2 = await ensure_fresh_snapshot("binance")
            self.assertEqual(status2, "OK")
            self.assertEqual(fake.call_count, 2)


if __name__ == "__main__":
    unittest.main()
