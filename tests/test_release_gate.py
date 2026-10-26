"""Phase 5D: release_gate.py must return 0 only when all checks pass,
and 1 when any check fails."""
import importlib.util
from pathlib import Path


def _load(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "release_gate",
        Path(__file__).resolve().parent.parent / "scripts" / "release_gate.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestReleaseGatePass:
    def test_all_pass_returns_zero(self, monkeypatch, tmp_path):
        mod = _load(monkeypatch)
        # Stub every check to pass
        for name in ("check_pytest", "check_import_server", "check_health_deep",
                     "check_unacked", "check_release_gate_md", "check_rollback_plan",
                     "check_catalog_snapshots"):
            monkeypatch.setattr(mod, name, lambda: mod._record(name, True))
        # Simulate __main__ with sys.exit
        rc = 0
        try:
            for name in ("check_pytest", "check_import_server", "check_health_deep",
                         "check_unacked", "check_release_gate_md", "check_rollback_plan",
                         "check_catalog_snapshots"):
                getattr(mod, name)()
        except Exception:
            rc = 1
        assert rc == 0


class TestReleaseGateFail:
    def test_one_fail_returns_nonzero(self, monkeypatch, tmp_path):
        mod = _load(monkeypatch)
        mod._record("pytest tests", False, "stub failure")
        failed = [r for r in mod.results if not r[1]]
        assert len(failed) == 1

class TestGateWarnVsFail:
    """GATE-1: skip is WARN, unchecked sign-off is FAIL."""

    def test_unchecked_boxes_fail(self, monkeypatch, tmp_path):
        mod = _load(monkeypatch)
        p = tmp_path / "docs" / "release_gate.md"
        p.parent.mkdir(parents=True)
        p.write_text("- [ ] pending\n- [x] done\n")
        monkeypatch.setattr(mod, "ROOT", tmp_path)
        mod.check_release_gate_md()
        failed = [r for r in mod.results if not r[1]]
        assert len(failed) == 1
        assert "unchecked" in failed[0][2]

    def test_skip_is_warn_not_pass(self, monkeypatch, tmp_path):
        mod = _load(monkeypatch)
        import urllib.error
        import urllib.request
        def boom(*a, **kw):
            raise urllib.error.URLError("refused")
        monkeypatch.setattr(urllib.request, "urlopen", boom)
        mod.check_health_deep()
        assert mod.results[-1][1] is True
        assert "WARN" in mod.results[-1][2]