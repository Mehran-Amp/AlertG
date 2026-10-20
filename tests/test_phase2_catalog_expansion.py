#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 2 Catalog Expansion (v3.9.0) Unit Tests:
- Seed and Candidate Counts:
  - seed/etfs_extended.json: exactly 114 symbols
  - seed/us_non_sp500.json: exactly 88 symbols
  - candidate_catalog_phase2.json: exactly 202 symbols
- Zero duplicate IDs or symbols (within and across files)
- Zero collision with existing catalog.json (SPY, QQQ, IWM, GLD, TSM, ASML, etc. strictly excluded)
- Mandatory fields present (id, symbol, nameEn, nameFa, category, exchange, currency, tier, provider_map, data_frequency, is_delayed)
- No guessed translations (nameFa == nameEn)
- ADR flags and countries for non-US equities
- Zero collision with existing index/equity aliases (such as DOW/DJI, SPX, NDX, etc.)
- Offline validator (validate_catalog_offline.py) passing for all 3 files

All tests run completely OFFLINE with NO network calls.
"""

import sys
import os
import json
import unittest
from unittest.mock import MagicMock

# Mock non-standard packages if running in minimal test environment
for mod in [
    'fastapi', 'fastapi.middleware.cors', 'fastapi.responses', 'pydantic', 'httpx',
    'apscheduler', 'apscheduler.schedulers', 'apscheduler.schedulers.asyncio',
    'firebase_admin', 'firebase_admin.credentials', 'firebase_admin.messaging', 'firebase_admin.exceptions'
]:
    if mod not in sys.modules:
        m = MagicMock()
        if mod == 'fastapi':
            class MockAPIRouter:
                def get(self, *args, **kwargs): return lambda func: func
                def post(self, *args, **kwargs): return lambda func: func
                def delete(self, *args, **kwargs): return lambda func: func
                def put(self, *args, **kwargs): return lambda func: func
            m.APIRouter = MockAPIRouter
            m.Depends = lambda x: x
            m.HTTPException = Exception
        if mod == 'pydantic':
            class BaseModel:
                def __init__(self, **kwargs):
                    for k, v in kwargs.items(): setattr(self, k, v)
                def dict(self): return self.__dict__
                def model_dump(self): return self.__dict__
            m.BaseModel = BaseModel
            m.Field = lambda *args, **kwargs: kwargs.get('default', None)
        sys.modules[mod] = m

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.validate_catalog_offline import validate_catalog_file


class TestPhase2CatalogExpansion(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.etfs_path = os.path.join(ROOT, "seed", "etfs_extended.json")
        cls.stocks_path = os.path.join(ROOT, "seed", "us_non_sp500.json")
        cls.candidate_path = os.path.join(ROOT, "candidate_catalog_phase2.json")
        cls.catalog_path = os.path.join(ROOT, "catalog.json")

        with open(cls.etfs_path, "r", encoding="utf-8") as f:
            cls.etfs_data = json.load(f)

        with open(cls.stocks_path, "r", encoding="utf-8") as f:
            cls.stocks_data = json.load(f)

        with open(cls.candidate_path, "r", encoding="utf-8") as f:
            cls.candidate_data = json.load(f)

        with open(cls.catalog_path, "r", encoding="utf-8") as f:
            cls.catalog_data = json.load(f)

    def test_01_seed_counts(self):
        """Validates exact counts: 114 ETFs, 88 Stocks, 202 Candidates"""
        etfs_symbols = self.etfs_data.get("symbols", [])
        stocks_symbols = self.stocks_data.get("symbols", [])
        candidate_symbols = self.candidate_data.get("symbols", [])

        self.assertEqual(len(etfs_symbols), 114, f"Expected 114 ETFs, got {len(etfs_symbols)}")
        self.assertEqual(len(stocks_symbols), 88, f"Expected 88 stocks, got {len(stocks_symbols)}")
        self.assertEqual(len(candidate_symbols), 202, f"Expected 202 candidates, got {len(candidate_symbols)}")

        # Verify header metadata
        self.assertEqual(self.etfs_data.get("source"), "curated owner list 2026-10-20")
        self.assertEqual(self.stocks_data.get("source"), "curated owner list 2026-10-20")
        self.assertEqual(self.candidate_data.get("source"), "curated owner list 2026-10-20")
        self.assertTrue(self.etfs_data.get("fetched_at"))
        self.assertTrue(self.stocks_data.get("fetched_at"))
        self.assertTrue(self.candidate_data.get("fetched_at"))

    def test_02_no_duplicate_ids_or_symbols(self):
        """Ensures 0 duplicate IDs or symbols within each seed file and across candidate catalog"""
        for label, data in [
            ("ETFs", self.etfs_data),
            ("Stocks", self.stocks_data),
            ("Candidates", self.candidate_data)
        ]:
            symbols = data.get("symbols", [])
            ids = [s.get("id") for s in symbols]
            syms = [s.get("symbol") for s in symbols]

            self.assertEqual(len(ids), len(set(ids)), f"Duplicate IDs found in {label}")
            self.assertEqual(len(syms), len(set(syms)), f"Duplicate symbols found in {label}")

    def test_03_no_collision_with_existing_catalog(self):
        """Verifies strictly zero collision with symbols already in catalog.json"""
        existing_ids = {s.get("id", "").upper() for s in self.catalog_data.get("symbols", [])}
        existing_syms = {s.get("symbol", "").upper() for s in self.catalog_data.get("symbols", [])}

        candidate_symbols = self.candidate_data.get("symbols", [])
        for item in candidate_symbols:
            item_id = item.get("id", "").upper()
            item_sym = item.get("symbol", "").upper()
            self.assertNotIn(item_id, existing_ids, f"Collision: {item_id} already exists in catalog.json")
            self.assertNotIn(item_sym, existing_syms, f"Collision: {item_sym} already exists in catalog.json")

        # Explicitly verify excluded symbols
        excluded_etfs = ['SPY', 'QQQ', 'IWM', 'GLD']
        for s in excluded_etfs:
            self.assertIn(s, existing_ids, f"{s} should be in catalog.json")
            self.assertNotIn(s, [x.get("id") for x in self.etfs_data["symbols"]], f"{s} must be excluded from etfs_extended.json")

        excluded_stocks = ['TSM', 'ASML', 'RACE', 'SHOP', 'SNOW', 'DDOG', 'TWLO', 'HOOD', 'COIN', 'MSTR', 'RKLB', 'ASTS', 'SPCX']
        for s in excluded_stocks:
            self.assertIn(s, existing_ids, f"{s} should be in catalog.json")
            self.assertNotIn(s, [x.get("id") for x in self.stocks_data["symbols"]], f"{s} must be excluded from us_non_sp500.json")

    def test_04_mandatory_fields_and_schema(self):
        """Verifies all mandatory fields, tier=popular, nameFa==nameEn, currency=USD, data_frequency=live"""
        for item in self.candidate_data.get("symbols", []):
            sym = item.get("id")
            self.assertTrue(item.get("id"), f"Missing id for {sym}")
            self.assertTrue(item.get("symbol"), f"Missing symbol for {sym}")
            self.assertTrue(item.get("nameEn"), f"Missing nameEn for {sym}")
            self.assertEqual(item.get("nameFa"), item.get("nameEn"), f"nameFa must equal nameEn (no guessed translations) for {sym}")
            self.assertIn(item.get("category"), ("etf", "stock"), f"Invalid category for {sym}")
            self.assertTrue(item.get("exchange") or item.get("marketName"), f"Missing exchange for {sym}")
            self.assertEqual(item.get("currency"), "USD", f"Currency must be USD for {sym}")
            self.assertEqual(item.get("tier"), "popular", f"Tier must be 'popular' for {sym}")
            self.assertEqual(item.get("data_frequency"), "live", f"data_frequency must be 'live' for {sym}")
            self.assertFalse(item.get("is_delayed"), f"is_delayed must be False for {sym}")

            # Provider map check
            pmap = item.get("provider_map", {})
            self.assertIsInstance(pmap, dict)
            self.assertIn("yahoo", pmap)
            self.assertEqual(pmap["yahoo"]["symbol"], sym)
            self.assertEqual(pmap["yahoo"]["priority"], 1)

        # Check ADR attributes on stocks
        for item in self.stocks_data.get("symbols", []):
            self.assertIn("is_adr", item, f"Missing is_adr on stock {item.get('id')}")
            self.assertIsInstance(item["is_adr"], bool)
            self.assertTrue(item.get("country"), f"Missing country for stock {item.get('id')}")

    def test_05_no_alias_or_index_collision(self):
        """Ensures new symbol IDs do not collide with known index/equity aliases (like DOW/DJI)"""
        from app.markets.global_stocks import EXACT_YF_MAP

        candidate_ids = {s.get("id") for s in self.candidate_data.get("symbols", [])}
        for c_id in candidate_ids:
            # New candidates should not collide with index aliases like SPX, DJI, NDX, etc.
            self.assertNotIn(c_id, EXACT_YF_MAP, f"New candidate {c_id} collides with index alias in EXACT_YF_MAP")

    def test_06_validate_catalog_offline_passes(self):
        """Runs scripts/validate_catalog_offline.py validation logic on all generated files"""
        is_valid_etf, errors_etf = validate_catalog_file(self.etfs_path)
        self.assertTrue(is_valid_etf, f"etfs_extended.json failed validation: {errors_etf}")
        self.assertEqual(len(errors_etf), 0)

        is_valid_stocks, errors_stocks = validate_catalog_file(self.stocks_path)
        self.assertTrue(is_valid_stocks, f"us_non_sp500.json failed validation: {errors_stocks}")
        self.assertEqual(len(errors_stocks), 0)

        is_valid_cand, errors_cand = validate_catalog_file(self.candidate_path)
        self.assertTrue(is_valid_cand, f"candidate_catalog_phase2.json failed validation: {errors_cand}")
        self.assertEqual(len(errors_cand), 0)


if __name__ == "__main__":
    unittest.main()
