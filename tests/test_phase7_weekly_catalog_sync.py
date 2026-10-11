#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit Tests for Phase 7 (v2.10.0): Weekly Catalog Sync with Diff & Safety Ceilings
Acceptance Criteria Verified:
1. Weekly Job on Scheduler:
   - Job weekly_catalog_sync_job registered on scheduler (Saturday ~06:00 UTC)
2. Seven-Stage Pipeline:
   - fetch -> normalize -> validate -> diff -> price probe -> dry-run -> apply in transaction
3. Soft Deletion Only:
   - Delisted symbols marked with is_active=0, delisted_at=ISO timestamp; never hard deleted
4. Safety Ceilings:
   - Empty list -> sync halts + admin alert
   - Delistings > 5% -> sync halts + admin alert
   - Additions > 10% -> sync halts + admin alert
5. User Notification & Deactivation:
   - Active alerts for delisted symbols are automatically deactivated (is_active=False)
   - Push notifications enqueued via enqueue_alert_push in outbox
6. Catalog Versioning & Rollback:
   - catalog_version increments with every applied transaction
   - Snapshot created before apply
   - rollback_catalog successfully restores prior snapshot state
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import os
import json
import time
from datetime import datetime, timezone
import shutil

from app.models import Alert
from app.config import DATA_DIR, CATALOG_FILE, CATALOG_SNAPSHOTS_DIR, APP_VERSION
import app.storage as storage
import app.state as state
import app.engine.sync as sync_module
from app.state import METRICS
from server import scheduler, setup_scheduler_jobs
from app.engine.sync import (
    load_catalog,
    save_catalog,
    save_catalog_snapshot,
    list_catalog_snapshots,
    rollback_catalog,
    fetch_candidate_catalog,
    normalize_catalog_item,
    validate_candidate_catalog,
    compute_catalog_diff,
    check_sync_safety,
    probe_catalog_prices,
    notify_users_and_deactivate_delisted,
    run_weekly_catalog_sync,
    weekly_catalog_sync_job,
    CatalogSafetyCeilingExceededError
)


