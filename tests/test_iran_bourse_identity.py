# -*- coding: utf-8 -*-
"""IB-3: Iranian Bourse identity, settings and kill switch. Other markets must not change."""
import os
import unittest
from unittest.mock import patch

import app.config as config
from app.engine.categories import (
    CATEGORY_CACHE_TTL, CATEGORY_OUTLIER_THRESHOLDS, resolve_symbol_category,
    get_category_cache_ttl, get_category_outlier_threshold,
)
from app.markets.kill_switch import is_category_killed

AYAR_ID = "34144395039913458"


class BourseIdentityTests(unittest.TestCase):
    def test_tsetmc_resolves_to_iran_bourse(self):
        self.assertEqual(resolve_symbol_category("tsetmc", AYAR_ID), "iran_bourse")
        self.assertEqual(resolve_symbol_category("TSETMC", AYAR_ID), "iran_bourse")

    def test_ttl_and_threshold(self):
        self.assertEqual(get_category_cache_ttl("iran_bourse"), 3.0)
        self.assertEqual(get_category_outlier_threshold("iran_bourse"), 0.50)

    def test_other_markets_unchanged(self):
        table = [
            (("tse", "TEPIX"), "iran_market"),
            (("bonbast", "USD"), "iran_market"),
            (("bridge", "USD"), "iran_market"),
            (("nobitex", "BTCIRT"), "iran_market"),
            (("iran_market", "USDT_TMN"), "iran_market"),
            (("iran_market", "GOLD_18"), "iran_market"),
            (("tabdeal", "BTCUSDT"), "iran_crypto"),
            (("binance", "BTCUSDT"), "crypto"),
            (("okx", "BTC-USDT"), "crypto"),
            (("global_stocks", "AAPL"), "stock"),
            (("global_stocks", "EURUSD"), "forex"),
            (("global_stocks", "SPX"), "index"),
            (("global_stocks", "XAUUSD"), "commodity"),
        ]
        for (ex, sym), expected in table:
            self.assertEqual(resolve_symbol_category(ex, sym), expected, f"{ex}:{sym}")

    def test_existing_ttl_and_thresholds_untouched(self):
        self.assertEqual(CATEGORY_CACHE_TTL["iran_market"], 60.0)
        self.assertEqual(CATEGORY_CACHE_TTL["iran_crypto"], 5.0)
        self.assertEqual(CATEGORY_CACHE_TTL["crypto"], 2.0)
        self.assertEqual(CATEGORY_OUTLIER_THRESHOLDS["iran_market"], 0.50)
        self.assertEqual(CATEGORY_OUTLIER_THRESHOLDS["iran_crypto"], 1.00)
        self.assertEqual(config.CACHE_TTL_IRAN, 60.0)

    def test_iran_market_ids_never_map_to_bourse(self):
        for ex in ("tse", "bonbast", "bridge", "iran_market", "nobitex"):
            self.assertNotEqual(resolve_symbol_category(ex, "X"), "iran_bourse", ex)


class BourseSettingsTests(unittest.TestCase):
    @unittest.skipIf(os.getenv("IRAN_BOURSE_ENABLED"), "env override present")
    def test_flag_off_by_default(self):
        self.assertIs(config.IRAN_BOURSE_ENABLED, False)

    def test_poll_never_below_three_seconds(self):
        self.assertGreaterEqual(config.IRAN_BOURSE_POLL_SECONDS, 3.0)

    def test_allowed_versions_default(self):
        if not os.getenv("IRAN_BOURSE_ALLOWED_VERSIONS"):
            self.assertEqual(config.IRAN_BOURSE_ALLOWED_VERSIONS, ["0.2.2"])


class BourseKillSwitchTests(unittest.TestCase):
    def test_kill_switch_only_hits_bourse(self):
        with patch.dict(os.environ, {"KILL_SWITCH_CATEGORIES": "iran_bourse"}):
            self.assertTrue(is_category_killed("iran_bourse"))
            for other in ("crypto", "iran_market", "iran_crypto", "stock", "forex", "index",
                          "commodity", "macro", "bond"):
                self.assertFalse(is_category_killed(other), other)

    def test_per_category_env_variable(self):
        with patch.dict(os.environ, {"KILL_SWITCH_CATEGORY_IRAN_BOURSE": "1"}):
            self.assertTrue(is_category_killed("iran_bourse"))
            self.assertFalse(is_category_killed("iran_market"))

    def test_killing_iran_market_does_not_kill_bourse(self):
        with patch.dict(os.environ, {"KILL_SWITCH_CATEGORIES": "iran,iran_market"}):
            self.assertTrue(is_category_killed("iran_market"))
            self.assertFalse(is_category_killed("iran_bourse"))

    def test_off_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            for k in ("KILL_SWITCH_CATEGORIES", "KILL_SWITCH_CATEGORY_IRAN_BOURSE"):
                os.environ.pop(k, None)
            self.assertFalse(is_category_killed("iran_bourse"))


if __name__ == "__main__":
    unittest.main()
