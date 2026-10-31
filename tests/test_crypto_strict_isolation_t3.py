#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — Acceptance Test T3: Strict Exchange Isolation Test (Phase 1 Fix).
For every registered crypto exchange:
1. Part A (Distinct Prices): All exchanges are mocked with different prices.
   Querying exchange X MUST return exchange X's exact price and query ONLY exchange X.
2. Part B (Selected Exchange Fails): Exchange X fails/returns None while all other exchanges are healthy.
   Querying exchange X MUST return None (NO_PRICE) and query ZERO other exchange APIs.
Zero cross-exchange fallback or leakage under all circumstances.
Rule R11: All source labels must contain the exchange ID in parentheses.
Owner Decision E1.2: CoinEx is deleted from registry and returns UNKNOWN_EXCHANGE.
"""

import unittest
import sys
import os
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any, Optional

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
from app.markets.crypto import fetch_crypto
from app.markets.crypto_registry import get_crypto_exchange, list_crypto_exchanges


# Distinct mock prices for every exchange to detect any cross-exchange leak
# Labels strictly adhere to Rule R11 (containing exchange ID)
EXCHANGE_DISTINCT_PRICES = {
    'binance': (60001.0, 'Binance (binance) Spot API'),
    'mexc': (60002.0, 'MEXC (mexc) Spot API'),
    'kucoin': (60003.0, 'KuCoin (kucoin) Spot API'),
    'gateio': (60004.0, 'Gate.io (gateio) Spot API'),
    'lbank': (60005.0, 'LBank (lbank) Spot API'),
    'okx': (60006.0, 'OKX (okx) Spot API'),
    'bybit': (60007.0, 'Bybit (bybit) Spot API'),
    'bitget': (60008.0, 'Bitget (bitget) Spot API'),
    'kraken': (60009.0, 'Kraken (kraken) Spot API'),
}


class TestCryptoStrictIsolationT3(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_client = AsyncMock()
        self._orig_engine_v2 = getattr(config, "CRYPTO_ENGINE_V2", False)
        config.CRYPTO_ENGINE_V2 = False
        os.environ['CRYPTO_STRICT_V2'] = 'true'
        config.CRYPTO_STRICT_V2 = True

    def tearDown(self):
        config.CRYPTO_ENGINE_V2 = self._orig_engine_v2
        os.environ['CRYPTO_STRICT_V2'] = 'false'
        config.CRYPTO_STRICT_V2 = False

    async def _run_isolation_scenario(self, target_ex: str, fail_target: bool = False):
        expected_price, target_source_name = EXCHANGE_DISTINCT_PRICES[target_ex]
        queried_sources = []

        async def mock_try_fetch(source_name: str, url: str, extract_func) -> Optional[float]:
            queried_sources.append(source_name)
            if fail_target and source_name == target_source_name:
                return None
            for ex, (price, s_name) in EXCHANGE_DISTINCT_PRICES.items():
                if source_name == s_name:
                    return price
            return None

        traces = []
        result_price = await fetch_crypto(
            client=self.mock_client,
            exchange=target_ex,
            symbol='BTCUSDT',
            _try_fetch=mock_try_fetch,
            traces=traces,
            collect_all_traces=False
        )

        if not fail_target:
            # Part A: Must return target's price and ONLY query target
            self.assertEqual(
                result_price,
                expected_price,
                f"Isolation Failure: {target_ex} returned {result_price} instead of {expected_price}"
            )
            self.assertEqual(
                queried_sources,
                [target_source_name],
                f"Isolation Failure: {target_ex} queried unauthorized endpoints: {queried_sources}"
            )
        else:
            # Part B: Must return None and NEVER fall back to another exchange
            self.assertIsNone(
                result_price,
                f"Isolation Failure: {target_ex} failed but returned {result_price} instead of None"
            )
            self.assertEqual(
                queried_sources,
                [target_source_name],
                f"Isolation Failure: Failed {target_ex} leaked requests to other exchanges: {queried_sources}"
            )

    async def test_01_binance_isolation_success_and_failure(self):
        await self._run_isolation_scenario('binance', fail_target=False)
        await self._run_isolation_scenario('binance', fail_target=True)

    async def test_02_mexc_isolation_success_and_failure(self):
        await self._run_isolation_scenario('mexc', fail_target=False)
        await self._run_isolation_scenario('mexc', fail_target=True)

    async def test_03_kucoin_isolation_success_and_failure(self):
        await self._run_isolation_scenario('kucoin', fail_target=False)
        await self._run_isolation_scenario('kucoin', fail_target=True)

    async def test_04_gateio_isolation_success_and_failure(self):
        await self._run_isolation_scenario('gateio', fail_target=False)
        await self._run_isolation_scenario('gateio', fail_target=True)

    async def test_05_lbank_isolation_success_and_failure(self):
        await self._run_isolation_scenario('lbank', fail_target=False)
        await self._run_isolation_scenario('lbank', fail_target=True)

    async def test_06_okx_isolation_success_and_failure(self):
        await self._run_isolation_scenario('okx', fail_target=False)
        await self._run_isolation_scenario('okx', fail_target=True)

    async def test_07_bybit_isolation_success_and_failure(self):
        await self._run_isolation_scenario('bybit', fail_target=False)
        await self._run_isolation_scenario('bybit', fail_target=True)

    async def test_08_bitget_isolation_success_and_failure(self):
        await self._run_isolation_scenario('bitget', fail_target=False)
        await self._run_isolation_scenario('bitget', fail_target=True)

    async def test_09_kraken_isolation_success_and_failure(self):
        await self._run_isolation_scenario('kraken', fail_target=False)
        await self._run_isolation_scenario('kraken', fail_target=True)

    async def test_10_coinex_rejected_as_unknown_exchange(self):
        """Owner Decision E1.2: CoinEx is deleted from registry and rejected immediately."""
        traces = []
        queried_sources = []

        async def mock_try_fetch(source_name: str, url: str, extract_func):
            queried_sources.append(source_name)
            return 60010.0

        result_price = await fetch_crypto(
            client=self.mock_client,
            exchange='coinex',
            symbol='BTCUSDT',
            _try_fetch=mock_try_fetch,
            traces=traces,
            collect_all_traces=False
        )
        self.assertIsNone(result_price)
        self.assertEqual(queried_sources, [])
        self.assertTrue(any('UNKNOWN_EXCHANGE' in str(t.get('error', '')) for t in traces))


if __name__ == '__main__':
    unittest.main()
