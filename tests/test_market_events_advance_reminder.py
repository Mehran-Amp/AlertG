import os
import time
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from app.engine import market_events


class TestMarketEventsAdvanceReminder(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._orig_state_file = market_events.EVENTS_STATE_FILE
        self._orig_sent = dict(market_events.SENT_REMINDERS)
        self._orig_user = dict(market_events.EVENT_USER_REMINDERS)
        self._orig_catalog = [dict(e) for e in market_events.CURATED_HIGH_IMPACT_CATALOG]
        self._orig_cache = list(market_events.MARKET_EVENTS_CACHE)

        self._tmp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp_file.close()
        market_events.EVENTS_STATE_FILE = self._tmp_file.name
        market_events.SENT_REMINDERS.clear()
        market_events.EVENT_USER_REMINDERS.clear()
        market_events.MARKET_EVENTS_CACHE.clear()

        # Set up a known event with a fixed start_utc (2,000,000)
        self.test_event_id = "test_fomc_event"
        self.fixed_start_utc = 2_000_000
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
        market_events.CURATED_HIGH_IMPACT_CATALOG.append(self.test_event)

    async def asyncTearDown(self):
        market_events.EVENTS_STATE_FILE = self._orig_state_file
        market_events.SENT_REMINDERS.clear()
        market_events.SENT_REMINDERS.update(self._orig_sent)
        market_events.EVENT_USER_REMINDERS.clear()
        market_events.EVENT_USER_REMINDERS.update(self._orig_user)
        market_events.CURATED_HIGH_IMPACT_CATALOG.clear()
        market_events.CURATED_HIGH_IMPACT_CATALOG.extend(self._orig_catalog)
        market_events.MARKET_EVENTS_CACHE.clear()
        market_events.MARKET_EVENTS_CACHE.extend(self._orig_cache)

        for p in (self._tmp_file.name, self._tmp_file.name + ".bad", self._tmp_file.name + ".tmp"):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass

    async def test_advance_reminder_sent_in_30m_window(self):
        """1. Validates that 30 minutes before event (remaining=1800s), an advance reminder is sent once (Phase 2B-3)."""
        # Register user for the test event
        market_events.EVENT_USER_REMINDERS[self.test_event_id] = {"trader_1": "chat_12345"}

        # Simulate now_ts = 30 minutes before start_utc (tolerance [1740, 1860])
        now_ts = self.fixed_start_utc - 1800
        mock_client = AsyncMock()

        with patch("app.engine.market_events.send_telegram_alert", new_callable=AsyncMock) as mock_send, \
             patch("app.engine.market_events.TELEGRAM_BOT_TOKEN", "valid_bot_token"):
            dispatched = await market_events.check_and_dispatch_30m_advance_reminders(
                client=mock_client, now_ts=now_ts
            )

        self.assertEqual(dispatched, 1)
        mock_send.assert_called_once()
        sent_chat_id = mock_send.call_args[0][1]
        sent_text = mock_send.call_args[0][2]
        self.assertEqual(sent_chat_id, "chat_12345")
        self.assertIn("30 MINUTES", sent_text)

        # Check recorded in SENT_REMINDERS with start_utc in key
        expected_key = f"{self.test_event_id}:chat_12345:advance_30m:{self.fixed_start_utc}"
        self.assertIn(expected_key, market_events.SENT_REMINDERS)

    async def test_advance_reminder_no_duplicate_in_same_or_later_window(self):
        """2. Validates that duplicate advance reminders are never sent in subsequent checks (Phase 2B-3)."""
        market_events.EVENT_USER_REMINDERS[self.test_event_id] = {"trader_1": "chat_12345"}
        mock_client = AsyncMock()

        # First run at T - 30m (remaining = 1800s)
        now_ts = self.fixed_start_utc - 1800
        with patch("app.engine.market_events.send_telegram_alert", new_callable=AsyncMock) as mock_send, \
             patch("app.engine.market_events.TELEGRAM_BOT_TOKEN", "valid_bot_token"):
            dispatched_1 = await market_events.check_and_dispatch_30m_advance_reminders(
                client=mock_client, now_ts=now_ts
            )
            self.assertEqual(dispatched_1, 1)

            # Second run 20 seconds later (remaining = 1780s, still in window)
            dispatched_2 = await market_events.check_and_dispatch_30m_advance_reminders(
                client=mock_client, now_ts=now_ts + 20
            )
            self.assertEqual(dispatched_2, 0)
            # send_telegram_alert still only called once
            self.assertEqual(mock_send.call_count, 1)

    async def test_advance_reminder_prevented_after_restart_and_handles_rescheduled_time(self):
        """3. Validates persisted state prevents duplicate after restart, but sends if event time changes (Phase 2B-3)."""
        market_events.EVENT_USER_REMINDERS[self.test_event_id] = {"trader_1": "chat_12345"}
        mock_client = AsyncMock()

        # 1. Send reminder and persist to disk
        now_ts = self.fixed_start_utc - 1800
        with patch("app.engine.market_events.send_telegram_alert", new_callable=AsyncMock), \
             patch("app.engine.market_events.TELEGRAM_BOT_TOKEN", "valid_bot_token"):
            await market_events.check_and_dispatch_30m_advance_reminders(
                client=mock_client, now_ts=now_ts
            )

        # 2. Simulate server restart: clear memory and reload from state file
        market_events.SENT_REMINDERS.clear()
        market_events.EVENT_USER_REMINDERS.clear()
        reloaded_sent, reloaded_user = market_events._load_events_state()
        market_events.SENT_REMINDERS.update(reloaded_sent)
        market_events.EVENT_USER_REMINDERS.update(reloaded_user)

        # Attempt to resend at same window
        with patch("app.engine.market_events.send_telegram_alert", new_callable=AsyncMock) as mock_send_2, \
             patch("app.engine.market_events.TELEGRAM_BOT_TOKEN", "valid_bot_token"):
            dispatched_after_restart = await market_events.check_and_dispatch_30m_advance_reminders(
                client=mock_client, now_ts=now_ts + 10
            )
            self.assertEqual(dispatched_after_restart, 0)
            mock_send_2.assert_not_called()

        # 3. If event start_utc is rescheduled to a new time (e.g. +50,000s)
        new_start_utc = self.fixed_start_utc + 50_000
        self.test_event["start_utc"] = new_start_utc

        with patch("app.engine.market_events.send_telegram_alert", new_callable=AsyncMock) as mock_send_3, \
             patch("app.engine.market_events.TELEGRAM_BOT_TOKEN", "valid_bot_token"):
            rescheduled_now = new_start_utc - 1800
            dispatched_rescheduled = await market_events.check_and_dispatch_30m_advance_reminders(
                client=mock_client, now_ts=rescheduled_now
            )
            self.assertEqual(dispatched_rescheduled, 1)
            mock_send_3.assert_called_once()


if __name__ == "__main__":
    unittest.main()
