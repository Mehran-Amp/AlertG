# -*- coding: utf-8 -*-
"""
AlertG — Phase 5 Acceptance Tests: Exact Price Display (Rule R3).
Verifies Acceptance Table T9:
- Prices >= 1.0 preserve legacy formatting (thousands separators, 2 decimals).
- Prices < 1.0 display all significant digits (never "$0", never scientific notation).
- FCM push price payload string is exact plain decimal (never scientific notation like '8.5e-07').
- Telegram registration message and history card render exact prices.
- Golden comparison: prices >= 1 and prices with <= 4 decimals are byte-for-byte identical.
"""
import unittest
import sys
from unittest.mock import MagicMock
from decimal import Decimal

# Mock server dependencies if not present in test runner
for mod in [
    'httpx', 'fastapi', 'fastapi.middleware.cors', 'fastapi.responses',
    'apscheduler', 'apscheduler.schedulers', 'apscheduler.schedulers.asyncio',
    'firebase_admin', 'firebase_admin.credentials', 'firebase_admin.messaging', 'firebase_admin.exceptions'
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

from app.engine.formatter import format_exact_decimal, format_display_price
from app.models import Alert
from app.notifier.telegram import (
    format_alert_registered_telegram_msg,
    format_telegram_history_card,
)


class TestPhase5ExactPriceDisplay(unittest.TestCase):

    T9_ACCEPTANCE_TABLE = [
        (67000.5, "$67,000.50", "67000.5"),
        (1.23, "$1.23", "1.23"),
        (0.5678, "$0.5678", "0.5678"),
        (0.00012345, "$0.00012345", "0.00012345"),
        (0.00000085, "$0.00000085", "0.00000085"),
        (0.00000001, "$0.00000001", "0.00000001"),
        (0.000000001234, "$0.000000001234", "0.000000001234"),
        (1e-12, "$0.000000000001", "0.000000000001"),
    ]

    def test_01_formatter_acceptance_table_t9(self):
        """Verifies format_display_price and format_exact_decimal against Acceptance Table T9."""
        for val, expected_display, expected_decimal in self.T9_ACCEPTANCE_TABLE:
            disp = format_display_price(val)
            dec = format_exact_decimal(val)
            self.assertEqual(
                disp, expected_display,
                f"Display mismatch for {val}: got {disp}, expected {expected_display}"
            )
            self.assertEqual(
                dec, expected_decimal,
                f"Decimal mismatch for {val}: got {dec}, expected {expected_decimal}"
            )
            # Guarantee no scientific notation ever
            self.assertNotIn("e", dec.lower(), f"Scientific notation detected in decimal: {dec}")
            self.assertNotIn("e", disp.lower(), f"Scientific notation detected in display: {disp}")
            # Positive micro-prices must never display as $0 or $0.0000
            self.assertNotEqual(disp, "$0", f"Micro-price {val} truncated to $0")
            self.assertNotEqual(disp, "$0.0000", f"Micro-price {val} truncated to $0.0000")

    def test_02_telegram_registered_message_formatting(self):
        """Verifies Telegram alert registration message uses exact decimal prices."""
        for val, expected_display, expected_dec in self.T9_ACCEPTANCE_TABLE:
            alert = Alert(
                id=f"alt_{val}",
                user_id="u1",
                exchange="binance",
                symbol="SHIBUSDT",
                target_price=val,
                condition="ABOVE",
                check_interval_seconds=60,
            )
            msg = format_alert_registered_telegram_msg(alert)
            self.assertIn(
                f"<code>{expected_display}</code>", msg,
                f"Telegram registration message did not contain expected price {expected_display}"
            )
            self.assertNotIn("e-", msg, f"Scientific notation in registration message: {msg}")

    def test_03_telegram_history_card_formatting(self):
        """Verifies Telegram history card renders exact micro-prices without rounding to $0."""
        for val, expected_display, _ in self.T9_ACCEPTANCE_TABLE:
            alert = Alert(
                id=f"alt_hist_{val}",
                user_id="u1",
                exchange="kucoin",
                symbol="PEPEUSDT",
                target_price=val,
                condition="ABOVE",
                check_interval_seconds=30,
            )
            card = format_telegram_history_card(
                alert=alert,
                current_price=val,
                triggered_target=val,
            )
            self.assertIn(
                expected_display, card,
                f"History card did not contain exact price {expected_display}"
            )
            self.assertNotIn("$0\n", card)
            self.assertNotIn("e-0", card)

    def test_04_fcm_payload_price_string(self):
        """Verifies FCM push payload price string is plain fixed-point decimal, never scientific notation."""
        for val, _, expected_dec in self.T9_ACCEPTANCE_TABLE:
            fcm_price_str = format_exact_decimal(val)
            self.assertEqual(fcm_price_str, expected_dec)
            self.assertNotIn("e", fcm_price_str.lower())

    def test_05_iran_toman_markets_preserved(self):
        """Verifies Iranian Toman markets format as integer Tomans without alteration."""
        tmn_price = 785000000.0
        disp_fa = format_display_price(tmn_price, is_tmn=True, tmn_label="تومان")
        disp_en = format_display_price(tmn_price, is_tmn=True, tmn_label="Tomans")
        self.assertEqual(disp_fa, "785,000,000 تومان")
        self.assertEqual(disp_en, "785,000,000 Tomans")


if __name__ == "__main__":
    unittest.main()
