# -*- coding: utf-8 -*-
"""
AlertG — Iranian Crypto Exchange Binding & Isolation Tests (Rule R1).
Guarantees that an alert configured on Tabdeal queries ONLY Tabdeal endpoints.
Zero cross-exchange fallback: failure on Tabdeal strictly yields NO_PRICE,
with 0 outbound HTTP calls to Nobitex, Wallex, Bitpin, Ramzinex, Binance, or any aggregator.
"""
import unittest
from unittest.mock import patch
import httpx

import app.config as config
from app.markets.base import fetch_price_with_trace


class TestIranianCryptoBinding(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self._orig_v2 = getattr(config, "CRYPTO_ENGINE_V2", False)
        config.CRYPTO_ENGINE_V2 = False

    async def asyncTearDown(self):
        config.CRYPTO_ENGINE_V2 = self._orig_v2

    async def test_01_tabdeal_alert_queries_only_tabdeal(self):
        """1. Verify that requesting Tabdeal price contacts ONLY Tabdeal, never Nobitex or Binance."""
        requested_urls = []

        async def mock_get(url, **kwargs):
            url_str = str(url)
            requested_urls.append(url_str)
            if "tabdeal.org" in url_str:
                # 271,250 Rials raw trade price -> converts to 27,125 Tomans
                return httpx.Response(
                    200,
                    json=[{"price": "271250.0", "qty": "100.0", "time": 1700000000000}],
                    request=httpx.Request("GET", url_str)
                )
            return httpx.Response(500, request=httpx.Request("GET", url_str))

        client = httpx.AsyncClient()
        with patch.object(client, "get", side_effect=mock_get):
            price, returned_traces = await fetch_price_with_trace(
                client=client,
                exchange="tabdeal",
                symbol="USDTIRT",
                collect_all_traces=True
            )

        # Assert result came strictly from Tabdeal and was converted to Tomans
        self.assertIsNotNone(price)
        self.assertEqual(price, 27125.0)

        # Assert ALL requested URLs belong strictly to Tabdeal
        self.assertGreater(len(requested_urls), 0)
        for url in requested_urls:
            self.assertIn("tabdeal.org", url, f"Forbidden cross-exchange URL called: {url}")
            self.assertNotIn("nobitex", url.lower())
            self.assertNotIn("wallex", url.lower())
            self.assertNotIn("bitpin", url.lower())
            self.assertNotIn("binance", url.lower())

    async def test_02_tabdeal_failure_returns_no_price_with_zero_foreign_calls(self):
        """2. When Tabdeal returns error, engine must return NO_PRICE with zero fallback to other exchanges."""
        requested_urls = []

        async def mock_get_failing(url, **kwargs):
            url_str = str(url)
            requested_urls.append(url_str)
            # Simulate Tabdeal 500 error / offline
            return httpx.Response(500, request=httpx.Request("GET", url_str))

        client = httpx.AsyncClient()
        with patch.object(client, "get", side_effect=mock_get_failing):
            price, returned_traces = await fetch_price_with_trace(
                client=client,
                exchange="tabdeal",
                symbol="BTCUSDT",
                collect_all_traces=True
            )

        # Strict isolation: must return None (NO_PRICE), never fall back to Binance or Nobitex
        self.assertIsNone(price, "Engine must NOT return a fallback price when Tabdeal fails")

        # Verify zero calls to foreign exchanges
        self.assertGreater(len(requested_urls), 0)
        for url in requested_urls:
            self.assertIn("tabdeal.org", url)
            self.assertNotIn("binance", url.lower())
            self.assertNotIn("nobitex", url.lower())
            self.assertNotIn("mexc", url.lower())

    async def test_03_foreign_prices_never_bleed_into_tabdeal(self):
        """3. Even if Binance or Nobitex has a price, Tabdeal alert receives ONLY Tabdeal's price."""
        requested_urls = []

        async def mock_get_divergent(url, **kwargs):
            url_str = str(url)
            requested_urls.append(url_str)
            if "tabdeal.org" in url_str:
                return httpx.Response(
                    200,
                    json=[{"price": "77777.0", "qty": "1.0", "time": 1700000000000}],
                    request=httpx.Request("GET", url_str)
                )
            if "binance" in url_str:
                return httpx.Response(200, json={"price": "99999.0"}, request=httpx.Request("GET", url_str))
            return httpx.Response(500, request=httpx.Request("GET", url_str))

        client = httpx.AsyncClient()
        with patch.object(client, "get", side_effect=mock_get_divergent):
            price, _ = await fetch_price_with_trace(
                client=client,
                exchange="tabdeal",
                symbol="BTCUSDT",
                collect_all_traces=False
            )

        self.assertEqual(price, 77777.0, "Tabdeal alert must receive Tabdeal's price exclusively")


if __name__ == "__main__":
    unittest.main()
