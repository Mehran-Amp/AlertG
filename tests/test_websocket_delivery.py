"""
Phase 4A-2: Tests for alert dispatch over WebSocket and ACK reception over WebSocket.
"""
import asyncio
import time
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from server import app
import server
import app.config as config
from app.models import Alert
from app.notifier import outbox, journal
from app.routes.ws import manager
import app.storage as storage


class TestWebSocketAlertDeliveryAndAck:
    """4A-2 / test 1 & 2: Alert dispatched over WebSocket to connected user with matching delivery_id, and ACK processed."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        orig_outbox = dict(outbox.OUTBOX)
        orig_journal = dict(journal.JOURNAL)
        outbox.OUTBOX.clear()
        journal.JOURNAL.clear()
        yield
        outbox.OUTBOX.clear()
        outbox.OUTBOX.update(orig_outbox)
        journal.JOURNAL.clear()
        journal.JOURNAL.update(orig_journal)

    def _make_alert(self, alert_id="alt-ws-1", user_id="ws_user_1"):
        return Alert(
            id=alert_id,
            user_id=user_id,
            exchange="binance",
            symbol="BTCUSDT",
            target_price=68000.0,
            condition="ABOVE",
            ack_supported=True,
            fcm_token="dummy_token_123456789012345678901234567890123456",
            created_at="2026-01-01T00:00:00Z",
        )

    def test_connected_user_receives_alert_over_websocket(self, monkeypatch):
        """1. When user is connected on WebSocket, alert is pushed over socket with identical delivery_id while FCM still sends."""
        test_key = "ws_test_key_delivery"
        user_id = "ws_user_1"
        monkeypatch.setattr(config, "API_KEY", test_key)
        monkeypatch.setattr(server, "API_KEY", test_key)

        alert = self._make_alert("alt-ws-1", user_id=user_id)
        storage.ALERTS_DB.append(alert)

        client = TestClient(app)

        with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_fcm:
            mock_fcm.return_value = (True, "OK")

            with client.websocket_connect(f"/ws?api_key={test_key}&user_id={user_id}") as ws:
                assert manager.is_user_connected(user_id)

                # Enqueue alert push (triggers immediate _deliver_outbox_entry)
                asyncio.run(outbox.enqueue_alert_push(
                    alert=alert,
                    title="BTC Target Hit",
                    body="BTC hit 68,000",
                    data_payload={"symbol": "BTCUSDT", "price": "68000"},
                ))

                # Receive message on WebSocket
                msg = ws.receive_json()
                assert msg.get("type") == "alert"
                assert msg.get("title") == "BTC Target Hit"
                delivery_id = msg.get("delivery_id")
                assert delivery_id is not None
                assert delivery_id in journal.JOURNAL

                # FCM was also called
                mock_fcm.assert_called_once()

    def test_ack_over_websocket_records_journal_and_clears_outbox(self, monkeypatch):
        """2. Sending ACK over WebSocket records ack in journal and clears the outbox entry."""
        test_key = "ws_test_key_delivery"
        user_id = "ws_user_ack"
        monkeypatch.setattr(config, "API_KEY", test_key)
        monkeypatch.setattr(server, "API_KEY", test_key)

        alert = self._make_alert("alt-ws-ack", user_id=user_id)
        storage.ALERTS_DB.append(alert)

        client = TestClient(app)

        with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_fcm:
            mock_fcm.return_value = (True, "OK")

            with client.websocket_connect(f"/ws?api_key={test_key}&user_id={user_id}") as ws:
                asyncio.run(outbox.enqueue_alert_push(
                    alert=alert,
                    title="ETH Breakout",
                    body="ETH above 3500",
                    data_payload={"symbol": "ETHUSDT"},
                ))

                msg = ws.receive_json()
                delivery_id = msg["delivery_id"]

                # Send ACK back via WebSocket
                ws.send_json({"action": "ack", "delivery_id": delivery_id})

                ack_resp = ws.receive_json()
                assert ack_resp.get("type") == "ack_response"
                assert ack_resp.get("status") == "acked"
                assert ack_resp.get("delivery_id") == delivery_id

                # Journal must now be acked
                assert journal.get_status(delivery_id) == "acked"
                # Outbox entry must be cleared
                assert delivery_id not in outbox.OUTBOX

    def test_disconnected_user_delivers_to_fcm_without_websocket_error(self, monkeypatch):
        """3. When user is not connected on WebSocket, FCM delivery proceeds without error."""
        test_key = "ws_test_key_delivery"
        user_id = "offline_user_999"
        monkeypatch.setattr(config, "API_KEY", test_key)
        monkeypatch.setattr(server, "API_KEY", test_key)

        alert = self._make_alert("alt-ws-offline", user_id=user_id)
        storage.ALERTS_DB.append(alert)

        assert not manager.is_user_connected(user_id)

        with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_fcm:
            mock_fcm.return_value = (True, "OK")

            asyncio.run(outbox.enqueue_alert_push(
                alert=alert,
                title="SOL Target Hit",
                body="SOL reached 200",
                data_payload={"symbol": "SOLUSDT"},
            ))

            mock_fcm.assert_called_once()
            # Outbox should have the entry in awaiting_ack
            assert len(outbox.OUTBOX) == 1
