# -*- coding: utf-8 -*-
"""
Phase S3 Acceptance Tests:
Validates wiring of on-demand snapshot refresh into crypto_strict V2 price path.
1. snapshot miss + adapter OK -> price returned, status OK.
2. snapshot miss + adapter error -> price None, status is the error status.
3. fresh OK snapshot -> adapter never called.
4. OKX native symbol and Gate.io native symbol still resolve with the snapshot lookup
   (BTC-USDT and BTC_USDT variants).
"""

import sys
import time
import asyncio
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

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
    update_exchange_snapshot,
)
from app.markets.crypto_strict import fetch_crypto_strict


class FakeAdapter:
    def __init__(self, prices=None, error_code="OK", error=None, sleep_seconds=0.0):
        self.prices = prices or {}
        self.error_code = error_code
        self.error = error
        self.sleep_seconds = sleep_seconds
        self.call_count = 0

    async def fetch_batch_prices(self, client=None):
        self.call_count += 1
        if self.sleep_seconds > 0:
            await asyncio.sleep(self.sleep_seconds)
        return BatchPriceResult(
            prices=dict(self.prices),
            as_of=int(time.time()),
            source="fake",
            error=self.error,
            error_code=self.error_code,
            http_status=200 if self.error_code == "OK" else 500,
        )


class TestCryptoV2OnDemandWiring(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        clear_snapshot_store()
        self.mock_client = AsyncMock()
        self._orig_v2 = getattr(config, "CRYPTO_ENGINE_V2", False)
        self._orig_ondemand = getattr(config, "CRYPTO_ONDEMAND_ENABLED", True)
        config.CRYPTO_ENGINE_V2 = True
        config.CRYPTO_ONDEMAND_ENABLED = True

    def tearDown(self):
        clear_snapshot_store()
        config.CRYPTO_ENGINE_V2 = self._orig_v2
        config.CRYPTO_ONDEMAND_ENABLED = self._orig_ondemand

    async def test_01_snapshot_miss_adapter_ok(self):
        """1. Snapshot miss + adapter OK -> price returned, status OK."""
        fake = FakeAdapter(prices={"BTCUSDT": 75123.50})
        with patch("app.markets.crypto_ondemand.get_exchange_adapter", return_value=fake):
            traces = []
            res = await fetch_crypto_strict(
                client=self.mock_client,
                exchange="binance",
                symbol="BTC",
                _try_fetch=None,
                traces=traces,
            )
            self.assertEqual(res.status, "OK")
            self.assertEqual(res.price, 75123.50)
            self.assertEqual(fake.call_count, 1)
            self.assertTrue(any(t.get("url") == "snapshot:binance" for t in traces))

    async def test_02_snapshot_miss_adapter_error(self):
        """2. Snapshot miss + adapter error -> price None, status is the error status."""
        fake = FakeAdapter(error_code="PROVIDER_BLOCKED", error="Blocked by Cloudflare")
        with patch("app.markets.crypto_ondemand.get_exchange_adapter", return_value=fake):
            traces = []
            res = await fetch_crypto_strict(
                client=self.mock_client,
                exchange="binance",
                symbol="BTC",
                _try_fetch=None,
                traces=traces,
            )
            self.assertIsNone(res.price)
            self.assertEqual(res.status, "PROVIDER_BLOCKED")
            self.assertEqual(fake.call_count, 1)

    async def test_03_fresh_ok_snapshot_skips_adapter(self):
        """3. Fresh OK snapshot -> adapter never called."""
        fake = FakeAdapter(prices={"BTCUSDT": 99999.0})
        update_exchange_snapshot("binance", {"BTCUSDT": 74500.0}, status="OK")
        with patch("app.markets.crypto_ondemand.get_exchange_adapter", return_value=fake):
            traces = []
            res = await fetch_crypto_strict(
                client=self.mock_client,
                exchange="binance",
                symbol="BTC",
                _try_fetch=None,
                traces=traces,
            )
            self.assertEqual(res.status, "OK")
            self.assertEqual(res.price, 74500.0)
            self.assertEqual(fake.call_count, 0)

    async def test_04_native_symbol_variants_okx_and_gateio(self):
        """4. OKX native symbol (BTC-USDT) and Gate.io native symbol (BTC_USDT) resolve with snapshot lookup."""
        # OKX uses hyphenated pair format: BTC-USDT
        fake_okx = FakeAdapter(prices={"BTC-USDT": 76100.0})
        with patch("app.markets.crypto_ondemand.get_exchange_adapter", return_value=fake_okx):
            traces_okx = []
            res_okx = await fetch_crypto_strict(
                client=self.mock_client,
                exchange="okx",
                symbol="BTC",
                _try_fetch=None,
                traces=traces_okx,
            )
            self.assertEqual(res_okx.status, "OK")
            self.assertEqual(res_okx.price, 76100.0)

        # Gate.io uses underscore pair format: BTC_USDT
        fake_gateio = FakeAdapter(prices={"BTC_USDT": 76200.0})
        with patch("app.markets.crypto_ondemand.get_exchange_adapter", return_value=fake_gateio):
            traces_gateio = []
            res_gateio = await fetch_crypto_strict(
                client=self.mock_client,
                exchange="gateio",
                symbol="BTC",
                _try_fetch=None,
                traces=traces_gateio,
            )
            self.assertEqual(res_gateio.status, "OK")
            self.assertEqual(res_gateio.price, 76200.0)


if __name__ == "__main__":
    unittest.main()
