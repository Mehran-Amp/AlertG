import time
import unittest
from unittest.mock import AsyncMock, patch

from app.notifier import outbox, journal
from app import storage
from app.models import Alert


class TestOutboxResend(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._orig_outbox = dict(outbox.OUTBOX)
        self._orig_journal = dict(journal.JOURNAL)
        outbox.OUTBOX.clear()
        journal.JOURNAL.clear()

    async def asyncTearDown(self):
        outbox.OUTBOX.clear()
        outbox.OUTBOX.update(self._orig_outbox)
        journal.JOURNAL.clear()
        journal.JOURNAL.update(self._orig_journal)

    def _make_alert(self, alert_id="alert-rs"):
        return Alert(
            id=alert_id,
            user_id="u",
            exchange="binance",
            symbol="BTCUSDT",
            target_price=1.0,
            condition="ABOVE",
            ack_supported=True,
            fcm_token="valid_fcm_token_1234567890123456789012345678901234567890",
            created_at="2026-01-01T00:00:00Z",
        )

    def _seed(self, eid, alert_id):
        outbox.OUTBOX[eid] = {
            "id": eid,
            "alert_id": alert_id,
            "token": "valid_fcm_token_1234567890123456789012345678901234567890",
            "title": "T",
            "body": "B",
            "data": {},
            "created_at": 0,
            "expires_at": 10**12,
            "next_attempt_at": 0,
            "next_retry_at": 0,
            "attempts": 0,
            "last_error": "",
            "blocked_token": None,
            "phase": "awaiting_ack",
            "ack_due_at": 0,
            "resend_count": 0,
        }
        journal.record_queued(eid, alert_id)

    async def test_first_deadline_triggers_one_resend(self):
        alert = self._make_alert("a-rs-1")
        storage.ALERTS_DB.append(alert)
        try:
            eid = "e-rs-1"
            self._seed(eid, "a-rs-1")
            outbox.OUTBOX[eid]["ack_due_at"] = time.time() - 1
            outbox.OUTBOX[eid]["resend_count"] = 0
            with patch.object(outbox, "send_fcm_notification_async", new_callable=AsyncMock) as mock_send, \
                 patch.object(outbox, "_save_outbox", new_callable=AsyncMock):
                mock_send.return_value = (True, "FCM Message ID: ok")
                await outbox._deliver_outbox_entry(eid)
            self.assertIn(eid, outbox.OUTBOX)
            self.assertEqual(outbox.OUTBOX[eid].get("resend_count"), 1)
            self.assertEqual(mock_send.call_count, 1)
        finally:
            storage.ALERTS_DB[:] = [a for a in storage.ALERTS_DB if a.id != "a-rs-1"]

    async def test_ack_during_resend_does_not_revive_entry(self):
        alert = self._make_alert("a-rs-2")
        storage.ALERTS_DB.append(alert)
        try:
            eid = "e-rs-2"
            self._seed(eid, "a-rs-2")
            outbox.OUTBOX[eid]["ack_due_at"] = time.time() - 1
            with patch.object(outbox, "_save_outbox", new_callable=AsyncMock):
                await outbox.on_delivery_acked(eid)
                await outbox._deliver_outbox_entry(eid)
            self.assertNotIn(eid, outbox.OUTBOX)
        finally:
            storage.ALERTS_DB[:] = [a for a in storage.ALERTS_DB if a.id != "a-rs-2"]

    async def test_budget_exhausted_marks_unacked(self):
        alert = self._make_alert("a-rs-3")
        storage.ALERTS_DB.append(alert)
        try:
            eid = "e-rs-3"
            self._seed(eid, "a-rs-3")
            outbox.OUTBOX[eid]["ack_due_at"] = time.time() - 1
            outbox.OUTBOX[eid]["resend_count"] = len(outbox.ACK_WAITS) - 1
            with patch.object(outbox, "send_fcm_notification_async", new_callable=AsyncMock) as mock_send, \
                 patch.object(outbox, "_save_outbox", new_callable=AsyncMock):
                await outbox._deliver_outbox_entry(eid)
            self.assertNotIn(eid, outbox.OUTBOX)
            self.assertEqual(journal.get_status(eid), "unacked")
            self.assertEqual(mock_send.call_count, 0)
        finally:
            storage.ALERTS_DB[:] = [a for a in storage.ALERTS_DB if a.id != "a-rs-3"]


if __name__ == "__main__":
    unittest.main()