"""Phase 3E-1: /health/deep returns 200 in healthy state and 503 when
the delivery pipeline is clearly degraded.

Auth strategy: the endpoint stays protected by API_DEP in production
(same as /api/status and /api/outbox). Tests override require_api_key
via FastAPI's dependency_overrides so they do not depend on the
API_KEY environment variable, and do not modify conftest.py.
"""
import time
from fastapi.testclient import TestClient


def _client(monkeypatch, *, outbox_len=0, fcm_success=0, fcm_failed=0,
            fcm_auth_error=0, delivery_unacked=0, outbox_blocked=0):
    """Build a TestClient with METRICS + OUTBOX overridden and auth bypassed."""
    from app.state import METRICS
    import app.routes.admin as admin_module
    import server
    from app.security import require_api_key

    # Bypass API auth for this endpoint only, without touching conftest.py
    # or depending on the API_KEY environment variable.
    server.app.dependency_overrides[require_api_key] = lambda: None

    # Override METRICS values
    METRICS["fcm_success"] = fcm_success
    METRICS["fcm_failed"] = fcm_failed
    METRICS["fcm_auth_error"] = fcm_auth_error
    METRICS["delivery_unacked"] = delivery_unacked
    METRICS["outbox_blocked"] = outbox_blocked
    METRICS["start_time"] = time.time() - 3600  # 1h uptime

    # Override OUTBOX by monkeypatching admin_module.OUTBOX reference
    fake_outbox = {f"id{i}": {"id": f"id{i}"} for i in range(outbox_len)}
    monkeypatch.setattr(admin_module, "OUTBOX", fake_outbox)

    return TestClient(server.app)


class TestHealthDeepHealthy:
    """3E-1 / test 1: healthy state returns 200 with ok status."""

    def test_healthy_returns_200(self, monkeypatch):
        client = _client(monkeypatch, outbox_len=2, fcm_success=100, fcm_failed=3)
        try:
            r = client.get("/health/deep")
            assert r.status_code == 200
            body = r.json()
            assert body["status"] == "ok"
            assert body["checks"]["outbox_len"] == 2
            assert body["warnings"] == []
        finally:
            import server
            server.app.dependency_overrides.clear()


class TestHealthDeepDegraded:
    """3E-1 / test 2: 503 when outbox backlog exceeds 100."""

    def test_outbox_backlog_returns_503(self, monkeypatch):
        client = _client(monkeypatch, outbox_len=150, fcm_success=1000)
        try:
            r = client.get("/api/health/deep")  # alias must work too
            assert r.status_code == 503
            body = r.json()
            assert body["status"] == "degraded"
            assert any("outbox backlog" in w for w in body["warnings"])
        finally:
            import server
            server.app.dependency_overrides.clear()


class TestHealthDeepFcmAuth:
    """3E-1 / test 3: 503 when fcm_auth_error exceeds 10."""

    def test_fcm_auth_error_returns_503(self, monkeypatch):
        client = _client(monkeypatch, fcm_auth_error=15, fcm_success=0)
        try:
            r = client.get("/health/deep")
            assert r.status_code == 503
            body = r.json()
            assert any("auth" in w.lower() for w in body["warnings"])
        finally:
            import server
            server.app.dependency_overrides.clear()