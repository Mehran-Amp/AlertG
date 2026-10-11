#!/usr/bin/env python3
"""
Phase-3 baseline tool (checklist steps 1-2: baseline + single source of truth).

1. Writes an MD5 manifest of the main project files to docs/MD5_MANIFEST.txt
   (format is `md5sum -c` compatible: "<md5>  <relative/path>").
2. Captures /api/symbols/wallstreet-macro, /api/price/<exchange>/<symbol> (fixed symbol set)
   and /api/markets/status from a running server into snapshots/baseline_<phase>_<UTC>.json.

The capture layout mirrors snapshots/golden_phase0.json so scripts/compare_golden.py can diff them.
snapshots/golden_phase0.json is NEVER written or overwritten (new files are created exclusively).

Usage (on the server that runs server.py):
    API_KEY=<key> python3 scripts/make_baseline.py --base-url http://127.0.0.1:8000 --phase phase3
No secret is stored: the API key is read from the environment and only sent as the X-API-Key header.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MANIFEST = os.path.join("docs", "MD5_MANIFEST.txt")
DEFAULT_SNAPSHOT_DIR = "snapshots"

# "Main files" covered by the manifest (globs relative to the repo root).
MANIFEST_GLOBS = [
    "server.py",
    "requirements.txt",
    "run_server.sh",
    "pubspec.yaml",
    "catalog.json",
    "app/**/*.py",
    "lib/**/*.dart",
    "tests/**/*.py",
    "scripts/*.py",
]

# Fixed symbol set: identical to snapshots/golden_phase0.json price_samples so runs stay comparable.
FIXED_PRICE_SAMPLES: List[Tuple[str, str]] = [
    ("nobitex", "USDTIRT"),
    ("nobitex", "BTCIRT"),
    ("binance", "BTCUSDT"),
    ("wallex", "USDTTMN"),
    ("yahoo", "AAPL"),
    ("yahoo", "TSLA"),
    ("yahoo", "EURUSD"),
    ("yahoo", "^TNX"),
    ("yahoo", "^GSPC"),
    ("bonbast", "USD/TMN"),
]

# Golden keys use the label "yahoo/..." but the server only routes global_stocks/stocks/macro/forex/bonds/wallstreet
# to the Yahoo-backed adapter; "/api/price/yahoo/..." has no handler and always answers 502.
REQUEST_EXCHANGE_ALIASES = {"yahoo": "global_stocks"}

STABLE_SYMBOL_KEYS = ("id", "symbol", "nameEn", "nameFa", "category", "marketName", "unit")


# ------------------------------------------------------------------ manifest
def md5_file(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_main_files(root: str = ROOT) -> List[str]:
    found = set()
    for pattern in MANIFEST_GLOBS:
        for full in glob.glob(os.path.join(root, pattern), recursive=True):
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if os.path.isfile(full) and "__pycache__" not in rel.split("/") and not rel.endswith(".pyc"):
                found.add(rel)
    return sorted(found)


def build_manifest(root: str = ROOT) -> List[str]:
    return [f"{md5_file(os.path.join(root, rel))}  {rel}" for rel in iter_main_files(root)]


def _atomic_write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def write_manifest(root: str = ROOT, out_path: str = DEFAULT_MANIFEST) -> int:
    lines = build_manifest(root)
    out = out_path if os.path.isabs(out_path) else os.path.join(root, out_path)
    _atomic_write(out, "\n".join(lines) + "\n")
    return len(lines)


def verify_manifest(root: str = ROOT, manifest_path: str = DEFAULT_MANIFEST) -> List[str]:
    """Returns a list of problems (empty list means every file matches)."""
    path = manifest_path if os.path.isabs(manifest_path) else os.path.join(root, manifest_path)
    problems: List[str] = []
    expected: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            m = re.match(r"^([0-9a-f]{32})  (.+)$", line)
            if not m:
                problems.append(f"malformed manifest line: {line[:80]}")
                continue
            expected[m.group(2)] = m.group(1)
    for rel, digest in expected.items():
        full = os.path.join(root, rel)
        if not os.path.isfile(full):
            problems.append(f"MISSING  {rel}")
        elif md5_file(full) != digest:
            problems.append(f"CHANGED  {rel}")
    for rel in iter_main_files(root):
        if rel not in expected:
            problems.append(f"UNLISTED {rel}")
    return problems


# ------------------------------------------------------------------ API capture
def normalize_symbol(symbol: str) -> str:
    return re.sub(r"[/\s]", "", symbol).upper()


def http_get_json(base_url: str, path: str, api_key: Optional[str], timeout: float = 15.0) -> Tuple[int, Any]:
    """Returns (http_status, parsed_json_or_None). Never raises on HTTP/network errors (status 0 = unreachable)."""
    req = urllib.request.Request(base_url.rstrip("/") + path)
    req.add_header("Accept", "application/json")
    if api_key:
        req.add_header("X-API-Key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = None
        return e.code, body
    except Exception:
        return 0, None


def capture_snapshot(base_url: str, api_key: Optional[str], phase: str, timeout: float = 15.0,
                     fetch=http_get_json, root: str = ROOT) -> Dict[str, Any]:
    status_root, root_body = fetch(base_url, "/", None, timeout)
    engine = (root_body or {}).get("engine", "unknown") if isinstance(root_body, dict) else "unknown"

    symbols_status, sym_body = fetch(base_url, "/api/symbols/wallstreet-macro", api_key, timeout)
    symbols_ep: Dict[str, Any] = {"http_status": symbols_status}
    if isinstance(sym_body, dict):
        symbols_ep.update({
            "status": sym_body.get("status"),
            "market": sym_body.get("market"),
            "total_count": sym_body.get("total_count"),
            "categories": sym_body.get("categories", {}),
            "symbols": [{k: s.get(k) for k in STABLE_SYMBOL_KEYS} for s in sym_body.get("symbols", [])],
        })

    markets_status, markets_body = fetch(base_url, "/api/markets/status", api_key, timeout)
    markets_ep: Dict[str, Any] = {"http_status": markets_status}
    if isinstance(markets_body, dict):
        markets_ep.update(markets_body)

    samples: Dict[str, Any] = {}
    for exchange, symbol in FIXED_PRICE_SAMPLES:
        norm = normalize_symbol(symbol)
        request_exchange = REQUEST_EXCHANGE_ALIASES.get(exchange, exchange)
        code, body = fetch(base_url, f"/api/price/{request_exchange}/{urllib.parse.quote(norm, safe='^')}", api_key, timeout)
        samples[f"{exchange}/{symbol}"] = {
            "exchange": exchange,
            "input_symbol": symbol,
            "normalized_symbol": norm,
            "cache_key": f"{exchange}:{norm}",
            "request_exchange": request_exchange,
            "http_status": code,
            "response_template": body if isinstance(body, dict) else None,
        }

    server_py = os.path.join(root, "server.py")
    meta: Dict[str, Any] = {
        "phase": phase,
        "server_version": engine,
        "captured_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": _git_commit(root),
    }
    if os.path.isfile(server_py):
        meta["server_py_md5"] = md5_file(server_py)
        with open(server_py, "rb") as f:
            meta["server_py_lines"] = sum(1 for _ in f)
    return {
        "metadata": meta,
        "endpoints": {
            "api_symbols_wallstreet_macro": symbols_ep,
            "api_markets_status": markets_ep,
            "price_samples": samples,
        },
    }


def _git_commit(root: str) -> Optional[str]:
    try:
        return subprocess.check_output(["git", "-C", root, "rev-parse", "--short", "HEAD"],
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return None


def write_snapshot(snapshot: Dict[str, Any], snapshot_dir: str, phase: str, root: str = ROOT) -> str:
    out_dir = snapshot_dir if os.path.isabs(snapshot_dir) else os.path.join(root, snapshot_dir)
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_phase = re.sub(r"[^A-Za-z0-9_.-]", "_", phase)
    path = os.path.join(out_dir, f"baseline_{safe_phase}_{stamp}.json")
    # "x" = exclusive create: an existing snapshot (including golden_phase0.json) can never be overwritten.
    with open(path, "x", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


# ------------------------------------------------------------------ CLI
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Create MD5 manifest + API baseline snapshot.")
    ap.add_argument("--base-url", default=os.getenv("BASELINE_BASE_URL", "http://127.0.0.1:8000"))
    ap.add_argument("--api-key-env", default="API_KEY", help="Environment variable holding the X-API-Key value.")
    ap.add_argument("--phase", default="phase3", help="Label used in the snapshot name/metadata.")
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST)
    ap.add_argument("--snapshot-dir", default=DEFAULT_SNAPSHOT_DIR)
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--skip-manifest", action="store_true")
    ap.add_argument("--skip-api", action="store_true")
    args = ap.parse_args(argv)

    if not args.skip_manifest:
        n = write_manifest(ROOT, args.manifest)
        print(f"[manifest] {n} files -> {args.manifest}")

    if not args.skip_api:
        api_key = os.getenv(args.api_key_env, "").strip() or None
        if api_key is None:
            print(f"[warn] ${args.api_key_env} is empty: /api endpoints will answer 401/503.", file=sys.stderr)
        snap = capture_snapshot(args.base_url, api_key, args.phase, args.timeout)
        ep = snap["endpoints"]
        if ep["api_symbols_wallstreet_macro"].get("http_status") != 200:
            print("[error] symbols endpoint not reachable/authorized; snapshot NOT written.", file=sys.stderr)
            return 1
        path = write_snapshot(snap, args.snapshot_dir, args.phase)
        ok = sum(1 for s in ep["price_samples"].values() if s["http_status"] == 200)
        print(f"[snapshot] {path} (symbols={ep['api_symbols_wallstreet_macro'].get('total_count')}, "
              f"price samples ok={ok}/{len(ep['price_samples'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
