import os
import json
import tempfile
import unittest
from unittest.mock import patch

from app.notifier import journal


class TestDeliveryJournal(unittest.TestCase):
    def setUp(self):
        self._orig_journal = dict(journal.JOURNAL)
        journal.JOURNAL.clear()
        self._tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp.close()
        self._orig_file = journal.JOURNAL_FILE
        journal.JOURNAL_FILE = self._tmp.name

    def tearDown(self):
        journal.JOURNAL.clear()
        journal.JOURNAL.update(self._orig_journal)
        journal.JOURNAL_FILE = self._orig_file
        try:
            os.remove(self._tmp.name)
        except Exception:
            pass

    def test_record_queued_and_sent(self):
        journal.record_queued("d1", "alert-1")
        self.assertEqual(journal.get_status("d1"), "queued")
        journal.record_sent("d1")
        self.assertEqual(journal.get_status("d1"), "sent")

    def test_record_acked_unknown_and_idempotent(self):
        self.assertFalse(journal.record_acked("nope"))
        journal.record_queued("d2", "alert-2")
        self.assertTrue(journal.record_acked("d2"))
        self.assertEqual(journal.get_status("d2"), "acked")
        # second ack is idempotent
        self.assertTrue(journal.record_acked("d2"))
        self.assertEqual(journal.get_status("d2"), "acked")

    def test_old_entries_dropped_on_load(self):
        now = 1_000_000.0
        with open(journal.JOURNAL_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "old": {"alert_id": "a", "state": "queued", "queued_at": now - 25 * 3600},
                "new": {"alert_id": "b", "state": "queued", "queued_at": now},
            }, f)
        with patch.object(journal, "time", type("T", (), {"time": staticmethod(lambda: now)})):
            loaded = journal._load_journal_from_disk()
        self.assertNotIn("old", loaded)
        self.assertIn("new", loaded)


if __name__ == "__main__":
    unittest.main()