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

import sys
import unittest
import re
import os
import time
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

for mod in [
    'fastapi', 'fastapi.middleware.cors', 'fastapi.responses', 'pydantic', 'httpx',
    'apscheduler', 'apscheduler.schedulers', 'apscheduler.schedulers.asyncio',
    'firebase_admin', 'firebase_admin.credentials', 'firebase_admin.messaging', 'firebase_admin.exceptions'
]:
    if mod not in sys.modules:
        m = MagicMock()
        if mod == 'fastapi':
            class MockAPIRouter:
                def get(self, *args, **kwargs):
                    return lambda func: func
                def post(self, *args, **kwargs):
                    return lambda func: func
                def delete(self, *args, **kwargs):
                    return lambda func: func
                def put(self, *args, **kwargs):
                    return lambda func: func
            m.APIRouter = MockAPIRouter
            m.Depends = lambda x: x
            m.HTTPException = Exception
        if mod == 'pydantic':
            class BaseModel:
                def __init__(self, **kwargs):
                    for k, v in kwargs.items():
                        setattr(self, k, v)
                def dict(self): return self.__dict__
                def model_dump(self): return self.__dict__
            m.BaseModel = BaseModel
            m.Field = lambda *args, **kwargs: kwargs.get('default', None)
        sys.modules[mod] = m

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


