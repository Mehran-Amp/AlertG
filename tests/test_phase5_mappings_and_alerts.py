#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit Tests for Phase 5 (v3.3.0): Provider Mappings & Alerts Resolution
Verifies Acceptance Criteria:
1. Provider-Specific Mappings:
   - Dotted US share classes (BRK.B, BF.B -> Yahoo dash 'BRK-B', 'BF-B'; Finnhub/TwelveData dots 'BRK.B', 'BF.B')
   - Forex pairs (Yahoo EURUSD=X, TwelveData EUR/USD, Finnhub OANDA:EUR_USD)
   - Indices and Futures (^GSPC, GC=F, CL=F, BZ=F, DX-Y.NYB)
   - China / Hong Kong local vs US ADR separation (0700.HK / 9988.HK in HKD vs TCEHY / BABA in USD)
2. symbol_aliases:
   - Resolves legacy aliases (GOLD, DXY, XAUUSD, OIL, WTI, SP500, US10Y, US02Y, etc.) to canonical symbols
3. FRED Rules:
   - Series frequency (daily vs monthly) enforced for macro/daily alerts
   - Strictly NO fallback from Yahoo to FRED for stocks, forex, indices, or commodities
   - 2-year yield (US02Y) is FRED-only (DGS2) and NEVER falls through to Yahoo (^IRX)
4. check_existing_alerts_resolution Script:
   - Offline verification and diagnostic capabilities tested with valid and invalid alerts
