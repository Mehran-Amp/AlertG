"""
Phase 4C: Chaos Testing & Edge Scenarios for WebSocket & Dual-Channel Delivery.
Tests:
1. Socket broken mid-dispatch: disconnects gracefully and proceeds with FCM delivery.
2. Dual-channel concurrent ACK idempotency: WebSocket ACK + HTTP ACK for the same delivery_id counts exactly once.
3. Reconnection outbox resend: offline user who reconnects receives pending alert on WebSocket resend and clears outbox via WS ACK.
"""
import asyncio
import time
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from server import app
import server
import app.config as config
from app.models import Alert
from app.notifier import outbox, journal
from app.routes.ws import manager
from app.state import METRICS
import app.storage as storage


class TestWebSocketChaosAndEdgeCases:
    """Phase 4C: Chaos, network disconnection, and dual-channel race condition tests."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        orig_outbox = dict(outbox.OUTBOX)
        orig_journal = dict(journal.JOURNAL)
        orig_alerts = list(storage.ALERTS_DB)
        outbox.OUTBOX.clear()
        journal.JOURNAL.clear()
        yield
        outbox.OUTBOX.clear()
        outbox.OUTBOX.update(orig_outbox)
        journal.JOURNAL.clear()
        journal.JOURNAL.update(orig_journal)
        storage.ALERTS_DB.clear()
        storage.ALERTS_DB.extend(orig_alerts)

    def _make_alert(self, alert_id="alt-chaos-1", user_id="chaos_user_1"):
        return Alert(
            id=alert_id,
            user_id=user_id,
            exchange="binance",
            symbol="BTCUSDT",
            target_price=70000.0,
            condition="ABOVE",
            ack_supported=True,
            fcm_token="dummy_token_123456789012345678901234567890123456",
            created_at="2026-01-01T00:00:00Z",
        )

    def test_socket_drop_during_dispatch_proceeds_with_fcm(self, monkeypatch):
        """1. If WebSocket fails mid-send (broken pipe), the socket is disconnected and FCM delivers smoothly."""
        test_key = "chaos_test_key_1"
        user_id = "chaos_user_broken_pipe"
        monkeypatch.setattr(config, "API_KEY", test_key)
        monkeypatch.setattr(server, "API_KEY", test_key)

        alert = self._make_alert("alt-chaos-broken", user_id=user_id)
        storage.ALERTS_DB.append(alert)

        client = TestClient(app)

        with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_fcm:
            mock_fcm.return_value = (True, "OK")

            with client.websocket_connect(f"/ws?api_key={test_key}&user_id={user_id}") as ws:
                assert manager.is_user_connected(user_id)

                # Simulate a broken socket on the active connection
                sockets = manager.get_user_connections(user_id)
                assert len(sockets) == 1
                broken_ws = sockets[0]

                # Mock send_json on this socket to throw a network disconnect exception
                async def _mock_broken_send(_):
                    raise RuntimeError("Broken pipe / connection dropped abruptly")
                broken_ws.send_json = _mock_broken_send

                async def _send():
                    await outbox.enqueue_alert_push(
                        alert=alert,
                        title="Chaos BTC Alert",
                        body="BTC 70k Spike",
                        data_payload={"symbol": "BTCUSDT", "price": "70050"},
                    )
                    await asyncio.sleep(0.05)

                asyncio.run(_send())

                # Broken socket should have been disconnected by manager
                assert not manager.is_user_connected(user_id)

                # FCM delivery must have succeeded despite WebSocket failure
                mock_fcm.assert_called_once()
                assert len(outbox.OUTBOX) == 1

    def test_concurrent_http_and_websocket_ack_idempotency(self, monkeypatch):
        """2. Dual-channel concurrent ACK (HTTP + WS) for same delivery_id increments metric only once."""
        test_key = "chaos_test_key_ack"
        user_id = "chaos_user_concurrent_ack"
        monkeypatch.setattr(config, "API_KEY", test_key)
        monkeypatch.setattr(server, "API_KEY", test_key)

        alert = self._make_alert("alt-chaos-ack", user_id=user_id)
        storage.ALERTS_DB.append(alert)

        initial_fcm_acked = METRICS.get("fcm_acked", 0)
        client = TestClient(app)

        with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_fcm:
            mock_fcm.return_value = (True, "OK")

            with client.websocket_connect(f"/ws?api_key={test_key}&user_id={user_id}") as ws:
                async def _send():
                    await outbox.enqueue_alert_push(
                        alert=alert,
                        title="Concurrent Ack Test",
                        body="Price Alert",
                        data_payload={"symbol": "BTCUSDT"},
                    )
                    await asyncio.sleep(0.05)

                asyncio.run(_send())

                msg = ws.receive_json()
                assert msg.get("type") == "alert"
                delivery_id = msg["delivery_id"]

                # Send WebSocket ACK
                ws.send_json({"action": "ack", "delivery_id": delivery_id})
                ws_ack_resp = ws.receive_json()
                assert ws_ack_resp.get("status") == "acked"

                # Immediately send concurrent HTTP ACK for same delivery_id
                http_resp = client.post(
                    f"/api/deliveries/{delivery_id}/ack",
                    headers={"X-API-Key": test_key},
                )
                assert http_resp.status_code == 200
                assert http_resp.json().get("status") == "acked"

                # Journal must be acked
                assert journal.get_status(delivery_id) == "acked"
                # Metric fcm_acked must have incremented by exactly 1
                assert METRICS.get("fcm_acked", 0) == initial_fcm_acked + 1
                # Outbox must be empty
                assert delivery_id not in outbox.OUTBOX

    def test_reconnecting_user_receives_alert_on_outbox_resend(self, monkeypatch):
        """3. Offline user who reconnects receives pending alert upon outbox resend and can ack via WS."""
        test_key = "chaos_test_key_reconnect"
        user_id = "user_reconnect_test"
        monkeypatch.setattr(config, "API_KEY", test_key)
        monkeypatch.setattr(server, "API_KEY", test_key)

        alert = self._make_alert("alt-chaos-reconn", user_id=user_id)
        storage.ALERTS_DB.append(alert)

        # 1. User is initially offline
        assert not manager.is_user_connected(user_id)

        with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_fcm:
            mock_fcm.return_value = (True, "OK")

            async def _send_initial():
                await outbox.enqueue_alert_push(
                    alert=alert,
                    title="Offline Enqueued Alert",
                    body="Solana break",
                    data_payload={"symbol": "SOLUSDT"},
                )
                await asyncio.sleep(0.05)

            asyncio.run(_send_initial())

            assert len(outbox.OUTBOX) == 1
            delivery_id = list(outbox.OUTBOX.keys())[0]
            entry = outbox.OUTBOX[delivery_id]
            assert entry["phase"] == "awaiting_ack"

            client = TestClient(app)

            # 2. User now reconnects via WebSocket
            with client.websocket_connect(f"/ws?api_key={test_key}&user_id={user_id}") as ws:
                assert manager.is_user_connected(user_id)

                # 3. Trigger outbox redelivery (simulating expiration of initial ack wait)
                async def _resend():
                    await outbox._deliver_outbox_entry(delivery_id)

                asyncio.run(_resend())

                # The reconnected socket receives the redelivered alert
                resend_msg = ws.receive_json()
                assert resend_msg.get("type") == "alert"
                assert resend_msg.get("delivery_id") == delivery_id
                assert resend_msg.get("title") == "Offline Enqueued Alert"

                # 4. User sends ACK over the reconnected WebSocket
                ws.send_json({"action": "ack", "delivery_id": delivery_id})
                ack_resp = ws.receive_json()
                assert ack_resp.get("status") == "acked"

                # Outbox is cleared and journal is marked acked
                assert delivery_id not in outbox.OUTBOX
                assert journal.get_status(delivery_id) == "acked"
