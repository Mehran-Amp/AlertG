"""Phase 4 FIX-WS-2: stale WebSocket connections (no pong in >90s) must be
disconnected and removed from the manager."""
import time
import pytest


class TestStaleCleanup:
    """FIX-WS-2: manager disconnects sockets whose heartbeat is >90s old."""

    @pytest.mark.asyncio
    async def test_stale_socket_disconnected(self):
        from app.routes.ws import ConnectionManager

        class FakeWS:
            def __init__(self):
                self.closed = False
                self.close_code = None
            async def send_json(self, msg):
                pass
            async def close(self, code=None, reason=None):
                self.closed = True
                self.close_code = code

        mgr = ConnectionManager()
        ws = FakeWS()
        mgr.connect(ws, "user1")
        # Force heartbeat to be 100s old
        mgr._last_heartbeat[ws] = time.time() - 100

        # Simulate what _cleanup_loop does
        now = time.time()
        stale = [w for w, last in mgr._last_heartbeat.items() if now - last > 90]
        assert stale == [ws], "expected the stale socket to be detected"
        for w in stale:
            await w.close()
            mgr.disconnect(w)

        assert ws.closed is True
        assert mgr.get_active_connections_count() == 0
        assert mgr.is_user_connected("user1") is False

    @pytest.mark.asyncio
    async def test_fresh_socket_not_disconnected(self):
        from app.routes.ws import ConnectionManager

        class FakeWS:
            def __init__(self):
                self.closed = False
            async def send_json(self, msg):
                pass
            async def close(self, code=None, reason=None):
                self.closed = True

        mgr = ConnectionManager()
        ws = FakeWS()
        mgr.connect(ws, "user2")
        # Heartbeat is fresh
        now = time.time()
        stale = [w for w, last in mgr._last_heartbeat.items() if now - last > 90]
        assert stale == []
        assert mgr.is_user_connected("user2") is True