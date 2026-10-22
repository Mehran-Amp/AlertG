import os
import json
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from app.notifier import journal, outbox


class TestDeliveryJournal(unittest.TestCase):
    def setUp(self):
        # Save originals
        self._orig_journal = dict(journal.JOURNAL)
        self._orig_journal_file = journal.JOURNAL_FILE
        self._orig_outbox = dict(outbox.OUTBOX)
        self._orig_outbox_file = outbox.OUTBOX_FILE
        journal.JOURNAL.clear()
        outbox.OUTBOX.clear()
        # Temp files for both journal and outbox
        self._tmp_journal = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp_journal.close()
        self._tmp_outbox = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp_outbox.close()
        journal.JOURNAL_FILE = self._tmp_journal.name
        outbox.OUTBOX_FILE = self._tmp_outbox.name

    def tearDown(self):
        journal.JOURNAL.clear()
        journal.JOURNAL.update(self._orig_journal)
        journal.JOURNAL_FILE = self._orig_journal_file
        outbox.OUTBOX.clear()
        outbox.OUTBOX.update(self._orig_outbox)
        outbox.OUTBOX_FILE = self._orig_outbox_file
        for p in (self._tmp_journal.name, self._tmp_outbox.name):
            try:
                os.remove(p)
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
        self.assertTrue(journal.record_acked("d2"))
        self.assertEqual(journal.get_status("d2"), "acked")

    def test_record_sent_does_not_regress_acked(self):
        journal.record_queued("d3", "alert-3")
        journal.record_acked("d3")
        self.assertEqual(journal.get_status("d3"), "acked")
        journal.record_sent("d3")
        self.assertEqual(journal.get_status("d3"), "acked")

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


class TestOutboxJournalIntegration(unittest.IsolatedAsyncioTestCase):
    """Proves outbox.py actually calls record_queued / record_sent."""

    async def asyncSetUp(self):
        self._orig_journal = dict(journal.JOURNAL)
        self._orig_journal_file = journal.JOURNAL_FILE
        self._orig_outbox = dict(outbox.OUTBOX)
        self._orig_outbox_file = outbox.OUTBOX_FILE
        journal.JOURNAL.clear()
        outbox.OUTBOX.clear()
        self._tmp_journal = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp_journal.close()
        self._tmp_outbox = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp_outbox.close()
        journal.JOURNAL_FILE = self._tmp_journal.name
        outbox.OUTBOX_FILE = self._tmp_outbox.name

    async def asyncTearDown(self):
        journal.JOURNAL.clear()
        journal.JOURNAL.update(self._orig_journal)
        journal.JOURNAL_FILE = self._orig_journal_file
        outbox.OUTBOX.clear()
        outbox.OUTBOX.update(self._orig_outbox)
        outbox.OUTBOX_FILE = self._orig_outbox_file
        for p in (self._tmp_journal.name, self._tmp_outbox.name):
            try:
                os.remove(p)
            except Exception:
                pass

    def _make_alert(self, alert_id="alert-x", token="fcm_token_1234567890123456789012345678901234567890"):
        class _A:
            pass
        a = _A()
        a.id = alert_id
        a.fcm_token = token
        return a

    async def test_enqueue_creates_queued_entry_with_delivery_id(self):
        alert = self._make_alert()
        with patch.object(outbox, "_save_outbox", new_callable=AsyncMock):
            await outbox.enqueue_alert_push(alert, "Title", "Body", {})
        # One outbox entry, one journal entry
        self.assertEqual(len(outbox.OUTBOX), 1)
        eid = next(iter(outbox.OUTBOX.keys()))
        self.assertEqual(journal.get_status(eid), "queued")
        entry = outbox.OUTBOX[eid]
        self.assertEqual(entry["data"]["delivery_id"], eid)

    async def test_fcm_success_marks_sent(self):
        alert = self._make_alert()
        with patch.object(outbox, "_save_outbox", new_callable=AsyncMock), \
             patch.object(outbox, "send_fcm_notification_async", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = (True, "FCM Message ID: test")
            await outbox.enqueue_alert_push(alert, "Title", "Body", {})
            # Wait for the spawned delivery task to finish (it's in _BG_TASKS)
            for _ in range(50):
                await __import__("asyncio").sleep(0.05)
                if not outbox.OUTBOX:
                    break
        # The entry should be removed from OUTBOX (delivered) and journal = sent
        self.assertEqual(len(outbox.OUTBOX), 0)
        states = [v.get("state") for v in journal.JOURNAL.values()]
        self.assertIn("sent", states)


if __name__ == "__main__":
    unittest.main()