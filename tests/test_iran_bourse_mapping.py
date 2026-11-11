# -*- coding: utf-8 -*-
"""IB-4b: gateway quote -> AlertG price result."""
import copy
import json
import os
import unittest

from app.markets.iran_bourse.mapping import (
    MappingError, meta_as_of, quote_to_price_result, REQUIRED_QUOTE_FIELDS,
)

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "iran_bourse")
AYAR_ID = "34144395039913458"


def load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


class MappingTests(unittest.TestCase):
    def setUp(self):
        env = load("quote_ayar.json")
        self.quote, self.meta = env["data"], env["meta"]

    def test_golden_ayar_last(self):
        r = quote_to_price_result(self.quote, self.meta)
        self.assertEqual(r["price"], 693731)
        self.assertEqual(r["prev_close"], 685477)
        self.assertEqual(r["currency"], "IRR")
        self.assertEqual(r["source"], "tsetmc-gateway")
        self.assertEqual(r["symbol"], AYAR_ID)
        self.assertEqual(r["name"], "صندوق طلای عیار مفید")
        self.assertEqual(r["ticker"], "عیار")
        self.assertTrue(r["traded_today"])
        self.assertEqual(r["state"], "LIVE")

    def test_close_price_field(self):
        r = quote_to_price_result(self.quote, self.meta, price_field="close")
        self.assertEqual(r["price"], 693152)
        self.assertEqual(r["change_pct"], self.quote["close_change_pct"])

    def test_no_unit_conversion(self):
        self.assertEqual(quote_to_price_result(self.quote, self.meta)["price"], self.quote["last"])

    def test_id_stays_a_string(self):
        r = quote_to_price_result(self.quote, self.meta)
        self.assertIsInstance(r["symbol"], str)
        self.assertGreater(int(r["symbol"]), 2 ** 53)

    def test_as_of_is_gateway_fetch_time_not_trade_time(self):
        meta = dict(self.meta, updated_at="2026-11-11T10:00:00+00:00")
        r = quote_to_price_result(self.quote, meta)
        self.assertEqual(r["asOf"], 1794391200)
        self.assertEqual(r["last_trade_time"], self.quote["update_time"])

    def test_meta_as_of_bad_values(self):
        self.assertIsNone(meta_as_of({}))
        self.assertIsNone(meta_as_of({"updated_at": "garbage"}))
        self.assertIsNone(meta_as_of(None))

    def test_stale_meta(self):
        r = quote_to_price_result(self.quote, dict(self.meta, stale=True))
        self.assertEqual(r["state"], "STALE")
        self.assertTrue(r["is_stale"])

    def test_not_traded_gives_no_trade_state(self):
        q = dict(self.quote, traded=False, trades=0, last=0)
        r = quote_to_price_result(q, self.meta)
        self.assertIsNone(r["price"])
        self.assertEqual(r["state"], "NO_TRADE_TODAY")

    def test_zero_price_is_none(self):
        self.assertIsNone(quote_to_price_result(dict(self.quote, last=0), self.meta)["price"])

    def test_null_labels_pass_through(self):
        q = dict(self.quote, market=None, board=None, sector=None)
        r = quote_to_price_result(q, self.meta)
        self.assertIsNone(r["market"])
        self.assertIsNone(r["board"])

    def test_every_required_field_is_enforced(self):
        for field in REQUIRED_QUOTE_FIELDS:
            q = copy.deepcopy(self.quote)
            del q[field]
            with self.assertRaises(MappingError, msg=field):
                quote_to_price_result(q, self.meta)

    def test_numeric_id_rejected(self):
        with self.assertRaises(MappingError):
            quote_to_price_result(dict(self.quote, id=34144395039913458), self.meta)

    def test_bad_price_field(self):
        with self.assertRaises(MappingError):
            quote_to_price_result(self.quote, self.meta, price_field="first")

    def test_input_not_mutated(self):
        before = copy.deepcopy(self.quote)
        quote_to_price_result(self.quote, self.meta)
        self.assertEqual(before, self.quote)


if __name__ == "__main__":
    unittest.main()
