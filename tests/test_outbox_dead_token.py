"""FIX-DEAD-TOKEN: blocked token must:
1. after total ack_waits, record_unacked once + Telegram once, entry stays.
2. when a new token arrives, resend and ack -> acked.
"""
import time
import pytest


class TestDeadToken:
    @pytest.mark.asyncio
    async def test_blocked_budget_exhausted_marks_unacked_once(self, monkeypatch):
        from app.notifier import outbox, journal
        from app.state import METRICS

        # Stub _send_telegram_fallback to count calls
        calls = []
        async def fake_tg(eid, chat_id, title, body):
            calls.append(eid)
        monkeypatch.setattr(outbox, "_send_telegram_fallback", fake_tg)

        eid = "test_dead_token_1"
        now = time.time()
        outbox.OUTBOX[eid] = {
            "id": eid,
            "alert_id": "alert_1",
            "user_id": "u1",
            "fallback_chat_id": "123456789",
            "token": "x" * 60,
            "title": "T",
            "body": "B",
            "data": {},
            "created_at": now,
            "expires_at": now + 86400,
            "next_attempt_at": now,
            "next_retry_at": now,
            "attempts": 0,
            "resend_count": 0,
            "ack_supported": True,
            "ack_waits": (45, 90, 180),
            "last_error": "",
            "blocked_token": "x" * 60,  # already blocked
            "blocked_at": now - 400,  # 400s > sum(waits) = 315
        }
        journal.record_queued(eid, "alert_1")
        # Call _deliver_outbox_entry
        await outbox._deliver_outbox_entry(eid)
        # Should have recorded unacked exactly once
        assert journal.get_status(eid) == "unacked"
        assert len(calls) == 1
        # Entry must still be in OUTBOX
        assert eid in outbox.OUTBOX
        assert outbox.OUTBOX[eid]["unacked_recorded"] is True

    @pytest.mark.asyncio
    async def test_new_token_after_unacked_resumes(self, monkeypatch):
        from app.notifier import outbox, journal
        from app.state import METRICS

        # Stub FCM to succeed
        async def fake_send(**kwargs):
            return True, "MOCK_OK"
        monkeypatch.setattr(outbox, "send_fcm_notification_async", fake_send)

        eid = "test_dead_token_2"
        now = time.time()
        outbox.OUTBOX[eid] = {
            "id": eid,
            "alert_id": "alert_2",
            "user_id": "u2",
            "fallback_chat_id": None,
            "token": "old" + "x" * 57,
            "title": "T",
            "body": "B",
            "data": {},
            "created_at": now,
            "expires_at": now + 86400,
            "next_attempt_at": now,
            "next_retry_at": now,
            "attempts": 0,
            "resend_count": 0,
            "ack_supported": True,
            "ack_waits": (45, 90, 180),
            "last_error": "",
            "blocked_token": "old" + "x" * 57,
            "blocked_at": now - 400,
            "unacked_recorded": True,
        }
        journal.record_queued(eid, "alert_2")
        journal.record_unacked(eid)  # already unacked

        # Simulate token rotation: new token
        new_token = "new" + "y" * 57
        outbox.on_alert_token_updated("alert_2", new_token)
        # Entry should have blocked_token cleared
        assert outbox.OUTBOX[eid]["blocked_token"] is None
        assert outbox.OUTBOX[eid]["unacked_recorded"] is False