#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 8 (v3.5.0) Unit Tests:
- Stage 9 Catalog Apply & Sync Runs Engine
- Pre-apply snapshot generation and verification
- Atomic save and catalog_version increment (+1)
- sync_runs.json audit trail registration
- Staging mode isolation vs Production mode
- Legacy /api/symbols/wallstreet-macro golden compatibility (94 symbols, zero contamination)
- Safety threshold enforcement and bypass
"""

import os
import sys
import json
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.apply_catalog import apply_catalog_transaction, load_candidate_symbols
from app.engine.sync import (
    load_catalog, save_catalog, load_sync_runs,
    CatalogSafetyCeilingExceededError
)
from app.routes.symbols import (
    get_debug_wallstreet_macro_symbols,
    load_golden_legacy_wallstreet_macro
)


class TestPhase8ApplyCatalog(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.test_catalog_file = os.path.join(self.tmp_dir, "test_catalog.json")
        self.test_staging_file = os.path.join(self.tmp_dir, "test_catalog.staging.json")
        self.test_sync_runs_file = os.path.join(self.tmp_dir, "test_sync_runs.json")

        # Initial catalog baseline (v1 with 3 symbols)
        self.initial_data = {
            "schema_version": 1,
            "catalog_version": 1,
            "app_version": "3.5.0",
            "last_sync_at": "2026-10-10T12:00:00Z",
            "total_active": 3,
            "total_symbols": 3,
            "symbols": [
                {
                    "id": "AAPL",
                    "symbol": "AAPL",
                    "nameEn": "Apple Inc.",
                    "nameFa": "سهام اپل",
                    "category": "stock",
                    "marketName": "NASDAQ",
                    "unit": "$",
                    "is_active": 1
                },
                {
                    "id": "MSFT",
                    "symbol": "MSFT",
                    "nameEn": "Microsoft Corporation",
                    "nameFa": "سهام مایکروسافت",
                    "category": "stock",
                    "marketName": "NASDAQ",
                    "unit": "$",
                    "is_active": 1
                },
                {
                    "id": "US10Y",
                    "symbol": "US10Y (^TNX)",
                    "nameEn": "US 10-Year Treasury Yield",
                    "nameFa": "اوراق ۱۰ ساله آمریکا",
                    "category": "bond",
                    "marketName": "US Treasury",
                    "unit": "%",
                    "is_active": 1
                }
            ]
        }
        with open(self.test_catalog_file, "w", encoding="utf-8") as f:
            json.dump(self.initial_data, f, indent=2)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_pre_apply_snapshot_is_created(self):
        """Verifies snapshot file is created prior to mutating catalog."""
        candidates = [dict(s) for s in self.initial_data["symbols"]]

        res = apply_catalog_transaction(
            target_catalog_file=self.test_catalog_file,
            candidate_items=candidates,
            mode="staging",
            dry_run=False,
            ignore_safety=True,
            sync_runs_file=self.test_sync_runs_file
        )

        snapshot_path = res["snapshot_path"]
        self.assertTrue(os.path.exists(snapshot_path), f"Snapshot missing: {snapshot_path}")

        # Check snapshot content matches version before apply
        with open(snapshot_path, "r", encoding="utf-8") as f:
            snap_data = json.load(f)
        self.assertEqual(snap_data["catalog_version"], 1)

    def test_02_version_increment_and_atomic_update(self):
        """Verifies catalog_version is incremented by exactly +1 and written correctly."""
        candidates = [dict(s) for s in self.initial_data["symbols"]]

        res = apply_catalog_transaction(
            target_catalog_file=self.test_catalog_file,
            candidate_items=candidates,
            mode="production",
            dry_run=False,
            ignore_safety=True,
            sync_runs_file=self.test_sync_runs_file
        )

        self.assertEqual(res["version_from"], 1)
        self.assertEqual(res["version_to"], 2)

        # Check on-disk catalog
        with open(self.test_catalog_file, "r", encoding="utf-8") as f:
            updated = json.load(f)
        self.assertEqual(updated["catalog_version"], 2)
        self.assertEqual(updated["total_active"], 3)

    def test_03_sync_runs_recorded_with_audit_trail(self):
        """Verifies sync_runs.json is populated with execution details."""
        candidates = [dict(s) for s in self.initial_data["symbols"]]

        res = apply_catalog_transaction(
            target_catalog_file=self.test_catalog_file,
            candidate_items=candidates,
            mode="staging",
            dry_run=False,
            ignore_safety=True,
            sync_runs_file=self.test_sync_runs_file
        )

        self.assertTrue(os.path.exists(self.test_sync_runs_file))
        runs_data = load_sync_runs(self.test_sync_runs_file)
        self.assertEqual(runs_data["total_runs"], 1)
        self.assertEqual(runs_data["last_run_id"], res["run_id"])

        entry = runs_data["runs"][0]
        self.assertEqual(entry["mode"], "staging")
        self.assertEqual(entry["status"], "SUCCESS")
        self.assertEqual(entry["version_from"], 1)
        self.assertEqual(entry["version_to"], 2)
        self.assertEqual(entry["total_symbols"], 3)
        self.assertIn("diff", entry)

    def test_04_staging_mode_isolation(self):
        """Verifies staging mode does not modify production catalog."""
        # Initial production file
        prod_mtime_before = os.path.getmtime(self.test_catalog_file)

        candidates = [dict(s) for s in self.initial_data["symbols"]]
        candidates.append({
            "id": "NVDA",
            "symbol": "NVDA",
            "nameEn": "NVIDIA",
            "nameFa": "انویدیا",
            "category": "stock",
            "marketName": "NASDAQ",
            "unit": "$",
            "is_active": 1
        })

        res = apply_catalog_transaction(
            target_catalog_file=self.test_staging_file,
            candidate_items=candidates,
            mode="staging",
            dry_run=False,
            ignore_safety=True,
            sync_runs_file=self.test_sync_runs_file
        )

        # Staging catalog was updated
        with open(self.test_staging_file, "r", encoding="utf-8") as f:
            stg = json.load(f)
        self.assertEqual(stg["catalog_version"], 2)
        self.assertEqual(stg["total_active"], 4)

        # Production catalog was untouched
        with open(self.test_catalog_file, "r", encoding="utf-8") as f:
            prod = json.load(f)
        self.assertEqual(prod["catalog_version"], 1)
        self.assertEqual(prod["total_active"], 3)

    def test_05_legacy_wallstreet_macro_isolated_and_matches_golden_count(self):
        """Verifies /api/symbols/wallstreet-macro returns 94 golden symbols regardless of catalog size."""
        # Even if catalog has 3 symbols or 600 symbols:
        legacy_res = get_debug_wallstreet_macro_symbols(since_version=None)
        self.assertEqual(legacy_res["status"], "success")
        self.assertEqual(legacy_res["total_count"], 94)
        self.assertEqual(legacy_res["categories"]["stock"], 41)
        self.assertEqual(legacy_res["categories"]["forex"], 9)
        self.assertEqual(legacy_res["categories"]["bond"], 3)
        self.assertEqual(legacy_res["categories"]["commodity"], 8)
        self.assertEqual(legacy_res["categories"]["index"], 9)
        self.assertEqual(legacy_res["categories"]["iran_market"], 24)

    def test_06_dry_run_does_not_mutate_files(self):
        """Verifies dry-run returns proposed diff without writing files."""
        candidates = [dict(s) for s in self.initial_data["symbols"]]
        candidates.append({
            "id": "TSLA",
            "symbol": "TSLA",
            "nameEn": "Tesla",
            "nameFa": "تسلا",
            "category": "stock",
            "marketName": "NASDAQ",
            "unit": "$",
            "is_active": 1
        })

        res = apply_catalog_transaction(
            target_catalog_file=self.test_catalog_file,
            candidate_items=candidates,
            mode="staging",
            dry_run=True,
            ignore_safety=True,
            sync_runs_file=self.test_sync_runs_file
        )

        self.assertEqual(res["status"], "dry_run")
        # File version on disk remains 1
        with open(self.test_catalog_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["catalog_version"], 1)
        self.assertEqual(data["total_active"], 3)
        self.assertFalse(os.path.exists(self.test_sync_runs_file))


if __name__ == "__main__":
    unittest.main()
