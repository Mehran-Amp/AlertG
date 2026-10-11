#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 4 Comprehensive Unit Tests:
 1. ExchangeRegistry disposeAll():
    - Clears _cachedHelpersByExchange, _cachedPairsByExchange, timestamps and pending fetches
    - Invokes dispose() on StandardRestExchange instances
 2. Pair Cache TTL & Concurrency:
    - pairCacheTtl constant defined (10 minutes)
    - _pendingPairFetches collapses concurrent requests to single in-flight Future
    - Failed/empty responses cached with timestamp to prevent tight-loop thrashing
 3. Cross-Exchange Search Performance:
    - searchPairsAcrossExchanges uses Future.wait with batch concurrency limit (6-8)
    - findExchangesForPair uses Future.wait with batch concurrency limit (6-8)
    - Individual exchange timeouts applied
 4. Magic string 'global_stocks' eliminated:
    - ExchangeRegistry.globalStocksId constant defined and used across methods
    - ExchangeCatalog.globalStocksId defined
 5. ExchangeCatalog structure & templates:
    - Clean separation of buildMarketsProviders() and buildCryptoExchanges()
    - Bitvavo uses {BASE_UPPER}-{QUOTE_UPPER}
    - Upbit uses {QUOTE_UPPER}-{BASE_UPPER}
    - BitMEX uses {BITMEX_SYMBOL}
    - StandardRestExchange.dispose() implemented
    - Exaggerated marketing claims ('100% price uptime', 'Exhaustive Catalog') removed

All tests run completely OFFLINE.
"""

import unittest
import re
import os

@unittest.skipIf(not os.path.isdir('lib'), "Flutter client code (lib/) not present in backend deployment")
class TestPhase4RegistryAndCatalog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open('lib/features/exchanges/registry/exchange_registry.dart', 'r', encoding='utf-8') as f:
            cls.registry_code = f.read()

        with open('lib/features/exchanges/registry/exchange_catalog.dart', 'r', encoding='utf-8') as f:
            cls.catalog_code = f.read()

        with open('lib/features/exchanges/base/standard_rest_exchange.dart', 'r', encoding='utf-8') as f:
            cls.standard_rest_code = f.read()

    def test_01_dispose_all_clears_all_caches_and_closes_clients(self):
        """Verify disposeAll clears _cachedHelpersByExchange and closes clients"""
        self.assertIn('_cachedHelpersByExchange.clear()', self.registry_code)
        self.assertIn('_cachedPairsByExchange.clear()', self.registry_code)
        self.assertIn('_pairCacheTimestamps.clear()', self.registry_code)
        self.assertIn('_pendingPairFetches.clear()', self.registry_code)
        self.assertIn('exchange.dispose()', self.registry_code)
        self.assertIn('void dispose()', self.standard_rest_code)

    def test_02_pair_cache_has_ttl_and_request_deduplication(self):
        """Verify TTL constant, timestamp map, and in-flight request collapsing"""
        self.assertIn('pairCacheTtl', self.registry_code)
        self.assertIn('_pairCacheTimestamps', self.registry_code)
        self.assertIn('_pendingPairFetches', self.registry_code)
        self.assertIn('now.difference(timestamp) < pairCacheTtl', self.registry_code)

    def test_03_search_pairs_uses_parallel_concurrency_pool(self):
        """Verify searchPairsAcrossExchanges and findExchangesForPair use Future.wait with limit"""
        self.assertIn('Future.wait', self.registry_code)
        self.assertIn('concurrencyLimit = 6', self.registry_code)
        self.assertIn('timeout(const Duration(seconds: 4))', self.registry_code)

    def test_04_global_stocks_constant_replaces_magic_strings(self):
        """Verify globalStocksId constant is defined and used instead of raw 'global_stocks'"""
        self.assertIn("static const String globalStocksId = 'global_stocks';", self.registry_code)
        self.assertIn("static const String globalStocksId = 'global_stocks';", self.catalog_code)
        
        # Check that registry logic uses globalStocksId
        self.assertIn("a.id == globalStocksId", self.registry_code)
        self.assertIn("e.id != globalStocksId", self.registry_code)

    def test_05_catalog_separated_into_markets_and_crypto(self):
        """Verify buildMarketsProviders and buildCryptoExchanges are cleanly separated"""
        self.assertIn('static List<Exchange> buildMarketsProviders()', self.catalog_code)
        self.assertIn('static List<Exchange> buildCryptoExchanges()', self.catalog_code)
        self.assertIn('...buildMarketsProviders()', self.catalog_code)
        self.assertIn('...buildCryptoExchanges()', self.catalog_code)

    def test_06_bitvavo_and_upbit_dynamic_quote_templates(self):
        """Verify Bitvavo uses {BASE_UPPER}-{QUOTE_UPPER} and Upbit uses {QUOTE_UPPER}-{BASE_UPPER}"""
        self.assertIn('market={BASE_UPPER}-{QUOTE_UPPER}', self.catalog_code)
        self.assertNotIn('market={BASE_UPPER}-EUR', self.catalog_code)

        self.assertIn('markets={QUOTE_UPPER}-{BASE_UPPER}', self.catalog_code)
        self.assertNotIn('markets=USDT-{BASE_UPPER}', self.catalog_code)

    def test_07_bitmex_symbol_handling(self):
        """Verify BitMEX uses {BITMEX_SYMBOL} and StandardRestExchange formats XBT/USD"""
        self.assertIn('symbol={BITMEX_SYMBOL}', self.catalog_code)
        self.assertIn('{BITMEX_SYMBOL}', self.standard_rest_code)
        self.assertIn("'XBT'", self.standard_rest_code)

    def test_08_exaggerated_marketing_comments_removed(self):
        """Verify comments like '100% price uptime' and 'Exhaustive Catalog' are removed"""
        self.assertNotIn('100% price uptime', self.catalog_code)
        self.assertNotIn('Exhaustive Catalog', self.catalog_code)


if __name__ == '__main__':
    unittest.main()
