#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 4 (v3.2.0) Comprehensive Unit Tests:
- Seed Files Structure & Headers
- Structural & Domain Validation Rules (SYMBOL_RE, EXCHANGE_RE, asset_class, currency, provider_map)
- Rejection of isolated Iran market and Crypto symbols from global catalog
- Duplicate and multi-category cross-contamination detection
- Offline Catalog Validator script execution
- Golden Phase 0 Endpoint Compatibility for /api/symbols/wallstreet-macro

All tests execute strictly OFFLINE with NO network requests.
"""

import unittest
import os
import sys
import json
import tempfile
import shutil
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
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from app.engine.sync import (
    validate_candidate_catalog,
    CatalogValidationError,
    SYMBOL_RE,
    EXCHANGE_RE,
    VALID_ASSET_CLASSES,
    VALID_CURRENCIES,
    ALLOWED_PROVIDERS,
    FORBIDDEN_CATEGORIES
)
from scripts.validate_catalog_offline import validate_catalog_payload, validate_catalog_file


class TestPhase4CatalogSeedAndValidation(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_valid_item_passes_validation(self):
        """Valid equity item passes both validate_candidate_catalog and validate_catalog_payload"""
        valid_item = {
            "id": "AAPL",
            "symbol": "AAPL",
            "display_name": "Apple Inc.",
            "nameEn": "Apple Inc.",
            "nameFa": "سهام اپل",
            "asset_class": "stock",
            "category": "stock",
            "exchange": "NASDAQ",
            "marketName": "NASDAQ",
            "currency": "USD",
            "unit": "$",
            "tier": 1,
            "provider_map": {
                "yahoo": {"symbol": "AAPL", "priority": 1},
                "finnhub": {"symbol": "AAPL", "priority": 2}
            },
            "data_frequency": "live",
            "is_delayed": False
        }
        res = validate_candidate_catalog([valid_item], strict=True)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["symbol"], "AAPL")

        is_valid, errors = validate_catalog_payload([valid_item])
        self.assertTrue(is_valid, f"Validation errors: {errors}")
        self.assertEqual(len(errors), 0)

    def test_02_symbol_regex_validation(self):
        """Invalid symbols violate SYMBOL_RE pattern"""
        invalid_symbols = ["", "   ", "AAPL@@@", "INVALID/LONG/TICKER/NAME/EXCEEDING/TWENTY/FOUR/CHARS", "$%^&*"]
        for bad_sym in invalid_symbols:
            item = {
                "id": bad_sym,
                "symbol": bad_sym,
                "category": "stock",
                "marketName": "NASDAQ",
                "unit": "$"
            }
            with self.assertRaises(CatalogValidationError):
                validate_candidate_catalog([item], strict=True)

            is_valid, errors = validate_catalog_payload([item])
            self.assertFalse(is_valid)

    def test_03_exchange_regex_validation(self):
        """Invalid exchanges violate EXCHANGE_RE pattern"""
        invalid_exchanges = ["", "@", "X", "VERY_LONG_NAME_EXCEEDING_FORTY_CHARACTERS_HERE_1234567890"]
        for bad_ex in invalid_exchanges:
            item = {
                "id": "TEST",
                "symbol": "TEST",
                "category": "stock",
                "marketName": bad_ex,
                "unit": "$"
            }
            with self.assertRaises(CatalogValidationError):
                validate_candidate_catalog([item], strict=True)

    def test_04_asset_class_validation(self):
        """Invalid asset class / category is rejected"""
        invalid_classes = ["unknown_class", "derivatives", "options", "crypto_futures"]
        for bad_class in invalid_classes:
            item = {
                "id": "TEST",
                "symbol": "TEST",
                "category": bad_class,
                "marketName": "NASDAQ",
                "unit": "$"
            }
            with self.assertRaises(CatalogValidationError):
                validate_candidate_catalog([item], strict=True)

    def test_05_iran_and_crypto_isolation(self):
        """Iran domestic market and crypto are forbidden in global catalog"""
        forbidden_samples = [
            {"id": "GOLD18", "symbol": "GOLD18", "category": "iran_market", "marketName": "Bonbast", "unit": "ت"},
            {"id": "BTC_CRYPTO", "symbol": "BTC", "category": "crypto", "marketName": "Binance", "unit": "$"}
        ]
        for forbidden in forbidden_samples:
            with self.assertRaises(CatalogValidationError):
                validate_candidate_catalog([forbidden], strict=True)

            is_valid, errors = validate_catalog_payload([forbidden])
            self.assertFalse(is_valid)
            self.assertTrue(any("isolated" in err.lower() for err in errors))

    def test_06_currency_validation(self):
        """Invalid currency codes are rejected"""
        bad_currency_item = {
            "id": "AAPL",
            "symbol": "AAPL",
            "category": "stock",
            "marketName": "NASDAQ",
            "unit": "INVALID_CURR"
        }
        with self.assertRaises(CatalogValidationError):
            validate_candidate_catalog([bad_currency_item], strict=True)

    def test_07_provider_map_rejects_unapproved_providers(self):
        """Only Yahoo, Finnhub, Twelve Data, FRED permitted; Stooq or unapproved providers rejected"""
        bad_prov_item = {
            "id": "AAPL",
            "symbol": "AAPL",
            "category": "stock",
            "marketName": "NASDAQ",
            "unit": "$",
            "provider_map": {
                "stooq": {"symbol": "AAPL.US", "priority": 1}
            }
        }
        with self.assertRaises(CatalogValidationError):
            validate_candidate_catalog([bad_prov_item], strict=True)

        is_valid, errors = validate_catalog_payload([bad_prov_item])
        self.assertFalse(is_valid)
        self.assertTrue(any("stooq" in err.lower() for err in errors))

    def test_08_duplicate_symbol_detection(self):
        """Duplicate symbols within candidate catalog are rejected in strict mode"""
        items = [
            {"id": "AAPL", "symbol": "AAPL", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
            {"id": "AAPL", "symbol": "AAPL", "category": "stock", "marketName": "NASDAQ", "unit": "$"}
        ]
        with self.assertRaises(CatalogValidationError):
            validate_candidate_catalog(items, strict=True)

        is_valid, errors = validate_catalog_payload(items)
        self.assertFalse(is_valid)
        self.assertTrue(any("duplicate" in err.lower() for err in errors))

    def test_09_multi_category_collision(self):
        """Symbol assigned to two different asset classes is rejected"""
        items = [
            {"id": "GOLD", "symbol": "GOLD", "category": "commodity", "marketName": "COMEX", "unit": "$"},
            {"id": "GOLD", "symbol": "GOLD", "category": "stock", "marketName": "NYSE", "unit": "$"}
        ]
        with self.assertRaises(CatalogValidationError):
            validate_candidate_catalog(items, strict=True)

    def test_10_seed_files_headers_and_integrity(self):
        """Verifies all 8 seed files exist, have headers (source, fetched_at), and pass offline validation"""
        seed_files = [
            "us_stocks.json", "etfs.json", "forex.json", "indices.json",
            "commodities.json", "bonds.json", "macro.json", "china_hk_stocks.json"
        ]
        seed_dir = os.path.join(ROOT, "seed")
        self.assertTrue(os.path.isdir(seed_dir), "seed/ directory must exist")

        for sfile in seed_files:
            path = os.path.join(seed_dir, sfile)
            self.assertTrue(os.path.exists(path), f"Seed file missing: {sfile}")
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("source", data)
            self.assertIn("fetched_at", data)
            self.assertIn("symbols", data)
            self.assertGreater(len(data["symbols"]), 0)

            # Validate each symbol in seed has mandatory fields
            for item in data["symbols"]:
                self.assertIn("id", item)
                self.assertIn("display_name", item)
                self.assertIn("asset_class", item)
                self.assertIn("exchange", item)
                self.assertIn("currency", item)
                self.assertIn("tier", item)
                self.assertIn("provider_map", item)
                self.assertIn("data_frequency", item)
                self.assertIn("is_delayed", item)

            # Offline validation passes
            is_valid, errors = validate_catalog_file(path)
            self.assertTrue(is_valid, f"Seed file {sfile} failed validation: {errors}")

    def test_11_legacy_wallstreet_macro_matches_golden_count_and_categories(self):
        """Verifies /api/symbols/wallstreet-macro returns 94 symbols matching golden categories"""
        from app.routes.symbols import get_debug_wallstreet_macro_symbols
        res = get_debug_wallstreet_macro_symbols(since_version=None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["total_count"], 94)
        self.assertEqual(res["categories"]["stock"], 41)
        self.assertEqual(res["categories"]["forex"], 9)
        self.assertEqual(res["categories"]["bond"], 3)
        self.assertEqual(res["categories"]["commodity"], 8)
        self.assertEqual(res["categories"]["index"], 9)
        self.assertEqual(res["categories"]["iran_market"], 24)


if __name__ == '__main__':
    unittest.main()
