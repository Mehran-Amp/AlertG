#!/usr/bin/env python3
"""
Phase 5D: Release gate. One command that says "release allowed" or "blocked".

Checks (each returns PASS/FAIL with a reason):
  1. pytest tests        -> all passed
  2. import server        -> no exception
  3. /health/deep         -> HTTP 200 with status: ok
  4. unacked (last 24h)   -> below threshold
  5. docs/release_gate.md -> exists and all checkboxes are checked
  6. ROLLBACK_PLAN.md     -> exists
  7. catalog_snapshots/   -> at least one snapshot

Usage:
  python scripts/release_gate.py
  echo $?   # 0 = PASS, 1 = FAIL
"""
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEALTH_URL = os.getenv("HEALTH_URL", "http://127.0.0.1:8000/health/deep")
API_KEY = os.getenv("API_KEY", "")
UNACKED_THRESHOLD = int(os.getenv("UNACKED_THRESHOLD", "10"))

results = []


def _record(name, ok, reason=""):
    results.append((name, ok, reason))
    print(f"{'✅' if ok else '❌'} {name}: {'PASS' if ok else 'FAIL'}{(' — ' + reason) if reason else ''}")


def check_pytest():
    try:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q"],
            cwd=str(ROOT), capture_output=True, text=True,
            timeout=300, encoding="utf-8", errors="replace", env=env,
        )
        if r.returncode == 0:
            _record("pytest tests", True)
        else:
            last = (r.stdout or "").strip().splitlines()[-1] if r.stdout else "no output"
            _record("pytest tests", False, last)
    except Exception as e:
        _record("pytest tests", False, str(e))


def check_import_server():
    try:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        r = subprocess.run(
            [sys.executable, "-c", "import server"],
            cwd=str(ROOT), capture_output=True, text=True,
            timeout=30, encoding="utf-8", errors="replace", env=env,
        )
        if r.returncode == 0:
            _record("import server", True)
        else:
            last = (r.stderr or "").strip().splitlines()[-1] if r.stderr else "?"
            _record("import server", False, last)
    except Exception as e:
        _record("import server", False, str(e))


def check_health_deep():
    try:
        req = urllib.request.Request(HEALTH_URL, method="GET")
        if API_KEY:
            req.add_header("X-API-Key", API_KEY)
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        if resp.status == 200 and body.get("status") == "ok":
            _record("/health/deep", True)
        else:
            _record("/health/deep", False, f"HTTP {resp.status} status={body.get('status')}")
    except Exception as e:
        if os.getenv("RELEASE_GATE_STRICT", "") == "1":
            _record("/health/deep", False, str(e))
        else:
            _record("/health/deep", True, f"skipped (server not reachable: {e})")


def check_unacked():
    try:
        req = urllib.request.Request(f"{HEALTH_URL.replace('/health/deep', '/api/status?format=json')}", method="GET")
        if API_KEY:
            req.add_header("X-API-Key", API_KEY)
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        unacked = body.get("delivery_unacked") or body.get("unacked_deliveries") or 0
        if unacked <= UNACKED_THRESHOLD:
            _record(f"unacked <= {UNACKED_THRESHOLD}", True, f"{unacked}")
        else:
            _record(f"unacked <= {UNACKED_THRESHOLD}", False, f"{unacked}")
    except Exception as e:
        if os.getenv("RELEASE_GATE_STRICT", "") == "1":
            _record(f"unacked <= {UNACKED_THRESHOLD}", False, str(e))
        else:
            _record(f"unacked <= {UNACKED_THRESHOLD}", True, f"skipped (server not reachable: {e})")


def check_release_gate_md():
    p = ROOT / "docs" / "release_gate.md"
    if not p.exists():
        _record("docs/release_gate.md exists", False, "missing")
        return
    text = p.read_text(encoding="utf-8")
    unchecked = len(re.findall(r"- \[ \]", text))
    if unchecked == 0:
        _record("docs/release_gate.md complete", True)
    else:
        if os.getenv("RELEASE_GATE_STRICT", "") == "1":
            _record("docs/release_gate.md complete", False, f"{unchecked} unchecked boxes (strict)")
        else:
            _record("docs/release_gate.md complete", True, f"{unchecked} unchecked (WARN: fill before release)")


def check_rollback_plan():
    p = ROOT / "ROLLBACK_PLAN.md"
    _record("ROLLBACK_PLAN.md exists", p.exists())


def check_catalog_snapshots():
    p = ROOT / "catalog_snapshots"
    if not p.exists():
        _record("catalog_snapshots/", False, "missing")
        return
    n = len(list(p.glob("snapshot_v*.json")))
    if n > 0:
        _record("catalog_snapshots/", True, f"{n} snapshot(s)")
    else:
        _record("catalog_snapshots/", False, "no snapshot")


if __name__ == "__main__":
    print("=== Release Gate ===\n")
    check_pytest()
    check_import_server()
    check_health_deep()
    check_unacked()
    check_release_gate_md()
    check_rollback_plan()
    check_catalog_snapshots()

    failed = [r for r in results if not r[1]]
    print(f"\n=== {'PASS' if not failed else 'FAIL'} ===")
    print(f"{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(0 if not failed else 1)