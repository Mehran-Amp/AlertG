import pytest
from starlette.websockets import WebSocketDisconnect


class TestWsDisabled:
    def test_ws_disabled_returns_1008(self, monkeypatch):
        import app.config as config
        monkeypatch.setattr(config, "WS_ENABLED", False)
        from fastapi.testclient import TestClient
        import server
        client = TestClient(server.app)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws?api_key=test-key&user_id=u1") as ws:
                ws.receive_text()
        assert exc_info.value.code == 1008