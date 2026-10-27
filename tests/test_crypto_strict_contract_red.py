#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — Phase 1 Executable Red Tests (Contract Enforcement).
These tests verify Rule R1:
1. Alert = (exchange_id, base_currency, market_symbol).
2. Price comes strictly and exclusively from the specified exchange.
3. No fallback to Binance, no fallback to another exchange, no aggregators.
4. Unknown exchange must return None/UNKNOWN_EXCHANGE, never default to Binance.

Status: These tests are marked with @unittest.expectedFailure against the current
v1 codebase (app/markets/crypto.py) because current code falls back to Binance.
In Phase 3 (Strict Price Core behind CRYPTO_STRICT_V2), these tests will turn GREEN.
Zero product code changes in this phase.
"""

import unittest
import sys
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

from app.markets.crypto import fetch_crypto


class TestCryptoStrictContractRed(unittest.IsolatedAsyncioTestCase):
    """
    Contract acceptance tests enforcing Rule R1 (Exchange Isolation).
    Currently expected to FAIL against legacy fetch_crypto implementation.
    """

    def setUp(self):
        self.mock_client = AsyncMock()

    @unittest.expectedFailure
    async def test_01_unknown_exchange_must_not_fallback_to_binance(self):
        """
        [Rule R1] An unknown or unregistered exchange ID must NEVER default to Binance.
        Current Bug: For any unknown exchange, fetch_crypto defaults to Binance spot price.
        Expected: Return None (UNKNOWN_EXCHANGE).
        """
        queried_sources = []

        async def mock_try_fetch(source_name: str, url: str, extract_func) -> Optional[float]:
            queried_sources.append(source_name)
            if 'Binance' in source_name:
                return 65000.0
            return None

        traces = []
        price = await fetch_crypto(
            client=self.mock_client,
            exchange='fake_broker_99',
            symbol='BTCUSDT',
            _try_fetch=mock_try_fetch,
            traces=traces,
            collect_all_traces=False
        )

        # Under Rule R1, an unknown exchange MUST return None, NOT Binance's 65,000!
        self.assertIsNone(
            price,
            f"R1 VIOLATION: Unknown exchange returned price={price} from {queried_sources}"
        )
        self.assertNotIn(
            'Binance Spot API',
            queried_sources,
            "R1 VIOLATION: Binance API was queried for an unknown exchange alert!"
        )

    @unittest.expectedFailure
    async def test_02_okx_alert_must_not_evaluate_with_binance_price(self):
        """
        [Rule R1] An alert set on OKX must NEVER be evaluated with Binance's price.
        Current Bug: OKX is not registered in backend fetch_crypto, so it falls back to Binance.
        Expected: Return None until OKX adapter is implemented in Phase 4f; never query Binance.
        """
        queried_sources = []

        async def mock_try_fetch(source_name: str, url: str, extract_func) -> Optional[float]:
            queried_sources.append(source_name)
            if 'Binance' in source_name:
                return 65120.0
            return None

        traces = []
        price = await fetch_crypto(
            client=self.mock_client,
            exchange='okx',
            symbol='BTC-USDT',
            _try_fetch=mock_try_fetch,
            traces=traces,
            collect_all_traces=False
        )

        self.assertIsNone(
            price,
            f"R1 VIOLATION: OKX alert evaluated with Binance price={price}"
        )
        self.assertNotIn(
            'Binance Spot API',
            queried_sources,
            "R1 VIOLATION: Binance Spot API was queried for an OKX alert!"
        )

    @unittest.expectedFailure
    async def test_03_lbank_alert_must_not_fallback_to_other_exchanges(self):
        """
        [Rule R1] An alert set on LBank must NEVER query Binance, MEXC, or KuCoin.
        Current Bug: LBank is not in backend fetch_crypto, so it defaults to Binance/MEXC loop.
        Expected: Return None until LBank adapter is active in Phase 4e; zero cross-exchange calls.
        """
        queried_sources = []

        async def mock_try_fetch(source_name: str, url: str, extract_func) -> Optional[float]:
            queried_sources.append(source_name)
            if 'Binance' in source_name:
                return 65200.0
            if 'MEXC' in source_name:
                return 65250.0
            return None

        traces = []
        price = await fetch_crypto(
            client=self.mock_client,
            exchange='lbank',
            symbol='BTC_USDT',
            _try_fetch=mock_try_fetch,
            traces=traces,
            collect_all_traces=False
        )

        self.assertIsNone(
            price,
            f"R1 VIOLATION: LBank alert evaluated with price={price} from {queried_sources}"
        )
        self.assertNotIn(
            'Binance Spot API',
            queried_sources,
            "R1 VIOLATION: Binance API was queried for an LBank alert!"
        )

    @unittest.expectedFailure
    async def test_04_coin_missing_on_selected_exchange_must_not_steal_from_another(self):
        """
        [Rule R1] If a coin is missing on KuCoin (e.g. 404 or None), fetch_crypto must NOT
        fall through to MEXC, Gate.io, or Binance to steal their price.
        Current Bug: When KuCoin returns None, the loop continues and returns the next provider's price.
        Expected: KuCoin fails -> stop immediately, return None (NO_PRICE/SYMBOL_NOT_LISTED).
        """
        queried_sources = []

        async def mock_try_fetch(source_name: str, url: str, extract_func) -> Optional[float]:
            queried_sources.append(source_name)
            # KuCoin does NOT have this coin
            if 'KuCoin' in source_name:
                return None
            # But Binance and MEXC DO have it
            if 'Binance' in source_name:
                return 0.05
            if 'MEXC' in source_name:
                return 0.051
            return None

        traces = []
        price = await fetch_crypto(
            client=self.mock_client,
            exchange='kucoin',
            symbol='RARECOIN-USDT',
            _try_fetch=mock_try_fetch,
            traces=traces,
            collect_all_traces=False
        )

        # Under Rule R1: If KuCoin didn't return price, return None. NEVER steal from Binance!
        self.assertIsNone(
            price,
            f"R1 VIOLATION: Missing KuCoin coin was stolen from another exchange! price={price}, sources={queried_sources}"
        )
        self.assertEqual(
            queried_sources,
            ['KuCoin Spot API'],
            f"R1 VIOLATION: Additional exchanges were queried after KuCoin: {queried_sources}"
        )


if __name__ == '__main__':
    unittest.main()
