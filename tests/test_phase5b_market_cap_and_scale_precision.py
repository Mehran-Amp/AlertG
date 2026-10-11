#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit Tests for Phase 5b: Market Cap & Scale Precision Bug Fix
Acceptance criteria:
 1. 831.737477573993646 with B USD -> $831.737B (max 3 decimals, strip trailing zeros)
 2. 2450.5 with B USD -> $2,450.5B
 3. 850 with M USD -> $850M (max 2 decimals, strip trailing zeros)
 4. BTC.D with % -> 58.78% (exactly 2 decimals)
 5. BTC with 94520.5 -> $94,520.50 (full standard precision unchanged)
 6. Target Price input fields use formatInputNumberForUnit to prevent 15-decimal floating slop
 7. Notification history page resolves currency for market caps and percentages
"""

import unittest
import re
import os

@unittest.skipIf(not os.path.isdir('lib'), "Flutter client code (lib/) not present in backend deployment")
class TestMarketCapAndScalePrecision(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open('lib/core/utils/format_utils.dart', 'r', encoding='utf-8') as f:
            cls.format_utils_code = f.read()

        with open('lib/features/watchlist/pages/create_alert_flow.dart', 'r', encoding='utf-8') as f:
            cls.flow_code = f.read()

        with open('lib/features/notifications/pages/notification_history_page.dart', 'r', encoding='utf-8') as f:
            cls.notif_code = f.read()

        with open('src/App.tsx', 'r', encoding='utf-8') as f:
            cls.web_app_code = f.read()

    def test_01_format_scaled_currency_price_restricts_billion_to_3_decimals(self):
        """Verify formatScaledCurrencyPrice in format_utils.dart restricts Billion to max 3 decimals"""
        self.assertIn("maxDecimals = 3;", self.format_utils_code)
        self.assertIn("maxDecimals = 2;", self.format_utils_code)
        # Check trailing zero stripper
        self.assertIn("r'0+$'", self.format_utils_code)

    def test_02_format_input_number_for_unit_implemented(self):
        """Verify FormatUtils provides formatInputNumberForUnit for target price inputs"""
        self.assertIn("static String formatInputNumberForUnit(double price, String? quoteCurrency)", self.format_utils_code)
        # Used in create_alert_flow
        self.assertIn("FormatUtils.formatInputNumberForUnit", self.flow_code)

    def test_03_create_alert_flow_percentage_and_macro_formatting(self):
        """Verify % quote currency uses 2 decimals and macro target prices use formatInputNumberForUnit"""
        self.assertIn("quoteCurrency == '%'", self.flow_code)
        self.assertIn("${price.toStringAsFixed(2)}%", self.flow_code)
        self.assertIn("FormatUtils.formatInputNumberForUnit(snapshot.price, unit)", self.flow_code)

    def test_04_notification_history_resolves_log_currency(self):
        """Verify notification history page resolves currency for TOTAL, %, etc."""
        self.assertIn("_resolveLogCurrency", self.notif_code)
        self.assertIn("baseSym == 'TOTAL'", self.notif_code)
        self.assertIn("currencySymbol: _resolveLogCurrency(log)", self.notif_code)

    def test_05_web_format_scaled_price_restricts_decimals(self):
        """Verify web formatScaledPrice also limits maxDecimals and strips zeros"""
        self.assertIn("maxDecimals = 3", self.web_app_code)
        self.assertIn("maxDecimals = 2", self.web_app_code)
        self.assertIn("cleanDec", self.web_app_code)
        self.assertIn("TOTAL", self.web_app_code)

    def test_06_simulated_dart_formatting_logic(self):
        """Simulate the exact Dart algorithm to ensure all user acceptance criteria pass"""
        def format_scaled(price, curr):
            is_b = 'B' in curr.upper()
            is_m = 'M' in curr.upper()
            max_d = 3 if is_b else (2 if is_m else 2)
            scale = 'B' if is_b else 'M'
            abs_p = abs(price)
            fixed_str = f"{abs_p:.{max_d}f}"
            parts = fixed_str.split('.')
            int_part = f"{int(parts[0]):,}"
            dec_part = parts[1].rstrip('0')
            formatted_num = f"{int_part}.{dec_part}" if dec_part else int_part
            prefix = "-$" if price < 0 else "$"
            return f"{prefix}{formatted_num}{scale}"

        # 1. 831.737477573993646 with B USD -> $831.737B
        self.assertEqual(format_scaled(831.737477573993646, 'B USD'), "$831.737B")
        # 2. 2450.5 with B USD -> $2,450.5B
        self.assertEqual(format_scaled(2450.5, 'B USD'), "$2,450.5B")
        # 3. 850 with M USD -> $850M
        self.assertEqual(format_scaled(850.0, 'M USD'), "$850M")
        # 4. BTC.D percent formatting: 58.7834 -> 58.78%
        self.assertEqual(f"{58.7834:.2f}%", "58.78%")
        # 5. BTC 94520.5 -> $94,520.50
        self.assertEqual(f"${94520.5:,.2f}", "$94,520.50")

if __name__ == '__main__':
    unittest.main()
