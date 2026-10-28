#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — Kraken Adapter Offline Tests (Sub-phase 4g).
Validates:
1. Two-way symbol mapping (canonical base <-> Kraken native symbol 'XBTUSDT' / 'ETHUSDT').
2. Spot-only, USDT-only, online-only parsing ('status == online' and quote is USDT).
3. Leveraged / ETF token detection.
4. Bulk ticker parsing with single HTTP call (c[0] extraction).
5. Fixture coverage computation (must be >= 95%).
6. Error classification: 429 (RATE_LIMITED), 403 (GEO_BLOCKED), timeout, invalid json/html.
7. T3 Isolation: Adapter queries ONLY Kraken endpoints, zero calls to others.
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

from app.markets.adapters.kraken import KrakenAdapter
from app.markets.adapters.base import SymbolInfo, BatchPriceResult, SinglePriceResult


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), 'fixtures', 'kraken')


def load_fixture(filename: str):
    path = os.path.join(FIXTURE_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


class TestKrakenAdapter(unittest.IsolatedAsyncioTestCase):
    """Offline unit & contract acceptance tests for Kraken Adapter."""

    def setUp(self):
        self.adapter = KrakenAdapter()
        self.asset_pairs_fixture = load_fixture('asset_pairs.json')
        self.ticker_fixture = load_fixture('ticker.json')
        self.error_429_fixture = load_fixture('error_429.json')
        self.error_403_fixture = load_fixture('error_403.json')

    def test_01_two_way_symbol_mapping(self):
        """Verifies canonical base <-> Kraken native symbol (XBTUSDT, ETHUSDT, etc.)."""
        # Canonical / user input to native
        self.assertEqual(self.adapter.to_native_symbol("BTC"), "XBTUSDT")
        self.assertEqual(self.adapter.to_native_symbol("btc"), "XBTUSDT")
        self.assertEqual(self.adapter.to_native_symbol("XBT"), "XBTUSDT")
        self.assertEqual(self.adapter.to_native_symbol("BTCUSDT"), "XBTUSDT")
        self.assertEqual(self.adapter.to_native_symbol("BTC-USDT"), "XBTUSDT")
        self.assertEqual(self.adapter.to_native_symbol("BTC_USDT"), "XBTUSDT")
        self.assertEqual(self.adapter.to_native_symbol("ETH"), "ETHUSDT")
        self.assertEqual(self.adapter.to_native_symbol("SOL"), "SOLUSDT")
        self.assertEqual(self.adapter.to_native_symbol("ADA"), "ADAUSDT")

        # Native to canonical base
        self.assertEqual(self.adapter.to_canonical_base("XBTUSDT"), "BTC")
        self.assertEqual(self.adapter.to_canonical_base("XBT/USDT"), "BTC")
        self.assertEqual(self.adapter.to_canonical_base("ETHUSDT"), "ETH")
        self.assertEqual(self.adapter.to_canonical_base("SOLUSDT"), "SOL")
        self.assertEqual(self.adapter.to_canonical_base("ADAUSDT"), "ADA")

    def test_02_parse_symbols_spot_usdt_online_only(self):
        """Verifies filtering: quote == USDT, status == online."""
        symbols = self.adapter.parse_symbols_response(self.asset_pairs_fixture)

        bases = {s.base for s in symbols}
        market_symbols = {s.market_symbol for s in symbols}

        self.assertIn("BTC", bases)
        self.assertIn("ETH", bases)
        self.assertIn("SOL", bases)
        self.assertIn("ADA", bases)
        self.assertIn("DOT", bases)
        self.assertIn("XBTUSDT", market_symbols)

        # Inactive/delisted pair (DELISTEDUSDT has status cancel_only) must be excluded
        self.assertNotIn("DELISTED", bases)
        self.assertNotIn("DELISTEDUSDT", market_symbols)

        # Non-USDT pair (XXBTZUSD, XETHXXBT) must be excluded
        self.assertNotIn("XXBTZUSD", market_symbols)
        self.assertNotIn("XETHXXBT", market_symbols)

    def test_03_detect_leveraged_etf_tokens(self):
        """Verifies leveraged / ETF tokens detection logic."""
        symbols = self.adapter.parse_symbols_response(self.asset_pairs_fixture)
        sym_map = {s.base: s for s in symbols}

        self.assertFalse(sym_map["BTC"].is_etf)
        self.assertFalse(sym_map["ETH"].is_etf)
        self.assertFalse(sym_map["SOL"].is_etf)

    def test_04_parse_batch_prices_strictly_positive_usdt(self):
        """Verifies bulk prices response extracts valid positive USDT quotes from c[0]."""
        prices = self.adapter.parse_batch_prices_response(self.ticker_fixture)

        self.assertIn("XBTUSDT", prices)
        self.assertAlmostEqual(prices["XBTUSDT"], 68450.2)
        self.assertAlmostEqual(prices["ETHUSDT"], 3518.25)
        self.assertAlmostEqual(prices["SOLUSDT"], 177.75)
        self.assertAlmostEqual(prices["ADAUSDT"], 0.3535)
        self.assertAlmostEqual(prices["DOTUSDT"], 4.245)

        # Non-USDT tickers should not be in the dictionary
        self.assertNotIn("XXBTZUSD", prices)
        self.assertNotIn("XETHXXBT", prices)

    def test_05_coverage_ratio_fixture(self):
        """Verifies that pricing coverage in fixture meets or exceeds 95%."""
        symbols = self.adapter.parse_symbols_response(self.asset_pairs_fixture)
        prices = self.adapter.parse_batch_prices_response(self.ticker_fixture)

        total_spot_usdt = len(symbols)
        priced_pairs = [s.market_symbol for s in symbols if s.market_symbol in prices and prices[s.market_symbol] > 0]

        coverage_pct = (len(priced_pairs) / total_spot_usdt) * 100 if total_spot_usdt else 0
        self.assertGreaterEqual(coverage_pct, 95.0, f"Coverage was {coverage_pct:.2f}%, required >= 95%")
        self.assertEqual(coverage_pct, 100.0)

    async def test_06_error_classification_rate_limit_429(self):
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

    async def test_07_error_classification_geo_blocked_403(self):
        """Verifies HTTP 403 maps to PROVIDER_BLOCKED / GEO_BLOCKED status."""
        client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = json.dumps(self.error_403_fixture)
        mock_resp.json.return_value = self.error_403_fixture
        client.get.return_value = mock_resp

        batch_res = await self.adapter.fetch_batch_prices(client)
        self.assertIn(batch_res.error_code, ("PROVIDER_BLOCKED", "GEO_BLOCKED"))

        single_res = await self.adapter.fetch_single_price(client, "ETH")
        self.assertIn(single_res.status, ("PROVIDER_BLOCKED", "GEO_BLOCKED"))

    async def test_08_error_classification_timeout(self):
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

    async def test_09_error_classification_invalid_json_html(self):
        """Verifies HTML or malformed response maps to INVALID_RESPONSE."""
        client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body>502 Bad Gateway Cloudflare</body></html>"
        mock_resp.json.side_effect = ValueError("Invalid JSON")
        client.get.return_value = mock_resp

        batch_res = await self.adapter.fetch_batch_prices(client)
        self.assertEqual(batch_res.error_code, "INVALID_RESPONSE")

    async def test_10_t3_isolation_only_kraken_endpoints_called(self):
        """
        Acceptance T3: Verifies that KrakenAdapter ONLY queries Kraken URLs.
        Zero cross-exchange fallback, zero calls to any other host.
        """
        client = AsyncMock()
        called_urls = []

        async def fake_get(url, **kwargs):
            called_urls.append(url)
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if "AssetPairs" in url:
                mock_resp.json.return_value = self.asset_pairs_fixture
            elif "pair=" in url:
                mock_resp.json.return_value = {
                    "error": [],
                    "result": {
                        "XBTUSDT": {
                            "c": ["68450.2", "0.05"]
                        }
                    }
                }
            else:
                mock_resp.json.return_value = self.ticker_fixture
            return mock_resp

        client.get.side_effect = fake_get

        # Fetch symbols
        symbols, _, _ = await self.adapter.fetch_symbols(client)
        self.assertGreater(len(symbols), 0)

        # Fetch batch prices
        batch_res = await self.adapter.fetch_batch_prices(client)
        self.assertEqual(batch_res.error_code, "SUCCESS")

        # Fetch single price
        single_res = await self.adapter.fetch_single_price(client, "BTC")
        self.assertEqual(single_res.status, "SUCCESS")
        self.assertAlmostEqual(single_res.price, 68450.2)

        # Assert every called URL is strictly from Kraken
        self.assertGreater(len(called_urls), 0)
        for url in called_urls:
            self.assertTrue(
                url.startswith("https://api.kraken.com/"),
                f"Violation of R1 Isolation: unexpected URL called: {url}"
            )


if __name__ == '__main__':
    unittest.main()
