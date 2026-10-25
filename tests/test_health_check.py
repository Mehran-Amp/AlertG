"""Phase 3E-2: health_check.py must (a) stay silent when /health/deep is 200,
(b) alert on 503, (c) auto-restart when the server is unreachable.
All network/subprocess/Telegram calls are mocked.
"""
import io
import json
import urllib.error
import urllib.request
from pathlib import Path


def _load_module(monkeypatch, tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "health_check",
        Path(__file__).resolve().parent.parent / "scripts" / "health_check.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "STATE_FILE", tmp_path / "state.json")
    return mod


class TestHealthyIsSilent:
    def test_200_is_silent(self, monkeypatch, tmp_path):
        mod = _load_module(monkeypatch, tmp_path)
        alerts = []
        monkeypatch.setattr(mod, "_send_admin_alert", lambda text: alerts.append(text) or True)
        monkeypatch.setattr(mod, "_api_key", lambda: "test-key")

        class FakeResp:
            status = 200
            def read(self): return b'{"status":"ok","checks":{"uptime_seconds":42}}'
            def __enter__(self): return self
            def __exit__(self, *a): return False

        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: FakeResp())
        rc = mod.check_once()
        assert rc == 0
        assert alerts == []


class TestDegradedAlerts:
    def test_503_sends_alert(self, monkeypatch, tmp_path):
        mod = _load_module(monkeypatch, tmp_path)
        alerts = []
        monkeypatch.setattr(mod, "_send_admin_alert", lambda text: alerts.append(text) or True)
        monkeypatch.setattr(mod, "_api_key", lambda: "test-key")

        body = json.dumps({"status": "degraded", "warnings": ["outbox backlog: 150 > 100"]}).encode()
        err = urllib.error.HTTPError(
            url="http://test/health/deep", code=503, msg="Service Unavailable",
            hdrs=None, fp=io.BytesIO(body),
        )
        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: (_ for _ in ()).throw(err))

        rc = mod.check_once()
        assert rc == 1
        assert len(alerts) == 1
        assert "outbox backlog" in alerts[0]

        alerts.clear()
        rc2 = mod.check_once()
        assert rc2 == 1
        assert alerts == []


class TestUnreachableRestarts:
    def test_unreachable_restart_succeeded_alerts_success(self, monkeypatch, tmp_path):
        mod = _load_module(monkeypatch, tmp_path)
        calls = []
        alerts = []
        monkeypatch.setattr(mod, "_send_admin_alert", lambda text: alerts.append(text) or True)
        monkeypatch.setattr(mod, "_api_key", lambda: "test-key")
        monkeypatch.setattr(mod, "_try_restart", lambda: calls.append("restart") or True)

        def boom(req, timeout):
            raise urllib.error.URLError(ConnectionRefusedError("refused"))
        monkeypatch.setattr(urllib.request, "urlopen", boom)

        rc = mod.check_once()
        assert rc == 1
        assert calls == ["restart"]
        assert len(alerts) == 1
        assert "succeeded" in alerts[0]
        assert "failed" not in alerts[0]

    def test_unreachable_restart_failed_alerts_failure(self, monkeypatch, tmp_path):
        mod = _load_module(monkeypatch, tmp_path)
        calls = []
        alerts = []
        monkeypatch.setattr(mod, "_send_admin_alert", lambda text: alerts.append(text) or True)
        monkeypatch.setattr(mod, "_api_key", lambda: "test-key")
        monkeypatch.setattr(mod, "_try_restart", lambda: calls.append("restart_fail") and False)

        def boom(req, timeout):
            raise urllib.error.URLError(ConnectionRefusedError("refused"))
        monkeypatch.setattr(urllib.request, "urlopen", boom)

        rc = mod.check_once()
        assert rc == 1
        assert calls == ["restart_fail"]
        assert len(alerts) == 1
        assert "failed" in alerts[0]
        assert "succeeded" not in alerts[0]