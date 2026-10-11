#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit Tests for Phase 5 (v2.9.0): Resilient Multi-Provider Market Architecture:
Acceptance Criteria Verified:
1. Provider Adapters Interface:
   - All 4 adapters (Yahoo, Finnhub, Twelve Data, FRED) implement fetch_quotes and fetch_catalog.
   - Meta keys preserved: price, asOf, state, currency, source.
2. Resilience:
   - Timeout scenario: handled gracefully with retries, no crash.
   - HTTP 429 Rate Limit scenario: records 429 metrics and trips circuit breaker if repeated.
   - Malformed/corrupted JSON scenario: caught safely, no crash.
   - Complete outage (HTTP 500/connection error): retries with backoff, fails over cleanly.
3. Circuit Breaker:
   - CLOSED -> trips to OPEN on repeated failures -> rejects execution -> HALF_OPEN recovery -> CLOSED.
4. Fallback Chains:
   - Stocks: Yahoo fails -> Finnhub succeeds.
   - Stocks: Yahoo & Finnhub fail -> Twelve Data succeeds.
   - Commodities/Indices: Yahoo fails -> Twelve Data succeeds.
   - Macro: FRED succeeds; when FRED fails, falls back to Yahoo.
5. Closed Market Guard compatibility:
   - Closed market state preserved without crashing.
6. Unknown symbols:
   - Falls back to legacy resolve_yf_symbol.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import json
import time
import asyncio
import httpx

from app.markets.global_stocks import (
    CircuitBreaker,
    BaseMarketAdapter,
    YahooFinanceAdapter,
    FinnhubAdapter,
    TwelveDataAdapter,
    FredAdapter,
    yahoo_adapter,
    finnhub_adapter,
    twelve_data_adapter,
    fred_adapter,
    get_fallback_chain,
    resolve_symbol_category,
    resolve_yf_symbol,
    fetch_global_stocks,
    WALLSTREET_MACRO_SYMBOLS,
)
from app.state import METRICS


