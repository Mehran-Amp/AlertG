import os
import time
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from app import storage
from app.engine import market_events
from app.engine.market_events import check_and_dispatch_event_notifications


class TestMarketEventsPersistence(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._orig_state_file = market_events.EVENTS_STATE_FILE
        self._orig_sent = dict(market_events.SENT_REMINDERS)
        self._orig_user = dict(market_events.EVENT_USER_REMINDERS)
        self._orig_disp = dict(market_events.DISPATCHED_EVENTS)
        self._orig_user_disp = {k: set(v) for k, v in market_events.USER_DISPATCHED_EVENTS.items()}
        self._orig_profiles = dict(storage.USER_PROFILES_DB)

        self._tmp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp_file.close()
        market_events.EVENTS_STATE_FILE = self._tmp_file.name
        market_events.SENT_REMINDERS.clear()
        market_events.EVENT_USER_REMINDERS.clear()
        market_events.DISPATCHED_EVENTS.clear()
        market_events.USER_DISPATCHED_EVENTS.clear()
        storage.USER_PROFILES_DB.clear()

    def tearDown(self):
        market_events.EVENTS_STATE_FILE = self._orig_state_file
        market_events.SENT_REMINDERS.clear()
        market_events.SENT_REMINDERS.update(self._orig_sent)
        market_events.EVENT_USER_REMINDERS.clear()
        market_events.EVENT_USER_REMINDERS.update(self._orig_user)
        market_events.DISPATCHED_EVENTS.clear()
        market_events.DISPATCHED_EVENTS.update(self._orig_disp)
        market_events.USER_DISPATCHED_EVENTS.clear()
        market_events.USER_DISPATCHED_EVENTS.update(self._orig_user_disp)
        storage.USER_PROFILES_DB.clear()
        storage.USER_PROFILES_DB.update(self._orig_profiles)

        for p in (self._tmp_file.name, self._tmp_file.name + ".bad", self._tmp_file.name + ".tmp"):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass

    def test_1_save_and_load_dispatched_events_with_7day_ttl_and_bad_file_handling(self):
        """1. Validates save/load of dispatched_events, 7-day TTL pruning, and .bad rename on corruption (FIX-5b)."""
        now = time.time()
        fresh_key = "user_alice:macro_fomc_rate:1770000000"
        stale_key = "user_bob:macro_cpi_inflation:1760000000"

        # Fresh event: dispatched 1 hour ago
        market_events.DISPATCHED_EVENTS[fresh_key] = now - 3600
        # Stale event: dispatched 8 days ago
        market_events.DISPATCHED_EVENTS[stale_key] = now - (8 * 86400)

        # Also test reminder and user registration persistence
        market_events.SENT_REMINDERS["remind_1:chat_1:advance_30m"] = now - 600
        market_events.EVENT_USER_REMINDERS["macro_fomc_rate"] = {"user_alice": "chat_1"}

        # Save to disk
        market_events.save_events_state()

        # Clear memory
        market_events.SENT_REMINDERS.clear()
        market_events.EVENT_USER_REMINDERS.clear()
        market_events.DISPATCHED_EVENTS.clear()

        # Reload from disk
        loaded_sent, loaded_user, loaded_disp = market_events._load_events_state()

        # Fresh dispatched event kept, stale entry pruned
        self.assertIn(fresh_key, loaded_disp)
        self.assertNotIn(stale_key, loaded_disp)
        self.assertIn("remind_1:chat_1:advance_30m", loaded_sent)
        self.assertIn("macro_fomc_rate", loaded_user)

        # Corrupted file test: load returns empty dicts and preserves .bad copy
        with open(market_events.EVENTS_STATE_FILE, "w", encoding="utf-8") as f:
            f.write("{ invalid json corrupted content [[[")

        corrupt_sent, corrupt_user, corrupt_disp = market_events._load_events_state()
        self.assertEqual(corrupt_sent, {})
        self.assertEqual(corrupt_user, {})
        self.assertEqual(corrupt_disp, {})
        self.assertTrue(os.path.exists(market_events.EVENTS_STATE_FILE + ".bad"))

    async def test_2_dispatched_events_prevent_redelivery_after_restart(self):
        """2. Validates that persisted dispatched_events prevent re-dispatching events after server restart (FIX-5b)."""
        user_id = "user_persist_test"
        chat_id = "chat_persist_123"
        storage.USER_PROFILES_DB[user_id] = {
            "user_id": user_id,
            "telegram_chat_id": chat_id,
            "events_telegram_enabled": True,
            "events_notification_enabled": True,
            "fcm_token": "valid_fcm_token_123456789012345678901234567890",
        }

        mock_client = AsyncMock()

        # 1. First run: events are dispatched and persisted to disk
        with patch("app.engine.market_events.send_telegram_alert", new_callable=AsyncMock) as mock_tg_1, \
             patch("app.engine.market_events.enqueue_alert_push", new_callable=AsyncMock) as mock_push_1, \
             patch("app.engine.market_events.TELEGRAM_BOT_TOKEN", "valid_bot_token"):
            await check_and_dispatch_event_notifications(mock_client)

        self.assertGreater(mock_tg_1.call_count, 0)
        self.assertGreater(mock_push_1.call_count, 0)
        self.assertGreater(len(market_events.DISPATCHED_EVENTS), 0)

        # 2. Simulate server restart: clear memory and re-initialize from persisted file
        market_events.DISPATCHED_EVENTS.clear()
        market_events.USER_DISPATCHED_EVENTS.clear()

        _, _, reloaded_disp = market_events._load_events_state()
        market_events.DISPATCHED_EVENTS.update(reloaded_disp)
        for k in reloaded_disp:
            parts = k.split(":")
            if len(parts) >= 2:
                market_events.USER_DISPATCHED_EVENTS.setdefault(parts[0], set()).add(parts[1])

        # 3. Second run after restart: no events should be re-dispatched
        mock_client_2 = AsyncMock()
        with patch("app.engine.market_events.send_telegram_alert", new_callable=AsyncMock) as mock_tg_2, \
             patch("app.engine.market_events.enqueue_alert_push", new_callable=AsyncMock) as mock_push_2, \
             patch("app.engine.market_events.TELEGRAM_BOT_TOKEN", "valid_bot_token"):
            await check_and_dispatch_event_notifications(mock_client_2)

        mock_tg_2.assert_not_called()
        mock_push_2.assert_not_called()


if __name__ == "__main__":
    unittest.main()
