import time
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

import firebase_admin
from firebase_admin import messaging, exceptions as fb_exceptions

from app.notifier import fcm, outbox
from app.models import Alert
from app import storage
from app.state import METRICS


class TestFcmAuthError(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._orig_outbox = dict(outbox.OUTBOX)
        self._orig_dead = set(outbox.DEAD_TOKENS)
        self._orig_metrics = dict(METRICS)
        self._orig_alerts = list(storage.ALERTS_DB)

        outbox.OUTBOX.clear()
        outbox.DEAD_TOKENS.clear()
        storage.ALERTS_DB.clear()

        if "fcm_auth_error" not in METRICS:
            METRICS["fcm_auth_error"] = 0
        if "fcm_invalid_token" not in METRICS:
            METRICS["fcm_invalid_token"] = 0

    async def asyncTearDown(self):
        outbox.OUTBOX.clear()
        outbox.OUTBOX.update(self._orig_outbox)
        outbox.DEAD_TOKENS.clear()
        outbox.DEAD_TOKENS.update(self._orig_dead)
        METRICS.clear()
        METRICS.update(self._orig_metrics)
        storage.ALERTS_DB.clear()
        storage.ALERTS_DB.extend(self._orig_alerts)

    def test_permission_denied_exception_returns_fcm_auth_error(self):
        """1. PermissionDeniedError is classified as FCM_AUTH_ERROR and outbox retries without blocking token (Phase 2C-2)."""
        test_token = "valid_fcm_token_1234567890123456789012345678901234567890"

        with patch.object(firebase_admin, "_apps", {"[DEFAULT]": True}), patch("time.sleep"):
            # Mock fb_exceptions.PermissionDeniedError
            err = getattr(fb_exceptions, "PermissionDeniedError", Exception)("Caller does not have permission")
            with patch.object(messaging, "send", side_effect=err):
                ok, msg = fcm._send_fcm_sync(test_token, "Title", "Body")
                self.assertFalse(ok)
                self.assertEqual(msg, "FCM_AUTH_ERROR")

    async def test_outbox_retries_fcm_auth_error_without_blocking_token(self):
        """2. Outbox handles FCM_AUTH_ERROR by retrying, incrementing fcm_auth_error, without blocking token (Phase 2C-2)."""
        test_token = "valid_fcm_token_9999999990123456789012345678901234567890"
        alert = Alert(
            id="alert_auth_test",
            user_id="trader_auth",
            exchange="binance",
            symbol="BTCUSDT",
            target_price=60000.0,
            fcm_token=test_token
        )
        storage.ALERTS_DB.append(alert)

        eid = "eid_auth_error_test"
        now = time.time()
        outbox.OUTBOX[eid] = {
            "id": eid,
            "alert_id": alert.id,
            "token": test_token,
            "title": "Title",
            "body": "Body",
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
            mock_send.return_value = (False, "FCM_AUTH_ERROR")

            await outbox._deliver_outbox_entry(eid)

        entry = outbox.OUTBOX[eid]
        self.assertEqual(entry["attempts"], 1)
        self.assertEqual(entry["last_error"], "FCM_AUTH_ERROR")
        # Token must NOT be blocked
        self.assertIsNone(entry.get("blocked_token"))
        self.assertNotIn(test_token, outbox.DEAD_TOKENS)
        self.assertGreater(METRICS.get("fcm_auth_error", 0), 0)
        self.assertEqual(METRICS.get("fcm_invalid_token", 0), 0)


if __name__ == "__main__":
    unittest.main()
