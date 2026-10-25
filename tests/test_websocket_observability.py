"""
Phase 5: WebSocket Observability, Health Metrics & Status Dashboard Integration.
Tests:
1. WebSocket connection counts (active connections and active users) accurately reflected in /status.
2. WebSocket dispatch metric (ws_sent) incremented and reflected in /status upon outbox alert delivery.
3. WebSocket ACK metric (ws_acked) incremented and reflected in /status upon client WebSocket ACK.
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
from app.state import METRICS
import app.storage as storage


class TestWebSocketObservability:
    """Phase 5: Observability, metrics and health monitoring for WebSocket connections."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        orig_outbox = dict(outbox.OUTBOX)
        orig_journal = dict(journal.JOURNAL)
        orig_alerts = list(storage.ALERTS_DB)
        orig_ws_sent = METRICS.get("ws_sent", 0)
        orig_ws_acked = METRICS.get("ws_acked", 0)
        outbox.OUTBOX.clear()
        journal.JOURNAL.clear()
        METRICS["ws_sent"] = 0
        METRICS["ws_acked"] = 0
        yield
        outbox.OUTBOX.clear()
        outbox.OUTBOX.update(orig_outbox)
        journal.JOURNAL.clear()
        journal.JOURNAL.update(orig_journal)
        storage.ALERTS_DB.clear()
        storage.ALERTS_DB.extend(orig_alerts)
        METRICS["ws_sent"] = orig_ws_sent
        METRICS["ws_acked"] = orig_ws_acked

    def _make_alert(self, alert_id="alt-obs-1", user_id="obs_user_1"):
        return Alert(
            id=alert_id,
            user_id=user_id,
            exchange="binance",
            symbol="BTCUSDT",
            target_price=75000.0,
            condition="ABOVE",
            ack_supported=True,
            fcm_token="dummy_token_123456789012345678901234567890123456",
            created_at="2026-01-01T00:00:00Z",
        )

    def test_websocket_connection_counts_in_status_endpoint(self, monkeypatch):
        """1. /status accurately tracks active WebSocket connections and distinct users."""
        api_k = "test_obs_api_key"
        admin_k = "test_obs_admin_key"
        monkeypatch.setattr(config, "API_KEY", api_k)
        monkeypatch.setattr(server, "API_KEY", api_k)
        monkeypatch.setattr(config, "ADMIN_KEY", admin_k)
        monkeypatch.setattr(server, "ADMIN_KEY", admin_k)

        client = TestClient(app)

        # Baseline: 0 active connections
        res = client.get("/status?format=json", headers={"x-admin-key": admin_k})
        assert res.status_code == 200
        body = res.json()
        assert "websocket" in body
        assert body["websocket"]["active_connections"] == 0
        assert body["websocket"]["active_users"] == 0

        # Connect client 1
        with client.websocket_connect(f"/ws?api_key={api_k}&user_id=obs_u1") as ws1:
            res_after_c1 = client.get("/status?format=json", headers={"x-admin-key": admin_k})
            assert res_after_c1.status_code == 200
            body1 = res_after_c1.json()
            assert body1["websocket"]["active_connections"] == 1
            assert body1["websocket"]["active_users"] == 1

            # Connect client 2 (same user)
            with client.websocket_connect(f"/ws?api_key={api_k}&user_id=obs_u1") as ws2:
                res_after_c2 = client.get("/status?format=json", headers={"x-admin-key": admin_k})
                body2 = res_after_c2.json()
                assert body2["websocket"]["active_connections"] == 2
                assert body2["websocket"]["active_users"] == 1

        # Both disconnected
        res_after_disc = client.get("/status?format=json", headers={"x-admin-key": admin_k})
        body_disc = res_after_disc.json()
        assert body_disc["websocket"]["active_connections"] == 0
        assert body_disc["websocket"]["active_users"] == 0

    def test_websocket_dispatch_metric_in_status(self, monkeypatch):
        """2. Delivering alert over WebSocket increments ws_sent metric and updates /status."""
        api_k = "test_obs_api_key_2"
        admin_k = "test_obs_admin_key_2"
        user_id = "obs_u2"
        monkeypatch.setattr(config, "API_KEY", api_k)
        monkeypatch.setattr(server, "API_KEY", api_k)
        monkeypatch.setattr(config, "ADMIN_KEY", admin_k)
        monkeypatch.setattr(server, "ADMIN_KEY", admin_k)

        alert = self._make_alert("alt-obs-2", user_id=user_id)
        storage.ALERTS_DB.append(alert)

        client = TestClient(app)

        with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_fcm:
            mock_fcm.return_value = (True, "OK")

            with client.websocket_connect(f"/ws?api_key={api_k}&user_id={user_id}") as ws:
                # Enqueue alert for user
                eid = outbox.enqueue(
                    alert=alert,
                    title="BTC Spike",
                    body="BTC hit 75k",
                    data={"price": "75000"},
                    trigger_price=75000.0,
                )

                # Execute delivery
                loop = asyncio.get_event_loop()
                loop.run_until_complete(outbox._deliver_outbox_entry(eid, outbox.OUTBOX[eid]))

                # Drain alert from socket
                msg = None
                for _ in range(5):
                    raw = ws.receive_json()
                    if raw.get("type") == "alert":
                        msg = raw
                        break
                assert msg is not None
                assert msg["delivery_id"] == eid

                # Check metric via /status
                res = client.get("/status?format=json", headers={"x-admin-key": admin_k})
                assert res.status_code == 200
                body = res.json()
                assert body["websocket"]["ws_sent"] == 1
                assert METRICS.get("ws_sent") == 1

    def test_websocket_ack_metric_in_status(self, monkeypatch):
        """3. Client ACK over WebSocket increments ws_acked metric and updates /status."""
        api_k = "test_obs_api_key_3"
        admin_k = "test_obs_admin_key_3"
        user_id = "obs_u3"
        monkeypatch.setattr(config, "API_KEY", api_k)
        monkeypatch.setattr(server, "API_KEY", api_k)
        monkeypatch.setattr(config, "ADMIN_KEY", admin_k)
        monkeypatch.setattr(server, "ADMIN_KEY", admin_k)

        client = TestClient(app)
        eid = "deliv-obs-ack-3"

        # Setup entry in awaiting_ack
        now = time.time()
        journal.record_sent(eid)
        outbox.OUTBOX[eid] = {
            "id": eid,
            "alert_id": "alt-obs-3",
            "fcm_token": "token123",
            "title": "Title",
            "body": "Body",
            "data": {},
            "trigger_price": 75000.0,
            "created_at": now,
            "expires_at": now + 300,
            "ack_supported": True,
            "delivery_phase": "awaiting_ack",
            "resend_count": 0,
            "ack_due_at": now + 45,
            "attempts": 1,
            "last_error": None,
        }

        with client.websocket_connect(f"/ws?api_key={api_k}&user_id={user_id}") as ws:
            # Send WS ACK
            ws.send_json({"action": "ack", "delivery_id": eid})

            # Receive ack_response (skip ping if any)
            resp = None
            for _ in range(5):
                raw = ws.receive_json()
                if raw.get("type") == "ack_response":
                    resp = raw
                    break

            assert resp is not None
            assert resp["delivery_id"] == eid
            assert resp["status"] == "acked"

            # Check journal
            assert journal.get_status(eid) == "acked"

            # Check metrics in /status
            res = client.get("/status?format=json", headers={"x-admin-key": admin_k})
            assert res.status_code == 200
            body = res.json()
            assert body["websocket"]["ws_acked"] == 1
            assert METRICS.get("ws_acked") == 1
