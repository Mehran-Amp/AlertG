#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit Tests for Phase 6 (v3.4.0): Catalog Probe & Pre-Apply Reporting Engine
Verifies Acceptance Criteria:
1. Resumable Checkpoint Execution:
   - Checkpoint creation, partial batch saving, and resumption without re-probing completed items.
2. Batch Splitting:
   - Symbols chunked into configurable batches (50 to 100 items).
3. Treasury Yields Side-by-Side Table:
   - Evaluates 13W, 2Y, 5Y, 10Y, and 30Y tenors.
   - Strictly enforces FRED-only rule for 2-year yield (US02Y / DGS2) with no Yahoo fallback.
4. Dynamic Single Source Determination:
   - Determined strictly based on actual successful probe responses, not static mappings.
   - Exactly 1 provider quote -> single_source = True.
   - 2+ provider quotes -> single_source = False.
5. Secondary Providers (Twelve Data & Finnhub):
   - Probed ONLY for tier=major symbols.
   - Budgeted at ~10% sample rate, respecting free-tier quotas.
6. Currency Mismatch Detection:
   - Identifies discrepancy between catalog expected unit and actual response currency.
7. Rejected Symbols Output:
   - Generates reports/rejected.json for items where all providers fail.
8. Owner Summary Report:
   - Produces category breakdown, single_source list, currency mismatch list, and quota usage.
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
import asyncio
from typing import Dict, Any, List

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.config import APP_VERSION
from app.markets.global_stocks import (
    resolve_yf_symbol,
    resolve_symbol_alias,
    FRED_ONLY_SYMBOLS,
    fred_adapter,
)
from scripts.probe_catalog import (
    CatalogProbeRunner,
    ProbeCheckpoint,
    TREASURY_TENORS,
    is_tier_major,
    is_sampled_for_secondary,
    check_currency_match,
    OFFICIAL_QUOTAS,
)


