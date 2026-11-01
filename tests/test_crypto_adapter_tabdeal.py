# -*- coding: utf-8 -*-
"""
AlertG — Unit Tests for Tabdeal Crypto Exchange Adapter (Phase 11).
Tests TabdealAdapter parsing, symbol mapping, Rial-to-Toman conversion, and error classification.
Uses recorded fixtures in tests/fixtures/crypto/tabdeal/2026-11-01/.
"""
import os
import json
import unittest
from unittest.mock import patch, AsyncMock
import httpx

from app.markets.adapters.tabdeal import TabdealAdapter
from app.markets.adapters.base import validate_adapter_specification, SymbolInfo


class TestTabdealAdapter(unittest.TestCase):

    def setUp(self):
        self.adapter = TabdealAdapter()
        self.fixtures_dir = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "fixtures", "crypto", "tabdeal", "2026-11-01"
        ))

    def test_01_specification_compliance(self):
        """1. Verify TabdealAdapter specification conforms to Phase 2 & Rule R11 constraints."""
        spec = self.adapter.specification
        self.assertEqual(spec.exchange_id, "tabdeal")
        self.assertIn("(tabdeal)", spec.display_name)
        self.assertEqual(spec.provider_key, "crypto_tabdeal")
        self.assertEqual(spec.status, "active")

        # Validate with standard specification validator
        errors = validate_adapter_specification(spec)
        self.assertEqual(len(errors), 0, f"Specification validation errors: {errors}")

    def test_02_symbol_mapping(self):
        """2. Verify native symbol two-way transformations."""
        # USDT pairs
        self.assertEqual(self.adapter.to_native_symbol("BTC", quote="USDT"), "BTCUSDT")
        self.assertEqual(self.adapter.to_native_symbol("BTCUSDT"), "BTCUSDT")
        self.assertEqual(self.adapter.to_native_symbol("BTC_USDT"), "BTCUSDT")

        # IRT / TMN pairs
        self.assertEqual(self.adapter.to_native_symbol("BTC", quote="TMN"), "BTCIRT")
        self.assertEqual(self.adapter.to_native_symbol("BTCTMN"), "BTCIRT")
        self.assertEqual(self.adapter.to_native_symbol("BTC_IRT"), "BTCIRT")

        # Market information symbol (with underscore)
        self.assertEqual(self.adapter.to_tabdeal_plot_symbol("BTCIRT"), "BTC_IRT")
        self.assertEqual(self.adapter.to_tabdeal_plot_symbol("BTCUSDT"), "BTC_USDT")

        # Canonical base & quote extraction
        base_u, quote_u = self.adapter.to_canonical_base_and_quote("BTCUSDT")
        self.assertEqual(base_u, "BTC")
        self.assertEqual(quote_u, "USDT")

        base_t, quote_t = self.adapter.to_canonical_base_and_quote("BTCIRT")
        self.assertEqual(base_t, "BTC")
        self.assertEqual(quote_t, "TMN")

        base_anchor, quote_anchor = self.adapter.to_canonical_base_and_quote("USDTIRT")
        self.assertEqual(base_anchor, "USDT")
        self.assertEqual(quote_anchor, "TMN")

    def test_03_parse_market_list_from_fixture(self):
        """3. Verify parsing exchangeInfo fixture extracts active spot pairs."""
        info_path = os.path.join(self.fixtures_dir, "exchangeInfo.json")
        if not os.path.exists(info_path):
            self.skipTest(f"Fixture not found at {info_path}")

        with open(info_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        symbols = self.adapter.parse_market_list(raw_data)
        self.assertGreater(len(symbols), 1000)

        # Verify key pairs are in the parsed results
        symbols_by_market = {s.market_symbol: s for s in symbols}
        self.assertIn("BTCUSDT", symbols_by_market)
        self.assertIn("BTCIRT", symbols_by_market)
        self.assertIn("USDTIRT", symbols_by_market)

        btc_irt = symbols_by_market["BTCIRT"]
        self.assertEqual(btc_irt.base, "BTC")
        self.assertEqual(btc_irt.quote, "TMN")
        self.assertTrue(btc_irt.is_active)
        self.assertFalse(btc_irt.is_etf)

    def test_04_parse_batch_prices_and_rial_to_toman_conversion(self):
        """4. Verify parse_batch_prices converts IRT Rials to canonical Tomans (divide by 10)."""
        mkt_path = os.path.join(self.fixtures_dir, "market_information.json")
        if not os.path.exists(mkt_path):
            self.skipTest(f"Fixture not found at {mkt_path}")

        with open(mkt_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        res = self.adapter.parse_batch_prices(raw_data)
        self.assertEqual(res.error_code, "OK")
        self.assertGreater(len(res.prices), 1000)

        # USDT/IRT: e.g. raw 271,250 Rials -> 27,125 Tomans
        self.assertIn("USDTIRT", res.prices)
        usdt_tmn = res.prices["USDTIRT"]
        self.assertAlmostEqual(usdt_tmn, 27125.0, delta=500.0)

        # BTC/IRT: e.g. raw ~21,095,833,291 Rials -> ~2,109,583,329.1 Tomans
        self.assertIn("BTCIRT", res.prices)
        btc_tmn = res.prices["BTCIRT"]
        self.assertAlmostEqual(btc_tmn, 2109583329.1, delta=100000000.0)

        # BTC/USDT: directly in USDT without factor 10
        self.assertIn("BTCUSDT", res.prices)
        btc_usdt = res.prices["BTCUSDT"]
        self.assertGreater(btc_usdt, 50000.0)
        self.assertLess(btc_usdt, 150000.0)

    def test_05_parse_single_price_from_trades_fixture(self):
        """5. Verify single trade price parsing (Last Traded Price) from fixture."""
        trades_path = os.path.join(self.fixtures_dir, "trades_sample.json")
        if not os.path.exists(trades_path):
            self.skipTest(f"Fixture not found at {trades_path}")

        with open(trades_path, "r", encoding="utf-8") as f:
            raw_trades = json.load(f)

        res = self.adapter.parse_single_price(raw_trades, "BTCIRT")
        self.assertEqual(res.status, "OK")
        self.assertIsNotNone(res.price)
        self.assertGreater(res.price, 1000000000.0)  # > 1 Billion Tomans
        self.assertEqual(res.currency, "TMN")
        self.assertEqual(res.source, self.adapter.display_name)


if __name__ == "__main__":
    unittest.main()
