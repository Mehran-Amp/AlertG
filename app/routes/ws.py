import asyncio
import json
import time
from typing import Dict, Set, List, Optional, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
import app.config as config
from app.security import _key_matches

router = APIRouter()


class ConnectionManager:
    """
    Phase 4A-1: Manages active WebSocket connections mapped per user_id / device.
    Allows point-to-point alert dispatch and ping/pong tracking.
    """
    def __init__(self):
        self._user_connections: Dict[str, Set[WebSocket]] = {}
        self._socket_to_user: Dict[WebSocket, str] = {}
        self._last_heartbeat: Dict[WebSocket, float] = {}

    def connect(self, websocket: WebSocket, user_id: str) -> None:
        user_id = (user_id or "anonymous").strip()
        if user_id not in self._user_connections:
            self._user_connections[user_id] = set()
        self._user_connections[user_id].add(websocket)
        self._socket_to_user[websocket] = user_id
        self._last_heartbeat[websocket] = time.time()

    def disconnect(self, websocket: WebSocket) -> None:
        user_id = self._socket_to_user.pop(websocket, None)
        if user_id and user_id in self._user_connections:
            self._user_connections[user_id].discard(websocket)
            if not self._user_connections[user_id]:
                self._user_connections.pop(user_id, None)
        self._last_heartbeat.pop(websocket, None)

    def is_user_connected(self, user_id: str) -> bool:
        user_id = (user_id or "").strip()
        return bool(self._user_connections.get(user_id))

    def get_user_connections(self, user_id: str) -> List[WebSocket]:
        user_id = (user_id or "").strip()
        return list(self._user_connections.get(user_id, set()))

    def get_active_connections_count(self) -> int:
        return len(self._socket_to_user)

    def get_active_users_count(self) -> int:
        return len(self._user_connections)

    def update_heartbeat(self, websocket: WebSocket) -> None:
        self._last_heartbeat[websocket] = time.time()

    async def send_to_user(self, user_id: str, message: Dict[str, Any]) -> int:
        """Sends a JSON message to all active sockets of user_id. Returns delivery count."""
        sockets = self.get_user_connections(user_id)
        sent = 0
        for ws in sockets:
            try:
                await ws.send_json(message)
                sent += 1
            except Exception:
                self.disconnect(ws)
        return sent

    async def broadcast(self, message: Dict[str, Any]) -> int:
        """Sends a JSON message to all active sockets on the server."""
        sent = 0
        all_sockets = list(self._socket_to_user.keys())
        for ws in all_sockets:
            try:
                await ws.send_json(message)
                sent += 1
            except Exception:
                self.disconnect(ws)
        return sent


manager = ConnectionManager()


def _validate_ws_auth(websocket: WebSocket) -> bool:
    """Validates API Key from query parameters (?api_key=, ?token=) or headers."""
    api_k = getattr(config, 'API_KEY', '')
    admin_k = getattr(config, 'ADMIN_KEY', '')
    if not api_k:
        try:
            import server
            api_k = getattr(server, 'API_KEY', '')
        except Exception:
            pass

    # Check query params and headers
    query = websocket.query_params
    provided = (
        query.get("api_key")
        or query.get("x-api-key")
        or query.get("token")
        or websocket.headers.get("x-api-key")
        or ""
    ).strip()

    if not provided or (not api_k and not admin_k):
        return False

    return _key_matches(provided, api_k) or _key_matches(provided, admin_k)


@router.websocket("/ws")
@router.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Phase 4A-1: WebSocket endpoint for real-time alert delivery.
    - Requires API Key authentication via query parameter or header.
    - Registers user connection for targeted alert dispatches.
    - Maintains 30s ping/pong heartbeat.
    """
    if not _validate_ws_auth(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or missing API key")
        return

    user_id = (websocket.query_params.get("user_id") or "anonymous").strip()
    await websocket.accept()
    manager.connect(websocket, user_id)

    async def _ping_loop():
        try:
            while True:
                await asyncio.sleep(30)
                await websocket.send_json({"type": "ping", "ts": time.time()})
        except Exception:
            pass

    ping_task = asyncio.create_task(_ping_loop())
    try:
        while True:
            text = await websocket.receive_text()
            if not text:
                continue

            parsed = None
            try:
                parsed = json.loads(text)
            except Exception:
                pass

            msg_action = (parsed.get("action") or parsed.get("type") if isinstance(parsed, dict) else text).strip().lower()
            if msg_action == "ping":
                await websocket.send_json({"type": "pong", "ts": time.time()})
            elif msg_action == "pong":
                manager.update_heartbeat(websocket)
            elif msg_action in ("ack", "delivery_ack"):
                delivery_id = parsed.get("delivery_id") if isinstance(parsed, dict) else None
                if delivery_id:
                    try:
                        from app.notifier import journal, outbox
                        from app.state import METRICS
                        prev_state = journal.get_status(delivery_id)
                        acked = journal.record_acked(delivery_id)
                        if acked and prev_state != "acked":
                            METRICS["fcm_acked"] = METRICS.get("fcm_acked", 0) + 1
                            METRICS["ws_acked"] = METRICS.get("ws_acked", 0) + 1
                        if acked:
                            await outbox.on_delivery_acked(delivery_id)
                        await websocket.send_json({
                            "type": "ack_response",
                            "delivery_id": delivery_id,
                            "status": "acked" if acked else "unknown",
                        })
                    except Exception as e:
                        print(f"⚠️ [WS Ack Error] {e}")
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        ping_task.cancel()
        manager.disconnect(websocket)
