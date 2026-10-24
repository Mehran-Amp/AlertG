import unittest
from unittest.mock import AsyncMock, patch

from app import storage
from app.models import Alert
from app.engine import market_events
from app.engine.market_events import EventAlertStub, check_and_dispatch_event_notifications


class TestMarketEventsOptinAndAck(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._orig_alerts = list(storage.ALERTS_DB)
        self._orig_profiles = dict(storage.USER_PROFILES_DB)
        self._orig_dispatched = {k: set(v) for k, v in market_events.USER_DISPATCHED_EVENTS.items()}
        storage.ALERTS_DB.clear()
        storage.USER_PROFILES_DB.clear()
        market_events.USER_DISPATCHED_EVENTS.clear()

    def tearDown(self):
        storage.ALERTS_DB.clear()
        storage.ALERTS_DB.extend(self._orig_alerts)
        storage.USER_PROFILES_DB.clear()
        storage.USER_PROFILES_DB.update(self._orig_profiles)
        market_events.USER_DISPATCHED_EVENTS.clear()
        market_events.USER_DISPATCHED_EVENTS.update(self._orig_dispatched)

    def test_1_user_without_ack_alert_has_ack_supported_false(self):
        """1. EventAlertStub derives ack_supported=False when user has no ack_supported alerts in ALERTS_DB (FIX-5a)."""
        # User has an alert with ack_supported=False
        storage.ALERTS_DB.append(Alert(
            id="alert_legacy",
            user_id="user_legacy",
            exchange="binance",
            symbol="BTCUSDT",
            target_price=50000.0,
            condition="ABOVE",
            ack_supported=False,
            created_at="2026-10-24T00:00:00Z"
        ))

        stub = EventAlertStub(
            alert_id="ev_test_1",
            user_id="user_legacy",
            fcm_token="sample_fcm_token_12345678901234567890",
            telegram_chat_id="chat_123"
        )
        self.assertFalse(stub.ack_supported)

    def test_2_user_with_ack_alert_has_ack_supported_true(self):
        """2. EventAlertStub derives ack_supported=True when user has at least one ack_supported=True alert (FIX-5a)."""
        storage.ALERTS_DB.append(Alert(
            id="alert_modern",
            user_id="user_modern",
            exchange="binance",
            symbol="ETHUSDT",
            target_price=3000.0,
            condition="ABOVE",
            ack_supported=True,
            created_at="2026-10-24T00:00:00Z"
        ))

        stub = EventAlertStub(
            alert_id="ev_test_2",
            user_id="user_modern",
            fcm_token="sample_fcm_token_12345678901234567890",
            telegram_chat_id="chat_456"
        )
        self.assertTrue(stub.ack_supported)

    async def test_3_telegram_only_user_receives_zero_fcm_pushes(self):
        """3. Users with telegram enabled but events_notification_enabled=False receive Telegram but zero FCM pushes (FIX-5a)."""
        user_id = "user_tg_only"
        chat_id = "chat_tg_only_123"
        storage.USER_PROFILES_DB[user_id] = {
            "user_id": user_id,
            "telegram_chat_id": chat_id,
            "events_telegram_enabled": True,
            "events_notification_enabled": False,  # No push opt-in
            "fcm_token": "valid_fcm_token_123456789012345678901234567890",
        }

        mock_client = AsyncMock()

        with patch("app.engine.market_events.send_telegram_alert", new_callable=AsyncMock) as mock_tg, \
             patch("app.engine.market_events.enqueue_alert_push", new_callable=AsyncMock) as mock_push, \
             patch("app.engine.market_events.TELEGRAM_BOT_TOKEN", "valid_bot_token"):
            await check_and_dispatch_event_notifications(mock_client)

        # Telegram alert was dispatched
        mock_tg.assert_called()
        self.assertEqual(mock_tg.call_args[0][1], chat_id)

        # FCM push was NEVER queued for this user
        mock_push.assert_not_called()


if __name__ == "__main__":
    unittest.main()
