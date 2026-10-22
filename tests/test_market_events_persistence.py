import os
import json
import time
import tempfile
import unittest
from app.engine import market_events


class TestMarketEventsPersistence(unittest.TestCase):
    def setUp(self):
        self._orig_state_file = market_events.EVENTS_STATE_FILE
        self._orig_sent = dict(market_events.SENT_REMINDERS)
        self._orig_user = dict(market_events.EVENT_USER_REMINDERS)

        self._tmp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp_file.close()
        market_events.EVENTS_STATE_FILE = self._tmp_file.name
        market_events.SENT_REMINDERS.clear()
        market_events.EVENT_USER_REMINDERS.clear()

    def tearDown(self):
        market_events.EVENTS_STATE_FILE = self._orig_state_file
        market_events.SENT_REMINDERS.clear()
        market_events.SENT_REMINDERS.update(self._orig_sent)
        market_events.EVENT_USER_REMINDERS.clear()
        market_events.EVENT_USER_REMINDERS.update(self._orig_user)

        for p in (self._tmp_file.name, self._tmp_file.name + ".bad", self._tmp_file.name + ".tmp"):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass

    def test_save_and_load_persists_state_and_prunes_older_than_7_days(self):
        """1. Validates atomic save/load for reminders & registrations, and 7-day TTL pruning (Phase 2B-2)."""
        now = time.time()
        fresh_key = "macro_fomc_rate:chat_111:advance_30m"
        stale_key = "macro_cpi_inflation:chat_222:advance_30m"

        # Fresh reminder: 2 hours ago
        market_events.SENT_REMINDERS[fresh_key] = now - 7200
        # Stale reminder: 8 days ago (older than 7 days)
        market_events.SENT_REMINDERS[stale_key] = now - (8 * 86400)

        # User reminder registration
        market_events.EVENT_USER_REMINDERS["macro_fomc_rate"] = {"u_alice": "chat_111"}

        # Save to disk
        market_events.save_events_state()

        # Clear in-memory dicts
        market_events.SENT_REMINDERS.clear()
        market_events.EVENT_USER_REMINDERS.clear()

        # Reload from disk
        loaded_sent, loaded_user = market_events._load_events_state()

        # Fresh key restored, stale key pruned
        self.assertIn(fresh_key, loaded_sent)
        self.assertNotIn(stale_key, loaded_sent)

        # User registration restored
        self.assertIn("macro_fomc_rate", loaded_user)
        self.assertEqual(loaded_user["macro_fomc_rate"].get("u_alice"), "chat_111")

    def test_corrupted_file_does_not_crash_and_renames_to_bad(self):
        """2. Validates corrupted state file creates .bad copy and starts fresh without crash (Phase 2B-2)."""
        # Write corrupted content
        with open(market_events.EVENTS_STATE_FILE, "w", encoding="utf-8") as f:
            f.write("{ invalid json corrupted content [[[")

        # Load must not throw
        loaded_sent, loaded_user = market_events._load_events_state()

        # Clean fallback state
        self.assertEqual(loaded_sent, {})
        self.assertEqual(loaded_user, {})

        # Corrupt file renamed to .bad
        bad_file = market_events.EVENTS_STATE_FILE + ".bad"
        self.assertTrue(os.path.exists(bad_file))


if __name__ == "__main__":
    unittest.main()
