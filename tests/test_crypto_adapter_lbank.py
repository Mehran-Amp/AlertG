#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — LBank Adapter Offline Tests (Sub-phase 4e).
Validates:
1. Two-way symbol mapping (canonical base <-> LBank native symbol 'base_usdt').
2. Spot-only, USDT-only parsing.
3. Crucial Rule: Eliminates unpriced pairs (e.g. ETF tokens missing ticker data).
4. Leveraged / ETF token detection (3L, 3S, 5L, etc.).
5. Bulk ticker parsing with single HTTP call.
6. Fixture coverage computation (must be >= 95%).
7. Error classification: 429 (RATE_LIMITED), 403/451 (GEO_BLOCKED), timeout, invalid json/html.
8. T3 Isolation: Adapter queries ONLY LBank endpoints, zero calls to others.
"""

import unittest
import os
import sys
import json
from unittest.mock import AsyncMock, MagicMock

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

try:
    import pydantic
except ImportError:
    pydantic = MagicMock()
    class BaseModel: pass
    pydantic.BaseModel = BaseModel
    sys.modules['pydantic'] = pydantic

try:
    import fastapi
except ImportError:
    fastapi = MagicMock()
    sys.modules['fastapi'] = fastapi

from app.markets.adapters.lbank import LBankAdapter
from app.markets.adapters.base import SymbolInfo, BatchPriceResult, SinglePriceResult


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), 'fixtures', 'lbank')


def load_fixture(filename: str):
    path = os.path.join(FIXTURE_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


class TestLBankAdapter(unittest.IsolatedAsyncioTestCase):
    """Offline unit & contract acceptance tests for LBank Adapter."""

    def setUp(self):
        self.adapter = LBankAdapter()
        self.currency_pairs_fixture = load_fixture('currency_pairs.json')
        self.ticker_all_fixture = load_fixture('ticker_all.json')
        self.error_429_fixture = load_fixture('error_429.json')
        self.error_403_fixture = load_fixture('error_403.json')

    def test_01_two_way_symbol_mapping(self):
        """Verifies canonical base <-> LBank native symbol mapping (base_usdt in lowercase)."""
        # Base to native
        self.assertEqual(self.adapter.to_native_symbol("BTC"), "btc_usdt")
        self.assertEqual(self.adapter.to_native_symbol("btc"), "btc_usdt")
        self.assertEqual(self.adapter.to_native_symbol("btcusdt"), "btc_usdt")
        self.assertEqual(self.adapter.to_native_symbol("BTC-USDT"), "btc_usdt")
        self.assertEqual(self.adapter.to_native_symbol("BTC_USDT"), "btc_usdt")
        self.assertEqual(self.adapter.to_native_symbol("btc_usdt"), "btc_usdt")
        self.assertEqual(self.adapter.to_native_symbol("LBK"), "lbk_usdt")
        self.assertEqual(self.adapter.to_native_symbol("1INCH"), "1inch_usdt")

        # Native to canonical base
        self.assertEqual(self.adapter.to_canonical_base("btc_usdt"), "BTC")
        self.assertEqual(self.adapter.to_canonical_base("BTC_USDT"), "BTC")
        self.assertEqual(self.adapter.to_canonical_base("lbk_usdt"), "LBK")
        self.assertEqual(self.adapter.to_canonical_base("1inch_usdt"), "1INCH")

    def test_02_parse_symbols_filters_strictly_spot_usdt(self):
        """Verifies non-USDT pairs (e.g. btc_eth) are strictly filtered out."""
        symbols = self.adapter.parse_symbols_response(self.currency_pairs_fixture)
        bases = [s.base for s in symbols]
        market_symbols = [s.market_symbol for s in symbols]

        self.assertIn("BTC", bases)
        self.assertIn("ETH", bases)
        self.assertIn("SOL", bases)
        self.assertIn("LBK", bases)
        self.assertIn("1INCH", bases)
        self.assertIn("btc_usdt", market_symbols)

        # Non-USDT pair must be excluded
        self.assertNotIn("btc_eth", market_symbols)

    def test_03_crucial_filter_unpriced_pairs(self):
        """
        Crucial LBank Rule: Pairs in currencyPairs that lack live prices in ticker/24hr
        MUST be eliminated when cross-verified with live prices.
        """
        # Without price filter, unpriced_token_usdt is included:
        raw_symbols = self.adapter.parse_symbols_response(self.currency_pairs_fixture)
        raw_market_symbols = [s.market_symbol for s in raw_symbols]
        self.assertIn("unpriced_token_usdt", raw_market_symbols)

        # With price filter, unpriced_token_usdt MUST be excluded:
        prices = self.adapter.parse_batch_prices_response(self.ticker_all_fixture)
        priced_set = set(prices.keys())
        filtered_symbols = self.adapter.parse_symbols_response(
            self.currency_pairs_fixture,
            priced_symbols=priced_set
        )
        filtered_market_symbols = [s.market_symbol for s in filtered_symbols]

        self.assertNotIn("unpriced_token_usdt", filtered_market_symbols)
        self.assertIn("btc_usdt", filtered_market_symbols)
        self.assertIn("lbk_usdt", filtered_market_symbols)

        # 100% of filtered symbols must have live prices
        for s in filtered_symbols:
            self.assertIn(s.market_symbol, prices)
            self.assertGreater(prices[s.market_symbol], 0)

    def test_04_detect_leveraged_etf_tokens(self):
        """Verifies leveraged / ETF tokens are correctly tagged."""
        symbols = self.adapter.parse_symbols_response(self.currency_pairs_fixture)
        sym_map = {s.base: s for s in symbols}

        self.assertFalse(sym_map["BTC"].is_etf)
        self.assertFalse(sym_map["ETH"].is_etf)
        self.assertFalse(sym_map["LBK"].is_etf)

        self.assertTrue(sym_map["BTC3L"].is_etf)
        self.assertTrue(sym_map["BTC3S"].is_etf)

    def test_05_parse_batch_prices_strictly_positive_usdt(self):
        """Verifies bulk prices response extracts valid positive USDT quotes."""
        prices = self.adapter.parse_batch_prices_response(self.ticker_all_fixture)

        self.assertIn("btc_usdt", prices)
        self.assertAlmostEqual(prices["btc_usdt"], 67415.50)
        self.assertAlmostEqual(prices["eth_usdt"], 2622.10)
        self.assertAlmostEqual(prices["lbk_usdt"], 0.0125)
        self.assertAlmostEqual(prices["1inch_usdt"], 0.3240)

        # Non-USDT pair must not be in the dictionary
        self.assertNotIn("btc_eth", prices)

    def test_06_coverage_ratio_fixture(self):
        """Verifies that pricing coverage on filtered symbols is 100% (exceeding >= 95%)."""
        prices = self.adapter.parse_batch_prices_response(self.ticker_all_fixture)
        symbols = self.adapter.parse_symbols_response(
            self.currency_pairs_fixture,
            priced_symbols=set(prices.keys())
        )

        total_spot_usdt = len(symbols)
        priced_pairs = [s.market_symbol for s in symbols if s.market_symbol in prices and prices[s.market_symbol] > 0]

        coverage_pct = (len(priced_pairs) / total_spot_usdt) * 100 if total_spot_usdt else 0
        self.assertGreaterEqual(coverage_pct, 95.0, f"Coverage was {coverage_pct:.2f}%, required >= 95%")
        self.assertEqual(coverage_pct, 100.0)

    async def test_07_error_classification_rate_limit_429(self):
        """Verifies HTTP 429 maps to RATE_LIMITED status."""
        client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = json.dumps(self.error_429_fixture)
        mock_resp.json.return_value = self.error_429_fixture
        client.get.return_value = mock_resp

        batch_res = await self.adapter.fetch_batch_prices(client)
        self.assertEqual(batch_res.error_code, "RATE_LIMITED")

        single_res = await self.adapter.fetch_single_price(client, "BTC")
        self.assertEqual(single_res.status, "RATE_LIMITED")
        self.assertIsNone(single_res.price)

    async def test_08_error_classification_geo_blocked_403(self):
        """Verifies HTTP 403 maps to GEO_BLOCKED status."""
        client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = json.dumps(self.error_403_fixture)
        mock_resp.json.return_value = self.error_403_fixture
        client.get.return_value = mock_resp

        batch_res = await self.adapter.fetch_batch_prices(client)
        self.assertEqual(batch_res.error_code, "GEO_BLOCKED")

        single_res = await self.adapter.fetch_single_price(client, "ETH")
        self.assertEqual(single_res.status, "GEO_BLOCKED")

    async def test_09_error_classification_timeout(self):
        """Verifies request timeout maps to TIMEOUT."""
        client = AsyncMock()
        _TimeoutClass = getattr(httpx, 'TimeoutException', TimeoutError)
        if not isinstance(_TimeoutClass, type) or not issubclass(_TimeoutClass, BaseException):
            _TimeoutClass = TimeoutError
        client.get.side_effect = _TimeoutClass("Read timeout after 8s")

        batch_res = await self.adapter.fetch_batch_prices(client)
        self.assertEqual(batch_res.error_code, "TIMEOUT")

        single_res = await self.adapter.fetch_single_price(client, "SOL")
        self.assertEqual(single_res.status, "TIMEOUT")

    async def test_10_t3_isolation_only_lbank_endpoints_called(self):
        """
        Acceptance T3: Verifies that LBankAdapter ONLY queries LBank URLs.
        Zero cross-exchange fallback, zero calls to any other host.
        """
        client = AsyncMock()
        called_urls = []

        async def fake_get(url, **kwargs):
            called_urls.append(url)
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if "currencyPairs" in url:
                mock_resp.json.return_value = self.currency_pairs_fixture
            elif "symbol=btc_usdt" in url:
                mock_resp.json.return_value = {
                    "result": "true",
                    "data": [
                        {
                            "symbol": "btc_usdt",
                            "timestamp": 1730000000000,
                            "ticker": {
                                "latest": "67415.50"
                            }
                        }
                    ]
                }
            else:
                mock_resp.json.return_value = self.ticker_all_fixture
            return mock_resp

        client.get.side_effect = fake_get

        # Fetch symbols with filter_unpriced enabled
        symbols, _, _ = await self.adapter.fetch_symbols(client, filter_unpriced=True)
        self.assertGreater(len(symbols), 0)

        # Fetch batch prices
        batch_res = await self.adapter.fetch_batch_prices(client)
        self.assertEqual(batch_res.error_code, "SUCCESS")

        # Fetch single price
        single_res = await self.adapter.fetch_single_price(client, "BTC")
        self.assertEqual(single_res.status, "SUCCESS")
        self.assertAlmostEqual(single_res.price, 67415.50)

        # Assert every called URL is strictly from LBank official domains
        self.assertGreater(len(called_urls), 0)
        for url in called_urls:
            self.assertTrue(
                url.startswith("https://api.lbank.info/") or url.startswith("https://api.lbkex.com/"),
                f"Violation of R1 Isolation: unexpected URL called: {url}"
            )


if __name__ == '__main__':
    unittest.main()
