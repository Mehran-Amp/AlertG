import sys
import os

# Guarantee project root is in sys.path even when pytest runs without explicit PYTHONPATH
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import glob
import hashlib
import shutil
import pytest
import app.config as config
import app.engine.sync as sync_module
import app.storage as storage


@pytest.fixture(scope="session", autouse=True)
def guard_live_crypto_catalogs_session():
    """
    PHASE T1: Session-level guard that records mtime and md5 of all live crypto catalog files at session start.
    At session end, fails if any live catalog file's mtime or md5 changed, or if files were created/deleted.
    """
    catalog_dirs = ["crypto_catalogs", "crypto_catalog"]
    initial_state = {}

    def _file_md5(filepath):
        h = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    for d in catalog_dirs:
        abs_d = os.path.abspath(d)
        if os.path.isdir(abs_d):
            for path in glob.glob(os.path.join(abs_d, "*.json")):
                initial_state[path] = {
                    "mtime": os.path.getmtime(path),
                    "md5": _file_md5(path),
                }

    yield

    violations = []
    for path, before in initial_state.items():
        if not os.path.exists(path):
            violations.append(f"DELETED: {os.path.basename(path)}")
            continue
        curr_mtime = os.path.getmtime(path)
        if curr_mtime != before["mtime"]:
            curr_md5 = _file_md5(path)
            if curr_md5 != before["md5"]:
                violations.append(
                    f"MODIFIED: {os.path.basename(path)} (md5 {before['md5'][:8]} -> {curr_md5[:8]})"
                )
            else:
                violations.append(
                    f"TOUCHED: {os.path.basename(path)} (mtime {before['mtime']} -> {curr_mtime})"
                )

    for d in catalog_dirs:
        abs_d = os.path.abspath(d)
        if os.path.isdir(abs_d):
            for path in glob.glob(os.path.join(abs_d, "*.json")):
                if path not in initial_state:
                    violations.append(f"CREATED in live dir: {os.path.basename(path)}")

    if violations:
        pytest.fail(
            "PHASE T1 VIOLATION — Live crypto catalog files modified during test session:\n  "
            + "\n  ".join(violations)
        )


@pytest.fixture(autouse=True)
def isolate_test_environment(tmp_path, monkeypatch, request):
    """
    Guarantees zero tests write into real sync_runs.json, catalog.json, alerts_data.json,
    or live crypto_catalogs/.
    All storage, sync paths, and catalog paths are bound to a clean isolated tmp_path directory.
    """
    temp_dir = str(tmp_path)
    test_cat = os.path.join(temp_dir, "catalog.json")
    test_snaps = os.path.join(temp_dir, "catalog_snapshots")
    test_runs = os.path.join(temp_dir, "sync_runs.json")
    test_db = os.path.join(temp_dir, "alerts_data.json")
    test_prof = os.path.join(temp_dir, "user_profiles.json")
    test_crypto_cat = os.path.join(temp_dir, "crypto_catalogs")
    os.makedirs(test_crypto_cat, exist_ok=True)

    # Seed with real catalog.json so read-only tests succeed seamlessly
    real_cat = os.path.abspath("catalog.json")
    if os.path.exists(real_cat):
        shutil.copy2(real_cat, test_cat)

    # Monkeypatch config
    monkeypatch.setattr(config, "DATA_DIR", temp_dir)
    monkeypatch.setattr(config, "CATALOG_FILE", test_cat)
    monkeypatch.setattr(config, "CATALOG_SNAPSHOTS_DIR", test_snaps)
    monkeypatch.setattr(config, "SYNC_RUNS_FILE", test_runs)
    monkeypatch.setattr(config, "ALERTS_DATA_FILE", test_db)
    monkeypatch.setattr(config, "USER_PROFILES_FILE", test_prof)
    monkeypatch.setattr(config, "CRYPTO_CATALOG_DIR", test_crypto_cat)
    # WS-OFF-1: WS_ENABLED is false in production. Most tests (including all
    # WebSocket tests) need it on. test_ws_disabled.py sets it to False
    # explicitly via monkeypatch, which overrides this.
    if "test_ws_disabled" not in request.node.nodeid:
        monkeypatch.setattr(config, "WS_ENABLED", True)
    # Monkeypatch module-level overrides
    monkeypatch.setattr(sync_module, "CATALOG_FILE", test_cat)
    monkeypatch.setattr(sync_module, "CATALOG_SNAPSHOTS_DIR", test_snaps)
    monkeypatch.setattr(sync_module, "SYNC_RUNS_FILE", test_runs)
    monkeypatch.setattr(storage, "DB_FILE", test_db)
    monkeypatch.setattr(storage, "PROFILES_FILE", test_prof)

    # Neutralize server background catalog sync in tests so lifespan never leaks to disk
    if "test_server_startup_catalog_sync" not in request.node.nodeid:
        if "server" in sys.modules:
            server_mod = sys.modules["server"]
            if hasattr(server_mod, "_run_background_crypto_catalog_sync"):
                async def _noop_bg_sync(): pass
                monkeypatch.setattr(server_mod, "_run_background_crypto_catalog_sync", _noop_bg_sync)

    # Snapshot state of root files before test execution
    def _read_bytes(path):
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
        return None

    # Detect if a live server instance is actively running in background (port 8000 or PID)
    def _is_live_server_running():
        if os.path.exists("server.pid"):
            try:
                with open("server.pid", "r") as pf:
                    pid = int(pf.read().strip())
                os.kill(pid, 0)
                return True
            except Exception:
                pass
        try:
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.05)
                if s.connect_ex(('127.0.0.1', 8000)) == 0:
                    return True
        except Exception:
            pass
        return False

    sentinel_files = ["catalog.json", "sync_runs.json"]
    if not _is_live_server_running():
        sentinel_files.append("alerts_data.json")

    root_sentinels = {fn: _read_bytes(fn) for fn in sentinel_files}

    yield

    # Teardown assertion: no test may pollute real workspace files
    for filename, before_content in root_sentinels.items():
        after_content = _read_bytes(filename)
        if before_content is None and after_content is not None:
            os.remove(filename)
            raise AssertionError(f"Test leaked created artifact into real workspace file: {filename}")
        elif before_content is not None and after_content != before_content:
            with open(filename, "wb") as f:
                f.write(before_content)
            raise AssertionError(f"Test modified real workspace file: {filename}")
