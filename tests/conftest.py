import os
import shutil
import pytest
import app.config as config
import app.engine.sync as sync_module
import app.storage as storage


@pytest.fixture(autouse=True)
def isolate_test_environment(tmp_path, monkeypatch):
    """
    Guarantees zero tests write into real sync_runs.json, catalog.json, or alerts_data.json.
    All storage and sync paths are bound to a clean isolated tmp_path directory for every test.
    """
    temp_dir = str(tmp_path)
    test_cat = os.path.join(temp_dir, "catalog.json")
    test_snaps = os.path.join(temp_dir, "catalog_snapshots")
    test_runs = os.path.join(temp_dir, "sync_runs.json")
    test_db = os.path.join(temp_dir, "alerts_data.json")
    test_prof = os.path.join(temp_dir, "user_profiles.json")

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

    # Monkeypatch module-level overrides
    monkeypatch.setattr(sync_module, "CATALOG_FILE", test_cat)
    monkeypatch.setattr(sync_module, "CATALOG_SNAPSHOTS_DIR", test_snaps)
    monkeypatch.setattr(sync_module, "SYNC_RUNS_FILE", test_runs)
    monkeypatch.setattr(storage, "DB_FILE", test_db)
    monkeypatch.setattr(storage, "PROFILES_FILE", test_prof)

    # Snapshot state of root files before test execution
    def _read_bytes(path):
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
        return None

    root_sentinels = {
        "catalog.json": _read_bytes("catalog.json"),
        "sync_runs.json": _read_bytes("sync_runs.json"),
        "alerts_data.json": _read_bytes("alerts_data.json"),
    }

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
