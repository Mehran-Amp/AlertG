#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — Acceptance Lint Tests for Adapter Specifications (Phase 2).
Verifies:
1. All exchange adapters expose a valid AdapterSpecification dataclass.
2. validate_adapter_specification passes for all registered adapters.
3. Every specification adheres to strictly HTTPS endpoints.
4. Rate limits are positive numbers.
5. All 9 active exchanges (Binance, MEXC, KuCoin, Gate.io, LBank, OKX, Kraken, Bybit, Bitget)
   have complete and compliant specifications.
"""

import unittest
import sys
from unittest.mock import MagicMock

try:
    import httpx
except ImportError:
    httpx = MagicMock()
    sys.modules['httpx'] = httpx

from app.markets.adapters.base import (
    AdapterSpecification,
    validate_adapter_specification,
)
from app.markets.adapters import (
    BinanceAdapter,
    MEXCAdapter,
    KuCoinAdapter,
    GateioAdapter,
    LBankAdapter,
    OKXAdapter,
    KrakenAdapter,
    BybitAdapter,
    BitgetAdapter,
)


class TestCryptoAdapterSpecificationLint(unittest.TestCase):
    """Lint suite ensuring all exchange adapters satisfy the specification contract."""

    ADAPTER_CLASSES = [
        BinanceAdapter,
        MEXCAdapter,
        KuCoinAdapter,
        GateioAdapter,
        LBankAdapter,
        OKXAdapter,
        KrakenAdapter,
        BybitAdapter,
        BitgetAdapter,
    ]

    def test_01_all_registered_adapters_have_valid_specification(self):
        """Verifies each adapter class defines a valid AdapterSpecification."""
        self.assertEqual(len(self.ADAPTER_CLASSES), 9, "Must have exactly 9 adapter classes registered")
        for cls in self.ADAPTER_CLASSES:
            spec = getattr(cls, 'specification', None)
            self.assertIsNotNone(spec, f"{cls.__name__} missing 'specification' attribute")
            self.assertIsInstance(
                spec,
                AdapterSpecification,
                f"{cls.__name__}.specification is not an AdapterSpecification instance"
            )
            # Must pass validator
            is_valid, reason = validate_adapter_specification(spec)
            self.assertTrue(is_valid, f"Specification validation failed for {cls.__name__}: {reason}")

    def test_02_specification_matches_class_attributes(self):
        """Verifies specification metadata matches adapter class-level attributes."""
        for cls in self.ADAPTER_CLASSES:
            spec = cls.specification
            self.assertEqual(spec.exchange_id, cls.exchange_id, f"{cls.__name__} exchange_id mismatch")
            self.assertEqual(spec.provider_key, cls.provider_key, f"{cls.__name__} provider_key mismatch")
            self.assertEqual(spec.market_list_url, cls.market_list_url, f"{cls.__name__} market_list_url mismatch")
            self.assertEqual(spec.batch_price_url, cls.batch_price_url, f"{cls.__name__} batch_price_url mismatch")
            self.assertEqual(spec.single_price_url, cls.single_price_url, f"{cls.__name__} single_price_url mismatch")

    def test_03_all_endpoints_are_strictly_https(self):
        """Rule R1: All endpoint URLs in specifications must strictly use HTTPS."""
        for cls in self.ADAPTER_CLASSES:
            spec = cls.specification
            self.assertTrue(
                spec.market_list_url.startswith("https://"),
                f"{cls.__name__} market_list_url must be HTTPS: {spec.market_list_url}"
            )
            self.assertTrue(
                spec.batch_price_url.startswith("https://"),
                f"{cls.__name__} batch_price_url must be HTTPS: {spec.batch_price_url}"
            )
            self.assertTrue(
                spec.single_price_url.startswith("https://"),
                f"{cls.__name__} single_price_url must be HTTPS: {spec.single_price_url}"
            )

    def test_04_rate_limits_positive_and_realistic(self):
        """Ensures rate limits are positive and within realistic exchange boundaries."""
        for cls in self.ADAPTER_CLASSES:
            spec = cls.specification
            self.assertGreater(spec.rate_limit_rps, 0.0, f"{cls.__name__} RPS must be > 0")
            self.assertLessEqual(spec.rate_limit_rps, 100.0, f"{cls.__name__} RPS exceeds sane limit")

    def test_05_bybit_and_bitget_specifications_present(self):
        """Specific check for Wave 1 newly completed adapters (Bybit & Bitget)."""
        bybit_spec = BybitAdapter.specification
        self.assertEqual(bybit_spec.exchange_id, "bybit")
        self.assertEqual(bybit_spec.status, "active")
        self.assertIn("v5/market/instruments-info", bybit_spec.market_list_url)
        self.assertIn("v5/market/tickers", bybit_spec.batch_price_url)

        bitget_spec = BitgetAdapter.specification
        self.assertEqual(bitget_spec.exchange_id, "bitget")
        self.assertEqual(bitget_spec.status, "active")
        self.assertIn("v2/spot/public/symbols", bitget_spec.market_list_url)
        self.assertIn("v2/spot/market/tickers", bitget_spec.batch_price_url)


if __name__ == '__main__':
    unittest.main()
