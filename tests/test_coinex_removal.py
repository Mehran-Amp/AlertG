# -*- coding: utf-8 -*-
"""
AlertG — Phase 12 / Part E Phase 11 Acceptance & Contract Tests:
CoinEx Data Migration, Backup, Pruning, and Restoration.
"""
import os
import sys
import json
import shutil
import tempfile
import unittest

from unittest.mock import MagicMock

try:
    import httpx
except ImportError:
    httpx = MagicMock()
    sys.modules['httpx'] = httpx

try:
    import apscheduler
except ImportError:
    apscheduler = MagicMock()
    sys.modules['apscheduler'] = apscheduler
    sys.modules['apscheduler.schedulers'] = apscheduler
    sys.modules['apscheduler.schedulers.asyncio'] = apscheduler

from scripts.remove_coinex_alerts import run_coinex_removal, is_coinex_alert
from app.markets.crypto_validation import validate_crypto_alert


class TestCoinExRemoval(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_coinex_migration_")
        self.db_file = os.path.join(self.test_dir, "test_alerts.json")
        self.backup_dir = os.path.join(self.test_dir, "test_backups")

        # Seed sample alerts (2 Binance, 3 CoinEx, 1 Tabdeal, 1 Yahoo)
        self.sample_alerts = [
            {
                "id": "alert_binance_1",
                "user_id": "user_alpha",
                "symbol": "BTCUSDT",
                "exchange": "binance",
                "target_price": 68000.0,
                "condition": "ABOVE",
                "is_active": True
            },
            {
                "id": "alert_coinex_1",
                "user_id": "user_beta",
                "symbol": "ETHUSDT",
                "exchange": "coinex",
                "target_price": 2500.0,
                "condition": "BELOW",
                "is_active": True
            },
            {
                "id": "alert_coinex_2",
                "user_id": "user_beta",
                "symbol": "CETUSDT",
                "exchange": "CoinEx",  # Mixed case
                "target_price": 0.05,
                "condition": "ABOVE",
                "is_active": False
            },
            {
                "id": "alert_coinex_3",
                "user_id": "user_gamma",
                "symbol": "SOLUSDT",
                "exchange_id": "coinex",  # Using exchange_id key
                "target_price": 180.0,
                "condition": "ABOVE",
                "is_active": True
            },
            {
                "id": "alert_tabdeal_1",
                "user_id": "user_alpha",
                "symbol": "USDTIRT",
                "exchange": "tabdeal",
                "target_price": 27000.0,
                "condition": "ABOVE",
                "is_active": True
            },
            {
                "id": "alert_yahoo_1",
                "user_id": "user_delta",
                "symbol": "^GSPC",
                "exchange": "stocks",
                "target_price": 5800.0,
                "condition": "ABOVE",
                "is_active": True
            }
        ]

        with open(self.db_file, "w", encoding="utf-8") as f:
            json.dump(self.sample_alerts, f, indent=2)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_is_coinex_alert_matcher(self):
        """1. Verify accurate case-insensitive matching of CoinEx alerts."""
        self.assertTrue(is_coinex_alert({"exchange": "coinex"}))
        self.assertTrue(is_coinex_alert({"exchange": "CoinEx"}))
        self.assertTrue(is_coinex_alert({"exchange": "COINEX"}))
        self.assertTrue(is_coinex_alert({"exchange_id": "coinex"}))

        # Other exchanges must never match
        self.assertFalse(is_coinex_alert({"exchange": "binance"}))
        self.assertFalse(is_coinex_alert({"exchange": "tabdeal"}))
        self.assertFalse(is_coinex_alert({"exchange": "okx"}))
        self.assertFalse(is_coinex_alert({}))

    def test_02_dry_run_audit_does_not_modify_database(self):
        """2. Verify dry-run accurately reports CoinEx counts without touching database."""
        mtime_before = os.path.getmtime(self.db_file)
        with open(self.db_file, "rb") as f:
            content_before = f.read()

        report = run_coinex_removal(
            db_file=self.db_file,
            backup_dir=self.backup_dir,
            apply=False
        )

        # Content must be completely unmodified
        with open(self.db_file, "rb") as f:
            content_after = f.read()
        self.assertEqual(content_before, content_after)
        self.assertEqual(os.path.getmtime(self.db_file), mtime_before)

        # Assert report accuracy
        self.assertEqual(report["status"], "DRY_RUN")
        self.assertEqual(report["total_alerts_before"], 6)
        self.assertEqual(report["coinex_alerts_found"], 3)
        self.assertEqual(report["total_alerts_after"], 6)
        self.assertEqual(report["affected_users_count"], 2)
        self.assertEqual(report["affected_users"], ["user_beta", "user_gamma"])
        self.assertEqual(report["symbol_breakdown"], {"ETHUSDT": 1, "CETUSDT": 1, "SOLUSDT": 1})
        self.assertIsNone(report["backup_file"])
        self.assertFalse(os.path.exists(self.backup_dir))

    def test_03_apply_mode_creates_backup_and_removes_coinex(self):
        """3. Verify --apply creates full JSON snapshot and removes only CoinEx alerts."""
        report = run_coinex_removal(
            db_file=self.db_file,
            backup_dir=self.backup_dir,
            apply=True
        )

        self.assertEqual(report["status"], "APPLIED")
        self.assertEqual(report["total_alerts_before"], 6)
        self.assertEqual(report["coinex_alerts_found"], 3)
        self.assertEqual(report["total_alerts_after"], 3)

        # Verify backup file exists and holds 100% of original alerts
        backup_file = report["backup_file"]
        self.assertIsNotNone(backup_file)
        self.assertTrue(os.path.exists(backup_file))

        with open(backup_file, "r", encoding="utf-8") as bf:
            backup_content = json.load(bf)
        self.assertEqual(len(backup_content), 6)
        self.assertEqual(backup_content, self.sample_alerts)

        # Verify pruned database contains only non-CoinEx alerts
        with open(self.db_file, "r", encoding="utf-8") as df:
            pruned_alerts = json.load(df)

        self.assertEqual(len(pruned_alerts), 3)
        remaining_ids = [a["id"] for a in pruned_alerts]
        self.assertIn("alert_binance_1", remaining_ids)
        self.assertIn("alert_tabdeal_1", remaining_ids)
        self.assertIn("alert_yahoo_1", remaining_ids)
        self.assertNotIn("alert_coinex_1", remaining_ids)
        self.assertNotIn("alert_coinex_2", remaining_ids)
        self.assertNotIn("alert_coinex_3", remaining_ids)

    def test_04_restore_mode_reverts_database_to_exact_original(self):
        """4. Verify --restore accurately recovers pruned alerts from backup snapshot."""
        # 1. Apply removal first
        apply_report = run_coinex_removal(
            db_file=self.db_file,
            backup_dir=self.backup_dir,
            apply=True
        )
        backup_file = apply_report["backup_file"]

        # Ensure DB has 3 alerts now
        with open(self.db_file, "r", encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)), 3)

        # 2. Restore from backup
        restore_res = run_coinex_removal(
            db_file=self.db_file,
            restore_file=backup_file
        )

        self.assertEqual(restore_res["status"], "RESTORED")
        self.assertEqual(restore_res["total_alerts"], 6)

        # 3. Assert DB is restored byte-identical to original
        with open(self.db_file, "r", encoding="utf-8") as f:
            restored_alerts = json.load(f)
        self.assertEqual(restored_alerts, self.sample_alerts)

    def test_05_database_with_zero_coinex_alerts(self):
        """5. Verify graceful execution when database contains no CoinEx alerts."""
        clean_alerts = [a for a in self.sample_alerts if not is_coinex_alert(a)]
        with open(self.db_file, "w", encoding="utf-8") as f:
            json.dump(clean_alerts, f)

        report = run_coinex_removal(db_file=self.db_file, backup_dir=self.backup_dir, apply=True)
        self.assertEqual(report["coinex_alerts_found"], 0)
        self.assertEqual(report["total_alerts_before"], 3)
        self.assertEqual(report["total_alerts_after"], 3)

    def test_06_crypto_validation_strictly_rejects_coinex(self):
        """6. Rule R1 & E1.2: Server validation immediately rejects new CoinEx alerts."""
        is_val, code, msg = validate_crypto_alert("coinex", "BTCUSDT")
        self.assertFalse(is_val)
        self.assertEqual(code, "EXCHANGE_NOT_SUPPORTED")
        self.assertIn("discontinued", msg.lower())

        # Also uppercase
        is_val_upper, code_upper, _ = validate_crypto_alert("COINEX", "BTCUSDT")
        self.assertFalse(is_val_upper)
        self.assertEqual(code_upper, "EXCHANGE_NOT_SUPPORTED")


if __name__ == "__main__":
    unittest.main()
