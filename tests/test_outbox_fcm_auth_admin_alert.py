import time
import unittest
from unittest.mock import AsyncMock, patch

from app.notifier import outbox
from app.state import METRICS


class TestOutboxFcmAuthAdminAlert(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._orig_outbox = dict(outbox.OUTBOX)
        self._orig_metrics = dict(METRICS)
        self._orig_consecutive = outbox._CONSECUTIVE_FCM_AUTH_ERRORS
        self._orig_last_alert_ts = outbox._LAST_FCM_AUTH_ADMIN_ALERT_TS

        outbox.OUTBOX.clear()
        outbox._CONSECUTIVE_FCM_AUTH_ERRORS = 0
        outbox._LAST_FCM_AUTH_ADMIN_ALERT_TS = 0.0

        if "fcm_auth_error" not in METRICS:
            METRICS["fcm_auth_error"] = 0

    async def asyncTearDown(self):
        outbox.OUTBOX.clear()
        outbox.OUTBOX.update(self._orig_outbox)
        METRICS.clear()
        METRICS.update(self._orig_metrics)
        outbox._CONSECUTIVE_FCM_AUTH_ERRORS = self._orig_consecutive
        outbox._LAST_FCM_AUTH_ADMIN_ALERT_TS = self._orig_last_alert_ts

    def _seed_entry(self, eid: str) -> None:
        now = time.time()
        outbox.OUTBOX[eid] = {
            "id": eid,
            "alert_id": f"alert_{eid}",
            "token": f"fcm_token_valid_for_testing_{eid}_1234567890",
            "title": "Alert Title",
            "body": "Alert Body",
            "data": {},
            "created_at": now,
            "expires_at": now + 3600,
            "next_attempt_at": now,
            "attempts": 0,
            "last_error": "",
            "blocked_token": None,
        }

    async def test_three_consecutive_fcm_auth_errors_triggers_one_admin_alert(self):
        """1. Three consecutive FCM_AUTH_ERRORs triggers exactly one notify_admin_telegram alert (Phase 2C-3)."""
        self._seed_entry("e1")
        self._seed_entry("e2")
        self._seed_entry("e3")

        with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_send, \
             patch("app.notifier.outbox.notify_admin_telegram", new_callable=AsyncMock) as mock_admin, \
             patch("app.notifier.outbox._save_outbox", new_callable=AsyncMock):

            mock_send.return_value = (False, "FCM_AUTH_ERROR")

            # Error 1
            await outbox._deliver_outbox_entry("e1")
            self.assertEqual(outbox._CONSECUTIVE_FCM_AUTH_ERRORS, 1)
            self.assertEqual(mock_admin.call_count, 0)

            # Error 2
            await outbox._deliver_outbox_entry("e2")
            self.assertEqual(outbox._CONSECUTIVE_FCM_AUTH_ERRORS, 2)
            self.assertEqual(mock_admin.call_count, 0)

            # Error 3: triggers admin alert
            await outbox._deliver_outbox_entry("e3")
            self.assertEqual(outbox._CONSECUTIVE_FCM_AUTH_ERRORS, 3)
            self.assertEqual(mock_admin.call_count, 1)

            # Check message contains diagnostic details
            admin_msg = mock_admin.call_args[0][0]
            self.assertIn("FCM AUTH FAILURE", admin_msg)
            self.assertIn("3", admin_msg)

    async def test_fourth_error_within_30m_is_rate_limited_and_success_resets_counter(self):
        """2. Fourth error within 30 minutes does not send new alert; success resets counter (Phase 2C-3)."""
        self._seed_entry("e1")
        self._seed_entry("e2")
        self._seed_entry("e3")
        self._seed_entry("e4")
        self._seed_entry("e_ok")

        with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_send, \
             patch("app.notifier.outbox.notify_admin_telegram", new_callable=AsyncMock) as mock_admin, \
             patch("app.notifier.outbox._save_outbox", new_callable=AsyncMock):

            mock_send.return_value = (False, "FCM_AUTH_ERROR")

            # Deliver 3 errors -> 1 alert sent
            await outbox._deliver_outbox_entry("e1")
            await outbox._deliver_outbox_entry("e2")
            await outbox._deliver_outbox_entry("e3")
            self.assertEqual(mock_admin.call_count, 1)

            # Error 4 immediately after (within 30m window) -> no new alert
            await outbox._deliver_outbox_entry("e4")
            self.assertEqual(outbox._CONSECUTIVE_FCM_AUTH_ERRORS, 4)
            self.assertEqual(mock_admin.call_count, 1)

            # Successful delivery resets consecutive errors counter to 0
            mock_send.return_value = (True, "msg_id_12345")
            await outbox._deliver_outbox_entry("e_ok")
            self.assertEqual(outbox._CONSECUTIVE_FCM_AUTH_ERRORS, 0)


if __name__ == "__main__":
    unittest.main()