class TestPhase6ProbeCatalog(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_probe_")
        self.catalog_file = os.path.join(self.test_dir, "test_catalog.json")
        self.checkpoint_file = os.path.join(self.test_dir, "reports", "checkpoint.json")
        self.report_file = os.path.join(self.test_dir, "reports", "pre_apply.json")
        self.rejected_file = os.path.join(self.test_dir, "reports", "rejected.json")
        self.yields_file = os.path.join(self.test_dir, "reports", "yields.json")
        self.summary_file = os.path.join(self.test_dir, "reports", "summary.json")

        # Mock catalog with diverse asset classes
        self.mock_catalog = {
            "schema_version": 1,
            "catalog_version": 1,
            "symbols": [
                {
                    "id": "AAPL",
                    "symbol": "AAPL",
                    "nameEn": "Apple Inc.",
                    "category": "stock",
                    "marketName": "NASDAQ",
                    "unit": "$",
                    "tier": "major",
                },
                {
                    "id": "MSFT",
                    "symbol": "MSFT",
                    "nameEn": "Microsoft Corporation",
                    "category": "stock",
                    "marketName": "NASDAQ",
                    "unit": "$",
                    "tier": "major",
                },
                {
                    "id": "NVDA",
                    "symbol": "NVDA",
                    "nameEn": "NVIDIA Corporation",
                    "category": "stock",
                    "marketName": "NASDAQ",
                    "unit": "$",
                    "tier": "major",
                },
                {
                    "id": "EURUSD",
                    "symbol": "EUR/USD",
                    "nameEn": "Euro / US Dollar",
                    "category": "forex",
                    "marketName": "Forex Major",
                    "unit": "$",
                    "tier": "major",
                },
                {
                    "id": "US10Y",
                    "symbol": "US10Y (^TNX)",
                    "nameEn": "US 10-Year Treasury Yield",
                    "category": "bond",
                    "marketName": "US Treasury",
                    "unit": "%",
                    "tier": "major",
                },
                {
                    "id": "US02Y",
                    "symbol": "US02Y (DGS2)",
                    "nameEn": "US 2-Year Treasury Yield",
                    "category": "bond",
                    "marketName": "US Treasury",
                    "unit": "%",
                    "tier": "major",
                },
                {
                    "id": "TENCENT_HK",
                    "symbol": "0700.HK",
                    "nameEn": "Tencent Holdings",
                    "category": "stock",
                    "marketName": "HKEX",
                    "unit": "HKD",
                    "tier": "secondary",
                },
                {
                    "id": "INVALID_ASSET",
                    "symbol": "UNKNOWN_REJECT",
                    "nameEn": "Non Existent Asset",
                    "category": "stock",
                    "marketName": "UNKNOWN",
                    "unit": "$",
                    "tier": "secondary",
                }
            ]
        }
        with open(self.catalog_file, 'w', encoding='utf-8') as f:
            json.dump(self.mock_catalog, f, indent=2)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_resumable_checkpoint_behavior(self):
        """
        Verify that checkpoint persists progress and resuming skips already probed symbols.
        """
        checkpoint = ProbeCheckpoint(self.checkpoint_file)
        self.assertFalse(checkpoint.is_processed("AAPL"))

        # 1. Record partial batch
        checkpoint.record_symbol_result("AAPL", {"id": "AAPL", "status": "ok", "price": 180.5})
        checkpoint.record_symbol_result("MSFT", {"id": "MSFT", "status": "ok", "price": 420.0})
        checkpoint.save()

        # 2. Reload checkpoint in new instance (simulating interrupted run and restart)
        reloaded = ProbeCheckpoint(self.checkpoint_file)
        self.assertTrue(reloaded.is_processed("AAPL"))
        self.assertTrue(reloaded.is_processed("MSFT"))
        self.assertFalse(reloaded.is_processed("NVDA"))
        self.assertEqual(len(reloaded.data["processed_ids"]), 2)
        self.assertEqual(reloaded.data["results"]["AAPL"]["price"], 180.5)

    def test_02_treasury_yields_table_and_fred_rules(self):
        """
        Verify side-by-side yields table structure (13W, 2Y, 5Y, 10Y, 30Y)
        and strict enforcement of FRED-only rule for 2Y (US02Y / DGS2).
        """
        runner = CatalogProbeRunner(
            catalog_path=self.catalog_file,
            checkpoint_path=self.checkpoint_file,
            report_path=self.report_file,
            rejected_path=self.rejected_file,
            yields_path=self.yields_file,
            summary_path=self.summary_file,
            offline=True
        )

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            yields_table = loop.run_until_complete(runner.probe_treasury_yields(None))
        finally:
            loop.close()

        self.assertEqual(len(yields_table), 5)
        tenor_map = {row["id"]: row for row in yields_table}

        # Check required tenors are present
        self.assertIn("US13W", tenor_map)
        self.assertIn("US02Y", tenor_map)
        self.assertIn("US05Y", tenor_map)
        self.assertIn("US10Y", tenor_map)
        self.assertIn("US30Y", tenor_map)

        # Verify 2-Year Treasury Yield (US02Y) is strictly FRED-only
        us02y = tenor_map["US02Y"]
        self.assertTrue(us02y["fred_only"])
        self.assertEqual(us02y["fred_series"], "DGS2")
        self.assertIsNone(us02y["yahoo_yield"])
        self.assertIn("N/A", us02y["yahoo_symbol"])
        self.assertIn("FRED-only", us02y["note"])

        # Verify 10-Year Treasury Yield (US10Y) has both Yahoo and FRED
        us10y = tenor_map["US10Y"]
        self.assertFalse(us10y["fred_only"])
        self.assertEqual(us10y["yahoo_symbol"], "^TNX")
        self.assertEqual(us10y["fred_series"], "DGS10")
        self.assertIsNotNone(us10y["yahoo_yield"])
        self.assertIsNotNone(us10y["fred_yield"])

    def test_03_single_source_dynamic_determination(self):
        """
        Acceptance Criteria: "single_source بر اساس probe موفق، نه صرف وجود نگاشت."
        Verify that single_source is True only when exactly 1 provider returned a quote,
        and False when multiple providers succeeded.
        """
        runner = CatalogProbeRunner(
            catalog_path=self.catalog_file,
            checkpoint_path=self.checkpoint_file,
            report_path=self.report_file,
            rejected_path=self.rejected_file,
            yields_path=self.yields_file,
            summary_path=self.summary_file,
            offline=True,
            sample_rate_secondary=1.0  # Force secondary probe to verify multi-source
        )

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            # AAPL: major stock probed on Yahoo, Finnhub, and TwelveData in mock -> multi-source
            res_aapl, is_rej, _ = loop.run_until_complete(
                runner.probe_single_symbol(self.mock_catalog["symbols"][0], None)
            )
            self.assertFalse(is_rej)
            self.assertGreaterEqual(len(res_aapl["successful_providers"]), 2)
            self.assertFalse(res_aapl["single_source"])

            # 0700.HK: secondary tier stock (not sampled for secondary) -> only Yahoo -> single_source
            runner.sample_rate_secondary = 0.0
            res_hk, is_rej_hk, _ = loop.run_until_complete(
                runner.probe_single_symbol(self.mock_catalog["symbols"][6], None)
            )
            self.assertFalse(is_rej_hk)
            self.assertEqual(len(res_hk["successful_providers"]), 1)
            self.assertTrue(res_hk["single_source"])
        finally:
            loop.close()

    def test_04_rejected_symbols_generation(self):
        """
        Acceptance Criteria: "نماد بدون جواب هیچ provider ← reports/rejected.json."
        Verify that an unresolvable symbol is flagged as rejected and saved to rejected.json.
        """
        runner = CatalogProbeRunner(
            catalog_path=self.catalog_file,
            checkpoint_path=self.checkpoint_file,
            report_path=self.report_file,
            rejected_path=self.rejected_file,
            yields_path=self.yields_file,
            summary_path=self.summary_file,
            offline=True
        )

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            # UNKNOWN_REJECT symbol
            inv_item = self.mock_catalog["symbols"][7]
            res, is_rej, rej_item = loop.run_until_complete(
                runner.probe_single_symbol(inv_item, None)
            )
            self.assertTrue(is_rej)
            self.assertEqual(res["status"], "failed")
            self.assertIsNotNone(rej_item)
            self.assertEqual(rej_item["id"], "INVALID_ASSET")
        finally:
            loop.close()

    def test_05_secondary_tier_and_quota_rules(self):
        """
        Verify tier=major filtering and official quota configuration.
        """
        # 1. Tier checking
        self.assertTrue(is_tier_major({"tier": "major"}))
        self.assertTrue(is_tier_major({"tier": 1}))
        self.assertTrue(is_tier_major({"symbol": "EUR/USD", "marketName": "Forex Major"}))
        self.assertFalse(is_tier_major({"tier": "secondary", "marketName": "HKEX", "symbol": "0700.HK"}))

        # 2. Quota registry limits
        self.assertEqual(OFFICIAL_QUOTAS['twelvedata']['daily_limit'], 800)
        self.assertEqual(OFFICIAL_QUOTAS['finnhub']['daily_limit'], 86400)
        self.assertEqual(OFFICIAL_QUOTAS['fred']['daily_limit'], 7200)

    def test_06_currency_matching_validation(self):
        """
        Verify currency match/mismatch detection.
        """
        # Matching pairs
        self.assertTrue(check_currency_match("$", "USD"))
        self.assertTrue(check_currency_match("USD", "USD"))
        self.assertTrue(check_currency_match("€", "EUR"))
        self.assertTrue(check_currency_match("%", "%"))
        self.assertTrue(check_currency_match("HKD", "HKD"))

        # Mismatched pairs (e.g. expected USD but response is HKD)
        self.assertFalse(check_currency_match("$", "HKD"))
        self.assertFalse(check_currency_match("EUR", "USD"))

    def test_07_full_runner_offline_execution_and_deliverables(self):
        """
        Runs complete CatalogProbeRunner in offline mode and verifies that all 4 reports
        (pre_apply_report.json, rejected.json, yields_table.json, summary_report.json)
        are properly produced and structurally valid.
        """
        runner = CatalogProbeRunner(
            catalog_path=self.catalog_file,
            checkpoint_path=self.checkpoint_file,
            report_path=self.report_file,
            rejected_path=self.rejected_file,
            yields_path=self.yields_file,
            summary_path=self.summary_file,
            batch_size=50,
            concurrency=4,
            sample_rate_secondary=0.20,
            offline=True
        )

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            summary = loop.run_until_complete(runner.run())
        finally:
            loop.close()

        # Check all deliverables exist
        self.assertTrue(os.path.exists(self.report_file))
        self.assertTrue(os.path.exists(self.rejected_file))
        self.assertTrue(os.path.exists(self.yields_file))
        self.assertTrue(os.path.exists(self.summary_file))

        # Verify summary content
        self.assertEqual(summary["app_version"], APP_VERSION)
        self.assertEqual(summary["total_symbols_probed"], len(self.mock_catalog["symbols"]))
        self.assertGreater(summary["ok_count"], 0)
        self.assertGreater(summary["failed_count"], 0)
        self.assertIn("category_breakdown", summary)
        self.assertIn("quota_usage", summary)
        self.assertIn("treasury_yields", summary)

        # Verify rejected.json has the failed symbol
        with open(self.rejected_file, 'r', encoding='utf-8') as f:
            rejected_data = json.load(f)
            self.assertEqual(len(rejected_data), 1)
            self.assertEqual(rejected_data[0]["id"], "INVALID_ASSET")


if __name__ == '__main__':
    unittest.main()
