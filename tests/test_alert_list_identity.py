#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for ALERTS_DB list identity consistency across all modules:
- Ensures sync_user_alerts, clear_all_alerts, and delete_alert use in-place slice mutation.
- Verifies checker, sync, admin, and user modules share the identical list reference.
- End-to-end alert creation and deletion checks.
- Static regex guard to prevent re-introducing storage.ALERTS_DB = assignments.
"""

import os
import re
import unittest
import asyncio
from unittest.mock import AsyncMock, patch

import app.storage as storage
from app.models import Alert
from app.routes.alerts import sync_user_alerts, clear_all_alerts, delete_alert
from app.engine import checker, sync
from app.routes import admin, user
from app.engine.checker import check_alerts_job


class TestAlertListIdentity(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self._orig_alerts = list(storage.ALERTS_DB)
        self._orig_profiles = dict(storage.USER_PROFILES_DB)
        storage.ALERTS_DB.clear()
        self._disk_patch = patch("app.storage.save_alerts_to_disk_async", new_callable=AsyncMock)
        self._disk_patch.start()

    def tearDown(self):
        try:
            self._disk_patch.stop()
        except Exception:
            pass
        storage.ALERTS_DB.clear()
        storage.ALERTS_DB.extend(self._orig_alerts)
        storage.USER_PROFILES_DB.clear()
        storage.USER_PROFILES_DB.update(self._orig_profiles)

    async def test_a_list_identity_preserved_across_operations(self):
        """a) after sync_user_alerts, clear_all_alerts and delete_alert: checker.ALERTS_DB is storage.ALERTS_DB, and the same for sync, admin, user."""
        def assert_all_identical():
            self.assertIs(checker.ALERTS_DB, storage.ALERTS_DB, "checker.ALERTS_DB is not storage.ALERTS_DB")
            self.assertIs(sync.ALERTS_DB, storage.ALERTS_DB, "sync.ALERTS_DB is not storage.ALERTS_DB")
            self.assertIs(admin.ALERTS_DB, storage.ALERTS_DB, "admin.ALERTS_DB is not storage.ALERTS_DB")
            self.assertIs(user.ALERTS_DB, storage.ALERTS_DB, "user.ALERTS_DB is not storage.ALERTS_DB")

        # Initial check
        assert_all_identical()

        # 1. After sync_user_alerts
        payload = {
            "user_id": "test_user_identity",
            "fcm_token": "valid_token_identity_123456789012345678901234567890",
            "alerts": [{
                "id": "alert_ident_1",
                "user_id": "test_user_identity",
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "target_price": 50000.0,
                "condition": "ABOVE",
                "condition_type": "priceThreshold",
                "is_active": True,
                "fcm_token": "valid_token_identity_123456789012345678901234567890"
            }]
        }
        await sync_user_alerts(payload)
        assert_all_identical()
        self.assertEqual(len(checker.ALERTS_DB), 1)

        # 2. After delete_alert
        await delete_alert("alert_ident_1")
        assert_all_identical()
        self.assertEqual(len(checker.ALERTS_DB), 0)

        # 3. Add via sync again and clear_all_alerts
        await sync_user_alerts(payload)
        self.assertEqual(len(checker.ALERTS_DB), 1)
        await clear_all_alerts(user_id="test_user_identity")
        assert_all_identical()
        self.assertEqual(len(checker.ALERTS_DB), 0)

    async def test_b_end_to_end_sync_eval_triggers_once(self):
        """b) end-to-end: create ABOVE-100 alert ONLY via sync_user_alerts; run check_alerts_job at 99 then 101 -> enqueue_alert_push called exactly once."""
        rule_id = "alert_e2e_above_100"
        user_id = "user_e2e_test"
        token = "valid_fcm_token_e2e_123456789012345678901234567890"

        payload = {
            "user_id": user_id,
            "fcm_token": token,
            "alerts": [{
                "id": rule_id,
                "user_id": user_id,
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "target_price": 100.0,
                "condition": "ABOVE",
                "condition_type": "priceThreshold",
                "is_active": True,
                "check_interval_seconds": 0,
                "fcm_token": token
            }]
        }
        await sync_user_alerts(payload)

        # Verify alert exists in checker.ALERTS_DB
        synced_alert = next((a for a in checker.ALERTS_DB if a.id == rule_id), None)
        self.assertIsNotNone(synced_alert)

        # 1. Evaluate at 99 -> does not trigger
        with patch("app.engine.checker.get_cached_price", new_callable=AsyncMock) as mock_price, \
             patch("app.engine.checker.enqueue_alert_push", new_callable=AsyncMock) as mock_push:
            mock_price.return_value = 99.0
            await check_alerts_job()

            self.assertEqual(synced_alert.last_eval_price, 99.0)
            self.assertFalse(synced_alert.waiting_for_cross)
            self.assertEqual(mock_push.call_count, 0)

            # 2. Evaluate at 101 -> crosses target and triggers push once
            mock_price.return_value = 101.0
            synced_alert.last_checked_at = 0.0
            await check_alerts_job()

            self.assertEqual(mock_push.call_count, 1)
            self.assertEqual(synced_alert.last_eval_price, 101.0)

    async def test_c_deleted_alert_does_not_push_on_price_cross(self):
        """c) delete an alert via delete_alert, then cross the price -> NO push."""
        rule_id = "alert_del_test_cross"
        user_id = "user_del_cross"
        token = "valid_fcm_token_del_123456789012345678901234567890"

        payload = {
            "user_id": user_id,
            "fcm_token": token,
            "alerts": [{
                "id": rule_id,
                "user_id": user_id,
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "target_price": 100.0,
                "condition": "ABOVE",
                "condition_type": "priceThreshold",
                "is_active": True,
                "check_interval_seconds": 0,
                "fcm_token": token
            }]
        }
        await sync_user_alerts(payload)
        self.assertEqual(len(checker.ALERTS_DB), 1)

        # Delete alert
        await delete_alert(rule_id)
        self.assertEqual(len(checker.ALERTS_DB), 0)

        # Now cross price
        with patch("app.engine.checker.get_cached_price", new_callable=AsyncMock) as mock_price, \
             patch("app.engine.checker.enqueue_alert_push", new_callable=AsyncMock) as mock_push:
            mock_price.return_value = 105.0
            await check_alerts_job()

            self.assertEqual(mock_push.call_count, 0, "Deleted alert must not trigger push")

    def test_d_static_guard_no_storage_alerts_db_assignment(self):
        """d) static guard: scan app/*.py with regex storage\\.ALERTS_DB\\s*=(?!=) -> zero matches."""
        pattern = re.compile(r"storage\.ALERTS_DB\s*=(?!=)")
        matches = []
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
        for root, _, files in os.walk(base_dir):
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    with open(full_path, "r", encoding="utf-8") as f:
                        for line_num, line in enumerate(f, 1):
                            if pattern.search(line):
                                matches.append((full_path, line_num, line.strip()))

        self.assertEqual(
            len(matches),
            0,
            f"Found forbidden storage.ALERTS_DB = assignment: {matches}"
        )


if __name__ == "__main__":
    unittest.main()
