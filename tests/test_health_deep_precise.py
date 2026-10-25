"""Phase 3E-1 follow-up: /health/deep must use precise timestamps
(last_fcm_ok_ts, last_check_ts) to detect:
  1. queue filling AND no successful FCM in > 1 hour
  2. checker stalled (no cycle in > 5 minutes)
"""
import time
from fastapi.testclient import TestClient


def _client(monkeypatch, *, outbox_len=0, fcm_success=0, fcm_failed=0,
            fcm_auth_error=0, last_fcm_ok_ts=None, last_check_ts=None):
    from app.state import METRICS
    import app.routes.admin as admin_module
    import server
    from app.security import require_api_key

    server.app.dependency_overrides[require_api_key] = lambda: None

    METRICS["fcm_success"] = fcm_success
    METRICS["fcm_failed"] = fcm_failed
    METRICS["fcm_auth_error"] = fcm_auth_error
    METRICS["outbox_blocked"] = 0
    METRICS["delivery_unacked"] = 0
    METRICS["start_time"] = time.time() - 3600
    METRICS["last_fcm_ok_ts"] = last_fcm_ok_ts
    METRICS["last_check_ts"] = last_check_ts

    fake_outbox = {f"id{i}": {"id": f"id{i}"} for i in range(outbox_len)}
    monkeypatch.setattr(admin_module, "OUTBOX", fake_outbox)

    return TestClient(server.app)


def _clear():
    import server
    server.app.dependency_overrides.clear()


class TestStaleFcmWithQueue:
    """3E-1 / test 1: queue > 10 AND no FCM success in > 1h -> 503."""

    def test_stale_fcm_with_queue_returns_503(self, monkeypatch):
        now = time.time()
        client = _client(
            monkeypatch,
            outbox_len=15,
            last_fcm_ok_ts=now - 4000,   # > 1h ago
            last_check_ts=now - 10,
        )
        try:
            r = client.get("/health/deep")
            assert r.status_code == 503
            body = r.json()
            assert body["status"] == "degraded"
            assert any("no successful FCM" in w for w in body["warnings"])
        finally:
            _clear()


class TestCheckerStalled:
    """3E-1 / test 2: no checker cycle in > 5 minutes -> 503."""

    def test_checker_stalled_returns_503(self, monkeypatch):
        now = time.time()
        client = _client(
            monkeypatch,
            outbox_len=0,
            last_fcm_ok_ts=now - 10,     # fresh, not the cause
            last_check_ts=now - 600,     # > 5min ago
        )
        try:
            r = client.get("/health/deep")
            assert r.status_code == 503
            body = r.json()
            assert any("checker stalled" in w for w in body["warnings"])
        finally:
            _clear()


class TestPreciseTimestampsHealthy:
    """3E-1 / test 3: fresh timestamps with empty queue -> 200 (no false positive)."""

    def test_fresh_timestamps_healthy(self, monkeypatch):
        now = time.time()
        client = _client(
            monkeypatch,
            outbox_len=0,
            last_fcm_ok_ts=now - 10,
            last_check_ts=now - 2,
        )
        try:
            r = client.get("/health/deep")
            assert r.status_code == 200
            body = r.json()
            assert body["status"] == "ok"
            assert body["warnings"] == []
            # New fields must be present in checks
            assert body["checks"]["last_fcm_ok_ts"] is not None
            assert body["checks"]["last_check_ts"] is not None
            assert "now" in body["checks"]
        finally:
            _clear()
        