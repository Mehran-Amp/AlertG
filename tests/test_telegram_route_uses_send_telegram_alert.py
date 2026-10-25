"""Phase 2C-1 follow-up: /api/telegram/test-message must go through
send_telegram_alert (retry 429/5xx, HTML->plain fallback, single
METRICS increment), not call state.http_client.post directly.
"""
import asyncio
import pytest
from fastapi.testclient import TestClient


def _client_with_auth_bypass():
    import server
    from app.security import require_api_key
    server.app.dependency_overrides[require_api_key] = lambda: None
    return TestClient(server.app)


def _clear_overrides():
    import server
    server.app.dependency_overrides.clear()


class TestTelegramRouteUsesSendTelegramAlert:
    """2C-1 / test 1: route calls send_telegram_alert, not http_client.post."""

    def test_route_calls_send_telegram_alert(self, monkeypatch):
        import app.routes.telegram as tg_route
        import app.state as state

        calls = []

        async def fake_send_telegram_alert(client, chat_id, message, bot_token=None, reply_markup=None):
            calls.append({"chat_id": chat_id, "message": message})
            return True

        # Ensure the module has the function imported (it does after the fix).
        monkeypatch.setattr(tg_route, "send_telegram_alert", fake_send_telegram_alert)
        monkeypatch.setattr(tg_route, "TELEGRAM_BOT_TOKEN", "fake_test_bot_token_123")

        # Stub http_client so the route's "not initialized" guard does not trip.
        class _FakeClient:
            pass
        monkeypatch.setattr(state, "http_client", _FakeClient())

        client = _client_with_auth_bypass()
        try:
            r = client.post("/api/telegram/test-message", json={"chat_id": "123456"})
            assert r.status_code == 200
            assert calls and calls[0]["chat_id"] == "123456"
        finally:
            _clear_overrides()


class TestTelegramRouteNoDoubleMetric:
    """2C-1 / test 2: route must NOT increment METRICS['telegram_sent'] itself
    (send_telegram_alert already does)."""

    def test_route_does_not_double_count_metric(self, monkeypatch):
        import app.routes.telegram as tg_route
        import app.state as state
        from app.state import METRICS

        async def fake_send_telegram_alert(client, chat_id, message, bot_token=None, reply_markup=None):
            # send_telegram_alert is responsible for this increment.
            METRICS["telegram_sent"] = METRICS.get("telegram_sent", 0) + 1
            return True

        monkeypatch.setattr(tg_route, "send_telegram_alert", fake_send_telegram_alert)
        monkeypatch.setattr(tg_route, "TELEGRAM_BOT_TOKEN", "fake_test_bot_token_123")

        class _FakeClient:
            pass
        monkeypatch.setattr(state, "http_client", _FakeClient())

        before = METRICS.get("telegram_sent", 0)
        client = _client_with_auth_bypass()
        try:
            r = client.post("/api/telegram/test-message", json={"chat_id": "123456"})
            assert r.status_code == 200
            after = METRICS.get("telegram_sent", 0)
            assert after == before + 1, (
                "route must not increment telegram_sent; send_telegram_alert already does"
            )
        finally:
            _clear_overrides()


class TestTelegramRouteReturns502OnFailure:
    """2C-1 / test 3: when send_telegram_alert returns False, route returns 502."""

    def test_route_returns_502_on_failure(self, monkeypatch):
        import app.routes.telegram as tg_route
        import app.state as state

        async def fake_send_telegram_alert(*a, **kw):
            return False

        monkeypatch.setattr(tg_route, "send_telegram_alert", fake_send_telegram_alert)
        monkeypatch.setattr(tg_route, "TELEGRAM_BOT_TOKEN", "fake_test_bot_token_123")

        class _FakeClient:
            pass
        monkeypatch.setattr(state, "http_client", _FakeClient())

        client = _client_with_auth_bypass()
        try:
            r = client.post("/api/telegram/test-message", json={"chat_id": "123456"})
            assert r.status_code == 502
        finally:
            _clear_overrides()