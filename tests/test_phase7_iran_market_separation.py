import unittest
import json
import os
import re

class TestIranMarketSeparation(unittest.TestCase):
    @unittest.skipIf(not os.path.isdir('lib'), "Flutter client code (lib/) not present in backend deployment")
    def test_iran_market_in_create_alert_flow(self):
        with open('lib/features/watchlist/pages/create_alert_flow.dart', 'r') as f:
            content = f.read()

        # Check MarketFlowType includes iran
        self.assertIn('MarketFlowType.iran', content)
        self.assertIn('_buildIranMarketPicker', content)
        self.assertIn('_onIranDomesticAssetChosen', content)

    @unittest.skipIf(not os.path.isdir('lib'), "Flutter client code (lib/) not present in backend deployment")
    def test_international_crypto_excludes_iranian_exchanges(self):
        with open('lib/features/watchlist/pages/create_alert_flow.dart', 'r') as f:
            content = f.read()

        # Check international crypto picker filters out Iranian exchanges
        self.assertIn('iranExchangeIds', content)
        self.assertIn('nobitex', content)
        self.assertIn('wallex', content)

    @unittest.skipIf(not os.path.isdir('lib'), "Flutter client code (lib/) not present in backend deployment")
    def test_iran_domestic_exchange_symbols(self):
        with open('lib/features/exchanges/stocks/iran_domestic_exchange.dart', 'r') as f:
            content = f.read()

        # Key REAL symbols check: Bonbast (Gold & FX), TSETMC (Indices, Gold & Leveraged Funds, Top Stocks), Tether & Digital Gold
        symbols = [
            'GERAM18', 'GERAM24', 'MESGHAL', 'COIN_EMAMI', 'COIN_BAHAR',
            'USD_TMN', 'EUR_TMN', 'AED_TMN', 'TEDPIX',
            'AYAR', 'TALA', 'ZAR', 'KAHROBA', 'GOHAR', 'NAAB', 'NAFIS',
            'ALTUN', 'MESGHAL_ETF', 'JAVAHER', 'ZARFAM',
            'AHRAM', 'JAHESH', 'TAVAN', 'SHETAB', 'MOJ', 'BIDAR',
            'PALAYESH', 'DARA1', 'FIRUZEH', 'SERVO', 'TEMESHK',
            'FOOLAD', 'FEMELLI', 'FARES', 'SHEPNA', 'SHETRAN', 'VEBMELAT', 'KHODRO', 'KHASAPA',
            'USDT_NOBITEX', 'USDT_WALLEX', 'USDT_TETHERLAND',
            'GOLD_NOBITEX', 'GOLD_WALLEX'
        ]
        for sym in symbols:
            self.assertIn(f"'{sym}'", content, f"Symbol {sym} must be present in IranDomesticExchange")

        # Rule 7: Assert that fake/static placeholder symbols have been removed
        fake_symbols = [
            'IME_GOLD_BAR', 'IME_SAFFRON', 'IME_SILVER',
            'AKHZA_YTM', 'INTERBANK_RATE',
            'ICE_USD_CASH', 'ICE_USD_REMIT', 'ICE_EUR_CASH', 'ICE_EUR_REMIT',
            'SANA_USD', 'NIMA_USD'
        ]
        for fake in fake_symbols:
            self.assertNotIn(f"'{fake}'", content, f"Fake symbol {fake} must be removed from IranDomesticExchange")

    def test_server_iran_sources_and_cache_ttl_60s(self):
        with open('server.py', 'r') as f:
            content = f.read()

        # Check 60-second strict cache and new legal source maps
        self.assertIn('CACHE_TTL_IRAN = 60.0', content)
        self.assertIn('BONBAST_MAP', content)
        self.assertIn('TSETMC_INDEX_MAP', content)
        self.assertIn('TSETMC_GOLD_FUNDS_MAP', content)
        self.assertIn('TSETMC_INSTRUMENTS_MAP', content)
        self.assertIn('bonbast.com', content)
        self.assertIn('cdn.tsetmc.com', content)

        # Rule 7: Verify static placeholder maps are removed
        self.assertNotIn('TREASURY_RATES_MAP', content)
        self.assertNotIn('ICE_MAP', content)

        # Assure TGJU is completely removed
        self.assertNotIn('TGJU_MAP', content)
        self.assertNotIn('tgju.org', content)

        # Assure TGJU is completely removed
        self.assertNotIn('TGJU_MAP', content)
        self.assertNotIn('tgju.org', content)

    @unittest.skipIf(not os.path.isdir('lib'), "Flutter client code (lib/) not present in backend deployment")
    def test_app_strings_translations(self):
        with open('lib/core/localization/app_strings.dart', 'r') as f:
            content = f.read()

        # Check Persian keys
        self.assertIn('iran_market_title', content)
        self.assertIn('iran_subtab_domestic', content)
        self.assertIn('iran_subtab_crypto', content)
        self.assertIn('iran_cat_gold', content)
        self.assertIn('iran_cat_coins', content)
        self.assertIn('iran_cat_currencies', content)
        self.assertIn('iran_cat_gold_funds', content)

    @unittest.skipIf(not os.path.isdir('lib'), "Flutter client code (lib/) not present in backend deployment")
    def test_persian_rtl_and_format_utils(self):
        with open('lib/features/watchlist/pages/create_alert_flow.dart', 'r') as f:
            content = f.read()

        # Check strict RTL directionality for Iran Market
        self.assertIn('TextDirection.rtl', content)
        self.assertIn('FormatUtils.formatIranPrice', content)
        self.assertIn('FormatUtils.normalizePersianDigits', content)

        with open('lib/core/utils/format_utils.dart', 'r') as f:
            fmt_content = f.read()

        self.assertIn('toPersianDigits', fmt_content)
        self.assertIn('normalizePersianDigits', fmt_content)
        self.assertIn('formatIranPrice', fmt_content)
        self.assertIn('formatAlertCardPrice', fmt_content)

    def test_bridge_v2_5_spec_compliance(self):
        with open('server.py', 'r') as f:
            content = f.read()

        # 1. Timeout must be at least 30s
        self.assertIn('timeout_sec=30.0', content)

        # 2. Authorization header with Bearer token
        self.assertIn("'Authorization': f'Bearer {IRAN_BRIDGE_TOKEN}'", content)

        # 3. Alert guards (Rule 5): No alerts triggered on carried_over, stale, market closed, or untraded
        self.assertIn("cached_meta.get('alert_eligible') is False", content)
        self.assertIn("cached_meta.get('carried_over') is True", content)
        self.assertIn("cached_meta.get('state') in ['CARRIED_OVER', 'STALE'", content)
        self.assertIn("traded_today", content)
        self.assertIn("daily_close", content)

        # 4. Markets status overview endpoint returns state_counts & symbols_with_price
        self.assertIn('/api/markets/status', content)
        self.assertIn('symbols_with_price', content)
        self.assertIn('state_counts', content)
        self.assertIn('state_fa', content)

    @unittest.skipIf(not os.path.isdir('lib'), "Flutter client code (lib/) not present in backend deployment")
    def test_rule_6_app_display(self):
        with open('lib/features/watchlist/pages/create_alert_flow.dart', 'r') as f:
            content = f.read()

        # Rule 6: TSE schedule_fa, next_open, and 'بسته' badge displayed
        self.assertIn('schedule_fa', content)
        self.assertIn('next_open', content)
        self.assertIn('بسته', content)
        self.assertIn('_loadIranMarketOverview', content)
        self.assertIn('_iranItemMeta', content)

        with open('lib/core/services/server_alert_service.dart', 'r') as f:
            srv_content = f.read()
        self.assertIn('fetchMarketsOverview', srv_content)

if __name__ == '__main__':
    unittest.main()
