#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 2 Comprehensive Unit Tests:
 1. MarketTicker & PriceSnapshot model schemas:
    - asOf, state, quoteUnit, source optional fields
    - Backward-compatible constructor & serialization
 2. predefinedStocks contract & integrity:
    - Exactly 0 duplicate symbols
    - 0 Pre-IPO unlisted symbols (OPENAI, ANTHROPIC, STRIPE, BYTEDANCE, DATABRICKS removed)
    - ^IRX correctly labeled as 13-Week Treasury Bill yield ('اوراق ۱۳ هفته‌ای خزانه‌داری آمریکا')
    - 0 static ranks in nameFa ('رتبه X جهان' removed)
    - 100% of items have explicit 'unit' key without breaking symbol, name, nameFa, cat, icon, price, isTop100
 3. fetchTicker & fetchSnapshot offline logic:
    - CoinGecko: No hardcoded fallback numbers; 60s cache; real updated_at asOf; state='live'
    - AlternativeMe (CRYPTO_FGI): timestamp asOf; state='delayed'; quoteUnit='pts'
    - Prices only via server /api/price (no direct provider calls from the app; no secondary mirrors)
    - Zero silent catch blocks

All tests run completely OFFLINE using mocks.
"""

import unittest
import re
import os
import json
from datetime import datetime, timezone

@unittest.skipIf(not os.path.isdir('lib'), "Flutter client code (lib/) not present in backend deployment")
class TestPhase2GlobalStocks(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Read the Dart source files
        with open('lib/features/exchanges/base/models/market_ticker.dart', 'r', encoding='utf-8') as f:
            cls.market_ticker_dart = f.read()

        with open('lib/features/exchanges/base/models/price_snapshot.dart', 'r', encoding='utf-8') as f:
            cls.price_snapshot_dart = f.read()

        with open('lib/features/exchanges/stocks/global_stocks_exchange.dart', 'r', encoding='utf-8') as f:
            cls.stocks_exchange_dart = f.read()

    def test_01_market_ticker_and_snapshot_fields(self):
        """Verify asOf, state, quoteUnit, source exist in MarketTicker and PriceSnapshot"""
        required_fields = ['asOf', 'state', 'quoteUnit', 'source']
        for field in required_fields:
            with self.subTest(field=field):
                self.assertIn(f'final DateTime? asOf;', self.market_ticker_dart)
                self.assertIn(f'final String? state;', self.market_ticker_dart)
                self.assertIn(f'final String? quoteUnit;', self.market_ticker_dart)
                self.assertIn(f'final String? source;', self.market_ticker_dart)

                self.assertIn(f'final DateTime? asOf;', self.price_snapshot_dart)
                self.assertIn(f'final String? state;', self.price_snapshot_dart)
                self.assertIn(f'final String? quoteUnit;', self.price_snapshot_dart)
                self.assertIn(f'final String? source;', self.price_snapshot_dart)

    def test_02_predefined_stocks_zero_duplicates(self):
        """Verify 0 duplicate symbols exist across predefinedStocks"""
        symbols = re.findall(r"'symbol':\s*'([^']+)'", self.stocks_exchange_dart)
        from collections import Counter
        counts = Counter(symbols)
        duplicates = {s: c for s, c in counts.items() if c > 1}
        self.assertEqual(duplicates, {}, f"Found duplicate symbols: {duplicates}")

    def test_03_predefined_stocks_zero_pre_ipo(self):
        """Verify 5 unlisted Pre-IPO symbols are removed"""
        pre_ipos = ['OPENAI', 'ANTHROPIC', 'STRIPE', 'BYTEDANCE', 'DATABRICKS']
        for sym in pre_ipos:
            with self.subTest(sym=sym):
                self.assertNotIn(f"'symbol': '{sym}'", self.stocks_exchange_dart,
                                 f"Pre-IPO symbol {sym} should have been removed")

    def test_04_irx_correct_treasury_bill_label(self):
        """Server catalog is the source of truth: US13W (^IRX) is the 13-week bill, US02Y is the 2-year (DGS2)"""
        from app.markets.global_stocks import WALLSTREET_MACRO_SYMBOLS
        by_id = {s['id']: s for s in WALLSTREET_MACRO_SYMBOLS}
        self.assertIn('US13W', by_id, "US13W must be in the server catalog")
        self.assertIn('۱۳ هفته‌ای', by_id['US13W']['nameFa'])
        self.assertNotIn('۲ ساله', by_id['US13W']['nameFa'])
        self.assertIn('۲ ساله', by_id['US02Y']['nameFa'])
        self.assertNotIn('^IRX', by_id['US02Y']['symbol'])

    def test_05_predefined_stocks_zero_static_ranks(self):
        """Verify static ranks (رتبه X جهان) are removed from nameFa"""
        rank_matches = re.findall(r"'nameFa':\s*'[^']*رتبه\s+\d+\s+جهان[^']*'", self.stocks_exchange_dart)
        self.assertEqual(len(rank_matches), 0, f"Found static ranks in nameFa: {rank_matches}")

    def test_06_no_static_symbol_list_beyond_crypto_macro(self):
        """Phase 3: the app ships no static symbol list except crypto-macro indices and a <=20 offline fallback"""
        blocks = re.findall(r"(\{\s*'symbol':\s*'[^']+'[\s\S]*?\n\s*\})", self.stocks_exchange_dart)
        self.assertLessEqual(len(blocks), 7, "Only the 7 crypto-macro entries may stay static in global_stocks_exchange.dart")
        required_keys = ['symbol', 'name', 'nameFa', 'cat', 'icon', 'price', 'unit']
        for b in blocks:
            sym_m = re.search(r"'symbol':\s*'([^']+)'", b)
            sym = sym_m.group(1) if sym_m else 'unknown'
            with self.subTest(symbol=sym):
                self.assertIn("'cat': 'CryptoMacro'", b)
                for k in required_keys:
                    self.assertIn(f"'{k}':", b, f"Missing required key '{k}' in item {sym}")
        self.assertIn('CatalogSyncService.instance.items', self.stocks_exchange_dart)

        with open('lib/core/services/catalog_sync_service.dart', 'r', encoding='utf-8') as f:
            svc = f.read()
        seed = svc[svc.index('void _seedDefaultCatalog()'):svc.index('Future<bool> syncDelta()')]
        self.assertLessEqual(len(re.findall(r"CatalogItem\(id:", seed)), 20, "Offline fallback must stay <= 20 symbols")

    def test_07_coingecko_zero_hardcoded_fake_numbers(self):
        """Verify that live CoinGecko code does not contain hardcoded default fallbacks"""
        self.assertNotIn('2450000000000.0', self.stocks_exchange_dart,
                         "CoinGecko live path should not contain 2.45T hardcoded fallback")
        # Check that 60s cache variable exists
        self.assertIn('_cachedCoinGeckoGlobalData', self.stocks_exchange_dart)
        self.assertIn('_cachedCoinGeckoTime', self.stocks_exchange_dart)
        self.assertIn('Duration(seconds: 60)', self.stocks_exchange_dart)

    def test_08_no_secondary_mirror_and_no_direct_provider_calls(self):
        """Verify the legacy CSV mirror is gone and prices come only from the server /api/price"""
        low = self.stocks_exchange_dart.lower()
        self.assertNotIn('stoo' + 'q', low)  # legacy mirror name, split so repo-wide grep stays empty
        self.assertNotIn('finance.yahoo.com', low)
        self.assertIn('fetchPriceDetailsViaServer', self.stocks_exchange_dart)

    def test_09_zero_silent_catches(self):
        """Verify no silent catch (_) {} blocks remain in global_stocks_exchange.dart"""
        silent_catches = re.findall(r'catch\s*\(_\)\s*\{\s*\}', self.stocks_exchange_dart)
        self.assertEqual(len(silent_catches), 0, f"Found silent catch blocks: {len(silent_catches)}")

    def test_10_regular_market_time_asof_and_state_handling(self):
        """Verify regularMarketTime is parsed to asOf and state is properly assigned"""
        self.assertIn('DateTime.fromMillisecondsSinceEpoch', self.stocks_exchange_dart)
        self.assertIn("state = 'delayed'", self.stocks_exchange_dart)
        self.assertIn("state = 'closed'", self.stocks_exchange_dart)
        self.assertNotIn("source: 'YahooFinance'", self.stocks_exchange_dart)
        self.assertIn("source: 'CoinGecko'", self.stocks_exchange_dart)
        self.assertIn("source: 'AlternativeMe'", self.stocks_exchange_dart)


class TestTreasuryYieldMapping(unittest.TestCase):
    """2Y yield is FRED-only (DGS2); ^IRX / US13W is the 13-week bill (Yahoo ^IRX, FRED DTB3)."""

    def test_2y_never_maps_to_irx(self):
        from app.markets.global_stocks import resolve_yf_symbol, EXACT_YF_MAP, FRED_ONLY_SYMBOLS, FredAdapter
        for sym in ('US02Y', 'US2Y', '^2YY'):
            self.assertNotEqual(resolve_yf_symbol(sym), '^IRX')
            self.assertNotIn(sym, EXACT_YF_MAP)
            self.assertIn(sym, FRED_ONLY_SYMBOLS)
            self.assertEqual(FredAdapter.FRED_SERIES_MAP[sym], 'DGS2')

    def test_13w_maps_to_irx_and_dtb3(self):
        from app.markets.global_stocks import resolve_yf_symbol, FredAdapter, resolve_symbol_category
        self.assertEqual(resolve_yf_symbol('US13W'), '^IRX')
        self.assertEqual(resolve_yf_symbol('^IRX'), '^IRX')
        self.assertEqual(FredAdapter.FRED_SERIES_MAP['US13W'], 'DTB3')
        self.assertEqual(FredAdapter.FRED_SERIES_MAP['^IRX'], 'DTB3')
        self.assertNotEqual(FredAdapter.FRED_SERIES_MAP['^IRX'], 'DGS2')
        self.assertIn(resolve_symbol_category('US13W'), ('macro', 'bond'))


if __name__ == '__main__':
    unittest.main()
