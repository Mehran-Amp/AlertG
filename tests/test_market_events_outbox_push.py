import time
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from app.engine import market_events
from app import storage


class TestMarketEventsOutboxPush(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._orig_state_file = market_events.EVENTS_STATE_FILE
        self._orig_sent = dict(market_events.SENT_REMINDERS)
        self._orig_user_reminders = dict(market_events.EVENT_USER_REMINDERS)
        self._orig_catalog = [dict(e) for e in market_events.CURATED_HIGH_IMPACT_CATALOG]
        self._orig_cache = list(market_events.MARKET_EVENTS_CACHE)
        self._orig_profiles = dict(storage.USER_PROFILES_DB)
        self._orig_alerts = list(storage.ALERTS_DB)
        self._orig_dispatched = dict(market_events.USER_DISPATCHED_EVENTS)

        self._tmp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp_file.close()
        market_events.EVENTS_STATE_FILE = self._tmp_file.name

        market_events.SENT_REMINDERS.clear()
        market_events.EVENT_USER_REMINDERS.clear()
        market_events.MARKET_EVENTS_CACHE.clear()
        market_events.USER_DISPATCHED_EVENTS.clear()
        storage.USER_PROFILES_DB.clear()
        storage.ALERTS_DB.clear()

        self.test_event_id = "test_fomc_push"
        self.fixed_start_utc = int(time.time()) + 7200
        self.test_event = {
            "id": self.test_event_id,
            "category": "macro",
            "market": "Forex & Global",
            "title": "US Fed Interest Rate Decision",
            "summary": "FOMC rate decision announcement.",
            "impact": "high",
            "time_utc": "Wednesday 18:00 UTC",
            "start_utc": self.fixed_start_utc,
            "symbol": "USD"
        }
        market_events.MARKET_EVENTS_CACHE.append(self.test_event)

    async def asyncTearDown(self):
        market_events.EVENTS_STATE_FILE = self._orig_state_file
        market_events.SENT_REMINDERS.clear()
        market_events.SENT_REMINDERS.update(self._orig_sent)
        market_events.EVENT_USER_REMINDERS.clear()
        market_events.EVENT_USER_REMINDERS.update(self._orig_user_reminders)
        market_events.CURATED_HIGH_IMPACT_CATALOG.clear()
        market_events.CURATED_HIGH_IMPACT_CATALOG.extend(self._orig_catalog)
        market_events.MARKET_EVENTS_CACHE.clear()
        market_events.MARKET_EVENTS_CACHE.extend(self._orig_cache)
        market_events.USER_DISPATCHED_EVENTS.clear()
        market_events.USER_DISPATCHED_EVENTS.update(self._orig_dispatched)

        storage.USER_PROFILES_DB.clear()
        storage.USER_PROFILES_DB.update(self._orig_profiles)
        storage.ALERTS_DB.clear()
        storage.ALERTS_DB.extend(self._orig_alerts)

        import os
        for p in (self._tmp_file.name, self._tmp_file.name + ".bad", self._tmp_file.name + ".tmp"):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass

    async def test_event_notification_enqueues_fcm_outbox_push(self):
        """1. User with events_notification_enabled gets push via enqueue_alert_push (Phase 2B-4)."""
        uid = "user_fcm_trader"
        dummy_fcm = "fcm_token_1234567890123456789012345678901234567890"

        # User profile with notifications enabled and FCM token
        storage.USER_PROFILES_DB[uid] = {
            "user_id": uid,
            "telegram_chat_id": "chat_555",
            "events_notification_enabled": True,
            "fcm_token": dummy_fcm
        }

        mock_client = AsyncMock()

        with patch("app.engine.market_events.enqueue_alert_push", new_callable=AsyncMock) as mock_push, \
             patch("app.engine.market_events.send_telegram_alert", new_callable=AsyncMock):
            await market_events.check_and_dispatch_event_notifications(client=mock_client)

        # Assert enqueue_alert_push was invoked
        mock_push.assert_called_once()
        call_kwargs = mock_push.call_args.kwargs
        call_args = mock_push.call_args.args

        # Verify alert stub passed
        alert_stub = call_kwargs.get("alert") or (call_args[0] if len(call_args) > 0 else None)
        self.assertIsNotNone(alert_stub)
        self.assertTrue(alert_stub.id.startswith(f"ev_{self.test_event_id}"))
        self.assertEqual(alert_stub.fcm_token, dummy_fcm)
        self.assertTrue(alert_stub.ack_supported)

        # Verify payload contains event metadata
        payload = call_kwargs.get("data_payload") or (call_args[3] if len(call_args) > 3 else {})
        self.assertEqual(payload.get("type"), "market_event")
        self.assertEqual(payload.get("event_id"), self.test_event_id)

    async def test_30m_advance_reminder_enqueues_fcm_outbox_push(self):
        """2. 30-minute advance reminder enqueues push via enqueue_alert_push with fallback_chat_id (Phase 2B-4)."""
        uid = "user_remind_trader"
        dummy_fcm = "fcm_token_9999999990123456789012345678901234567890"

        # User profile with FCM token and Telegram chat
        storage.USER_PROFILES_DB[uid] = {
            "user_id": uid,
            "telegram_chat_id": "chat_888",
            "fcm_token": dummy_fcm
        }

        # User registered for 30m reminder
        market_events.EVENT_USER_REMINDERS[self.test_event_id] = {uid: "chat_888"}

        # Simulate T - 30 minutes
        now_ts = self.fixed_start_utc - 1800
        mock_client = AsyncMock()

        with patch("app.engine.market_events.enqueue_alert_push", new_callable=AsyncMock) as mock_push, \
             patch("app.engine.market_events.send_telegram_alert", new_callable=AsyncMock):
            dispatched = await market_events.check_and_dispatch_30m_advance_reminders(
                client=mock_client, now_ts=now_ts
            )

        self.assertEqual(dispatched, 1)
        mock_push.assert_called_once()

        call_kwargs = mock_push.call_args.kwargs
        call_args = mock_push.call_args.args

        alert_stub = call_kwargs.get("alert") or (call_args[0] if len(call_args) > 0 else None)
        self.assertIsNotNone(alert_stub)
        self.assertTrue(alert_stub.id.startswith(f"remind_{self.test_event_id}"))
        self.assertEqual(alert_stub.fcm_token, dummy_fcm)

        # Verify fallback_chat_id
        fallback_chat = call_kwargs.get("fallback_chat_id") or (call_args[4] if len(call_args) > 4 else None)
        self.assertEqual(fallback_chat, "chat_888")

        # Verify payload type
        payload = call_kwargs.get("data_payload") or (call_args[3] if len(call_args) > 3 else {})
        self.assertEqual(payload.get("type"), "event_advance_reminder")
        self.assertEqual(payload.get("is_advance_notice"), "true")


if __name__ == "__main__":
    unittest.main()
