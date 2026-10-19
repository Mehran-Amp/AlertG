#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for FCM Outbox permanent failure handling and expiration pruning.
- UNREGISTERED and INVALID_ARGUMENT are permanent errors: entry dropped immediately and token marked invalid.
- Expired entries are discarded upon loading from disk.
"""

import sys
import unittest
import time
import os
import json
from unittest.mock import AsyncMock, patch, MagicMock

for mod in [
    'fastapi', 'fastapi.middleware.cors', 'fastapi.responses', 'pydantic', 'httpx',
    'apscheduler', 'apscheduler.schedulers', 'apscheduler.schedulers.asyncio',
    'firebase_admin', 'firebase_admin.credentials', 'firebase_admin.messaging', 'firebase_admin.exceptions'
]:
    if mod not in sys.modules:
        m = MagicMock()
        if mod == 'pydantic':
            class BaseModel:
                def __init__(self, **kwargs):
                    for k, v in kwargs.items():
                        setattr(self, k, v)
                def dict(self): return self.__dict__
                def model_dump(self): return self.__dict__
            m.BaseModel = BaseModel
            m.Field = lambda *args, **kwargs: kwargs.get('default', None)
        sys.modules[mod] = m

import app.storage as storage
from app.models import Alert
from app.notifier import outbox


class TestOutboxFCM(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        outbox.OUTBOX.clear()
        outbox.INVALID_TOKENS.clear()
        self._orig_alerts = list(storage.ALERTS_DB)
        storage.ALERTS_DB.clear()

    def tearDown(self):
        outbox.OUTBOX.clear()
        outbox.INVALID_TOKENS.clear()
        storage.ALERTS_DB.clear()
        storage.ALERTS_DB.extend(self._orig_alerts)

    async def test_unregistered_error_drops_entry_and_invalidates_token(self):
        """FCM returning UNREGISTERED drops the outbox entry immediately and invalidates token."""
        test_token = "valid_fcm_token_1234567890123456789012345678901234567890"
        alert = Alert(
            id="alert_test_1",
            user_id="user_1",
            exchange="binance",
            symbol="BTCUSDT",
            target_price=65000.0,
            fcm_token=test_token
        )
        storage.ALERTS_DB.append(alert)

        eid = "eid_unregistered_test"
        outbox.OUTBOX[eid] = {
            "id": eid,
            "alert_id": alert.id,
            "token": test_token,
            "title": "Alert Triggered",
            "body": "BTC reached target",
            "data": {},
            "created_at": time.time(),
            "expires_at": time.time() + 3600,
            "next_attempt_at": time.time(),
            "attempts": 0,
            "last_error": "",
        }

        with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_send, \
             patch("app.notifier.outbox._save_outbox", new_callable=AsyncMock):
            mock_send.return_value = (False, "UNREGISTERED")

            await outbox._deliver_outbox_entry(eid)

            # Entry must be immediately removed from OUTBOX
            self.assertNotIn(eid, outbox.OUTBOX)
            # Token must be added to INVALID_TOKENS
            self.assertIn(test_token, outbox.INVALID_TOKENS)
            # Alert token in ALERTS_DB must be wiped
            self.assertEqual(alert.fcm_token, "")

    async def test_invalid_argument_error_drops_entry_and_invalidates_token(self):
        """FCM returning INVALID_ARGUMENT drops the outbox entry immediately and marks token invalid."""
        test_token = "invalid_arg_token_1234567890123456789012345678901234567890"
        alert = Alert(
            id="alert_test_2",
            user_id="user_2",
            exchange="nobitex",
            symbol="USDTIRT",
            target_price=70000.0,
            fcm_token=test_token
        )
        storage.ALERTS_DB.append(alert)

        eid = "eid_invalid_arg_test"
        outbox.OUTBOX[eid] = {
            "id": eid,
            "alert_id": alert.id,
            "token": test_token,
            "title": "Alert Triggered",
            "body": "USDT reached target",
            "data": {},
            "created_at": time.time(),
            "expires_at": time.time() + 3600,
            "next_attempt_at": time.time(),
            "attempts": 0,
            "last_error": "",
        }

        with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_send, \
             patch("app.notifier.outbox._save_outbox", new_callable=AsyncMock):
            mock_send.return_value = (False, "INVALID_ARGUMENT: The registration token is not a valid FCM registration token")

            await outbox._deliver_outbox_entry(eid)

            self.assertNotIn(eid, outbox.OUTBOX)
            self.assertIn(test_token, outbox.INVALID_TOKENS)
            self.assertEqual(alert.fcm_token, "")

    def test_load_outbox_discards_expired_entries(self):
        """Entries past their expires_at are discarded on load."""
        now = time.time()
        sample_data = {
            "entry_expired": {
                "id": "entry_expired",
                "expires_at": now - 100,  # in the past
                "title": "Old Alert"
            },
            "entry_valid": {
                "id": "entry_valid",
                "expires_at": now + 500,  # in the future
                "title": "Fresh Alert"
            }
        }
        test_file = "/tmp/test_fcm_outbox_load.json"
        with open(test_file, "w", encoding="utf-8") as f:
            json.dump(sample_data, f)

        try:
            with patch("app.notifier.outbox.OUTBOX_FILE", test_file):
                loaded = outbox._load_outbox_from_disk()
                self.assertNotIn("entry_expired", loaded, "Expired entry must be discarded")
                self.assertIn("entry_valid", loaded, "Valid future entry must be retained")
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)


if __name__ == "__main__":
    unittest.main()
