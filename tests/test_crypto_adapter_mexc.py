#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — MEXC Adapter Offline Tests (Sub-phase 4b).
Validates:
1. Two-way symbol mapping (canonical base <-> native symbol).
2. Spot-only, USDT-only, active-only parsing ('ENABLED', '1', 'TRADING').
3. Leveraged / ETF token detection (3L, 3S, 5L, etc.).
4. Bulk ticker parsing with single HTTP call.
5. Fixture coverage computation (must be >= 95%).
6. Error classification: 429 (RATE_LIMITED), 403/451 (GEO_BLOCKED), timeout, invalid json/html.
7. T3 Isolation: Adapter queries ONLY MEXC endpoints, zero calls to others.
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

from app.markets.adapters.mexc import MEXCAdapter
from app.markets.adapters.base import SymbolInfo, BatchPriceResult, SinglePriceResult


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), 'fixtures', 'mexc')


def load_fixture(filename: str):
    path = os.path.join(FIXTURE_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


class TestMEXCAdapter(unittest.IsolatedAsyncioTestCase):
    """Offline unit & contract acceptance tests for MEXC Adapter."""

    def setUp(self):
        self.adapter = MEXCAdapter()
        self.exchange_info_fixture = load_fixture('exchange_info.json')
        self.ticker_price_fixture = load_fixture('ticker_price.json')
        self.error_429_fixture = load_fixture('error_429.json')
        self.error_403_fixture = load_fixture('error_403.json')

    def test_01_two_way_symbol_mapping(self):
        """Verifies canonical base <-> MEXC native symbol mapping."""
        # Base to native
        self.assertEqual(self.adapter.to_native_symbol("BTC"), "BTCUSDT")
        self.assertEqual(self.adapter.to_native_symbol("btc"), "BTCUSDT")
        self.assertEqual(self.adapter.to_native_symbol("KAS"), "KASUSDT")
        self.assertEqual(self.adapter.to_native_symbol("1INCH"), "1INCHUSDT")
        self.assertEqual(self.adapter.to_native_symbol("BTCUSDT"), "BTCUSDT")

        # Native to canonical base
        self.assertEqual(self.adapter.to_canonical_base("BTCUSDT"), "BTC")
        self.assertEqual(self.adapter.to_canonical_base("KASUSDT"), "KAS")
        self.assertEqual(self.adapter.to_canonical_base("1INCHUSDT"), "1INCH")

    def test_02_parse_symbols_filters_strictly_spot_usdt_active(self):
        """Verifies non-USDT, inactive, and non-spot pairs are strictly filtered out."""
        symbols = self.adapter.parse_symbols_response(self.exchange_info_fixture)
        bases = [s.base for s in symbols]
        market_symbols = [s.market_symbol for s in symbols]

        # Active USDT spot pairs must be present (handling ENABLED, 1, TRADING)
        self.assertIn("BTC", bases)
        self.assertIn("ETH", bases)
        self.assertIn("SOL", bases)
        self.assertIn("KAS", bases)
        self.assertIn("1INCH", bases)
        self.assertIn("BTCUSDT", market_symbols)

        # Inactive pair (OLDCOINUSDT has status DISABLED) must be excluded
        self.assertNotIn("OLDCOIN", bases)
        self.assertNotIn("OLDCOINUSDT", market_symbols)

        # Non-USDT pairs must be excluded
        self.assertNotIn("BTCUSDC", market_symbols)
        self.assertNotIn("ETHBTC", market_symbols)

        # Non-spot pair (FUTURES_USDT) must be excluded
        self.assertNotIn("FUTURES", bases)
        self.assertNotIn("FUTURES_USDT", market_symbols)

    def test_03_detect_leveraged_etf_tokens(self):
        """Verifies leveraged / ETF tokens are correctly tagged."""
        symbols = self.adapter.parse_symbols_response(self.exchange_info_fixture)
        sym_map = {s.base: s for s in symbols}

        self.assertFalse(sym_map["BTC"].is_etf)
        self.assertFalse(sym_map["ETH"].is_etf)
        self.assertFalse(sym_map["KAS"].is_etf)

        self.assertTrue(sym_map["BTC3L"].is_etf)
        self.assertTrue(sym_map["BTC3S"].is_etf)
        self.assertTrue(sym_map["ETH5L"].is_etf)

    def test_04_parse_batch_prices_strictly_positive_usdt(self):
        """Verifies bulk prices response extracts valid positive USDT quotes."""
        prices = self.adapter.parse_batch_prices_response(self.ticker_price_fixture)

        self.assertIn("BTCUSDT", prices)
        self.assertAlmostEqual(prices["BTCUSDT"], 67480.00)
        self.assertAlmostEqual(prices["ETHUSDT"], 2618.50)
        self.assertAlmostEqual(prices["KASUSDT"], 0.1345)
        self.assertAlmostEqual(prices["1INCHUSDT"], 0.3240)

        # Non-USDT tickers must not be in the dictionary
        self.assertNotIn("BTCUSDC", prices)
        self.assertNotIn("ETHBTC", prices)

    def test_05_coverage_ratio_fixture(self):
        """Verifies that pricing coverage in fixture meets or exceeds 95%."""
        symbols = self.adapter.parse_symbols_response(self.exchange_info_fixture)
        prices = self.adapter.parse_batch_prices_response(self.ticker_price_fixture)

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

        # Test batch prices
        batch_res = await self.adapter.fetch_batch_prices(client)
        self.assertEqual(batch_res.error_code, "RATE_LIMITED")
        self.assertIn("429", batch_res.error or "")

        # Test single price
        single_res = await self.adapter.fetch_single_price(client, "BTC")
        self.assertEqual(single_res.status, "RATE_LIMITED")
        self.assertIsNone(single_res.price)

    async def test_07_error_classification_geo_blocked_403(self):
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

    async def test_10_t3_isolation_only_mexc_endpoints_called(self):
        """
        Acceptance T3: Verifies that MEXCAdapter ONLY queries MEXC URLs.
        Zero cross-exchange fallback, zero calls to any other host.
        """
        client = AsyncMock()
        called_urls = []

        async def fake_get(url, **kwargs):
            called_urls.append(url)
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if "exchangeInfo" in url:
                mock_resp.json.return_value = self.exchange_info_fixture
            elif "symbol=" in url:
                mock_resp.json.return_value = {"symbol": "BTCUSDT", "price": "67480.00"}
            else:
                mock_resp.json.return_value = self.ticker_price_fixture
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
        self.assertAlmostEqual(single_res.price, 67480.00)

        # Assert every called URL is strictly from MEXC
        self.assertGreater(len(called_urls), 0)
        for url in called_urls:
            self.assertTrue(
                url.startswith("https://api.mexc.com/"),
                f"Violation of R1 Isolation: unexpected URL called: {url}"
            )


if __name__ == '__main__':
    unittest.main()
