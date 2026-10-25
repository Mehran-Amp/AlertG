"""
Phase 4A-1: WebSocket endpoint tests for /ws.
Verifies API Key authentication, connection registration, and ping/pong.
"""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from server import app
import app.config as config
from app.routes.ws import manager


class TestWebSocketAuthAndRegistry:
    """4A-1 / test 1: Valid API key connects, registers in manager, and unregisters on disconnect."""

    def test_ws_connection_and_registration(self, monkeypatch):
        test_key = "test_ws_secret_key_123"
        user_id = "test_trader_42"
        monkeypatch.setattr(config, "API_KEY", test_key)

        client = TestClient(app)
        assert not manager.is_user_connected(user_id)

        with client.websocket_connect(f"/ws?api_key={test_key}&user_id={user_id}") as ws:
            assert manager.is_user_connected(user_id)
            conns = manager.get_user_connections(user_id)
            assert len(conns) == 1

        assert not manager.is_user_connected(user_id)


class TestWebSocketPingPong:
    """4A-1 / test 2: Ping text or JSON receives pong reply with timestamp."""

    def test_ws_ping_pong(self, monkeypatch):
        test_key = "test_ws_secret_key_123"
        monkeypatch.setattr(config, "API_KEY", test_key)

        client = TestClient(app)
        with client.websocket_connect(f"/ws?api_key={test_key}&user_id=ping_user") as ws:
            # Test string ping
            ws.send_text("ping")
            data = ws.receive_json()
            assert data.get("type") == "pong"
            assert "ts" in data

            # Test JSON ping
            ws.send_json({"type": "ping"})
            data2 = ws.receive_json()
            assert data2.get("type") == "pong"
            assert "ts" in data2


class TestWebSocketAuthRejection:
    """4A-1 / test 3: Missing or invalid API key closes socket with code 1008."""

    def test_ws_missing_or_invalid_auth_rejected(self, monkeypatch):
        test_key = "test_ws_secret_key_123"
        monkeypatch.setattr(config, "API_KEY", test_key)

        client = TestClient(app)

        # 1. Missing API key
        with pytest.raises(WebSocketDisconnect) as exc_missing:
            with client.websocket_connect("/ws?user_id=no_auth_user"):
                pass
        assert exc_missing.value.code == 1008

        # 2. Invalid API key
        with pytest.raises(WebSocketDisconnect) as exc_invalid:
            with client.websocket_connect("/ws?api_key=wrong_key_xyz&user_id=bad_user"):
                pass
        assert exc_invalid.value.code == 1008