"""

import unittest
import asyncio
from typing import List, Dict, Any

from app.config import APP_VERSION
from app.models import Alert
from app.markets.global_stocks import (
    resolve_yf_symbol,
    resolve_symbol_alias,
    resolve_symbol_category,
    validate_fred_alert_frequency,
    yahoo_adapter,
    finnhub_adapter,
    twelve_data_adapter,
    fred_adapter,
    get_fallback_chain,
    EXACT_YF_MAP,
    SYMBOL_ALIASES,
    FOREX_PAIRS,
    FRED_ONLY_SYMBOLS,
    FRED_SERIES_FREQUENCY,
)
from scripts.check_existing_alerts_resolution import (
    resolve_symbol_offline,
    check_alerts,
    load_catalog_symbols,
)


class TestPhase5MappingsAndAlerts(unittest.TestCase):

    def test_01_dotted_symbols_mapping_per_provider(self):
        """
        Verify dotted US share classes map correctly per provider:
        - Yahoo Finance requires dash: BRK.B -> BRK-B, BF.B -> BF-B
        - Finnhub & Twelve Data use dots: BRK.B, BF.B
        """
        # 1. Yahoo Finance
        self.assertEqual(yahoo_adapter.resolve_symbol('BRK.B'), 'BRK-B')
        self.assertEqual(yahoo_adapter.resolve_symbol('BRKB'), 'BRK-B')
        self.assertEqual(yahoo_adapter.resolve_symbol('BRK-B'), 'BRK-B')
        self.assertEqual(yahoo_adapter.resolve_symbol('BF.B'), 'BF-B')
        self.assertEqual(yahoo_adapter.resolve_symbol('BFB'), 'BF-B')
        self.assertEqual(yahoo_adapter.resolve_symbol('BF-B'), 'BF-B')

        # 2. Finnhub
        self.assertEqual(finnhub_adapter.resolve_symbol('BRK.B'), 'BRK.B')
        self.assertEqual(finnhub_adapter.resolve_symbol('BRKB'), 'BRK.B')
        self.assertEqual(finnhub_adapter.resolve_symbol('BRK-B'), 'BRK.B')
        self.assertEqual(finnhub_adapter.resolve_symbol('BF.B'), 'BF.B')
        self.assertEqual(finnhub_adapter.resolve_symbol('BFB'), 'BF.B')
        self.assertEqual(finnhub_adapter.resolve_symbol('BF-B'), 'BF.B')

        # 3. Twelve Data
        self.assertEqual(twelve_data_adapter.resolve_symbol('BRK.B'), 'BRK.B')
        self.assertEqual(twelve_data_adapter.resolve_symbol('BRKB'), 'BRK.B')
        self.assertEqual(twelve_data_adapter.resolve_symbol('BRK-B'), 'BRK.B')
        self.assertEqual(twelve_data_adapter.resolve_symbol('BF.B'), 'BF.B')
        self.assertEqual(twelve_data_adapter.resolve_symbol('BFB'), 'BF.B')
        self.assertEqual(twelve_data_adapter.resolve_symbol('BF-B'), 'BF.B')

    def test_02_forex_symbols_mapping_per_provider(self):
        """
        Verify forex pairs map to appropriate provider representations:
        - Yahoo: {PAIR}=X (e.g. EURUSD=X)
        - Twelve Data: {BASE}/{QUOTE} (e.g. EUR/USD)
        - Finnhub: OANDA:{BASE}_{QUOTE} (e.g. OANDA:EUR_USD)
        """
        pairs = ['EUR/USD', 'GBP/USD', 'USD/JPY', 'AUD/USD', 'USD/CAD', 'USD/CHF']

        for p in pairs:
            base, quote = p.split('/')
            raw_pair = f"{base}{quote}"

            # Yahoo -> {PAIR}=X
            self.assertEqual(yahoo_adapter.resolve_symbol(p), f"{raw_pair}=X")
            self.assertEqual(yahoo_adapter.resolve_symbol(raw_pair), f"{raw_pair}=X")
            self.assertEqual(yahoo_adapter.resolve_symbol(f"{raw_pair}=X"), f"{raw_pair}=X")

            # Twelve Data -> BASE/QUOTE
            self.assertEqual(twelve_data_adapter.resolve_symbol(p), f"{base}/{quote}")
            self.assertEqual(twelve_data_adapter.resolve_symbol(raw_pair), f"{base}/{quote}")
            self.assertEqual(twelve_data_adapter.resolve_symbol(f"{raw_pair}=X"), f"{base}/{quote}")

            # Finnhub -> OANDA:BASE_QUOTE
            self.assertEqual(finnhub_adapter.resolve_symbol(p), f"OANDA:{base}_{quote}")
            self.assertEqual(finnhub_adapter.resolve_symbol(raw_pair), f"OANDA:{base}_{quote}")
            self.assertEqual(finnhub_adapter.resolve_symbol(f"{raw_pair}=X"), f"OANDA:{base}_{quote}")

    def test_03_indices_and_futures_mapping_per_provider(self):
        """
        Verify indices and futures symbols map correctly per provider:
        - Yahoo: ^GSPC, GC=F, CL=F, BZ=F, DX-Y.NYB
        - Twelve Data: SPX, XAU/USD, WTI/USD, BRENT, DXY
        """
        # S&P 500
        self.assertEqual(yahoo_adapter.resolve_symbol('SP500'), '^GSPC')
        self.assertEqual(yahoo_adapter.resolve_symbol('SPX'), '^GSPC')
        self.assertEqual(yahoo_adapter.resolve_symbol('^GSPC'), '^GSPC')
        self.assertEqual(twelve_data_adapter.resolve_symbol('SP500'), 'SPX')
        self.assertEqual(twelve_data_adapter.resolve_symbol('^GSPC'), 'SPX')

        # Gold Futures
        self.assertEqual(yahoo_adapter.resolve_symbol('GOLD'), 'GC=F')
        self.assertEqual(yahoo_adapter.resolve_symbol('XAUUSD'), 'GC=F')
        self.assertEqual(yahoo_adapter.resolve_symbol('GC=F'), 'GC=F')
        self.assertEqual(twelve_data_adapter.resolve_symbol('GOLD'), 'XAU/USD')
        self.assertEqual(twelve_data_adapter.resolve_symbol('GC=F'), 'XAU/USD')

        # Crude Oil (WTI)
        self.assertEqual(yahoo_adapter.resolve_symbol('WTI'), 'CL=F')
        self.assertEqual(yahoo_adapter.resolve_symbol('OIL'), 'CL=F')
        self.assertEqual(yahoo_adapter.resolve_symbol('OIL_WTI'), 'CL=F')
        self.assertEqual(yahoo_adapter.resolve_symbol('CL=F'), 'CL=F')
        self.assertEqual(twelve_data_adapter.resolve_symbol('WTI'), 'WTI/USD')
        self.assertEqual(twelve_data_adapter.resolve_symbol('OIL_WTI'), 'WTI/USD')
        self.assertEqual(twelve_data_adapter.resolve_symbol('CL=F'), 'WTI/USD')

        # Brent Oil
        self.assertEqual(yahoo_adapter.resolve_symbol('BRENT'), 'BZ=F')
        self.assertEqual(yahoo_adapter.resolve_symbol('OIL_BRENT'), 'BZ=F')
        self.assertEqual(yahoo_adapter.resolve_symbol('BZ=F'), 'BZ=F')
        self.assertEqual(twelve_data_adapter.resolve_symbol('BRENT'), 'BRENT')
        self.assertEqual(twelve_data_adapter.resolve_symbol('OIL_BRENT'), 'BRENT')
        self.assertEqual(twelve_data_adapter.resolve_symbol('BZ=F'), 'BRENT')

        # US Dollar Index (DXY)
        self.assertEqual(yahoo_adapter.resolve_symbol('DXY'), 'DX-Y.NYB')
        self.assertEqual(yahoo_adapter.resolve_symbol('USDX'), 'DX-Y.NYB')
        self.assertEqual(yahoo_adapter.resolve_symbol('DX-Y.NYB'), 'DX-Y.NYB')
        self.assertEqual(twelve_data_adapter.resolve_symbol('DXY'), 'DXY')
        self.assertEqual(twelve_data_adapter.resolve_symbol('DX-Y.NYB'), 'DXY')

    def test_04_china_hongkong_local_vs_adr_separation(self):
        """
        Verify China/Hong Kong local stocks vs US ADR separation:
        - HK local shares retain '.HK' or HKEX exchange context in HKD currency (e.g. 0700.HK, 9988.HK)
        - US ADRs trade on NYSE/NASDAQ/OTC in USD currency (e.g. TCEHY, BABA, XIACY, BIDU, JD)
        - ADR and local shares must NEVER be conflated into each other.
        """
        # Local Hong Kong shares
        self.assertEqual(yahoo_adapter.resolve_symbol('0700.HK'), '0700.HK')
        self.assertEqual(yahoo_adapter.resolve_symbol('9988.HK'), '9988.HK')
        self.assertEqual(yahoo_adapter.resolve_symbol('1810.HK'), '1810.HK')
        self.assertEqual(twelve_data_adapter.resolve_symbol('0700.HK'), '0700')
        self.assertEqual(twelve_data_adapter.resolve_symbol('9988.HK'), '9988')

        # US ADRs
        self.assertEqual(yahoo_adapter.resolve_symbol('BABA'), 'BABA')
        self.assertEqual(yahoo_adapter.resolve_symbol('TCEHY'), 'TCEHY')
        self.assertEqual(yahoo_adapter.resolve_symbol('XIACY'), 'XIACY')
        self.assertEqual(yahoo_adapter.resolve_symbol('BIDU'), 'BIDU')
        self.assertEqual(yahoo_adapter.resolve_symbol('JD'), 'JD')

        self.assertEqual(finnhub_adapter.resolve_symbol('BABA'), 'BABA')
        self.assertEqual(finnhub_adapter.resolve_symbol('TCEHY'), 'TCEHY')
        self.assertEqual(finnhub_adapter.resolve_symbol('XIACY'), 'XIACY')

        self.assertEqual(twelve_data_adapter.resolve_symbol('BABA'), 'BABA')
        self.assertEqual(twelve_data_adapter.resolve_symbol('TCEHY'), 'TCEHY')

        # Strict separation assertion: BABA != 9988.HK, TCEHY != 0700.HK
        self.assertNotEqual(yahoo_adapter.resolve_symbol('BABA'), yahoo_adapter.resolve_symbol('9988.HK'))
        self.assertNotEqual(yahoo_adapter.resolve_symbol('TCEHY'), yahoo_adapter.resolve_symbol('0700.HK'))

    def test_05_symbol_aliases_canonical_resolution(self):
        """
        Verify resolve_symbol_alias maps legacy shorthand notations to canonical catalog symbols.
        """
        # Commodities
        self.assertEqual(resolve_symbol_alias('GOLD'), 'GOLD')
        self.assertEqual(resolve_symbol_alias('XAU'), 'GOLD')
        self.assertEqual(resolve_symbol_alias('XAUUSD'), 'GOLD')
        self.assertEqual(resolve_symbol_alias('XAU/USD'), 'GOLD')
        self.assertEqual(resolve_symbol_alias('GC=F'), 'GOLD')

        self.assertEqual(resolve_symbol_alias('SILVER'), 'SILVER')
        self.assertEqual(resolve_symbol_alias('XAG'), 'SILVER')
        self.assertEqual(resolve_symbol_alias('XAGUSD'), 'SILVER')
        self.assertEqual(resolve_symbol_alias('SI=F'), 'SILVER')

        self.assertEqual(resolve_symbol_alias('OIL'), 'OIL_WTI')
        self.assertEqual(resolve_symbol_alias('WTI'), 'OIL_WTI')
        self.assertEqual(resolve_symbol_alias('CRUDE'), 'OIL_WTI')
        self.assertEqual(resolve_symbol_alias('CL=F'), 'OIL_WTI')
        self.assertEqual(resolve_symbol_alias('BRENT'), 'OIL_BRENT')
        self.assertEqual(resolve_symbol_alias('BZ=F'), 'OIL_BRENT')

        # Indices
        self.assertEqual(resolve_symbol_alias('DXY'), 'DXY')
        self.assertEqual(resolve_symbol_alias('USDX'), 'DXY')
        self.assertEqual(resolve_symbol_alias('DX-Y.NYB'), 'DXY')
        self.assertEqual(resolve_symbol_alias('SP500'), 'SP500')
        self.assertEqual(resolve_symbol_alias('SPX'), 'SP500')
        self.assertEqual(resolve_symbol_alias('^GSPC'), 'SP500')
        self.assertEqual(resolve_symbol_alias('NASDAQ'), 'NASDAQ100')
        self.assertEqual(resolve_symbol_alias('NDX'), 'NASDAQ100')
        self.assertEqual(resolve_symbol_alias('^NDX'), 'NASDAQ100')
        self.assertEqual(resolve_symbol_alias('DOW'), 'DOWJONES')
        self.assertEqual(resolve_symbol_alias('DJI'), 'DOWJONES')
        self.assertEqual(resolve_symbol_alias('^DJI'), 'DOWJONES')

        # Treasury Yields
        self.assertEqual(resolve_symbol_alias('US10Y'), 'US10Y')
        self.assertEqual(resolve_symbol_alias('TNX'), 'US10Y')
        self.assertEqual(resolve_symbol_alias('^TNX'), 'US10Y')
        self.assertEqual(resolve_symbol_alias('US02Y'), 'US02Y')
        self.assertEqual(resolve_symbol_alias('US2Y'), 'US02Y')
        self.assertEqual(resolve_symbol_alias('^2YY'), 'US02Y')
        self.assertEqual(resolve_symbol_alias('US13W'), 'US13W')
        self.assertEqual(resolve_symbol_alias('^IRX'), 'US13W')

        # Dotted equities
        self.assertEqual(resolve_symbol_alias('BRKB'), 'BRK.B')
        self.assertEqual(resolve_symbol_alias('BRK-B'), 'BRK.B')
        self.assertEqual(resolve_symbol_alias('BFB'), 'BF.B')
        self.assertEqual(resolve_symbol_alias('BF-B'), 'BF.B')

    def test_06_fred_rules_and_no_yahoo_to_fred_fallback(self):
        """
        Verify FRED rules:
        - Daily and monthly series frequency checks
        - Strictly NO fallback from Yahoo to FRED for stocks, forex, indices, commodities
        - US02Y is FRED-only (DGS2); never falls back to Yahoo ^IRX
        """
        # 1. Update frequency classification
        self.assertEqual(fred_adapter.get_series_frequency('US10Y'), 'daily')
        self.assertEqual(fred_adapter.get_series_frequency('DGS10'), 'daily')
        self.assertEqual(fred_adapter.get_series_frequency('US02Y'), 'daily')
        self.assertEqual(fred_adapter.get_series_frequency('DGS2'), 'daily')
        self.assertEqual(fred_adapter.get_series_frequency('US13W'), 'daily')
        self.assertEqual(fred_adapter.get_series_frequency('DTB3'), 'daily')
        self.assertEqual(fred_adapter.get_series_frequency('CPIAUCSL'), 'monthly')
        self.assertEqual(fred_adapter.get_series_frequency('UNRATE'), 'monthly')
        self.assertEqual(fred_adapter.get_series_frequency('M2SL'), 'monthly')

        # 2. FRED Alert frequency validation
        valid_daily, _ = validate_fred_alert_frequency('DGS10', '1d')
        self.assertTrue(valid_daily)

        valid_macro_none, _ = validate_fred_alert_frequency('CPIAUCSL', None)
        self.assertTrue(valid_macro_none)

        invalid_intraday, msg = validate_fred_alert_frequency('CPIAUCSL', '1m')
        self.assertFalse(invalid_intraday)
        self.assertIn("prohibited", msg)

        invalid_intraday_yield, msg2 = validate_fred_alert_frequency('DGS10', '5m')
        self.assertFalse(invalid_intraday_yield)
        self.assertIn("prohibited", msg2)

        # 3. No fallback from Yahoo to FRED:
        # Stocks chain: Yahoo -> Finnhub -> Twelve Data (FRED NEVER present)
        stock_chain = get_fallback_chain('AAPL')
        self.assertNotIn(fred_adapter, stock_chain)

        # Forex chain: Yahoo -> Finnhub -> Twelve Data (FRED NEVER present)
        forex_chain = get_fallback_chain('EURUSD')
        self.assertNotIn(fred_adapter, forex_chain)

        # Commodities chain: Yahoo -> Twelve Data (FRED NEVER present)
        comm_chain = get_fallback_chain('GOLD')
        self.assertNotIn(fred_adapter, comm_chain)

        # Indices chain: Yahoo -> Twelve Data (FRED NEVER present)
        idx_chain = get_fallback_chain('SP500')
        self.assertNotIn(fred_adapter, idx_chain)

        # 4. FRED-only 2Y yield
        self.assertIn('US02Y', FRED_ONLY_SYMBOLS)
        self.assertIn('US2Y', FRED_ONLY_SYMBOLS)
        self.assertIn('^2YY', FRED_ONLY_SYMBOLS)

    def test_07_check_existing_alerts_resolution_offline(self):
        """
        Verify check_existing_alerts_resolution logic in offline mode:
        - Resolves valid alerts
        - Correctly flags invalid/unmapped alerts with reason and suggested fix
        """
        cat_symbols = load_catalog_symbols()

        # Valid alerts
        valid_alerts = [
            Alert(id="a1", user_id=123, symbol="AAPL", exchange="global_stocks", target_price=200.0, condition="ABOVE"),
            Alert(id="a2", user_id=123, symbol="EUR/USD", exchange="global_stocks", target_price=1.08, condition="ABOVE"),
            Alert(id="a3", user_id=123, symbol="GOLD", exchange="global_stocks", target_price=2700.0, condition="ABOVE"),
            Alert(id="a4", user_id=123, symbol="BTCUSDT", exchange="binance", target_price=65000.0, condition="ABOVE"),
            Alert(id="a5", user_id=123, symbol="USD", exchange="bonbast", target_price=60000.0, condition="ABOVE"),
            Alert(id="a6", user_id=123, symbol="US10Y", exchange="macro", target_price=4.2, condition="ABOVE"),
        ]

        resolved, unresolved, failed = asyncio.run(check_alerts(valid_alerts, offline=True))
        self.assertEqual(resolved, len(valid_alerts))
        self.assertEqual(unresolved, 0)
        self.assertEqual(len(failed), 0)

        # Invalid alert scenario
        invalid_alerts = [
            Alert(id="bad1", user_id=123, symbol="NON_EXISTENT_TICKER_XYZ", exchange="global_stocks", target_price=10.0, condition="ABOVE"),
            Alert(id="bad2", user_id=123, symbol="INVALID_IRAN_ITEM", exchange="iran", target_price=100.0, condition="ABOVE"),
        ]

        resolved_inv, unresolved_inv, failed_inv = asyncio.run(check_alerts(invalid_alerts, offline=True))
        self.assertEqual(resolved_inv, 0)
        self.assertEqual(unresolved_inv, 2)
        self.assertEqual(len(failed_inv), 2)
        self.assertEqual(failed_inv[0]['id'], 'bad1')
        self.assertIn("not found", failed_inv[0]['reason'].lower())


if __name__ == '__main__':
    unittest.main()
