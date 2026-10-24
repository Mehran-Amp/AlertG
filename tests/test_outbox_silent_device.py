import time
import unittest
from unittest.mock import AsyncMock, patch

from app.notifier import outbox, journal
from app.routes import devices
from app import storage
from app.models import Alert


class TestOutboxSilentDevice(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._orig_outbox = dict(outbox.OUTBOX)
        self._orig_journal = dict(journal.JOURNAL)
        self._orig_device_health = dict(devices.DEVICE_HEALTH)
        outbox.OUTBOX.clear()
        journal.JOURNAL.clear()
        devices.DEVICE_HEALTH.clear()

    async def asyncTearDown(self):
        outbox.OUTBOX.clear()
        outbox.OUTBOX.update(self._orig_outbox)
        journal.JOURNAL.clear()
        journal.JOURNAL.update(self._orig_journal)
        devices.DEVICE_HEALTH.clear()
        devices.DEVICE_HEALTH.update(self._orig_device_health)

    def _make_alert(self, alert_id="alert-silent", user_id="user_silent", ack_supported=True):
        return Alert(
            id=alert_id,
            user_id=user_id,
            exchange="binance",
            symbol="BTCUSDT",
            target_price=65000.0,
            condition="ABOVE",
            ack_supported=ack_supported,
            fcm_token="valid_fcm_token_1234567890123456789012345678901234567890",
            created_at="2026-01-01T00:00:00Z",
        )

    async def test_silent_device_shortens_ack_waits_and_triggers_quicker_fallback(self):
        """1. Last heartbeat > 45 minutes ago shortens ack waits to (15, 30)s and speeds up fallback (Phase 3A-3)."""
        now = time.time()
        uid = "user_silent_trader"

        # Record a stale heartbeat (60 minutes old > 45 minutes)
        devices.DEVICE_HEALTH[uid] = {
            "user_id": uid,
            "fcm_token_tail": "123456",
            "received_at": now - 3600,
        }

        alert = self._make_alert("alt-1", user_id=uid, ack_supported=True)
        storage.ALERTS_DB.append(alert)

        try:
            with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_fcm, \
                 patch("app.notifier.outbox._send_telegram_fallback", new_callable=AsyncMock) as mock_tg:
                mock_fcm.return_value = (True, "OK")

                await outbox.enqueue_alert_push(
                    alert=alert,
                    title="Price Alert",
                    body="BTC hit 65k",
                    data_payload={"symbol": "BTCUSDT"},
                    fallback_chat_id="chat_silent_999"
                )

                self.assertEqual(len(outbox.OUTBOX), 1)
                eid = list(outbox.OUTBOX.keys())[0]
                entry = outbox.OUTBOX[eid]

                # Assert shortened ack waits schedule was assigned
                self.assertEqual(entry.get("ack_waits"), (15, 30))

                # Allow first delivery to complete
                await outbox._deliver_outbox_entry(eid)

                # Entry is in awaiting_ack phase with 15s wait
                self.assertEqual(entry.get("phase"), "awaiting_ack")
                self.assertAlmostEqual(entry.get("ack_due_at"), now + 15, delta=2.0)

                # Simulate time pass: first ack deadline expires -> resend (attempt 1/1)
                with patch("time.time", return_value=now + 16):
                    await outbox._deliver_outbox_entry(eid)
                    self.assertEqual(entry.get("phase"), "resending")
                    self.assertEqual(entry.get("resend_count"), 1)

                    # FCM fires again for resend
                    await outbox._deliver_outbox_entry(eid)
                    self.assertEqual(entry.get("phase"), "awaiting_ack")
                    # Second wait is 30s
                    self.assertAlmostEqual(entry.get("ack_due_at"), (now + 16) + 30, delta=2.0)

                # Simulate time pass: second ack deadline expires -> budget exhausted!
                with patch("time.time", return_value=now + 48):
                    await outbox._deliver_outbox_entry(eid)

                    # Entry was popped and marked unacked
                    self.assertNotIn(eid, outbox.OUTBOX)
                    self.assertEqual(journal.get_delivery_status(eid), "unacked")
                    # Telegram fallback triggered
                    mock_tg.assert_called_once_with(eid, "chat_silent_999", "Price Alert", "BTC hit 65k")

        finally:
            storage.ALERTS_DB = [a for a in storage.ALERTS_DB if a.id != "alt-1"]

    async def test_active_device_or_never_seen_retains_default_waits(self):
        """2. Active device (<45m) or user with no prior heartbeat keeps default (45, 90, 180) waits (Phase 3A-3)."""
        now = time.time()
        uid_active = "user_active_trader"
        uid_new = "user_new_trader"

        # 10 minutes old heartbeat (active)
        devices.DEVICE_HEALTH[uid_active] = {
            "user_id": uid_active,
            "received_at": now - 600,
        }

        alert_active = self._make_alert("alt-active", user_id=uid_active, ack_supported=True)
        alert_new = self._make_alert("alt-new", user_id=uid_new, ack_supported=True)
        storage.ALERTS_DB.extend([alert_active, alert_new])

        try:
            with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_fcm:
                mock_fcm.return_value = (True, "OK")

                # Enqueue active
                await outbox.enqueue_alert_push(alert=alert_active, title="Active", body="B1", data_payload={})
                # Enqueue new (never seen)
                await outbox.enqueue_alert_push(alert=alert_new, title="New", body="B2", data_payload={})

                # Both should have default ACK_WAITS
                for eid, entry in outbox.OUTBOX.items():
                    self.assertEqual(entry.get("ack_waits"), outbox.ACK_WAITS)
        finally:
            storage.ALERTS_DB = [a for a in storage.ALERTS_DB if a.id not in ("alt-active", "alt-new")]


if __name__ == "__main__":
    unittest.main()
