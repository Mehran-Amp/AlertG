#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 2 Apply Expansion Verification Tests (v3.9.1)

Validates the applied catalog v3 completely OFFLINE:
1. catalog_version == 3, total_symbols == 772, total_active == 772, app_version == 3.9.1
2. IDs and symbols are strictly unique; SPLG is absent
3. Every one of the 571 previous symbols is identical to snapshot v2
4. Verification fields present on all 201 new symbols (source, verified_provider, last_verified_at, etc.)
5. /api/symbols/catalog?since_version=2 returns delta with exactly 201 added, 0 updated, 0 delisted
6. /api/symbols/catalog?since_version=0 returns all 772 symbols
7. /api/symbols?q=VOO and /api/symbols?q=BABA successfully return matching symbols
8. Offline execution in isolated temp dir does not touch production files
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

from fastapi.testclient import TestClient
from server import app
import app.config as config
from app.config import API_KEY, APP_VERSION
from app.engine.sync import list_catalog_snapshots, load_catalog, get_snapshots_dir
from scripts.apply_catalog_expansion import apply_expansion


class TestPhase2ApplyExpansion(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.headers = {"X-API-Key": API_KEY}
        cls.catalog_path = os.path.join(ROOT, "catalog.json")

        with open(cls.catalog_path, "r", encoding="utf-8") as f:
            cls.catalog_data = json.load(f)

    def setUp(self):
        # conftest isolates storage paths into tmp_path. Seed isolated snapshots dir
        # from ROOT/catalog_snapshots so delta endpoint has snapshot v2 available.
        snaps_dir = get_snapshots_dir()
        real_snaps = os.path.join(ROOT, "catalog_snapshots")
        if os.path.exists(real_snaps) and os.path.abspath(snaps_dir) != os.path.abspath(real_snaps):
            os.makedirs(snaps_dir, exist_ok=True)
            for item in os.listdir(real_snaps):
                src = os.path.join(real_snaps, item)
                dst = os.path.join(snaps_dir, item)
                if os.path.isfile(src) and not os.path.exists(dst):
                    shutil.copy2(src, dst)

        snapshots = list_catalog_snapshots()
        self.v2_snapshot = None
        for s in snapshots:
            if s.get("version") == 2:
                self.v2_snapshot = s
                break

    def test_01_catalog_version_and_counts(self):
        """Verifies catalog_version=3, total_symbols=772, total_active=772, app_version=3.9.1"""
        self.assertEqual(self.catalog_data.get("catalog_version"), 3)
        self.assertEqual(self.catalog_data.get("total_symbols"), 772)
        self.assertEqual(self.catalog_data.get("total_active"), 772)
        self.assertEqual(self.catalog_data.get("app_version"), APP_VERSION)
        self.assertEqual(APP_VERSION, "3.9.1")
        self.assertEqual(len(self.catalog_data.get("symbols", [])), 772)

    def test_02_id_and_symbol_uniqueness_and_absence_of_splg(self):
        """Ensures all 772 IDs and symbols are strictly unique, and SPLG is absent"""
        symbols = self.catalog_data.get("symbols", [])
        ids = [s.get("id") for s in symbols]
        syms = [s.get("symbol") for s in symbols]

        self.assertEqual(len(ids), len(set(ids)), "Duplicate IDs found in catalog.json")
        self.assertEqual(len(syms), len(set(syms)), "Duplicate symbols found in catalog.json")

        # Absence of SPLG
        upper_ids = {str(i).upper() for i in ids if i}
        upper_syms = {str(s).upper() for s in syms if s}
        self.assertNotIn("SPLG", upper_ids, "SPLG must be completely absent from catalog IDs")
        self.assertNotIn("SPLG", upper_syms, "SPLG must be completely absent from catalog symbols")

    def test_03_previous_571_symbols_identical_to_snapshot_v2(self):
        """Verifies all 571 symbols from snapshot v2 exist and are unchanged in catalog v3"""
        self.assertIsNotNone(self.v2_snapshot, "Snapshot for catalog version 2 must exist in catalog_snapshots/")
        snap_path = self.v2_snapshot["filepath"]
        self.assertTrue(os.path.exists(snap_path), f"Snapshot file not found at {snap_path}")

        with open(snap_path, "r", encoding="utf-8") as f:
            v2_data = json.load(f)

        v2_symbols = v2_data.get("symbols", [])
        self.assertEqual(len(v2_symbols), 571, f"Expected 571 symbols in snapshot v2, got {len(v2_symbols)}")

        current_map = {s["id"]: s for s in self.catalog_data.get("symbols", [])}

        for old in v2_symbols:
            old_id = old["id"]
            self.assertIn(old_id, current_map, f"Original symbol {old_id} missing from catalog v3")
            curr = current_map[old_id]

            # Core invariant fields must be preserved identically
            for field in ("id", "symbol", "nameEn", "nameFa", "category", "marketName", "unit", "currency", "is_active"):
                if field in old:
                    self.assertEqual(
                        curr.get(field), old.get(field),
                        f"Field '{field}' changed on existing symbol {old_id}: {old.get(field)} -> {curr.get(field)}"
                    )

    def test_04_verified_fields_on_201_new_symbols(self):
        """Validates schema and verification fields on the 201 newly added symbols"""
        self.assertIsNotNone(self.v2_snapshot, "Snapshot for v2 must be present")
        with open(self.v2_snapshot["filepath"], "r", encoding="utf-8") as f:
            v2_ids = {s["id"] for s in json.load(f).get("symbols", [])}

        new_symbols = [s for s in self.catalog_data.get("symbols", []) if s["id"] not in v2_ids]
        self.assertEqual(len(new_symbols), 201, f"Expected exactly 201 newly added symbols, found {len(new_symbols)}")

        for s in new_symbols:
            sym_id = s.get("id")
            self.assertEqual(s.get("source"), "curated owner list 2026-10-20", f"Invalid source for {sym_id}")
            self.assertEqual(s.get("verified_provider"), "yahoo", f"Invalid verified_provider for {sym_id}")
            self.assertTrue(s.get("last_verified_at"), f"Missing last_verified_at for {sym_id}")
            self.assertEqual(s.get("data_frequency"), "live", f"Invalid data_frequency for {sym_id}")
            self.assertFalse(s.get("is_delayed"), f"is_delayed must be False for {sym_id}")
            self.assertEqual(s.get("tier"), "popular", f"tier must be popular for {sym_id}")
            self.assertEqual(s.get("currency"), "USD", f"currency must be USD for {sym_id}")
            self.assertEqual(s.get("nameFa"), s.get("nameEn"), f"nameFa must equal nameEn for {sym_id}")
            self.assertNotIn("exchange", s, f"Redundant 'exchange' field must be removed from {sym_id}")
            self.assertNotIn("asset_class", s, f"Redundant 'asset_class' field must be removed from {sym_id}")

            cat = s.get("category")
            self.assertIn(cat, ("stock", "etf"), f"Invalid category for {sym_id}")
            if cat == "stock":
                self.assertEqual(s.get("unit"), "$", f"Stock unit must be '$' for {sym_id}")
                self.assertIn("is_adr", s, f"Missing is_adr on stock {sym_id}")
                self.assertTrue(s.get("country"), f"Missing country on stock {sym_id}")
            elif cat == "etf":
                self.assertEqual(s.get("unit"), "USD", f"ETF unit must be 'USD' for {sym_id}")

    def test_05_catalog_delta_api_since_version_2(self):
        """Verifies GET /api/symbols/catalog?since_version=2 returns exactly 201 added symbols"""
        resp = self.client.get("/api/symbols/catalog?since_version=2", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data.get("status"), "delta_success")
        self.assertTrue(data.get("is_delta"))
        self.assertTrue(data.get("has_changes"))
        self.assertEqual(data.get("catalog_version"), 3)
        self.assertEqual(data.get("since_version"), 2)

        added = data.get("added", [])
        updated = data.get("updated", [])
        delisted = data.get("delisted", [])

        self.assertEqual(len(added), 201, f"Expected 201 added in delta, got {len(added)}")
        self.assertEqual(len(updated), 0, f"Expected 0 updated in delta, got {len(updated)}")
        self.assertEqual(len(delisted), 0, f"Expected 0 delisted in delta, got {len(delisted)}")

        added_syms = {s.get("symbol") for s in added}
        self.assertIn("VOO", added_syms)
        self.assertIn("BABA", added_syms)
        self.assertNotIn("SPLG", added_syms)

    def test_06_catalog_api_since_version_0(self):
        """Verifies GET /api/symbols/catalog?since_version=0 returns all 772 active symbols"""
        resp = self.client.get("/api/symbols/catalog?since_version=0", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn(data.get("status"), ("success", "full_catalog"))
        self.assertEqual(data.get("catalog_version"), 3)
        self.assertEqual(data.get("total_count"), 772)
        self.assertEqual(len(data.get("symbols", [])), 772)

    def test_07_search_symbols_q_voo_and_baba(self):
        """Verifies /api/symbols?q=VOO and /api/symbols?q=BABA locate the new symbols"""
        # Test q=VOO
        resp_voo = self.client.get("/api/symbols?q=VOO", headers=self.headers)
        self.assertEqual(resp_voo.status_code, 200)
        voo_items = resp_voo.json().get("symbols", [])
        self.assertTrue(any(s.get("symbol") == "VOO" for s in voo_items), "VOO not found in search results")

        # Test q=BABA
        resp_baba = self.client.get("/api/symbols?q=BABA", headers=self.headers)
        self.assertEqual(resp_baba.status_code, 200)
        baba_items = resp_baba.json().get("symbols", [])
        self.assertTrue(any(s.get("symbol") == "BABA" for s in baba_items), "BABA not found in search results")

    def test_08_tmp_path_offline_expansion_isolation(self):
        """Runs expansion in isolated temporary directory to guarantee production files are untouched"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_candidate = os.path.join(tmp_dir, "test_candidates.json")
            candidate_payload = {
                "source": "curated owner list 2026-10-20",
                "total_count": 2,
                "symbols": [
                    {
                        "id": "TEST1",
                        "symbol": "TEST1",
                        "nameEn": "Test Stock 1",
                        "nameFa": "Test Stock 1",
                        "category": "stock",
                        "marketName": "NASDAQ",
                        "currency": "USD"
                    },
                    {
                        "id": "SPLG",
                        "symbol": "SPLG",
                        "nameEn": "SPDR Portfolio S&P 500 ETF",
                        "nameFa": "SPDR Portfolio S&P 500 ETF",
                        "category": "etf",
                        "marketName": "NYSE Arca",
                        "currency": "USD"
                    }
                ]
            }
            with open(tmp_candidate, "w", encoding="utf-8") as f:
                json.dump(candidate_payload, f)

            # Test dry-run with exclusion of SPLG
            res = apply_expansion(
                candidate_path=tmp_candidate,
                exclude="SPLG",
                verified_at="2026-10-26T12:00:00Z",
                verified_provider="yahoo",
                dry_run=True
            )
            self.assertEqual(res.get("added_count"), 1)
            self.assertIn("TEST1", res.get("added_symbols", []))
            self.assertNotIn("SPLG", res.get("added_symbols", []))


if __name__ == "__main__":
    unittest.main()
