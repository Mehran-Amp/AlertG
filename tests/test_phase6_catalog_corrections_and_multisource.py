#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit Tests for Catalog Corrections & Multi-Source Observability:
1. 11 Pre-IPO symbols removed from catalog.json, candidate catalogs, and global stocks.
2. USDT_TMN removed from global forex and preserved exclusively in Iran catalog.
3. Treasury Bonds:
   - Clean tickers (^TNX, DGS2, ^IRX, ^TYX) with NO parentheses
   - Explicit provider_map
   - US02Y strictly FRED-only (DGS2) with data_frequency=daily
4. Macro Indicators (CPIAUCSL, WALCL, M2SL):
   - Units read from FRED metadata (not static %)
   - Separation of unit_match from currency_match
5. probe_catalog.py Observability:
   - latency_ms is None (null) on failed probes
   - expected_currency normalized with ISO code or standard indicator
   - secondary_probed and confirmed_single_source fields
   - provider_prices and price_difference_pct stored in reports

All tests execute strictly OFFLINE with NO external network requests.
"""

import os
import sys
import json
import unittest
import asyncio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.markets.global_stocks import (
    WALLSTREET_MACRO_SYMBOLS,
    EXACT_YF_MAP,
    FRED_ONLY_SYMBOLS,
    FredAdapter,
    fred_adapter,
    resolve_yf_symbol,
    resolve_symbol_alias,
)
from scripts.probe_catalog import (
    CatalogProbeRunner,
    check_currency_match,
    check_unit_match,
    normalize_expected_currency,
    is_sampled_for_secondary_rotation,
)
from scripts.validate_catalog_offline import validate_catalog_file


class TestCatalogCorrectionsAndMultiSource(unittest.TestCase):

    def setUp(self):
        self.pre_ipo_symbols = {
            'SPACEX', 'STARLINK', 'XAI', 'X_CORP', 'NEURALINK',
            'BORING', 'DOGE_MUSK', 'OPENAI', 'ANTHROPIC', 'STRIPE', 'BYTEDANCE'
        }

    def test_01_pre_ipo_and_usdt_tmn_removed_from_global_catalogs(self):
        """Verify 11 Pre-IPO symbols and USDT_TMN are completely removed from global catalog and seeds."""
        with open(os.path.join(ROOT, 'catalog.json'), 'r', encoding='utf-8') as f:
            cat = json.load(f)

        catalog_symbols = [s.get('id') or s.get('symbol') for s in cat.get('symbols', [])]
        for sym in self.pre_ipo_symbols:
            self.assertNotIn(sym, catalog_symbols, f"Pre-IPO symbol {sym} must be removed from catalog.json")

        self.assertNotIn('USDT_TMN', catalog_symbols, "USDT_TMN must not be in global catalog.json")

        # Check candidate_catalog_full.json
        with open(os.path.join(ROOT, 'candidate_catalog_full.json'), 'r', encoding='utf-8') as f:
            cand = json.load(f)
        cand_symbols = [s.get('id') or s.get('symbol') for s in cand.get('symbols', [])]
        for sym in self.pre_ipo_symbols:
            self.assertNotIn(sym, cand_symbols, f"Pre-IPO symbol {sym} must be removed from candidate_catalog_full.json")
        self.assertNotIn('USDT_TMN', cand_symbols)

        # Check WALLSTREET_MACRO_SYMBOLS
        macro_ids = [s.get('id') for s in WALLSTREET_MACRO_SYMBOLS]
        for sym in self.pre_ipo_symbols:
            self.assertNotIn(sym, macro_ids, f"Pre-IPO symbol {sym} must be removed from WALLSTREET_MACRO_SYMBOLS")
        self.assertNotIn('USDT_TMN', macro_ids)

        # Check USDT_TMN is in iran_catalog.json
        with open(os.path.join(ROOT, 'iran_catalog.json'), 'r', encoding='utf-8') as f:
            iran_cat = json.load(f)
        iran_ids = [s.get('id') for s in iran_cat.get('symbols', [])]
        self.assertIn('USDT_TMN', iran_ids, "USDT_TMN must be present in iran_catalog.json under iran_market")

    def test_02_treasury_bonds_clean_tickers_and_provider_maps(self):
        """Verify bond symbols have clean tickers (^TNX, DGS2, ^IRX, ^TYX) with NO parentheses and explicit provider_map."""
        with open(os.path.join(ROOT, 'catalog.json'), 'r', encoding='utf-8') as f:
            cat = json.load(f)

        bond_map = {s.get('id'): s for s in cat.get('symbols', []) if s.get('id') in ('US10Y', 'US02Y', 'US13W', 'US30Y')}
        self.assertEqual(len(bond_map), 4)

        # US10Y
        self.assertEqual(bond_map['US10Y']['symbol'], '^TNX')
        self.assertNotIn('(', bond_map['US10Y']['symbol'])
        self.assertIn('yahoo', bond_map['US10Y']['provider_map'])
        self.assertIn('fred', bond_map['US10Y']['provider_map'])

        # US02Y
        self.assertEqual(bond_map['US02Y']['symbol'], 'DGS2')
        self.assertNotIn('(', bond_map['US02Y']['symbol'])
        self.assertEqual(list(bond_map['US02Y']['provider_map'].keys()), ['fred'])
        self.assertEqual(bond_map['US02Y'].get('data_frequency'), 'daily')
        self.assertIn('DGS2', FRED_ONLY_SYMBOLS)

        # US13W
        self.assertEqual(bond_map['US13W']['symbol'], '^IRX')
        self.assertNotIn('(', bond_map['US13W']['symbol'])

        # US30Y
        self.assertEqual(bond_map['US30Y']['symbol'], '^TYX')
        self.assertNotIn('(', bond_map['US30Y']['symbol'])
        self.assertEqual(EXACT_YF_MAP.get('US30Y'), '^TYX')
        self.assertEqual(EXACT_YF_MAP.get('^TYX'), '^TYX')

    def test_03_macro_fred_series_units_and_separation(self):
        """Verify macro series units in FRED_SERIES_METADATA and unit_match / currency_match separation."""
        meta = FredAdapter.FRED_SERIES_METADATA

        # CPIAUCSL is an index level, not %
        self.assertIn('CPIAUCSL', meta)
        self.assertIn('Index', meta['CPIAUCSL']['units'])
        self.assertEqual(meta['CPIAUCSL']['currency'], 'PTS')

        # WALCL is millions of dollars
        self.assertIn('WALCL', meta)
        self.assertIn('Millions', meta['WALCL']['units'])
        self.assertEqual(meta['WALCL']['currency'], 'USD')

        # M2SL is billions of dollars
        self.assertIn('M2SL', meta)
        self.assertIn('Billions', meta['M2SL']['units'])
        self.assertEqual(meta['M2SL']['currency'], 'USD')

        # Unit match separation
        self.assertTrue(check_unit_match('Index 1982-1984=100', 'Index 1982-1984=100', category='macro'))
        self.assertTrue(check_unit_match('Millions of U.S. Dollars', 'Mil. of U.S. $', category='macro'))
        self.assertTrue(check_unit_match('%', '%', category='bond'))

        # Currency match
        self.assertTrue(check_currency_match('PTS', 'PTS', category='macro'))
        self.assertTrue(check_currency_match('USD', 'USD', category='macro'))
        self.assertTrue(check_currency_match('%', '%', category='bond'))
        self.assertTrue(check_currency_match('%', 'USD', category='bond'))  # Yahoo quotes bond in USD

    def test_04_probe_catalog_failure_latency_null(self):
        """Verify that failed symbols return latency_ms=None (null), not misleading 0.0."""
        runner = CatalogProbeRunner(
            catalog_path=os.path.join(ROOT, 'catalog.json'),
            checkpoint_path='/tmp/test_probe_null_lat_cp.json',
            report_path='/tmp/test_probe_null_lat_rep.json',
            rejected_path='/tmp/test_probe_null_lat_rej.json',
            yields_path='/tmp/test_probe_null_lat_yld.json',
            summary_path='/tmp/test_probe_null_lat_sum.json',
            offline=True
        )

        invalid_item = {
            'id': 'NON_EXISTENT_TICKER_XYZ',
            'symbol': 'UNKNOWN_REJECT',
            'nameEn': 'Fake Stock',
            'category': 'stock',
            'marketName': 'None',
            'unit': '$'
        }

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            res, is_rej, rej_item = loop.run_until_complete(runner.probe_single_symbol(invalid_item, None))
            self.assertTrue(is_rej)
            self.assertEqual(res['status'], 'failed')
            self.assertIsNone(res['latency_ms'], "Failed symbols must have latency_ms=None (null), not 0.0")
        finally:
            loop.close()

    def test_05_secondary_probed_and_confirmed_single_source_and_price_diff(self):
        """Verify secondary_probed, confirmed_single_source, provider_prices, and price_difference_pct."""
        runner = CatalogProbeRunner(
            catalog_path=os.path.join(ROOT, 'catalog.json'),
            checkpoint_path='/tmp/test_probe_multi_cp.json',
            report_path='/tmp/test_probe_multi_rep.json',
            rejected_path='/tmp/test_probe_multi_rej.json',
            yields_path='/tmp/test_probe_multi_yld.json',
            summary_path='/tmp/test_probe_multi_sum.json',
            offline=True,
            sample_rate_secondary=1.0  # Force secondary probing
        )

        major_stock = {
            'id': 'AAPL',
            'symbol': 'AAPL',
            'nameEn': 'Apple Inc.',
            'category': 'stock',
            'tier': 1,
            'marketName': 'NASDAQ',
            'unit': '$'
        }

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            res, is_rej, _ = loop.run_until_complete(runner.probe_single_symbol(major_stock, None))
            self.assertFalse(is_rej)
            self.assertTrue(res['secondary_probed'], "Secondary should be flagged as probed")
            self.assertFalse(res['confirmed_single_source'], "Multi-source stock should not be confirmed single source")
            self.assertFalse(res['single_source'])
            self.assertIn('yahoo', res['provider_prices'])
            self.assertIn('finnhub', res['provider_prices'])
            self.assertIsNotNone(res['price_difference_pct'])
            self.assertIsInstance(res['price_difference_pct'], float)

            # Test symbol without secondary probing
            runner.sample_rate_secondary = 0.0
            non_major = {
                'id': 'SMALL_STOCK_1',
                'symbol': 'SMALL1',
                'nameEn': 'Small Stock',
                'category': 'stock',
                'tier': 3,
                'marketName': 'OTC',
                'unit': '$'
            }
            res_small, _, _ = loop.run_until_complete(runner.probe_single_symbol(non_major, None))
            self.assertFalse(res_small['secondary_probed'])
            # Since secondary was NOT probed, confirmed_single_source should be None
            self.assertIsNone(res_small['confirmed_single_source'])
        finally:
            loop.close()

    def test_06_expected_currency_iso_normalization(self):
        """Verify expected_currency normalizes symbols to ISO standards."""
        self.assertEqual(normalize_expected_currency('$'), 'USD')
        self.assertEqual(normalize_expected_currency('€'), 'EUR')
        self.assertEqual(normalize_expected_currency('£'), 'GBP')
        self.assertEqual(normalize_expected_currency('¥'), 'JPY')
        self.assertEqual(normalize_expected_currency('ت'), 'TMN')
        self.assertEqual(normalize_expected_currency('%'), '%')
        self.assertEqual(normalize_expected_currency('Index 1982-1984=100'), 'PTS')
        self.assertEqual(normalize_expected_currency('Millions of U.S. Dollars'), 'USD')

    def test_07_validate_catalog_offline_passes(self):
        """Verify validate_catalog_offline passes for catalog.json, seed/bonds.json, and seed/macro.json."""
        for path in ['catalog.json', 'seed/bonds.json', 'seed/macro.json']:
            full_path = os.path.join(ROOT, path)
            is_valid, errors = validate_catalog_file(full_path)
            self.assertTrue(is_valid, f"{path} failed offline validation: {errors}")

    def test_08_dow_equity_vs_dowjones_index_resolution(self):
        """Verify Dow Inc. (id=DOW) resolves to equity 'DOW', not the '^DJI' index."""
        from app.engine.categories import resolve_symbol_category
        # 1. resolve_yf_symbol for 'DOW' and ('global_stocks', 'DOW') != '^DJI'
        self.assertNotEqual(resolve_yf_symbol('global_stocks', 'DOW'), '^DJI')
        self.assertEqual(resolve_yf_symbol('global_stocks', 'DOW'), 'DOW')
        self.assertEqual(resolve_yf_symbol('DOW'), 'DOW')

        # 2. DJI and DOWJONES resolve to '^DJI'
        self.assertEqual(resolve_yf_symbol('DJI'), '^DJI')
        self.assertEqual(resolve_yf_symbol('global_stocks', 'DJI'), '^DJI')
        self.assertEqual(resolve_yf_symbol('DOWJONES'), '^DJI')

        # 3. Category for DOW is 'stock', whereas DJI is 'index'
        self.assertEqual(resolve_symbol_category('global_stocks', 'DOW'), 'stock')
        self.assertEqual(resolve_symbol_category('global_stocks', 'DJI'), 'index')

        # 4. 'DOW' is not an index alias in EXACT_YF_MAP
        self.assertNotIn('DOW', EXACT_YF_MAP)

    def test_09_no_two_non_alias_ids_share_same_provider_symbol_in_catalog(self):
        """Global test verifying that no two non-alias IDs share the same provider_symbol in catalog.json."""
        cat_path = os.path.join(ROOT, 'catalog.json')
        with open(cat_path, 'r', encoding='utf-8') as f:
            cat_data = json.load(f)

        symbols = cat_data.get('symbols', [])
        # Provider symbol mapping: provider_symbol -> list of item ids
        provider_map_seen = {}
        for item in symbols:
            item_id = item.get('id')
            prov_map = item.get('provider_map')
            if prov_map and isinstance(prov_map, dict):
                for p_name, p_info in prov_map.items():
                    if isinstance(p_info, dict) and 'symbol' in p_info:
                        key = (p_name, p_info['symbol'])
                        provider_map_seen.setdefault(key, []).append(item_id)
            else:
                # Fallback to resolved Yahoo symbol
                yf_sym = resolve_yf_symbol(item.get('symbol', item_id))
                key = ('yahoo_resolved', yf_sym)
                provider_map_seen.setdefault(key, []).append(item_id)

        conflicts = {k: v for k, v in provider_map_seen.items() if len(v) > 1}
        self.assertEqual(conflicts, {}, f"Found multiple non-alias IDs mapped to the same provider symbol: {conflicts}")

    def test_10_usdcny_duplicate_removed_and_aliased(self):
        """Verify USDCNY is removed from catalog.json and aliased to USD_CNY."""
        cat_path = os.path.join(ROOT, 'catalog.json')
        with open(cat_path, 'r', encoding='utf-8') as f:
            cat_data = json.load(f)

        ids = [s.get('id') for s in cat_data.get('symbols', [])]
        self.assertNotIn('USDCNY', ids, "USDCNY duplicate must be removed from catalog.json")
        self.assertIn('USD_CNY', ids, "Canonical USD_CNY must exist in catalog.json")
        self.assertEqual(resolve_symbol_alias('USDCNY'), 'USD_CNY')

    def test_11_all_symbols_have_currency_populated(self):
        """Verify currency field is populated (non-None) for all symbols in catalog.json."""
        cat_path = os.path.join(ROOT, 'catalog.json')
        with open(cat_path, 'r', encoding='utf-8') as f:
            cat_data = json.load(f)

        symbols = cat_data.get('symbols', [])
        missing_currency = [s.get('id') for s in symbols if not s.get('currency')]
        self.assertEqual(missing_currency, [], f"Symbols missing currency in catalog.json: {missing_currency}")


if __name__ == '__main__':
    unittest.main()

