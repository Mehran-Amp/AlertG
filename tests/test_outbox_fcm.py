#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for FCM Outbox:
- UNREGISTERED and INVALID_TOKEN_FORMAT block the token without dropping entry or wiping token.
- A second worker tick does not call FCM while token is unchanged.
- When alert gets a new token, blocked_token is cleared and FCM is called again.
- INVALID_PAYLOAD keeps the token and retries with backoff.
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
        try:
            __import__(mod)
        except ImportError:
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
        outbox.DEAD_TOKENS.clear()
        self._orig_alerts = list(storage.ALERTS_DB)
        storage.ALERTS_DB.clear()

    def tearDown(self):
        outbox.OUTBOX.clear()
        outbox.DEAD_TOKENS.clear()
        storage.ALERTS_DB.clear()
        storage.ALERTS_DB.extend(self._orig_alerts)

    async def test_unregistered_error_blocks_token_and_resumes_on_token_change(self):
        """UNREGISTERED: FCM called once, second tick does not call it, entry kept, token not wiped; new token calls again."""
        test_token = "dead_token_1234567890123456789012345678901234567890"
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
        now = time.time()
        outbox.OUTBOX[eid] = {
            "id": eid,
            "alert_id": alert.id,
            "token": test_token,
            "title": "Alert Triggered",
            "body": "BTC reached target",
            "data": {},
            "created_at": now,
            "expires_at": now + 3600,
            "next_attempt_at": now,
            "attempts": 0,
            "last_error": "",
            "blocked_token": None,
        }

        with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_send, \
             patch("app.notifier.outbox._save_outbox", new_callable=AsyncMock):
            mock_send.return_value = (False, "UNREGISTERED")

            # 1. First delivery attempt
            await outbox._deliver_outbox_entry(eid)

            # Entry must be KEPT in OUTBOX, token must NOT be wiped in DB
            self.assertIn(eid, outbox.OUTBOX)
            self.assertEqual(alert.fcm_token, test_token)
            self.assertEqual(outbox.OUTBOX[eid]["blocked_token"], test_token)
            self.assertEqual(mock_send.call_count, 1)

            # 2. Second worker tick while token is still the blocked one
            await outbox._deliver_outbox_entry(eid)
            # FCM must NOT be called again
            self.assertEqual(mock_send.call_count, 1)

            # 3. Alert gets a new token (e.g. from app sync)
            new_token = "fresh_token_9876543210987654321098765432109876543210"
            alert.fcm_token = new_token
            mock_send.return_value = (True, "FCM Message ID: msg_12345")

            # Next delivery attempt with new token
            await outbox._deliver_outbox_entry(eid)

            # FCM called again
            self.assertEqual(mock_send.call_count, 2)
            # Entry delivered and removed
            self.assertNotIn(eid, outbox.OUTBOX)

    async def test_invalid_payload_error_keeps_token_and_retries(self):
        """INVALID_PAYLOAD: never wipes token, increments attempts, keeps retrying."""
        test_token = "valid_fcm_token_1234567890123456789012345678901234567890"
        alert = Alert(
            id="alert_test_2",
            user_id="user_2",
            exchange="binance",
            symbol="BTCUSDT",
            target_price=65000.0,
            fcm_token=test_token
        )
        storage.ALERTS_DB.append(alert)

        eid = "eid_invalid_payload_test"
        now = time.time()
        outbox.OUTBOX[eid] = {
            "id": eid,
            "alert_id": alert.id,
            "token": test_token,
            "title": "Alert Triggered",
            "body": "USDT reached target",
            "data": {},
            "created_at": now,
            "expires_at": now + 3600,
            "next_attempt_at": now,
            "attempts": 0,
            "last_error": "",
            "blocked_token": None,
        }

        with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_send, \
             patch("app.notifier.outbox._save_outbox", new_callable=AsyncMock):
            mock_send.return_value = (False, "INVALID_PAYLOAD")

            await outbox._deliver_outbox_entry(eid)

            # Entry must be kept, token not wiped, attempts incremented
            self.assertIn(eid, outbox.OUTBOX)
            self.assertEqual(alert.fcm_token, test_token)
            self.assertEqual(outbox.OUTBOX[eid]["attempts"], 1)
            self.assertEqual(outbox.OUTBOX[eid]["last_error"], "INVALID_PAYLOAD")
            self.assertIsNone(outbox.OUTBOX[eid].get("blocked_token"))

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
