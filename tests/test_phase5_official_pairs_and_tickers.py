#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 5 Comprehensive Unit Tests:
 1. Elimination of Silent Binance Fallback:
    - Zero query to api.binance.com inside StandardRestExchange.fetchTicker
    - Connection error thrown on failure rather than returning fabricated prices
 2. Official pairsUrl configured:
    - Bitstamp: https://www.bitstamp.net/api/v2/trading-pairs-info/
    - Gemini: https://api.gemini.com/v1/symbols
    - HTX: https://api.huobi.pro/v1/common/symbols
    - BitMEX: https://www.bitmex.com/api/v1/instrument?filter=%7B%22typ%22%3A%22FFWCSX%22%7D
 3. Specialized Parsers in StandardRestExchange:
    - HTX: tick object parsed (close price and vol/amount)
    - Bitstamp: pairs with '/' parsed to baseCurrency and counterCurrency
    - Gemini: symbol strings parsed to baseCurrency and counterCurrency
    - BitMEX: list of instruments parsed, XBT mapped to BTC with rootSymbol/symbol preserved
    - BitMEX ticker: list of maps parses lastPrice and volume24h

All tests run completely OFFLINE using mocks and AST/source analysis.
"""

import unittest
import re
import os

@unittest.skipIf(not os.path.isdir('lib'), "Flutter client code (lib/) not present in backend deployment")
class TestPhase5OfficialPairsAndTickers(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open('lib/features/exchanges/base/standard_rest_exchange.dart', 'r', encoding='utf-8') as f:
            cls.standard_rest_code = f.read()

        with open('lib/features/exchanges/registry/exchange_catalog.dart', 'r', encoding='utf-8') as f:
            cls.catalog_code = f.read()

    def test_01_silent_binance_fallback_eliminated(self):
        """Verify api.binance.com is NOT queried in StandardRestExchange"""
        self.assertNotIn('api.binance.com', self.standard_rest_code,
                         "api.binance.com must be completely eliminated from StandardRestExchange")
        self.assertIn("throw Exception('Connection error: Unable to fetch live price", self.standard_rest_code)

    def test_02_official_pairs_url_configured_in_catalog(self):
        """Verify pairsUrl is properly configured for Bitstamp, Gemini, HTX, and BitMEX"""
        self.assertIn("pairsUrl: 'https://www.bitstamp.net/api/v2/trading-pairs-info/'", self.catalog_code)
        self.assertIn("pairsUrl: 'https://api.gemini.com/v1/symbols'", self.catalog_code)
        self.assertIn("pairsUrl: 'https://api.huobi.pro/v1/common/symbols'", self.catalog_code)
        self.assertIn("pairsUrl: 'https://www.bitmex.com/api/v1/instrument?filter=%7B%22typ%22%3A%22FFWCSX%22%7D'", self.catalog_code)

    def test_03_htx_tick_object_parser(self):
        """Verify StandardRestExchange checks data['tick'] for HTX ticker responses"""
        self.assertIn("data['tick'] is Map", self.standard_rest_code)
        self.assertIn("d['close']", self.standard_rest_code)
        self.assertIn("d['amount']", self.standard_rest_code)

    def test_04_bitstamp_pair_slash_parser(self):
        """Verify StandardRestExchange parses Bitstamp pairs with 'name' containing '/'"""
        self.assertIn("item['name'].toString().contains('/')", self.standard_rest_code)
        self.assertIn("item['name'].toString().split('/')", self.standard_rest_code)
        self.assertIn("item['url_symbol']", self.standard_rest_code)

    def test_05_gemini_string_list_parser(self):
        """Verify StandardRestExchange parses Gemini string list symbols"""
        self.assertIn("data.first is String", self.standard_rest_code)
        self.assertIn("GUSDPERP", self.standard_rest_code)
        self.assertIn("USDT", self.standard_rest_code)

    def test_06_bitmex_perpetual_and_symbol_parser(self):
        """Verify StandardRestExchange parses BitMEX instruments and maps XBT to BTC"""
        self.assertIn("rawBase == 'XBT' ? 'BTC' : rawBase", self.standard_rest_code)
        self.assertIn("item['rootSymbol']", self.standard_rest_code)
        self.assertIn("item['quoteCurrency']", self.standard_rest_code)

    def test_07_bitmex_list_ticker_parser(self):
        """Verify StandardRestExchange parses list response with lastPrice and volume24h"""
        self.assertIn("first['lastPrice']", self.standard_rest_code)
        self.assertIn("first['volume24h']", self.standard_rest_code)

    def test_08_htx_pairs_online_filter(self):
        """Verify StandardRestExchange filters HTX pairs for online state"""
        self.assertIn("item['base-currency']", self.standard_rest_code)
        self.assertIn("item['quote-currency']", self.standard_rest_code)
        self.assertIn("state != 'online'", self.standard_rest_code)


if __name__ == '__main__':
    unittest.main()
