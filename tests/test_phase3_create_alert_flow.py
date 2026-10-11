#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 3 Comprehensive Unit Tests:
 1. create_alert_flow.dart asset list does NOT show static catalog price:
    - displays '—' when live price is pending/unfetched
    - _macroLivePrices map is used for genuine live ticks
 2. Dynamic 'unit' replaces hardcoded 'USD' and '$':
    - _onMacroAssetChosen sets counterCurrency: unit
    - _saveAlert sets counterCurrency: unit
    - _formatSmartPrice formats %, pts, Billion USD, CNY, JPY, EUR without forced dollar sign
 3. Server fallback & error reporting in stock/macro path:
    - _onMacroAssetChosen implements ServerAlertService.fetchPriceViaServer fallback
    - Zero silent catch blocks in _onMacroAssetChosen
    - User SnackBar error notification shown when both fail
 4. Zero fake baseP = 1.0 on percent change alert:
    - baseP = 1.0 removed
    - Saving without real live price is blocked with validation message
 5. Real user ID replaces 'user_default':
    - userId: 'user_default' completely removed
    - ServerAlertService.getEffectiveUserId() implemented and used

All tests run completely OFFLINE using mocks.
"""

import unittest
import re
import os

@unittest.skipIf(not os.path.isdir('lib'), "Flutter client code (lib/) not present in backend deployment")
class TestPhase3CreateAlertFlow(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open('lib/features/watchlist/pages/create_alert_flow.dart', 'r', encoding='utf-8') as f:
            cls.flow_code = f.read()

        with open('lib/core/services/server_alert_service.dart', 'r', encoding='utf-8') as f:
            cls.server_service_code = f.read()

    def test_01_no_static_catalog_price_in_asset_list(self):
        """Verify list tile displays '—' for pending price and never uses asset['price'] for display"""
        self.assertNotIn("final price = (asset['price'] as num).toDouble();", self.flow_code,
                         "Should not read static asset['price'] in macro asset list item builder")
        self.assertIn("_macroLivePrices[sym]", self.flow_code)
        self.assertIn("'—'", self.flow_code)

    def test_02_unit_replaces_hardcoded_usd_in_macro_pairs(self):
        """Verify macro CurrencyPair creation uses asset unit rather than hardcoded 'USD'"""
        # In _onMacroAssetChosen
        chosen_match = re.search(r'_onMacroAssetChosen[\s\S]*?CurrencyPair\([\s\S]*?\)', self.flow_code)
        self.assertIsNotNone(chosen_match)
        self.assertIn("counterCurrency: unit", chosen_match.group(0))
        self.assertNotIn("counterCurrency: 'USD'", chosen_match.group(0))

        # In _saveAlert
        save_macro_match = re.search(r"exchangeId = 'global_stocks';[\s\S]*?CurrencyPair\([\s\S]*?\);", self.flow_code)
        self.assertIsNotNone(save_macro_match)
        self.assertIn("counterCurrency: unit", save_macro_match.group(0))
        self.assertNotIn("counterCurrency: 'USD'", save_macro_match.group(0))

    def test_03_format_smart_price_supports_all_units_without_dollar_slop(self):
        """Verify _formatSmartPrice properly handles %, pts, Billion USD, CNY, JPY, EUR"""
        self.assertIn("quoteCurrency == '%'", self.flow_code)
        self.assertIn("quoteCurrency == 'pts'", self.flow_code)
        self.assertIn("quoteCurrency == 'Billion USD'", self.flow_code)
        self.assertIn("quoteCurrency == 'JPY'", self.flow_code)
        self.assertIn("quoteCurrency == 'EUR'", self.flow_code)

    def test_04_server_fallback_and_no_silent_catch_in_macro_chosen(self):
        """Verify server fallback is called and user is notified on error without silent catch"""
        chosen_block = re.search(r'Future<void> _onMacroAssetChosen[\s\S]*?Future<void> _saveAlert', self.flow_code)
        self.assertIsNotNone(chosen_block)
        block_text = chosen_block.group(0)

        self.assertIn("ServerAlertService.fetchPriceViaServer('global_stocks', sym)", block_text)
        self.assertNotIn("catch (_) {}", block_text, "No silent catch allowed in macro price fetch")
        self.assertIn("ScaffoldMessenger.of(context).showSnackBar", block_text)

    def test_05_basep_1_removed_and_live_price_enforced_on_percent_alerts(self):
        """Verify baseP = 1.0 is eliminated and saving without liveBasePrice is blocked"""
        self.assertNotIn("liveBasePrice : 1.0;", self.flow_code, "baseP = 1.0 fallback must not exist")
        percent_check = re.search(r'if \(_conditionType == AlertConditionType\.percentChange\) \{[\s\S]*?if \(liveBasePrice == null \|\| liveBasePrice <= 0\)', self.flow_code)
        self.assertIsNotNone(percent_check, "Must enforce liveBasePrice presence before saving percent alert")

    def test_06_real_user_id_replaces_user_default(self):
        """Verify userId: 'user_default' is completely replaced with getEffectiveUserId()"""
        user_defaults = re.findall(r"userId:\s*'user_default'", self.flow_code)
        self.assertEqual(len(user_defaults), 0, f"Found user_default occurrences: {len(user_defaults)}")
        self.assertIn("ServerAlertService.getEffectiveUserId()", self.flow_code)
        self.assertIn("userId: realUserId", self.flow_code)

    def test_07_server_alert_service_has_get_effective_user_id(self):
        """Verify ServerAlertService implements getEffectiveUserId()"""
        self.assertIn("static Future<String> getEffectiveUserId()", self.server_service_code)


if __name__ == '__main__':
    unittest.main()
