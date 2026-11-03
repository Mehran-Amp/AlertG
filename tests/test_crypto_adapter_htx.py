#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — HTX Adapter Offline Tests (Phase 6 / Wave 2).
Validates:
1. Two-way symbol mapping (canonical base <-> native symbol).
2. Spot-only, USDT-only, active-only ('online') parsing.
3. Leveraged / ETF token detection.
4. Bulk ticker parsing with single HTTP call.
5. Fixture coverage computation.
6. Error classification: 429 (RATE_LIMITED).
7. Error classification: 403 (PROVIDER_BLOCKED / GEO_BLOCKED).
8. Error classification: timeout.
9. Error classification: invalid json/html.
10. T3 Isolation: Adapter queries ONLY HTX/Huobi endpoints, zero calls to others.
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

from app.markets.adapters.htx import HTXAdapter
from app.markets.adapters.base import SymbolInfo, BatchPriceResult, SinglePriceResult

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), 'fixtures', 'htx')


def load_fixture(filename: str):
    path = os.path.join(FIXTURE_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


class TestHTXAdapter(unittest.IsolatedAsyncioTestCase):
    """Offline unit & contract acceptance tests for HTX Adapter."""

    def setUp(self):
        self.adapter = HTXAdapter()
        self.symbols_fixture = load_fixture('symbols.json')
        self.tickers_fixture = load_fixture('tickers.json')
        self.error_429_fixture = load_fixture('error_429.json')
        self.error_403_fixture = load_fixture('error_403.json')

    def test_01_two_way_symbol_mapping(self):
        """Verifies canonical base <-> HTX native symbol mapping."""
        # Base to native
        self.assertEqual(self.adapter.to_native_symbol("BTC"), "btcusdt")
        self.assertEqual(self.adapter.to_native_symbol("btc"), "btcusdt")
        self.assertEqual(self.adapter.to_native_symbol("ETH"), "ethusdt")
        self.assertEqual(self.adapter.to_native_symbol("1INCH"), "1inchusdt")
        self.assertEqual(self.adapter.to_native_symbol("BTCUSDT"), "btcusdt")
        self.assertEqual(self.adapter.to_native_symbol("BTC-USDT"), "btcusdt")

        # Native to canonical base
        self.assertEqual(self.adapter.to_canonical_base("btcusdt"), "BTC")
        self.assertEqual(self.adapter.to_canonical_base("ethusdt"), "ETH")
        self.assertEqual(self.adapter.to_canonical_base("1inchusdt"), "1INCH")

    def test_02_parse_symbols_filters_strictly_spot_usdt_active(self):
        """Verifies non-USDT, inactive, and non-spot pairs are strictly filtered out."""
        symbols = self.adapter.parse_symbols_response(self.symbols_fixture)
        bases = [s.base for s in symbols]
        market_symbols = [s.market_symbol for s in symbols]

        # Active USDT spot pairs must be present
        self.assertIn("BTC", bases)
        self.assertIn("ETH", bases)
        self.assertIn("SOL", bases)
        self.assertIn("1INCH", bases)
        self.assertIn("btcusdt", market_symbols)

        # Inactive pair (LUNA with state 'offline') must be excluded
        self.assertNotIn("LUNA", bases)
        self.assertNotIn("lunausdt", market_symbols)

        # Non-USDT pair (BTCUSDC) must be excluded
        self.assertNotIn("btcusdc", market_symbols)

    def test_03_detect_leveraged_etf_tokens(self):
        """Verifies leveraged / ETF tokens are correctly tagged."""
        symbols = self.adapter.parse_symbols_response(self.symbols_fixture)
        sym_map = {s.base: s for s in symbols}

        self.assertFalse(sym_map["BTC"].is_etf)
        self.assertFalse(sym_map["ETH"].is_etf)
        self.assertFalse(sym_map["1INCH"].is_etf)
        self.assertTrue(sym_map["BTC3L"].is_etf)

    def test_04_parse_batch_prices_strictly_positive_usdt(self):
        """Verifies bulk tickers parser extracts strictly positive prices for USDT pairs."""
        prices = self.adapter.parse_batch_prices_response(self.tickers_fixture)

        self.assertIn("btcusdt", prices)
        self.assertEqual(prices["btcusdt"], 68500.5)
        self.assertIn("ethusdt", prices)
        self.assertEqual(prices["ethusdt"], 2650.25)

        # Zero price pair must be excluded
        self.assertNotIn("zero_usdt", prices)

    def test_05_fixture_coverage(self):
        """Verifies price coverage ratio between active symbols and bulk tickers."""
        symbols = self.adapter.parse_symbols_response(self.symbols_fixture)
        prices = self.adapter.parse_batch_prices_response(self.tickers_fixture)

        priced_count = sum(1 for s in symbols if s.market_symbol in prices)
        coverage_pct = (priced_count / len(symbols)) * 100
        self.assertGreaterEqual(coverage_pct, 80.0, f"Coverage too low: {coverage_pct}%")

    async def test_06_error_classification_429(self):
        """HTTP 429 returns RATE_LIMITED status."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = json.dumps(self.error_429_fixture)
        mock_response.headers = {"Retry-After": "10"}

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        res = await self.adapter.fetch_batch_prices(mock_client)
        self.assertEqual(res.error_code, "RATE_LIMITED")
        self.assertEqual(res.retry_after, 10.0)

    async def test_07_error_classification_403(self):
        """HTTP 403 returns PROVIDER_BLOCKED or GEO_BLOCKED status."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = json.dumps(self.error_403_fixture)
        mock_response.headers = {}

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        res = await self.adapter.fetch_batch_prices(mock_client)
        self.assertIn(res.error_code, ("PROVIDER_BLOCKED", "GEO_BLOCKED"))

    async def test_08_error_classification_timeout(self):
        """TimeoutException returns TIMEOUT status."""
        mock_client = AsyncMock()
        mock_client.get.side_effect = TimeoutError("Request timed out")

        res = await self.adapter.fetch_batch_prices(mock_client)
        self.assertEqual(res.error_code, "TIMEOUT")

    async def test_09_error_classification_invalid_json(self):
        """Invalid JSON / HTML returns INVALID_RESPONSE status."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.text = "<html>502 Bad Gateway</html>"

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        res = await self.adapter.fetch_batch_prices(mock_client)
        self.assertEqual(res.error_code, "INVALID_RESPONSE")

    async def test_10_isolation_contract(self):
        """Rule R1: Adapter queries strictly huobi/htx endpoints."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.tickers_fixture
        mock_response.headers = {}

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        await self.adapter.fetch_batch_prices(mock_client)
        called_url = mock_client.get.call_args[0][0]
        self.assertIn("huobi.pro", called_url, "Must query huobi.pro endpoint")
        self.assertNotIn("binance.com", called_url)
        self.assertNotIn("coinex.com", called_url)


if __name__ == '__main__':
    unittest.main()