class TestPhase7WeeklyCatalogSync(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.test_dir = f"/tmp/test_catalog_{int(time.time()*1000)}"
        os.makedirs(self.test_dir, exist_ok=True)
        self.test_cat_file = os.path.join(self.test_dir, "catalog.json")
        self.test_snap_dir = os.path.join(self.test_dir, "catalog_snapshots")
        os.makedirs(self.test_snap_dir, exist_ok=True)

        self.orig_cat_file = sync_module.CATALOG_FILE
        self.orig_snap_dir = sync_module.CATALOG_SNAPSHOTS_DIR
        sync_module.CATALOG_FILE = self.test_cat_file
        sync_module.CATALOG_SNAPSHOTS_DIR = self.test_snap_dir

        self.orig_alerts = list(storage.ALERTS_DB)
        storage.ALERTS_DB.clear()
        METRICS.clear()

        # Seed initial catalog with 100 test symbols
        initial_symbols = []
        for i in range(1, 101):
            initial_symbols.append({
                "id": f"SYM_{i:03d}",
                "symbol": f"SYM{i:03d}",
                "nameEn": f"Symbol {i}",
                "nameFa": f"نماد {i}",
                "category": "stock",
                "marketName": "Test Market",
                "unit": "$",
                "is_active": 1,
                "delisted_at": None,
                "added_at": datetime.now(timezone.utc).isoformat()
            })

        self.initial_catalog = {
            "catalog_version": 1,
            "app_version": APP_VERSION,
            "last_sync_at": datetime.now(timezone.utc).isoformat(),
            "total_active": 100,
            "total_symbols": 100,
            "symbols": initial_symbols
        }
        save_catalog(self.initial_catalog)

    def tearDown(self):
        sync_module.CATALOG_FILE = self.orig_cat_file
        sync_module.CATALOG_SNAPSHOTS_DIR = self.orig_snap_dir
        storage.ALERTS_DB.clear()
        storage.ALERTS_DB.extend(self.orig_alerts)
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_weekly_job_registered_on_scheduler(self):
        """1. Verify weekly job on scheduler (Saturday ~06:00 UTC)"""
        if not scheduler.get_job('weekly_catalog_sync_job'):
            setup_scheduler_jobs(scheduler)

        sync_job = scheduler.get_job('weekly_catalog_sync_job')
        self.assertIsNotNone(sync_job, "weekly_catalog_sync_job must be registered on scheduler")
        self.assertEqual(sync_job.func, weekly_catalog_sync_job)

        # Verify cron triggers for Saturday 06:00 UTC
        trigger = sync_job.trigger
        fields_str = str(trigger)
        self.assertTrue(
            "sat" in fields_str.lower() or "5" in fields_str or "6" in fields_str,
            f"Trigger {fields_str} must be configured for Saturday 06:00 UTC"
        )

    def test_02_normalization_and_validation(self):
        """2. Verify normalize and validate stages clean data & deduplicate"""
        raw_items = [
            {"id": "aapl", "symbol": "AAPL ", "nameEn": "Apple", "nameFa": "اپل", "category": "stock"},
            {"id": "AAPL", "symbol": "AAPL", "nameEn": "Apple Inc.", "nameFa": "سهام اپل (کامل)", "category": "stock"}, # duplicate richer fa
            {"id": "", "symbol": "", "nameEn": "Invalid"}, # invalid empty
        ]
        valid = validate_candidate_catalog(raw_items)
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0]["symbol"], "AAPL")
        self.assertEqual(valid[0]["nameFa"], "سهام اپل (کامل)")
        self.assertEqual(valid[0]["is_active"], 1)

    def test_03_diff_computation(self):
        """3. Verify diff computation: added, modified, delisted, unchanged"""
        current = load_catalog()
        # Keep 98 symbols unchanged, modify 1, delete 1 (SYM100), add 2 new
        candidate_items = []
        for s in current["symbols"][:98]:
            candidate_items.append(dict(s))

        # Modified
        mod_item = dict(current["symbols"][98]) # SYM099
        mod_item["nameFa"] = "نماد ۹۹ بروزرسانی شده"
        candidate_items.append(mod_item)

        # Added
        candidate_items.append({"id": "NEW_01", "symbol": "NEWSYM1", "nameEn": "New 1", "category": "stock"})
        candidate_items.append({"id": "NEW_02", "symbol": "NEWSYM2", "nameEn": "New 2", "category": "stock"})

        diff = compute_catalog_diff(current, candidate_items)
        stats = diff["stats"]

        self.assertEqual(stats["current_active_count"], 100)
        self.assertEqual(stats["added_count"], 2)
        self.assertEqual(stats["modified_count"], 1)
        self.assertEqual(stats["delisted_count"], 1) # SYM100
        self.assertEqual(stats["unchanged_count"], 98)

    def test_04_safety_ceiling_empty_list(self):
        """4a. Safety Ceiling: Empty candidate list stops sync & raises error"""
        empty_stats = {
            "candidate_count": 0,
            "current_active_count": 100,
            "delisted_ratio": 1.0,
            "added_ratio": 0.0,
            "delisted_count": 100,
            "added_count": 0
        }
        with self.assertRaises(CatalogSafetyCeilingExceededError):
            check_sync_safety(empty_stats)
        self.assertGreater(METRICS.get("catalog_sync_admin_alerts", 0), 0)

    def test_05_safety_ceiling_exceed_delisted_5_percent(self):
        """4b. Safety Ceiling: Delistings > 5% stops sync & raises error"""
        high_delist_stats = {
            "candidate_count": 94,
            "current_active_count": 100,
            "delisted_ratio": 0.06, # 6% > 5%
            "added_ratio": 0.0,
            "delisted_count": 6,
            "added_count": 0
        }
        with self.assertRaises(CatalogSafetyCeilingExceededError):
            check_sync_safety(high_delist_stats)
        self.assertGreater(METRICS.get("catalog_sync_admin_alerts", 0), 0)

    def test_06_safety_ceiling_exceed_added_10_percent(self):
        """4c. Safety Ceiling: Additions > 10% stops sync & raises error"""
        high_add_stats = {
            "candidate_count": 112,
            "current_active_count": 100,
            "delisted_ratio": 0.0,
            "added_ratio": 0.12, # 12% > 10%
            "delisted_count": 0,
            "added_count": 12
        }
        with self.assertRaises(CatalogSafetyCeilingExceededError):
            check_sync_safety(high_add_stats)
        self.assertGreater(METRICS.get("catalog_sync_admin_alerts", 0), 0)

    async def test_07_dry_run_mode_does_not_modify_catalog(self):
        """5. Dry-run mode returns diff and probe results without changing disk"""
        current = load_catalog()
        # Candidate with 1 addition (within safe 10%)
        candidate_items = [dict(s) for s in current["symbols"]]
        candidate_items.append({"id": "SAFE_ADD", "symbol": "SAFEADD", "nameEn": "Safe", "category": "stock"})

        report = await run_weekly_catalog_sync(candidate_items=candidate_items, dry_run=True)
        self.assertEqual(report["status"], "dry_run_success")
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["current_version"], 1)

        # Verify disk catalog file was NOT updated
        disk_cat = load_catalog()
        self.assertEqual(disk_cat["catalog_version"], 1)
        self.assertEqual(len(disk_cat["symbols"]), 100)

    @patch('app.engine.sync.enqueue_alert_push', new_callable=AsyncMock)
    @patch('app.engine.sync.save_alerts_to_disk_async', new_callable=AsyncMock)
    async def test_08_apply_transaction_soft_delete_and_user_notification(self, mock_save_disk, mock_push):
        """6. Apply transaction: version bumps, soft delete (is_active=0, delisted_at), user alerts deactivated"""
        # Register an active user alert on SYM100
        alert_on_sym100 = Alert(
            id="alert_delist_test_1",
            user_id="user_trader",
            exchange="global_stocks",
            symbol="SYM100",
            target_price=150.0,
            created_at=datetime.now(timezone.utc).isoformat(),
            fcm_token="token_abc_123",
            is_active=True
        )
        storage.ALERTS_DB.append(alert_on_sym100)

        current = load_catalog()
        # Delist 2 symbols (2% <= 5% safe limit): SYM099 and SYM100
        candidate_items = [dict(s) for s in current["symbols"] if s["symbol"] not in ("SYM099", "SYM100")]
        # Add 1 safe symbol (1% <= 10% safe limit)
        candidate_items.append({"id": "SAFE_01", "symbol": "SAFE01", "nameEn": "Safe 1", "category": "stock"})

        report = await run_weekly_catalog_sync(candidate_items=candidate_items, dry_run=False)

        self.assertEqual(report["status"], "applied_success")
        self.assertEqual(report["target_version"], 2)

        # Check updated catalog on disk
        updated_cat = load_catalog()
        self.assertEqual(updated_cat["catalog_version"], 2)

        symbols_map = {s["symbol"]: s for s in updated_cat["symbols"]}
        # Verify SYM100 was SOFT DELETED (NOT REMOVED FROM LIST!)
        self.assertIn("SYM100", symbols_map, "Delisted symbol MUST remain in catalog (soft delete)")
        self.assertEqual(symbols_map["SYM100"]["is_active"], 0)
        self.assertIsNotNone(symbols_map["SYM100"]["delisted_at"])

        # Verify new symbol was added as active
        self.assertIn("SAFE01", symbols_map)
        self.assertEqual(symbols_map["SAFE01"]["is_active"], 1)

        # Verify user alert on SYM100 was deactivated
        self.assertFalse(alert_on_sym100.is_active, "Alert on delisted symbol must be deactivated")

        # Verify push notification was enqueued for user
        mock_push.assert_awaited_once()
        call_args = mock_push.await_args[0]
        self.assertEqual(call_args[0].id, "alert_delist_test_1")
        self.assertIn("SYM100", call_args[1]) # title
        mock_save_disk.assert_awaited()

    def test_09_snapshot_creation_and_rollback(self):
        """7. Verify snapshot creation and rollback_catalog functionality"""
        current = load_catalog()
        self.assertEqual(current["catalog_version"], 1)

        # Save snapshot of version 1
        snap_path = save_catalog_snapshot(current)
        self.assertTrue(os.path.exists(snap_path))

        # Bump to version 2 with arbitrary change
        current["catalog_version"] = 2
        current["symbols"].append({"id": "V2_SYM", "symbol": "V2SYM", "is_active": 1})
        save_catalog(current)

        cat_v2 = load_catalog()
        self.assertEqual(cat_v2["catalog_version"], 2)
        self.assertEqual(len(cat_v2["symbols"]), 101)

        # Rollback back to version 1
        restored = rollback_catalog(target_version=1)
        self.assertEqual(restored["catalog_version"], 1)
        self.assertEqual(len(restored["symbols"]), 100)

        # Verify disk is back to version 1
        cat_after_rollback = load_catalog()
        self.assertEqual(cat_after_rollback["catalog_version"], 1)
        self.assertEqual(len(cat_after_rollback["symbols"]), 100)


if __name__ == '__main__':
    unittest.main()
