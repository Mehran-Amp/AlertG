"""
Phase 5A-1: Server delivery chaos suite covering mock scenarios.

Scenarios tested:
1. FCM down and recovery: FCM raises 5xx / connection error, outbox retains entry for resend,
   succeeds once FCM is restored.
2. Dead FCM token & token replacement: FCM returns unregistered/invalid token error,
   alert update replaces token, next cycle delivers to new token.
3. Server restart mid-ack: Restarting (reloading outbox/journal from disk) while waiting for ACK
   preserves state without losing pending deliveries.
4. Duplicate ACK and ACK before sent: Duplicate ACK is idempotent; out-of-order ACK before dispatch
   is handled safely without regressing status.
5. Corrupt journal file: When journal JSON is unparseable/corrupted, system recovers gracefully
   (keeps .bad backup) without fatal crash.
6. Disk full: Disk write fails (OSError ENOSPC), but in-memory delivery/dispatch continues cleanly.
"""
import errno
import json
import os
import tempfile
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import app.config as config
from app.models import Alert
from app.notifier import fcm, journal, outbox
from app.state import METRICS
import app.storage as storage
import server
from server import app


class TestChaosDeliverySuite:
    """Suite 5A-1: Delivery chaos & resilience tests."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self, tmp_path):
        # Backup original memory state
        self.orig_outbox = dict(outbox.OUTBOX)
        self.orig_journal = dict(journal.JOURNAL)
        self.orig_alerts = list(storage.ALERTS_DB)
        self.orig_dead_tokens = set(outbox.DEAD_TOKENS)
        self.orig_latencies = list(journal.ACK_LATENCIES)
        self.orig_metrics = dict(METRICS)

        # Backup file paths
        self.orig_outbox_file = outbox.OUTBOX_FILE
        self.orig_journal_file = journal.JOURNAL_FILE

        # Isolated temp files for test persistence
        self.tmp_outbox_file = str(tmp_path / "fcm_outbox.json")
        self.tmp_journal_file = str(tmp_path / "delivery_journal.json")
        outbox.OUTBOX_FILE = self.tmp_outbox_file
        journal.JOURNAL_FILE = self.tmp_journal_file

        # Clean state
        outbox.OUTBOX.clear()
        journal.JOURNAL.clear()
        outbox.DEAD_TOKENS.clear()
        journal.ACK_LATENCIES.clear()

        # Set API key for client tests
        self.api_key = "chaos_api_key_5a1"
        self.orig_api_key = config.API_KEY
        self.orig_server_key = server.API_KEY
        config.API_KEY = self.api_key
        server.API_KEY = self.api_key

        yield

        # Restore everything
        outbox.OUTBOX.clear()
        outbox.OUTBOX.update(self.orig_outbox)
        journal.JOURNAL.clear()
        journal.JOURNAL.update(self.orig_journal)
        storage.ALERTS_DB.clear()
        storage.ALERTS_DB.extend(self.orig_alerts)
        outbox.DEAD_TOKENS.clear()
        outbox.DEAD_TOKENS.update(self.orig_dead_tokens)
        journal.ACK_LATENCIES.clear()
        journal.ACK_LATENCIES.extend(self.orig_latencies)
        METRICS.clear()
        METRICS.update(self.orig_metrics)

        outbox.OUTBOX_FILE = self.orig_outbox_file
        journal.JOURNAL_FILE = self.orig_journal_file
        config.API_KEY = self.orig_api_key
        server.API_KEY = self.orig_server_key

    def _make_alert(
        self,
        alert_id="alt-chaos-1",
        user_id="user_chaos_1",
        fcm_token="valid_fcm_token_1234567890123456789012345678901234567890",
        ack_supported=True,
    ) -> Alert:
        return Alert(
            id=alert_id,
            user_id=user_id,
            exchange="binance",
            symbol="BTCUSDT",
            target_price=68000.0,
            condition="ABOVE",
            ack_supported=ack_supported,
            fcm_token=fcm_token,
            created_at="2026-01-01T00:00:00Z",
        )

    def _auth_headers(self):
        return {"X-API-Key": self.api_key}

    # --------------------------------------------------------------------------
    # Scenario 1: FCM down and recovery
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_fcm_down_and_recovery(self):
        """1. FCM raises 5xx / FIREBASE_UNAVAILABLE; outbox retains entry and retries.

        Once FCM recovers, delivery succeeds and advances to awaiting_ack.
        """
        alert = self._make_alert("alt-fcm-down", user_id="user-down")
        storage.ALERTS_DB.append(alert)

        with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_send:
            # First attempt: FCM is unavailable (5xx / network error)
            mock_send.return_value = (False, "FIREBASE_UNAVAILABLE")

            await outbox.enqueue_alert_push(
                alert=alert,
                title="Chaos Alert: Price High",
                body="BTC > 68000",
                data_payload={"symbol": "BTCUSDT", "price": "68100"},
            )

            # Wait briefly for background dispatch task
            for _ in range(20):
                await __import__("asyncio").sleep(0.02)
                if len(outbox.OUTBOX) == 1 and next(iter(outbox.OUTBOX.values())).get("attempts", 0) > 0:
                    break

            assert len(outbox.OUTBOX) == 1
            eid = next(iter(outbox.OUTBOX.keys()))
            entry = outbox.OUTBOX[eid]

            assert entry["attempts"] >= 1
            assert "FIREBASE_UNAVAILABLE" in entry["last_error"]
            assert entry.get("phase") != "awaiting_ack"
            assert journal.get_status(eid) == "queued"

            # Second attempt: FCM service recovers
            mock_send.return_value = (True, "projects/chaos/messages/recovered-msg-999")

            # Force next attempt time to past and deliver entry
            entry["next_attempt_at"] = time.time() - 1
            entry["next_retry_at"] = time.time() - 1
            await outbox._deliver_outbox_entry(eid)

            # Should now succeed and transition to awaiting_ack (because ack_supported=True)
            assert eid in outbox.OUTBOX
            assert outbox.OUTBOX[eid]["phase"] == "awaiting_ack"
            assert journal.get_status(eid) == "sent"

    # --------------------------------------------------------------------------
    # Scenario 2: Dead FCM token & token replacement
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_dead_fcm_token_and_token_replacement(self):
        """2. Dead token triggers blocked_token & DEAD_TOKENS.

        Skipped on next delivery attempts until alert token is replaced.
        """
        dead_token = "dead_token_unregistered_999999999999999999999999"
        fresh_token = "fresh_new_token_8888888888888888888888888888888"
        alert = self._make_alert("alt-dead-tok", user_id="user-dead", fcm_token=dead_token)
        storage.ALERTS_DB.append(alert)

        with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_send:
            # FCM returns UNREGISTERED
            mock_send.return_value = (False, "UNREGISTERED")

            await outbox.enqueue_alert_push(
                alert=alert,
                title="Dead Token Test",
                body="Testing dead token handling",
                data_payload={},
            )

            for _ in range(20):
                await __import__("asyncio").sleep(0.02)
                if len(outbox.OUTBOX) == 1 and next(iter(outbox.OUTBOX.values())).get("blocked_token"):
                    break

            eid = next(iter(outbox.OUTBOX.keys()))
            entry = outbox.OUTBOX[eid]

            assert dead_token in outbox.DEAD_TOKENS
            assert entry["blocked_token"] == dead_token
            assert mock_send.call_count == 1

            # Another delivery attempt with the same dead token must skip FCM call
            mock_send.reset_mock()
            entry["next_attempt_at"] = time.time() - 1
            await outbox._deliver_outbox_entry(eid)
            # FCM should NOT have been called
            mock_send.assert_not_called()
            assert entry["blocked_token"] == dead_token

            # Token replacement: app updates FCM token for this alert
            alert.fcm_token = fresh_token
            mock_send.return_value = (True, "projects/chaos/messages/token-rotated-ok")

            outbox.on_alert_token_updated(alert.id, fresh_token)

            for _ in range(20):
                await __import__("asyncio").sleep(0.02)
                if outbox.OUTBOX[eid].get("phase") == "awaiting_ack":
                    break

            # Now delivered using fresh token!
            mock_send.assert_called_once()
            called_token = mock_send.call_args.kwargs.get("fcm_token")
            assert called_token == fresh_token
            assert outbox.OUTBOX[eid]["blocked_token"] is None
            assert outbox.OUTBOX[eid]["phase"] == "awaiting_ack"
            assert journal.get_status(eid) == "sent"

    # --------------------------------------------------------------------------
    # Scenario 3: Server restart mid-ack
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_server_restart_mid_ack(self):
        """3. Server restart (reload outbox & journal from disk) mid-ack preserves state.

        Arriving ACK then successfully confirms delivery and removes outbox entry.
        """
        alert = self._make_alert("alt-mid-ack", user_id="user-mid")
        storage.ALERTS_DB.append(alert)

        with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = (True, "msg-mid-ack")

            await outbox.enqueue_alert_push(
                alert=alert,
                title="Restart Mid-Ack",
                body="Testing persistence across restart",
                data_payload={},
            )

            for _ in range(20):
                await __import__("asyncio").sleep(0.02)
                if len(outbox.OUTBOX) == 1 and next(iter(outbox.OUTBOX.values())).get("phase") == "awaiting_ack":
                    break

            eid = next(iter(outbox.OUTBOX.keys()))
            assert outbox.OUTBOX[eid]["phase"] == "awaiting_ack"
            assert journal.get_status(eid) == "sent"

            # Ensure data was flushed to disk
            await outbox._save_outbox()
            journal._save_journal()

            assert os.path.exists(self.tmp_outbox_file)
            assert os.path.exists(self.tmp_journal_file)

            # SIMULATE SERVER RESTART: clear memory and re-load from disk
            outbox.OUTBOX.clear()
            journal.JOURNAL.clear()
            assert len(outbox.OUTBOX) == 0
            assert len(journal.JOURNAL) == 0

            # Reload from disk
            reloaded_outbox = outbox._load_outbox_from_disk()
            reloaded_journal = journal._load_journal_from_disk()
            outbox.OUTBOX.update(reloaded_outbox)
            journal.JOURNAL.update(reloaded_journal)

            assert eid in outbox.OUTBOX
            assert outbox.OUTBOX[eid]["phase"] == "awaiting_ack"
            assert eid in journal.JOURNAL
            assert journal.get_status(eid) == "sent"

            # Now the client's ACK arrives via HTTP endpoint post-restart
            client = TestClient(app)
            res = client.post(f"/api/deliveries/{eid}/ack", headers=self._auth_headers())
            assert res.status_code == 200
            assert res.json()["status"] == "acked"

            # Post-restart state is completely fulfilled
            assert journal.get_status(eid) == "acked"
            assert eid not in outbox.OUTBOX

    # --------------------------------------------------------------------------
    # Scenario 4: Duplicate ACK and ACK before sent
    # --------------------------------------------------------------------------
    def test_duplicate_ack_and_ack_before_sent(self):
        """4. Duplicate ACK is idempotent and metrics increment once.

        ACK before sent does not regress to sent when record_sent arrives.
        """
        client = TestClient(app)

        # 4a. Duplicate ACK idempotency
        d_dup = "delivery-dup-chaos-4a"
        journal.record_queued(d_dup, "alt-dup")
        journal.record_sent(d_dup)

        initial_acked_metric = METRICS.get("fcm_acked", 0)

        # Repeated 3 times
        for _ in range(3):
            res = client.post(f"/api/deliveries/{d_dup}/ack", headers=self._auth_headers())
            assert res.status_code == 200
            assert res.json()["status"] == "acked"

        assert journal.get_status(d_dup) == "acked"
        # Metric fcm_acked must have incremented by exactly 1
        assert METRICS.get("fcm_acked", 0) == initial_acked_metric + 1

        # 4b. Out-of-order ACK arriving before FCM dispatch callback (record_sent)
        d_early = "delivery-early-chaos-4b"
        journal.record_queued(d_early, "alt-early")
        assert journal.get_status(d_early) == "queued"

        # Client acks immediately (e.g. fast WebSocket arrival before FCM callback)
        res_early = client.post(f"/api/deliveries/{d_early}/ack", headers=self._auth_headers())
        assert res_early.status_code == 200
        assert res_early.json()["status"] == "acked"
        assert journal.get_status(d_early) == "acked"

        # FCM callback completes afterwards and calls record_sent:
        journal.record_sent(d_early)

        # Status must NOT regress to 'sent'; it must stay 'acked'
        assert journal.get_status(d_early) == "acked"

    # --------------------------------------------------------------------------
    # Scenario 5: Corrupt journal file
    # --------------------------------------------------------------------------
    def test_corrupt_journal_file_recovery(self):
        """5. Unparseable/corrupted journal JSON recovers gracefully without crashing.

        Keeps a .bad copy and re-initializes cleanly.
        """
        # Create a corrupt journal file on disk
        with open(self.tmp_journal_file, "w", encoding="utf-8") as f:
            f.write("{invalid_json: true, unexpected_token <<<>>>}")

        # Loading from disk should not raise an exception
        recovered_data = journal._load_journal_from_disk()
        assert isinstance(recovered_data, dict)
        assert len(recovered_data) == 0

        # A .bad copy should be preserved for post-mortem forensics
        bad_file = self.tmp_journal_file + ".bad"
        assert os.path.exists(bad_file)
        with open(bad_file, "r", encoding="utf-8") as bf:
            assert "unexpected_token" in bf.read()

        # Subsequent writes operate smoothly and write valid JSON
        journal.JOURNAL.clear()
        journal.record_queued("d-corrupt-recover", "alt-recover")
        assert os.path.exists(self.tmp_journal_file)
        with open(self.tmp_journal_file, "r", encoding="utf-8") as jf:
            persisted = json.load(jf)
            assert "d-corrupt-recover" in persisted
            assert persisted["d-corrupt-recover"]["state"] == "queued"

    # --------------------------------------------------------------------------
    # Scenario 6: Disk full
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_disk_full_resilience(self):
        """6. Disk write failures (ENOSPC / disk full) are handled cleanly.

        In-memory delivery and state management proceed without fatal crashes.
        """
        alert = self._make_alert("alt-disk-full", user_id="user-disk-full")
        storage.ALERTS_DB.append(alert)

        def mock_failing_write(*args, **kwargs):
            raise OSError(errno.ENOSPC, "No space left on device")

        with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_send, \
             patch("builtins.open", side_effect=mock_failing_write):
            mock_send.return_value = (True, "msg-disk-full")

            # Enqueue push: journal and outbox disk writes will fail with ENOSPC
            # but must not raise an unhandled exception or abort the workflow
            await outbox.enqueue_alert_push(
                alert=alert,
                title="Disk Full Chaos",
                body="Disk writes are failing",
                data_payload={"symbol": "BTCUSDT"},
            )

            for _ in range(20):
                await __import__("asyncio").sleep(0.02)
                if len(outbox.OUTBOX) == 1 and next(iter(outbox.OUTBOX.values())).get("phase") == "awaiting_ack":
                    break

            assert len(outbox.OUTBOX) == 1
            eid = next(iter(outbox.OUTBOX.keys()))

            # In-memory delivery state is fully updated despite disk error
            assert outbox.OUTBOX[eid]["phase"] == "awaiting_ack"
            assert journal.get_status(eid) == "sent"

            # ACK also succeeds in-memory despite failing disk write
            client = TestClient(app)
            res = client.post(f"/api/deliveries/{eid}/ack", headers=self._auth_headers())
            assert res.status_code == 200
            assert res.json()["status"] == "acked"
            assert eid not in outbox.OUTBOX
            assert journal.get_status(eid) == "acked"