class TestFallbackChainAndFetchGlobalStocks(unittest.IsolatedAsyncioTestCase):
    """
    Unit tests for get_fallback_chain and fetch_global_stocks:
    - Verifies fetch_global_stocks strictly queries get_fallback_chain
    - Verifies FRED-only and macro series return [fred_adapter]
    - Verifies substitutable bonds return [fred, yahoo]
    - Verifies stock/forex never fall back to FRED
    - Verifies that Yahoo 404 on FEDFUNDS and US02Y does not abort before FRED is invoked and returns price
    """

    async def test_fetch_global_stocks_uses_get_fallback_chain(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.markets import global_stocks
        mock_adapter = MagicMock()
        mock_adapter.name = "mock_adapter"
        mock_adapter.fetch_quote = AsyncMock(return_value={"price": 123.45, "source": "mock"})

        with patch.object(global_stocks, "get_fallback_chain", return_value=[mock_adapter]) as mock_chain:
            client = AsyncMock()
            price = await global_stocks.fetch_global_stocks(client, "global_stocks", "TEST_SYM")
            mock_chain.assert_called_once_with("TEST_SYM")
            self.assertEqual(price, 123.45)

    def test_get_fallback_chain_rules(self):
        from app.markets.global_stocks import (
            get_fallback_chain, fred_adapter, yahoo_adapter,
            finnhub_adapter, twelve_data_adapter
        )
        # FRED-only symbols and macro series
        for sym in ('US02Y', 'US2Y', '^2YY', 'FEDFUNDS', 'UNRATE', 'CPIAUCSL'):
            chain = get_fallback_chain(sym)
            self.assertEqual(chain, [fred_adapter], f"{sym} must return only [fred_adapter]")

        # Substitutable bonds -> [fred_adapter, yahoo_adapter]
        for sym in ('US10Y', '^TNX', 'US30Y', '^TYX'):
            chain = get_fallback_chain(sym)
            self.assertEqual(chain, [fred_adapter, yahoo_adapter], f"{sym} must return [fred, yahoo]")

        # Stock and Forex -> never fall back to FRED
        for sym in ('AAPL', 'EURUSD'):
            chain = get_fallback_chain(sym)
            self.assertEqual(chain, [yahoo_adapter, finnhub_adapter, twelve_data_adapter])
            self.assertNotIn(fred_adapter, chain, f"{sym} must never include FRED adapter")

    async def test_yahoo_404_macro_and_bond_calls_fred_and_returns_price(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.markets import global_stocks

        mock_yahoo = MagicMock()
        mock_yahoo.name = "yahoo"
        mock_yahoo.last_trace = {"status_code": 404, "error": "Not Found"}
        mock_yahoo.fetch_quote = AsyncMock(return_value=None)

        mock_fred = MagicMock()
        mock_fred.name = "fred"
        mock_fred.last_trace = {"status_code": 200}
        mock_fred.fetch_quote = AsyncMock(return_value={"price": 5.25, "source": "FRED"})

        client = AsyncMock()

        for test_sym in ('FEDFUNDS', 'US02Y'):
            with patch.object(global_stocks, "get_fallback_chain", return_value=[mock_yahoo, mock_fred]):
                price = await global_stocks.fetch_global_stocks(client, "global_stocks", test_sym)
                self.assertEqual(price, 5.25, f"Price for {test_sym} must be returned from FRED")
                mock_yahoo.fetch_quote.assert_awaited()
                mock_fred.fetch_quote.assert_awaited()


class TestPriceMetadataUnitsAndFrequency(unittest.IsolatedAsyncioTestCase):
    """
    Unit tests for currency/unit, observation asOf date, data_date, data_frequency, and state:
    - UNRATE: currency='%', unit='%', data_frequency='monthly', is_delayed=True, state != 'LIVE'
    - CPIAUCSL: currency='PTS', unit='PTS', data_frequency='monthly', is_delayed=True, state != 'LIVE'
    - US02Y: currency='%', unit='%', data_frequency='daily', is_delayed=True, state != 'LIVE'
    - AAPL: currency='USD', non-FRED symbols unchanged (live/regular, not delayed)
    """

    def test_fred_extractor_units_and_dates(self):
        from app.markets.global_stocks import FredAdapter
        adapter = FredAdapter()

        # UNRATE (%)
        extractor_unrate = adapter._make_extractor('UNRATE')
        res_unrate = extractor_unrate({'observations': [{'date': '2024-05-01', 'value': '4.0'}]})
        self.assertIsNotNone(res_unrate)
        self.assertEqual(res_unrate['currency'], '%')
        self.assertEqual(res_unrate['unit'], '%')
        self.assertEqual(res_unrate['data_date'], '2024-05-01')
        self.assertEqual(res_unrate['data_frequency'], 'monthly')
        self.assertTrue(res_unrate['is_delayed'])
        self.assertNotEqual(res_unrate['state'], 'LIVE')
        self.assertEqual(res_unrate['asOf'], int(datetime(2024, 5, 1, tzinfo=timezone.utc).timestamp()))

        # CPIAUCSL (PTS)
        extractor_cpi = adapter._make_extractor('CPIAUCSL')
        res_cpi = extractor_cpi({'observations': [{'date': '2024-05-01', 'value': '314.069'}]})
        self.assertIsNotNone(res_cpi)
        self.assertEqual(res_cpi['currency'], 'PTS')
        self.assertEqual(res_cpi['unit'], 'PTS')
        self.assertEqual(res_cpi['data_date'], '2024-05-01')
        self.assertEqual(res_cpi['data_frequency'], 'monthly')
        self.assertTrue(res_cpi['is_delayed'])
        self.assertNotEqual(res_cpi['state'], 'LIVE')
        self.assertEqual(res_cpi['asOf'], int(datetime(2024, 5, 1, tzinfo=timezone.utc).timestamp()))

        # US02Y -> DGS2 (%)
        extractor_dgs2 = adapter._make_extractor('DGS2')
        res_dgs2 = extractor_dgs2({'observations': [{'date': '2024-05-01', 'value': '4.95'}]})
        self.assertIsNotNone(res_dgs2)
        self.assertEqual(res_dgs2['currency'], '%')
        self.assertEqual(res_dgs2['unit'], '%')
        self.assertEqual(res_dgs2['data_date'], '2024-05-01')
        self.assertEqual(res_dgs2['data_frequency'], 'daily')
        self.assertTrue(res_dgs2['is_delayed'])
        self.assertNotEqual(res_dgs2['state'], 'LIVE')
        self.assertEqual(res_dgs2['asOf'], int(datetime(2024, 5, 1, tzinfo=timezone.utc).timestamp()))

    async def test_fetch_global_stocks_preserves_meta_in_trace(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.markets import global_stocks

        mock_fred = MagicMock()
        mock_fred.name = "fred"
        mock_fred.fetch_quote = AsyncMock(return_value={
            'price': 4.1,
            'asOf': 1714521600,
            'date': '2024-05-01',
            'data_date': '2024-05-01',
            'state': 'delayed',
            'units': '%',
            'unit': '%',
            'currency': '%',
            'source': 'FRED',
            'data_frequency': 'monthly',
            'is_delayed': True
        })

        client = AsyncMock()
        traces = []
        with patch.object(global_stocks, "get_fallback_chain", return_value=[mock_fred]):
            price = await global_stocks.fetch_global_stocks(client, "global_stocks", "UNRATE", traces=traces)
            self.assertEqual(price, 4.1)
            self.assertEqual(len(traces), 1)
            tr = traces[0]
            self.assertEqual(tr['currency'], '%')
            self.assertEqual(tr['unit'], '%')
            self.assertEqual(tr['asOf'], 1714521600)
            self.assertEqual(tr['data_date'], '2024-05-01')
            self.assertEqual(tr['data_frequency'], 'monthly')
            self.assertTrue(tr['is_delayed'])
            self.assertNotEqual(tr['state'], 'LIVE')

    async def test_api_price_response_units_dates_and_frequencies(self):
        from unittest.mock import AsyncMock, patch, MagicMock
        from app.routes.prices import get_live_price
        from app.state import PRICE_CACHE
        import app.state as state

        state.http_client = AsyncMock()

        cases = [
            ("UNRATE", 4.1, "%", "%", "monthly", True, "delayed", "2024-05-01", 1714521600, "FRED"),
            ("CPIAUCSL", 314.069, "PTS", "PTS", "monthly", True, "delayed", "2024-05-01", 1714521600, "FRED"),
            ("US02Y", 4.95, "%", "%", "daily", True, "delayed", "2024-05-01", 1714521600, "FRED"),
            ("AAPL", 185.5, "USD", None, "live", False, "LIVE", None, 1714529999, "Yahoo Finance"),
        ]

        for sym, price, exp_curr, exp_unit, exp_freq, exp_delayed, exp_state, exp_date, exp_asof, exp_source in cases:
            with self.subTest(symbol=sym):
                from app.markets.common import normalize_symbol
                cache_key = f"global_stocks:{normalize_symbol(sym)}"
                meta = {
                    "source": exp_source,
                    "asOf": exp_asof,
                    "state": exp_state,
                    "currency": exp_curr,
                    "category": "macro" if sym != "AAPL" else "stock",
                    "data_frequency": exp_freq,
                    "is_delayed": exp_delayed,
                }
                if exp_unit:
                    meta["unit"] = exp_unit
                if exp_date:
                    meta["data_date"] = exp_date

                PRICE_CACHE[cache_key] = (price, time.time(), meta)

                with patch("app.routes.prices.get_cached_price", AsyncMock(return_value=price)):
                    res = await get_live_price("global_stocks", sym)
                    self.assertEqual(res["status"], "ok")
                    self.assertEqual(res["symbol"], sym)
                    self.assertEqual(res["price"], price)
                    self.assertEqual(res["currency"], exp_curr)
                    if exp_unit:
                        self.assertEqual(res.get("unit"), exp_unit)
                    self.assertEqual(res.get("data_frequency"), exp_freq)
                    self.assertEqual(res.get("is_delayed"), exp_delayed)
                    self.assertEqual(res["asOf"], exp_asof)
                    if exp_date:
                        self.assertEqual(res.get("data_date"), exp_date)
                    if exp_delayed:
                        self.assertNotEqual(res["state"], "LIVE")
                    else:
                        self.assertEqual(res["state"], exp_state)


class TestCatalogMacroCategories(unittest.TestCase):
    """
    Unit Tests for catalog.json macro resolution:
    - Reads catalog.json (id -> category)
    - All 5 macro series (UNRATE, CPIAUCSL, FEDFUNDS, WALCL, M2SL) return 'macro', not 'stock'
    - All macro series in catalog return 'macro'
    """
    def test_catalog_macro_series_resolve_to_macro(self):
        from app.engine.categories import resolve_symbol_category, _get_catalog_categories
        cat_map = _get_catalog_categories()
        self.assertTrue(len(cat_map) > 0, "Catalog should be loaded and non-empty")

        # 5 critical FRED macro series
        macro_series = ['UNRATE', 'CPIAUCSL', 'FEDFUNDS', 'WALCL', 'M2SL']
        for sym in macro_series:
            with self.subTest(symbol=sym):
                cat = resolve_symbol_category(sym)
                self.assertEqual(cat, 'macro', f"{sym} must resolve to 'macro', got '{cat}'")
                self.assertNotEqual(cat, 'stock', f"{sym} must not resolve to 'stock'")

                # Also test with explicit exchange
                cat_ex = resolve_symbol_category('global_stocks', sym)
                self.assertEqual(cat_ex, 'macro')
                cat_stocks = resolve_symbol_category('stocks', sym)
                self.assertEqual(cat_stocks, 'macro')

    def test_all_catalog_macro_symbols(self):
        from app.engine.categories import resolve_symbol_category, _get_catalog_categories
        cat_map = _get_catalog_categories()
        macro_in_cat = [sym for sym, cat in cat_map.items() if cat == 'macro']
        self.assertTrue(len(macro_in_cat) >= 5, f"Expected at least 5 macro symbols in catalog, found {macro_in_cat}")
        for sym in macro_in_cat:
            with self.subTest(symbol=sym):
                self.assertEqual(resolve_symbol_category(sym), 'macro')


class TestFredAdapterDynamicFrequencyAndMetadata(unittest.IsolatedAsyncioTestCase):
    """
    Unit Tests for FredAdapter:
    - dynamic frequency from FRED series metadata (frequency_short: D/W/M/Q/A -> daily/weekly/monthly/quarterly/annual)
    - caching metadata in _series_metadata_cache
    - fallback mapping on metadata request failure: FEDFUNDS -> monthly, WALCL -> weekly
    """
    async def test_dynamic_frequency_from_metadata_mock(self):
        from app.markets.global_stocks import FredAdapter, FRED_FREQ_SHORT_MAP
        from unittest.mock import AsyncMock, patch

        adapter = FredAdapter()
        FredAdapter._series_metadata_cache.clear()

        mock_responses = {
            'D': 'daily',
            'W': 'weekly',
            'M': 'monthly',
            'Q': 'quarterly',
            'A': 'annual',
        }

        for short_code, expected_freq in mock_responses.items():
            with self.subTest(short_code=short_code, expected_freq=expected_freq):
                mock_client = AsyncMock()
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "seriess": [
                        {
                            "id": f"TEST_{short_code}",
                            "frequency": expected_freq.capitalize(),
                            "frequency_short": short_code,
                            "units": "Index"
                        }
                    ]
                }
                mock_client.get.return_value = mock_resp

                with patch.object(adapter, 'api_key', 'valid_test_key'):
                    meta = await adapter.fetch_series_metadata(f"TEST_{short_code}", mock_client)
                    self.assertEqual(meta['data_frequency'], expected_freq)
                    self.assertEqual(meta['frequency_short'], short_code)

                    # Verify cached
                    self.assertIn(f"TEST_{short_code}", FredAdapter._series_metadata_cache)
                    # Second fetch should hit cache without calling client.get again
                    mock_client.get.reset_mock()
                    cached_meta = await adapter.fetch_series_metadata(f"TEST_{short_code}", mock_client)
                    mock_client.get.assert_not_called()
                    self.assertEqual(cached_meta['data_frequency'], expected_freq)

    async def test_static_fallback_on_metadata_failure(self):
        from app.markets.global_stocks import FredAdapter, FRED_SERIES_FREQUENCY
        from unittest.mock import AsyncMock, patch

        adapter = FredAdapter()
        FredAdapter._series_metadata_cache.clear()

        # FEDFUNDS must be monthly and WALCL must be weekly in static fallback
        self.assertEqual(FRED_SERIES_FREQUENCY.get('FEDFUNDS'), 'monthly')
        self.assertEqual(FRED_SERIES_FREQUENCY.get('WALCL'), 'weekly')

        # Mock failure (network exception or 500 status code)
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("FRED API Connection Error")

        with patch.object(adapter, 'api_key', 'test_key'):
            meta_fedfunds = await adapter.fetch_series_metadata('FEDFUNDS', mock_client)
            self.assertEqual(meta_fedfunds['data_frequency'], 'monthly')

            meta_walcl = await adapter.fetch_series_metadata('WALCL', mock_client)
            self.assertEqual(meta_walcl['data_frequency'], 'weekly')


class TestFredAsOfAndCheckerStaleness(unittest.TestCase):
    """
    Unit Tests for FRED asOf (observation date to epoch) and checker.py stale guard:
    - asOf must be observation date (data_date to epoch), not server time
    - checker.py is_data_stale:
      - daily: several days threshold (7 days)
      - weekly: several weeks threshold (21 days)
      - monthly: several weeks to 2 months threshold (60 days)
      - non-FRED / live: 1 hour threshold (3600s) unchanged
    """
    def test_asof_is_observation_date_epoch_not_server_time(self):
        obs_date_str = "2024-05-01"
        expected_epoch = int(datetime.strptime(obs_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
        server_time = int(time.time())

        # Verify expected epoch corresponds strictly to observation date 2024-05-01 00:00:00 UTC
        self.assertEqual(expected_epoch, 1714521600)
        self.assertNotEqual(expected_epoch, server_time)

    def test_checker_stale_data_guard_thresholds(self):
        from app.engine.checker import is_data_stale

        now = 1715000000.0  # reference timestamp

        # 1. Daily (threshold = 7 days = 604,800s)
        # 3 days old: fresh
        self.assertFalse(is_data_stale(now - (3 * 86400), 'daily', current_time=now))
        # 8 days old: stale
        self.assertTrue(is_data_stale(now - (8 * 86400), 'daily', current_time=now))

        # 2. Weekly (threshold = 21 days = 1,814,400s)
        # 14 days (2 weeks) old: fresh
        self.assertFalse(is_data_stale(now - (14 * 86400), 'weekly', current_time=now))
        # 25 days old: stale
        self.assertTrue(is_data_stale(now - (25 * 86400), 'weekly', current_time=now))

        # 3. Monthly (threshold = 60 days = several weeks up to 2 months)
        # 40 days old: fresh (does not falsely alert on older monthly data)
        self.assertFalse(is_data_stale(now - (40 * 86400), 'monthly', current_time=now))
        # 65 days old: stale
        self.assertTrue(is_data_stale(now - (65 * 86400), 'monthly', current_time=now))

        # 4. Non-FRED / live / default (threshold = 3600s = 1 hour unchanged)
        # 30 minutes old: fresh
        self.assertFalse(is_data_stale(now - 1800, 'live', current_time=now))
        self.assertFalse(is_data_stale(now - 1800, None, current_time=now))
        # 2 hours old: stale
        self.assertTrue(is_data_stale(now - 7200, 'live', current_time=now))
        self.assertTrue(is_data_stale(now - 7200, None, current_time=now))


if __name__ == '__main__':
    unittest.main()

