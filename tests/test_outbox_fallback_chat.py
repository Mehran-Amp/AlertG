import unittest
from unittest.mock import AsyncMock, patch

from app.notifier import outbox, journal
from app.models import Alert


class TestOutboxFallbackChat(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._orig_outbox = dict(outbox.OUTBOX)
        self._orig_journal = dict(journal.JOURNAL)
        outbox.OUTBOX.clear()
        journal.JOURNAL.clear()

    async def asyncTearDown(self):
        outbox.OUTBOX.clear()
        outbox.OUTBOX.update(self._orig_outbox)
        journal.JOURNAL.clear()
        journal.JOURNAL.update(self._orig_journal)

    def _make_alert(self):
        return Alert(
            id="alert-fb",
            user_id="u",
            exchange="binance",
            symbol="BTCUSDT",
            target_price=1.0,
            condition="ABOVE",
            ack_supported=False,
            fcm_token="valid_fcm_token_1234567890123456789012345678901234567890",
            created_at="2026-01-01T00:00:00Z",
        )

    async def test_with_fallback_chat_id(self):
        alert = self._make_alert()
        def _close_coro(coro):
            coro.close()
            return None

        with patch.object(outbox, "_save_outbox", new_callable=AsyncMock), \
             patch.object(outbox, "_spawn", side_effect=_close_coro):
            await outbox.enqueue_alert_push(
                alert, "T", "B", {}, fallback_chat_id="123456"
            )
        eid = next(iter(outbox.OUTBOX.keys()))
        self.assertEqual(outbox.OUTBOX[eid].get("fallback_chat_id"), "123456")

    async def test_without_fallback_chat_id(self):
        alert = self._make_alert()
        def _close_coro(coro):
            coro.close()
            return None

        with patch.object(outbox, "_save_outbox", new_callable=AsyncMock), \
             patch.object(outbox, "_spawn", side_effect=_close_coro):
            await outbox.enqueue_alert_push(alert, "T", "B", {})
        eid = next(iter(outbox.OUTBOX.keys()))
        self.assertIsNone(outbox.OUTBOX[eid].get("fallback_chat_id"))


if __name__ == "__main__":
    unittest.main()