#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — Acceptance Test T3: Strict Exchange Isolation Test.
For every registered crypto exchange:
1. Part A (Distinct Prices): All exchanges are mocked with different prices.
   Querying exchange X MUST return exchange X's exact price and query ONLY exchange X.
2. Part B (Selected Exchange Fails): Exchange X fails/returns None while all other exchanges are healthy.
   Querying exchange X MUST return None (NO_PRICE) and query ZERO other exchange APIs.
Zero cross-exchange fallback or leakage under all circumstances.
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
from app.markets.crypto_registry import list_crypto_exchanges


# Distinct mock prices for every exchange to detect any cross-exchange leak
EXCHANGE_DISTINCT_PRICES = {
    'binance': (60001.0, 'Binance Spot API'),
    'mexc': (60002.0, 'MEXC Spot API'),
    'kucoin': (60003.0, 'KuCoin Spot API'),
    'gateio': (60004.0, 'Gate.io Spot API'),
    'lbank': (60005.0, 'LBank Spot API'),
    'okx': (60006.0, 'OKX Spot API'),
    'bybit': (60007.0, 'Bybit Spot API'),
    'bitget': (60008.0, 'Bitget Spot API'),
    'kraken': (60009.0, 'Kraken Spot API'),
    'coinex': (60010.0, 'CoinEx Spot API'),
}


class TestCryptoStrictIsolationT3(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_client = AsyncMock()
        os.environ['CRYPTO_STRICT_V2'] = 'true'
        config.CRYPTO_STRICT_V2 = True

    def tearDown(self):
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
                f"Isolation Failure: {target_ex} queried extra sources: {queried_sources}"
            )
        else:
            # Part B: Must return None and ZERO other exchange calls
            self.assertIsNone(
                result_price,
                f"Leakage Failure: Failing {target_ex} returned price {result_price} from another exchange!"
            )
            self.assertEqual(
                queried_sources,
                [target_source_name],
                f"Leakage Failure: Failing {target_ex} triggered queries to other exchanges: {queried_sources}"
            )

    # 1. Binance Isolation
    async def test_01_binance_isolation_success_and_failure(self):
        await self._run_isolation_scenario('binance', fail_target=False)
        await self._run_isolation_scenario('binance', fail_target=True)

    # 2. MEXC Isolation
    async def test_02_mexc_isolation_success_and_failure(self):
        await self._run_isolation_scenario('mexc', fail_target=False)
        await self._run_isolation_scenario('mexc', fail_target=True)

    # 3. KuCoin Isolation
    async def test_03_kucoin_isolation_success_and_failure(self):
        await self._run_isolation_scenario('kucoin', fail_target=False)
        await self._run_isolation_scenario('kucoin', fail_target=True)

    # 4. Gate.io Isolation
    async def test_04_gateio_isolation_success_and_failure(self):
        await self._run_isolation_scenario('gateio', fail_target=False)
        await self._run_isolation_scenario('gateio', fail_target=True)

    # 5. LBank Isolation (CoinEx replacement)
    async def test_05_lbank_isolation_success_and_failure(self):
        await self._run_isolation_scenario('lbank', fail_target=False)
        await self._run_isolation_scenario('lbank', fail_target=True)

    # 6. OKX Isolation
    async def test_06_okx_isolation_success_and_failure(self):
        await self._run_isolation_scenario('okx', fail_target=False)
        await self._run_isolation_scenario('okx', fail_target=True)

    # 7. Bybit Isolation
    async def test_07_bybit_isolation_success_and_failure(self):
        await self._run_isolation_scenario('bybit', fail_target=False)
        await self._run_isolation_scenario('bybit', fail_target=True)

    # 8. Bitget Isolation
    async def test_08_bitget_isolation_success_and_failure(self):
        await self._run_isolation_scenario('bitget', fail_target=False)
        await self._run_isolation_scenario('bitget', fail_target=True)

    # 9. Kraken Isolation
    async def test_09_kraken_isolation_success_and_failure(self):
        await self._run_isolation_scenario('kraken', fail_target=False)
        await self._run_isolation_scenario('kraken', fail_target=True)

    # 10. CoinEx Isolation
    async def test_10_coinex_isolation_success_and_failure(self):
        await self._run_isolation_scenario('coinex', fail_target=False)
        await self._run_isolation_scenario('coinex', fail_target=True)


if __name__ == '__main__':
    unittest.main()