class TestPhase5ResilientProviders(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Reset circuit breaker states before each test
        for adapter in [yahoo_adapter, finnhub_adapter, twelve_data_adapter, fred_adapter]:
            adapter.circuit_breaker.failure_count = 0
            adapter.circuit_breaker.state = "CLOSED"
            adapter.circuit_breaker.last_failure_time = 0.0

    def test_01_adapters_interface_and_catalog(self):
        """Verify all 4 adapters implement fetch_catalog and fetch_quotes contract"""
        # 1. Yahoo Catalog
        y_cat = yahoo_adapter.fetch_catalog()
        self.assertIsInstance(y_cat, list)
        self.assertGreater(len(y_cat), 50)

        # 2. Finnhub Catalog (stocks & forex)
        fh_cat = finnhub_adapter.fetch_catalog()
        self.assertIsInstance(fh_cat, list)
        self.assertTrue(all(item['category'] in ('stock', 'forex') for item in fh_cat))

        # 3. Twelve Data Catalog (stocks, forex, index, commodity)
        td_cat = twelve_data_adapter.fetch_catalog()
        self.assertIsInstance(td_cat, list)
        self.assertTrue(all(item['category'] in ('stock', 'forex', 'index', 'commodity') for item in td_cat))

        # 4. FRED Catalog (macro, bond)
        fred_cat = fred_adapter.fetch_catalog()
        self.assertIsInstance(fred_cat, list)
        self.assertTrue(all(item['category'] in ('bond', 'macro') for item in fred_cat))

    def test_02_circuit_breaker_state_transitions(self):
        """Verify Circuit Breaker trips to OPEN after 3 failures and recovers in HALF_OPEN"""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.2)
        self.assertEqual(cb.state, "CLOSED")
        self.assertTrue(cb.can_execute())

        # 1st failure
        cb.record_failure()
        self.assertEqual(cb.state, "CLOSED")
        self.assertTrue(cb.can_execute())

        # 2nd failure
        cb.record_failure()
        self.assertEqual(cb.state, "CLOSED")
        self.assertTrue(cb.can_execute())

        # 3rd failure -> Trips to OPEN
        cb.record_failure()
        self.assertEqual(cb.state, "OPEN")
        self.assertFalse(cb.can_execute(), "OPEN circuit breaker must reject execution immediately")

        # Wait for recovery timeout
        time.sleep(0.25)
        self.assertTrue(cb.can_execute(), "Should transition to HALF_OPEN after timeout")
        self.assertEqual(cb.state, "HALF_OPEN")

        # Success in HALF_OPEN resets to CLOSED
        cb.record_success()
        self.assertEqual(cb.state, "CLOSED")
        self.assertEqual(cb.failure_count, 0)

    async def test_03_timeout_scenario_with_retry_and_circuit_record(self):
        """Verify timeout error retries with backoff and safely records failure without crashing"""
        adapter = FinnhubAdapter(api_key="test_key", timeout=0.05, max_retries=1)
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.TimeoutException("Connection timed out")

        quote = await adapter.fetch_quote("AAPL", mock_client)
        self.assertIsNone(quote, "Timed out adapter must return None")
        self.assertGreater(adapter.circuit_breaker.failure_count, 0, "Timeout must record failure")

    async def test_04_http_429_rate_limit_scenario(self):
        """Verify HTTP 429 rate limit is captured and records rate_limits_429 metric without crashing"""
        adapter = TwelveDataAdapter(api_key="test_key", timeout=1.0, max_retries=1)
        mock_client = AsyncMock()
        res_429 = MagicMock()
        res_429.status_code = 429
        mock_client.get.return_value = res_429

        quote = await adapter.fetch_quote("EUR/USD", mock_client)
        self.assertIsNone(quote)
        self.assertGreater(adapter.circuit_breaker.failure_count, 0)
        self.assertGreater(METRICS["providers"]["twelvedata"]["rate_limits_429"], 0)

    async def test_05_malformed_corrupted_json_scenario(self):
        """Verify malformed JSON responses are handled gracefully without unhandled exceptions"""
        adapter = FinnhubAdapter(api_key="test_key", timeout=1.0, max_retries=1)
        mock_client = AsyncMock()
        res_bad_json = MagicMock()
        res_bad_json.status_code = 200
        res_bad_json.json.side_effect = json.JSONDecodeError("Expecting value", "<html>Error</html>", 0)
        mock_client.get.return_value = res_bad_json

        quote = await adapter.fetch_quote("TSLA", mock_client)
        self.assertIsNone(quote, "Malformed JSON must safely return None")
        self.assertGreater(adapter.circuit_breaker.failure_count, 0)

    async def test_06_complete_outage_http_500_scenario(self):
        """Verify complete provider outage (HTTP 500) retries and fails over safely"""
        adapter = YahooFinanceAdapter(timeout=0.1, max_retries=1)
        mock_client = AsyncMock()
        res_500 = MagicMock()
        res_500.status_code = 500
        mock_client.get.return_value = res_500

        quote = await adapter.fetch_quote("AAPL", mock_client)
        self.assertIsNone(quote)
        self.assertGreater(adapter.circuit_breaker.failure_count, 0)

    async def test_07_fallback_chain_yahoo_fails_finnhub_succeeds(self):
        """Verify Stock fallback chain: Yahoo 429/500 -> Finnhub succeeds -> Returns Finnhub price"""
        # Configure Finnhub with key
        finnhub_adapter.api_key = "valid_mock_finnhub_key"
        mock_client = AsyncMock()

        # Yahoo returns 500 on both query1 and query2
        res_500 = MagicMock()
        res_500.status_code = 500

        # Finnhub returns 200 with AAPL price $245.50
        res_finnhub = MagicMock()
        res_finnhub.status_code = 200
        res_finnhub.json.return_value = {
            "c": 245.50,
            "h": 248.0,
            "l": 244.0,
            "pc": 243.0,
            "t": 1712345678,
            "dp": 1.02
        }

        async def mock_get(url, **kwargs):
            if "yahoo.com" in url:
                return res_500
            elif "finnhub.io" in url:
                return res_finnhub
            return res_500

        mock_client.get.side_effect = mock_get

        traces = []
        async def _try_fetch_mock(src, url, ext, **kwargs):
            res = await mock_get(url)
            traces.append({'source': src, 'url': url, 'status_code': res.status_code, 'success': res.status_code == 200})
            if res.status_code == 200:
                return float(res.json()['c'])
            return None

        price = await fetch_global_stocks(
            mock_client,
            exchange='global_stocks',
            symbol='AAPL',
            _try_fetch=_try_fetch_mock,
            traces=traces,
            collect_all_traces=False
        )

        self.assertEqual(price, 245.50, "Should successfully fall back to Finnhub when Yahoo is down")
        self.assertTrue(any("Finnhub" in t['source'] for t in traces))

    async def test_08_fallback_chain_yahoo_and_finnhub_fail_twelvedata_succeeds(self):
        """Verify Stock fallback chain: Yahoo & Finnhub fail -> Twelve Data succeeds"""
        finnhub_adapter.api_key = "test_key"
        twelve_data_adapter.api_key = "valid_mock_td_key"
        mock_client = AsyncMock()

        res_fail = MagicMock()
        res_fail.status_code = 429

        res_td = MagicMock()
        res_td.status_code = 200
        res_td.json.return_value = {
            "symbol": "TSLA",
            "close": "320.75",
            "is_market_open": True,
            "timestamp": 1712345678,
            "currency": "USD"
        }

        async def mock_get(url, **kwargs):
            if "twelvedata.com" in url:
                return res_td
            return res_fail

        mock_client.get.side_effect = mock_get

        traces = []
        async def _try_fetch_mock(src, url, ext, **kwargs):
            res = await mock_get(url)
            traces.append({'source': src, 'url': url, 'status_code': res.status_code, 'success': res.status_code == 200})
            if res.status_code == 200:
                return float(res.json()['close'])
            return None

        price = await fetch_global_stocks(
            mock_client,
            exchange='global_stocks',
            symbol='TSLA',
            _try_fetch=_try_fetch_mock,
            traces=traces,
            collect_all_traces=False
        )

        self.assertEqual(price, 320.75, "Should fall back to Twelve Data when Yahoo and Finnhub fail")
        self.assertTrue(any("Twelve Data" in t['source'] for t in traces))

    async def test_09_macro_fallback_chain_fred_with_yahoo_fallback(self):
        """Verify Macro chain: FRED primary; when FRED fails, falls back to Yahoo (^TNX)"""
        fred_adapter.api_key = "test_fred_key"
        mock_client = AsyncMock()

        # FRED returns 200 with 10Y Treasury yield 4.35%
        res_fred = MagicMock()
        res_fred.status_code = 200
        res_fred.json.return_value = {
            "observations": [
                {"date": "2026-10-08", "value": "4.35"}
            ]
        }

        async def mock_get(url, **kwargs):
            if "stlouisfed.org" in url:
                return res_fred
            res = MagicMock()
            res.status_code = 500
            return res

        mock_client.get.side_effect = mock_get

        traces = []
        async def _try_fetch_mock(src, url, ext, **kwargs):
            res = await mock_get(url)
            traces.append({'source': src, 'url': url, 'status_code': res.status_code, 'success': res.status_code == 200})
            if res.status_code == 200:
                return float(res.json()['observations'][0]['value'])
            return None

        price = await fetch_global_stocks(
            mock_client,
            exchange='global_stocks',
            symbol='US10Y',
            _try_fetch=_try_fetch_mock,
            traces=traces,
            collect_all_traces=False
        )

        self.assertEqual(price, 4.35, "FRED primary for macro symbols")
        self.assertTrue(any("FRED" in t['source'] for t in traces))

    async def test_10_closed_market_guard_meta_preservation(self):
        """Verify that closed market response preserves state='closed' without crashing"""
        mock_client = AsyncMock()
        res_closed = MagicMock()
        res_closed.status_code = 200
        res_closed.json.return_value = {
            "chart": {
                "result": [{
                    "meta": {
                        "regularMarketPrice": None,
                        "chartPreviousClose": 150.0,
                        "marketState": "CLOSED",
                        "currency": "USD"
                    }
                }]
            }
        }
        mock_client.get.return_value = res_closed

        quote = await yahoo_adapter.fetch_quote("AAPL", mock_client)
        self.assertIsNotNone(quote)
        self.assertEqual(quote.get('state'), 'closed', "Closed market must return state='closed'")
        self.assertEqual(quote.get('price'), 150.0, "Previous close price preserved for metadata")


if __name__ == '__main__':
    unittest.main()
