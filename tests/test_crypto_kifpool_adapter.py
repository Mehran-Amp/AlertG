# -*- coding: utf-8 -*-
"""
AlertG — Kifpool Adapter Acceptance Tests (Phase 10 / Iranian Crypto).
Tests Kifpool adapter:
1. Specification integrity (Rule R11, provider key, status == 'active').
2. Registration in crypto_registry and get_exchange_adapter factory.
3. Parsing of market symbols response (Dual-quote architecture: USDT & TMN).
4. Parsing of batch prices (both USDT and IRT->TMN prices).
5. Single price resolution.
"""
import unittest
import sys
from unittest.mock import MagicMock

try:
    import httpx
except ImportError:
    httpx = MagicMock()
    sys.modules['httpx'] = httpx

try:
    import apscheduler
except ImportError:
    apscheduler = MagicMock()
    sys.modules['apscheduler'] = apscheduler
    sys.modules['apscheduler.schedulers'] = apscheduler
    sys.modules['apscheduler.schedulers.asyncio'] = apscheduler

try:
    import pydantic
except ImportError:
    pydantic = MagicMock()
    class BaseModel: pass
    pydantic.BaseModel = BaseModel
    sys.modules['pydantic'] = pydantic

from app.markets.crypto_registry import get_crypto_exchange
from app.markets.crypto_catalog import get_exchange_adapter
from app.markets.adapters.kifpool import KifpoolAdapter


class TestKifpoolAdapter(unittest.TestCase):
    """Test suite for Kifpool exchange adapter."""

    def setUp(self):
        self.adapter = KifpoolAdapter()

    def test_01_registry_registration(self):
        """Kifpool must be registered in crypto_registry as active Iranian crypto exchange."""
        meta = get_crypto_exchange("kifpool")
        self.assertIsNotNone(meta, "Kifpool must be registered")
        self.assertEqual(meta.status, "active")
        self.assertEqual(meta.category, "iran_crypto")
        self.assertEqual(meta.provider_key, "crypto_kifpool")
        self.assertIn("kifpool", meta.source_label.lower())

    def test_02_factory_resolution(self):
        """get_exchange_adapter('kifpool') must instantiate KifpoolAdapter."""
        inst = get_exchange_adapter("kifpool")
        self.assertIsInstance(inst, KifpoolAdapter)

    def test_03_dual_quote_symbols_parsing(self):
        """Kifpool adapter must generate both USDT and TMN symbols for each coin."""
        raw_mock = [
            {
                "symbol": "BTC",
                "name": "Bitcoin",
                "faName": "بیت کوین",
                "price": 80000.0,
                "priceBuyIRT": 21400000000.0,
                "priceSellIRT": 21500000000.0,
            },
            {
                "symbol": "ETH",
                "name": "Ethereum",
                "faName": "اتریوم",
                "price": 2400.0,
                "priceBuyIRT": 640000000.0,
                "priceSellIRT": 650000000.0,
            },
            {
                "symbol": "USDT",
                "name": "Tether",
                "faName": "تتر",
                "price": 1.0,
                "priceBuyIRT": 267000.0,
                "priceSellIRT": 268000.0,
            }
        ]

        symbols = self.adapter.parse_symbols_response(raw_mock)
        # 3 coins * 2 quotes = 6 pairs
        self.assertEqual(len(symbols), 6)

        # Check BTC USDT & TMN
        btc_usdt = next((s for s in symbols if s.market_symbol == "BTCUSDT"), None)
        self.assertIsNotNone(btc_usdt)
        self.assertEqual(btc_usdt.quote, "USDT")
        self.assertEqual(btc_usdt.base, "BTC")

        btc_tmn = next((s for s in symbols if s.market_symbol == "BTCTMN"), None)
        self.assertIsNotNone(btc_tmn)
        self.assertEqual(btc_tmn.quote, "TMN")
        self.assertEqual(btc_tmn.base, "BTC")

    def test_04_batch_prices_parsing(self):
        """Kifpool adapter must extract exact USDT price and convert IRT (Rials) to Tomans (div 10)."""
        raw_mock = [
            {
                "symbol": "BTC",
                "price": 80306.41,
                "priceBuyIRT": 21400000000.0,
                "priceSellIRT": 21600000000.0,
            },
            {
                "symbol": "USDT",
                "price": 1.0,
                "priceBuyIRT": 267000.0,
                "priceSellIRT": 269000.0,
            }
        ]

        res = self.adapter.parse_batch_prices(raw_mock)
        self.assertEqual(res.error_code, "OK")
        self.assertIn("BTCUSDT", res.prices)
        self.assertAlmostEqual(res.prices["BTCUSDT"], 80306.41)

        # TMN calculation: (21,400,000,000 + 21,600,000,000) / 2 / 10 = 2,150,000,000 Tomans
        self.assertIn("BTCTMN", res.prices)
        self.assertAlmostEqual(res.prices["BTCTMN"], 2150000000.0)

        # USDT/TMN calculation: (267,000 + 269,000) / 2 / 10 = 26,800 Tomans
        self.assertIn("USDTTMN", res.prices)
        self.assertAlmostEqual(res.prices["USDTTMN"], 26800.0)

    def test_05_single_price_resolution(self):
        """Single price lookup must resolve both direct and base/quote formats."""
        raw_mock = [
            {
                "symbol": "SOL",
                "price": 96.5,
                "priceBuyIRT": 25800000.0,
                "priceSellIRT": 26000000.0,
            }
        ]

        res_usdt = self.adapter.parse_single_price(raw_mock, "SOLUSDT")
        self.assertEqual(res_usdt.status, "OK")
        self.assertAlmostEqual(res_usdt.price, 96.5)

        res_tmn = self.adapter.parse_single_price(raw_mock, "SOLTMN")
        self.assertEqual(res_tmn.status, "OK")
        self.assertAlmostEqual(res_tmn.price, 2590000.0)


if __name__ == "__main__":
    unittest.main()
