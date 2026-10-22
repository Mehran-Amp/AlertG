import unittest
from unittest.mock import AsyncMock, patch

from app.notifier import outbox, journal
from app import storage
from app.models import Alert


class TestOutboxAwaitingAck(unittest.IsolatedAsyncioTestCase):
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

    def _make_alert(self, alert_id="alert-ack", ack_supported=True):
        a = Alert(
            id=alert_id,
            user_id="u",
            exchange="binance",
            symbol="BTCUSDT",
            target_price=1.0,
            condition="ABOVE",
            ack_supported=ack_supported,
            fcm_token="valid_fcm_token_1234567890123456789012345678901234567890",
            created_at="2026-01-01T00:00:00Z",
        )
        return a

    def _seed_outbox_entry(self, eid, alert_id):
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
        }
        journal.record_queued(eid, alert_id)

    async def test_ack_supported_alert_keeps_entry_after_success(self):
        alert = self._make_alert("a-1", ack_supported=True)
        storage.ALERTS_DB.append(alert)
        try:
            eid = "e-1"
            self._seed_outbox_entry(eid, "a-1")
            with patch.object(outbox, "send_fcm_notification_async", new_callable=AsyncMock) as mock_send, \
                 patch.object(outbox, "_save_outbox", new_callable=AsyncMock):
                mock_send.return_value = (True, "FCM Message ID: ok")
                await outbox._deliver_outbox_entry(eid)
            self.assertIn(eid, outbox.OUTBOX)
            self.assertEqual(outbox.OUTBOX[eid].get("phase"), "awaiting_ack")
            self.assertEqual(journal.get_status(eid), "sent")
        finally:
            storage.ALERTS_DB[:] = [a for a in storage.ALERTS_DB if a.id != "a-1"]

    async def test_non_ack_alert_drops_entry_after_success(self):
        alert = self._make_alert("a-2", ack_supported=False)
        storage.ALERTS_DB.append(alert)
        try:
            eid = "e-2"
            self._seed_outbox_entry(eid, "a-2")
            with patch.object(outbox, "send_fcm_notification_async", new_callable=AsyncMock) as mock_send, \
                 patch.object(outbox, "_save_outbox", new_callable=AsyncMock):
                mock_send.return_value = (True, "FCM Message ID: ok")
                await outbox._deliver_outbox_entry(eid)
            self.assertNotIn(eid, outbox.OUTBOX)
        finally:
            storage.ALERTS_DB[:] = [a for a in storage.ALERTS_DB if a.id != "a-2"]

    async def test_on_delivery_acked_removes_entry(self):
        alert = self._make_alert("a-3", ack_supported=True)
        storage.ALERTS_DB.append(alert)
        try:
            eid = "e-3"
            self._seed_outbox_entry(eid, "a-3")
            outbox.OUTBOX[eid]["phase"] = "awaiting_ack"
            with patch.object(outbox, "_save_outbox", new_callable=AsyncMock):
                removed = await outbox.on_delivery_acked(eid)
            self.assertTrue(removed)
            self.assertNotIn(eid, outbox.OUTBOX)
        finally:
            storage.ALERTS_DB[:] = [a for a in storage.ALERTS_DB if a.id != "a-3"]


if __name__ == "__main__":
    unittest.main()