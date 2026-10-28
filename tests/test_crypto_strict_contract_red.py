#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — Phase 3 Contract Enforcement Tests.
Verifies Rule R1:
1. Alert = (exchange_id, base_currency, market_symbol).
2. Price comes strictly and exclusively from the specified exchange.
3. No fallback to Binance, no fallback to another exchange, no aggregators.
4. Unknown exchange returns None/UNKNOWN_EXCHANGE.
5. In Phase 3, these tests are active assertions (GREEN) with CRYPTO_STRICT_V2=true.
6. When CRYPTO_STRICT_V2=false, exact legacy fallback is preserved for backward compatibility.
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


class TestCryptoStrictContractRed(unittest.IsolatedAsyncioTestCase):
    """
    Contract acceptance tests enforcing Rule R1 (Exchange Isolation).
    In Phase 3, these tests are GREEN under CRYPTO_STRICT_V2=True.
    """

    def setUp(self):
        self.mock_client = AsyncMock()
        # Enable strict mode for tests
        os.environ['CRYPTO_STRICT_V2'] = 'true'
        config.CRYPTO_STRICT_V2 = True

    def tearDown(self):
        # Reset flag
        os.environ['CRYPTO_STRICT_V2'] = 'false'
        config.CRYPTO_STRICT_V2 = False

    async def test_01_unknown_exchange_must_not_fallback_to_binance(self):
        """
        [Rule R1] An unknown or unregistered exchange ID must NEVER default to Binance.
        Expected: Return None (UNKNOWN_EXCHANGE), zero queries to Binance.
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

    async def test_02_okx_alert_must_not_evaluate_with_binance_price(self):
        """
        [Rule R1] An alert set on OKX must query ONLY OKX endpoint; never query Binance.
        """
        queried_sources = []

        async def mock_try_fetch(source_name: str, url: str, extract_func) -> Optional[float]:
            queried_sources.append(source_name)
            if 'OKX' in source_name:
                return 65120.0
            if 'Binance' in source_name:
                return 65000.0
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

        self.assertEqual(price, 65120.0, "OKX must return OKX price")
        self.assertTrue(any('okx' in s.lower() for s in queried_sources), "OKX Spot API must be queried")
        self.assertNotIn('Binance (binance) Spot API', queried_sources, "Binance must NEVER be queried for OKX")

    async def test_03_lbank_alert_must_not_fallback_to_other_exchanges(self):
        """
        [Rule R1] An alert set on LBank must query ONLY LBank; never query Binance or MEXC.
        """
        queried_sources = []

        async def mock_try_fetch(source_name: str, url: str, extract_func) -> Optional[float]:
            queried_sources.append(source_name)
            if 'lbank' in source_name.lower():
                return 65200.0
            if 'binance' in source_name.lower():
                return 65000.0
            if 'mexc' in source_name.lower():
                return 65050.0
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

        self.assertEqual(price, 65200.0, "LBank must return LBank price")
        self.assertTrue(any('lbank' in s.lower() for s in queried_sources), "LBank Spot API must be queried")
        self.assertNotIn('Binance (binance) Spot API', queried_sources, "Binance must NEVER be queried for LBank")
        self.assertNotIn('MEXC (mexc) Spot API', queried_sources, "MEXC must NEVER be queried for LBank")

    async def test_04_coin_missing_on_selected_exchange_must_not_steal_from_another(self):
        """
        [Rule R1] If a coin is missing on KuCoin (returns None), fetch_crypto must NOT
        fall through to MEXC, Gate.io, or Binance. Must return None immediately.
        """
        queried_sources = []

        async def mock_try_fetch(source_name: str, url: str, extract_func) -> Optional[float]:
            queried_sources.append(source_name)
            if 'kucoin' in source_name.lower():
                return None
            if 'binance' in source_name.lower():
                return 0.05
            if 'mexc' in source_name.lower():
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
            ['KuCoin (kucoin) Spot API'],
            f"R1 VIOLATION: Additional exchanges were queried after KuCoin: {queried_sources}"
        )

    async def test_05_legacy_fallback_preserved_when_flag_is_off(self):
        """
        [Backward Compatibility R6] When CRYPTO_STRICT_V2=False, the exact legacy
        behavior (prioritization and fallback) is 100% preserved.
        """
        os.environ['CRYPTO_STRICT_V2'] = 'false'
        config.CRYPTO_STRICT_V2 = False

        queried_sources = []

        async def mock_try_fetch(source_name: str, url: str, extract_func) -> Optional[float]:
            queried_sources.append(source_name)
            # KuCoin fails, but Binance returns
            if 'KuCoin' in source_name:
                return None
            if 'Binance' in source_name:
                return 50000.0
            return None

        traces = []
        price = await fetch_crypto(
            client=self.mock_client,
            exchange='kucoin',
            symbol='BTCUSDT',
            _try_fetch=mock_try_fetch,
            traces=traces,
            collect_all_traces=False
        )

        # In legacy mode (flag=False), KuCoin falls back to Binance!
        self.assertEqual(price, 50000.0)
        self.assertIn('Binance Spot API', queried_sources)


if __name__ == '__main__':
    unittest.main()
