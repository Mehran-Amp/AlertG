# -*- coding: utf-8 -*-
"""
AlertG — Phase 11 Integration & Verification Suite: Tabdeal & Iranian Crypto.
Covers:
1. 'iran_crypto' category resolution, 5.0s cache TTL, 1.00 outlier threshold.
2. Complete isolation of legacy 'iran_market' (60.0s cache TTL untouched).
3. Quote-based price formatting:
   - Large Toman prices (>= 100 TMN) formatted with thousands separators.
   - Micro Toman prices (< 100 TMN) keep exact decimals, never truncate to 0.
   - USDT micro prices (< 1.0) keep exact significant digits, never "$0", never scientific notation.
4. Tabdeal registration in crypto_registry with dedicated provider key and R11 source label.
5. Compliance matrix documentation verification.
"""
import os
import unittest
from decimal import Decimal

from app.engine.categories import (
    resolve_symbol_category,
    CATEGORY_CACHE_TTL,
    CATEGORY_OUTLIER_THRESHOLDS,
)
from app.engine.formatter import format_exact_decimal, format_display_price
from app.markets.crypto_registry import (
    get_crypto_exchange,
    is_supported_crypto_exchange,
    list_crypto_exchanges,
)
from app.markets.crypto_catalog import get_exchange_adapter


class TestPhase11TabdealAndIranCrypto(unittest.TestCase):

    def test_01_category_resolution_for_tabdeal(self):
        """1. Verify Tabdeal symbols resolve to 'iran_crypto' with 5s cache TTL and 100% threshold."""
        # Both USDT and IRT/TMN pairs on Tabdeal must resolve to 'iran_crypto'
        self.assertEqual(resolve_symbol_category("tabdeal", "BTCUSDT"), "iran_crypto")
        self.assertEqual(resolve_symbol_category("tabdeal", "BTCIRT"), "iran_crypto")
        self.assertEqual(resolve_symbol_category("tabdeal", "USDTIRT"), "iran_crypto")

        # Verify cache TTL: fast 5.0s for iran_crypto
        self.assertEqual(CATEGORY_CACHE_TTL.get("iran_crypto"), 5.0)

        # Verify outlier jump threshold: 100% (1.00)
        self.assertEqual(CATEGORY_OUTLIER_THRESHOLDS.get("iran_crypto"), 1.00)

    def test_02_legacy_iran_market_remains_untouched(self):
        """2. Verify legacy domestic markets (TSE, Bonbast, Gold) retain strict 60s cache TTL."""
        self.assertEqual(CATEGORY_CACHE_TTL.get("iran_market"), 60.0)
        self.assertEqual(CATEGORY_OUTLIER_THRESHOLDS.get("iran_market"), 0.50)

        # TSE and Bonbast pairs continue resolving to 'iran_market'
        self.assertEqual(resolve_symbol_category("tse", "FOULAD"), "iran_market")
        self.assertEqual(resolve_symbol_category("bonbast", "USD_TMN"), "iran_market")

    def test_03_crypto_registry_tabdeal_metadata(self):
        """3. Verify Tabdeal is registered in crypto_registry conforming to Rule R11."""
        self.assertTrue(is_supported_crypto_exchange("tabdeal"))

        meta = get_crypto_exchange("tabdeal")
        self.assertIsNotNone(meta)
        self.assertEqual(meta.id, "tabdeal")
        self.assertEqual(meta.name, "Tabdeal")
        self.assertEqual(meta.category, "iran_crypto")
        self.assertEqual(meta.provider_key, "crypto_tabdeal")
        self.assertEqual(meta.status, "active")

        # Rule R11: source_label must contain exchange id '(tabdeal)'
        self.assertIn("(tabdeal)", meta.source_label)

        # Aliases support
        self.assertEqual(get_crypto_exchange("tabdeal_spot").id, "tabdeal")
        self.assertEqual(get_crypto_exchange("tabdeal_iran").id, "tabdeal")

        # Adapter factory lookup
        adapter = get_exchange_adapter("tabdeal")
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.exchange_id, "tabdeal")

    def test_04_quote_based_toman_price_formatting(self):
        """4. Verify Toman price formatting: integer commas for >= 100, exact decimals for < 100."""
        # Large Toman prices >= 100
        formatted_btc = format_display_price(2109583329.1, is_tmn=True, tmn_label="تومان")
        self.assertEqual(formatted_btc, "2,109,583,329 تومان")

        formatted_usdt = format_display_price(27125.0, is_tmn=True, tmn_label="تومان")
        self.assertEqual(formatted_usdt, "27,125 تومان")

        # Micro Toman prices < 100 (e.g. PEPE, BTTC, SHIB) must NOT truncate to 0!
        formatted_pepe = format_display_price(0.1356, is_tmn=True, tmn_label="تومان")
        self.assertEqual(formatted_pepe, "0.1356 تومان")

        formatted_bttc = format_display_price(0.0095, is_tmn=True, tmn_label="تومان")
        self.assertEqual(formatted_bttc, "0.0095 تومان")

        # Zero value
        self.assertEqual(format_display_price(0.0, is_tmn=True, tmn_label="تومان"), "0 تومان")

    def test_05_usdt_micro_price_formatting(self):
        """5. Verify USDT micro coin prices (< 1.0) preserve all significant decimals (Rule R3)."""
        # Micro price (PEPE = 0.0000049532)
        pepe_fmt = format_display_price(0.0000049532, currency_prefix="$", is_tmn=False)
        self.assertEqual(pepe_fmt, "$0.0000049532")
        self.assertNotIn("$0", pepe_fmt[1:])  # Never plain "$0"
        self.assertNotIn("e", pepe_fmt.lower())  # Never scientific notation

        # Sub-satoshi micro price (BTTC = 0.00000035)
        bttc_fmt = format_display_price(0.00000035, currency_prefix="$", is_tmn=False)
        self.assertEqual(bttc_fmt, "$0.00000035")

        # Standard price >= 1.0
        btc_fmt = format_display_price(78181.50, currency_prefix="$", is_tmn=False)
        self.assertEqual(btc_fmt, "$78,181.50")

    def test_06_compliance_matrix_documentation_exists(self):
        """6. Verify docs/iran_exchanges_compliance.md exists and documents Iranian exchanges."""
        doc_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "docs", "iran_exchanges_compliance.md"
        ))
        self.assertTrue(os.path.exists(doc_path), f"Compliance doc missing at {doc_path}")

        with open(doc_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check required rows from compliance checklist
        self.assertIn("tabdeal", content)
        self.assertIn("APPROVED", content)
        self.assertIn("nobitex", content)
        self.assertIn("FROZEN", content)
        self.assertIn("wallex", content)
        self.assertIn("bitpin", content)
        self.assertIn("ramzinex", content)


if __name__ == "__main__":
    unittest.main()
