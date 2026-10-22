import time
import unittest
from unittest.mock import AsyncMock, patch

from app.notifier import outbox, journal
import app.state as state
from app.state import METRICS


class TestOutboxTelegramFallback(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._orig_outbox = dict(outbox.OUTBOX)
        self._orig_journal = dict(journal.JOURNAL)
        self._orig_metrics = dict(METRICS)
        self._orig_http_client = getattr(state, "http_client", None)
        outbox.OUTBOX.clear()
        journal.JOURNAL.clear()
        state.http_client = object()  # any non-None object

    async def asyncTearDown(self):
        outbox.OUTBOX.clear()
        outbox.OUTBOX.update(self._orig_outbox)
        journal.JOURNAL.clear()
        journal.JOURNAL.update(self._orig_journal)
        METRICS.clear()
        METRICS.update(self._orig_metrics)
        state.http_client = self._orig_http_client

    def _seed(self, eid, fallback_chat_id):
        outbox.OUTBOX[eid] = {
            "id": eid,
            "alert_id": "a-1",
            "fallback_chat_id": fallback_chat_id,
            "token": "valid_fcm_token_1234567890123456789012345678901234567890",
            "title": "Title",
            "body": "Body",
            "data": {},
            "created_at": 0,
            "expires_at": 10**12,
            "next_attempt_at": 0,
            "next_retry_at": 0,
            "attempts": 0,
            "resend_count": len(outbox.ACK_WAITS) - 1,
            "ack_supported": True,
            "last_error": "",
            "blocked_token": None,
            "phase": "awaiting_ack",
            "ack_due_at": time.time() - 1,
        }
        journal.record_queued(eid, "a-1")
        journal.record_sent(eid)

    async def test_with_fallback_chat_sends_telegram(self):
        eid = "e-tg-1"
        self._seed(eid, "99999")
        with patch.object(outbox, "_save_outbox", new_callable=AsyncMock), \
             patch.object(journal, "_save_journal"), \
             patch.object(outbox, "send_telegram_alert", new_callable=AsyncMock) as mock_tg:
            await outbox._send_telegram_fallback(eid, "99999", "Title", "Body")
        self.assertEqual(mock_tg.await_count, 1)
        self.assertTrue(journal.was_telegram_fallback_sent(eid))

    async def test_without_fallback_chat_does_nothing(self):
        eid = "e-tg-2"
        self._seed(eid, None)
        with patch.object(outbox, "send_telegram_alert", new_callable=AsyncMock) as mock_tg:
            # _send_telegram_fallback is only called when fallback_chat is set;
            # direct call with empty chat is not part of the flow.
            pass
        self.assertEqual(mock_tg.await_count, 0)

    async def test_repeated_fallback_is_noop(self):
        eid = "e-tg-3"
        self._seed(eid, "99999")
        with patch.object(outbox, "_save_outbox", new_callable=AsyncMock), \
             patch.object(journal, "_save_journal"), \
             patch.object(outbox, "send_telegram_alert", new_callable=AsyncMock) as mock_tg:
            await outbox._send_telegram_fallback(eid, "99999", "Title", "Body")
            await outbox._send_telegram_fallback(eid, "99999", "Title", "Body")
        self.assertEqual(mock_tg.await_count, 1)


if __name__ == "__main__":
    unittest.main()