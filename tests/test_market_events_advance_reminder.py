import os
import time
import tempfile
import unittest
from datetime import datetime, timezone
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

        # Recurring test event without hardcoded import-time start_utc (FIX-4a)
        self.test_event_id = "test_fomc_rate"
        self.test_event = {
            "id": self.test_event_id,
            "category": "macro",
            "market": "Forex & Global",
            "title": "US Fed Interest Rate Decision (FOMC)",
            "summary": "FOMC rate decision announcement.",
            "impact": "high",
            "time_utc": "Wednesday 18:00 UTC",
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

    async def test_1_recurring_event_found_in_30m_window_after_one_week_and_one_day(self):
        """1. Recurring event is dynamically discovered in 30m window 8 days after initial boot/import (FIX-4a)."""
        market_events.EVENT_USER_REMINDERS[self.test_event_id] = {"trader_1": "chat_12345"}

        # Simulate check 8 days (1 week + 1 day) later: Wednesday 2026-10-28 at 17:30 UTC
        now_dt = datetime(2026, 10, 28, 17, 30, 0, tzinfo=timezone.utc)
        now_ts = now_dt.timestamp()
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

        # Expected dynamic start_utc is Wednesday 2026-10-28 18:00:00 UTC
        expected_start_utc = int(datetime(2026, 10, 28, 18, 0, 0, tzinfo=timezone.utc).timestamp())
        expected_key = f"{self.test_event_id}:chat_12345:advance_30m:{expected_start_utc}"
        self.assertIn(expected_key, market_events.SENT_REMINDERS)

    async def test_2_recurring_event_dispatched_only_once_per_occurrence(self):
        """2. Validates that each recurring occurrence receives reminder exactly once (FIX-4a)."""
        market_events.EVENT_USER_REMINDERS[self.test_event_id] = {"trader_1": "chat_12345"}
        mock_client = AsyncMock()

        # Occurrence 1: Wednesday 2026-10-28 at 17:30 UTC
        now_dt_1 = datetime(2026, 10, 28, 17, 30, 0, tzinfo=timezone.utc)
        now_ts_1 = now_dt_1.timestamp()

        with patch("app.engine.market_events.send_telegram_alert", new_callable=AsyncMock) as mock_send, \
             patch("app.engine.market_events.TELEGRAM_BOT_TOKEN", "valid_bot_token"):
            # First check -> dispatched
            dispatched_1 = await market_events.check_and_dispatch_30m_advance_reminders(
                client=mock_client, now_ts=now_ts_1
            )
            self.assertEqual(dispatched_1, 1)
            self.assertEqual(mock_send.call_count, 1)

            # Re-check 15 seconds later -> duplicate suppressed
            dispatched_2 = await market_events.check_and_dispatch_30m_advance_reminders(
                client=mock_client, now_ts=now_ts_1 + 15
            )
            self.assertEqual(dispatched_2, 0)
            self.assertEqual(mock_send.call_count, 1)

            # Occurrence 2: Next week Wednesday 2026-11-04 at 17:30 UTC -> dispatched again once
            now_dt_2 = datetime(2026, 11, 4, 17, 30, 0, tzinfo=timezone.utc)
            now_ts_2 = now_dt_2.timestamp()

            dispatched_3 = await market_events.check_and_dispatch_30m_advance_reminders(
                client=mock_client, now_ts=now_ts_2
            )
            self.assertEqual(dispatched_3, 1)
            self.assertEqual(mock_send.call_count, 2)

    async def test_3_invalid_or_vague_time_utc_never_dispatched(self):
        """3. Events with vague or unparseable time_utc (e.g. 'Upcoming Weekend') are never dispatched (FIX-4a)."""
        vague_event_id = "energy_vague_opec"
        vague_event = {
            "id": vague_event_id,
            "category": "energy",
            "market": "Global Energy",
            "title": "OPEC+ Meeting",
            "impact": "high",
            "time_utc": "Upcoming Weekend",
            "symbol": "BRENT"
        }
        market_events.CURATED_HIGH_IMPACT_CATALOG.append(vague_event)
        market_events.EVENT_USER_REMINDERS[vague_event_id] = {"trader_1": "chat_12345"}

        mock_client = AsyncMock()
        now_ts = datetime(2026, 10, 24, 12, 0, 0, tzinfo=timezone.utc).timestamp()

        with patch("app.engine.market_events.send_telegram_alert", new_callable=AsyncMock) as mock_send, \
             patch("app.engine.market_events.TELEGRAM_BOT_TOKEN", "valid_bot_token"):
            dispatched = await market_events.check_and_dispatch_30m_advance_reminders(
                client=mock_client, now_ts=now_ts
            )

        self.assertEqual(dispatched, 0)
        mock_send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
