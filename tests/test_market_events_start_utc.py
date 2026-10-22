import unittest
from datetime import datetime, timezone
from app.engine.calendar import parse_event_start_utc
from app.engine.market_events import get_market_events, CURATED_HIGH_IMPACT_CATALOG


class TestMarketEventsStartUtc(unittest.TestCase):
    def test_timezone_conversion_to_start_utc(self):
        """1. Validates accurate conversion of ISO and weekday UTC schedules into epoch seconds (Phase 2B-1)."""
        # Test 1a: ISO 8601 UTC string
        iso_str = "2026-10-28 18:00 UTC"
        epoch = parse_event_start_utc(iso_str)
        self.assertIsInstance(epoch, int)
        expected_dt = datetime(2026, 10, 28, 18, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(epoch, int(expected_dt.timestamp()))

        # Test 1b: Recurring weekday schedule relative to a fixed UTC reference datetime
        # 2026-10-27 is a Tuesday. The next Wednesday is 2026-10-28 18:00:00 UTC.
        ref_tuesday = datetime(2026, 10, 27, 10, 0, 0, tzinfo=timezone.utc)
        epoch_wd = parse_event_start_utc("Wednesday 18:00 UTC", now_dt=ref_tuesday)
        self.assertIsInstance(epoch_wd, int)
        self.assertEqual(epoch_wd, int(datetime(2026, 10, 28, 18, 0, 0, tzinfo=timezone.utc).timestamp()))

    def test_invalid_or_vague_time_returns_none(self):
        """2. Validates that vague ('Upcoming Weekend') or invalid times return None without guessing (Phase 2B-1)."""
        self.assertIsNone(parse_event_start_utc("Upcoming Weekend"))
        self.assertIsNone(parse_event_start_utc("TBD / Unannounced"))
        self.assertIsNone(parse_event_start_utc(""))
        self.assertIsNone(parse_event_start_utc(None))
        self.assertIsNone(parse_event_start_utc("Someday 12:00 UTC"))

    def test_events_contain_start_utc_and_preserve_all_existing_fields(self):
        """3. Validates every market event exposes start_utc while preserving all existing string fields intact (Phase 2B-1)."""
        events = get_market_events()
        self.assertGreater(len(events), 0)

        expected_fields = [
            "id", "category", "market", "title",
            "summary", "impact", "time_utc", "badge_color", "symbol"
        ]

        for ev in events:
            # 1. start_utc must be present in every event
            self.assertIn("start_utc", ev)
            self.assertTrue(ev["start_utc"] is None or isinstance(ev["start_utc"], int))

            # 2. All legacy/display fields must be preserved and untouched
            for field in expected_fields:
                self.assertIn(field, ev, f"Missing original field '{field}' in event {ev.get('id')}")
                self.assertIsInstance(ev[field], str)

        # 3. Specifically verify 'energy_opec_meeting' has start_utc = None
        opec = next((e for e in events if e.get("id") == "energy_opec_meeting"), None)
        self.assertIsNotNone(opec)
        self.assertIsNone(opec["start_utc"])

        # 4. Specifically verify scheduled event 'macro_fomc_rate' has an integer epoch
        fomc = next((e for e in events if e.get("id") == "macro_fomc_rate"), None)
        self.assertIsNotNone(fomc)
        self.assertIsInstance(fomc["start_utc"], int)


if __name__ == "__main__":
    unittest.main()
