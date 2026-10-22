import os
import json
import time
import re
import asyncio
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

import app.config as config
from app.config import (
    DATA_DIR, CATALOG_FILE, CATALOG_SNAPSHOTS_DIR, SYNC_RUNS_FILE,
    APP_VERSION, SYMBOL_RE, CATALOG_SCHEMA_VERSION
)

WIKIPEDIA_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
USER_AGENT = "SignalAlertSeedBot/3.2.0 (contact: admin@signalalert.internal)"
DELIST_CONSECUTIVE_FAILURES_THRESHOLD = 3

def get_catalog_file() -> str:
    cfg_cat = getattr(config, "CATALOG_FILE", None)
    data_dir = getattr(config, "DATA_DIR", ".")
    if cfg_cat and cfg_cat != "catalog.json":
        return cfg_cat
    mod_cat = globals().get("CATALOG_FILE")
    if mod_cat and mod_cat != "catalog.json":
        return mod_cat
    if data_dir and data_dir != ".":
        return os.path.join(data_dir, "catalog.json")
    return cfg_cat or mod_cat or "catalog.json"

def get_snapshots_dir() -> str:
    cfg_snaps = getattr(config, "CATALOG_SNAPSHOTS_DIR", None)
    data_dir = getattr(config, "DATA_DIR", ".")
    if cfg_snaps and cfg_snaps != "catalog_snapshots":
        return cfg_snaps
    mod_snaps = globals().get("CATALOG_SNAPSHOTS_DIR")
    if mod_snaps and mod_snaps != "catalog_snapshots":
        return mod_snaps
    if data_dir and data_dir != ".":
        return os.path.join(data_dir, "catalog_snapshots")
    return cfg_snaps or mod_snaps or "catalog_snapshots"

def get_sync_runs_file(filepath: Optional[str] = None) -> str:
    if filepath:
        return filepath
    cfg_runs = getattr(config, "SYNC_RUNS_FILE", None)
    data_dir = getattr(config, "DATA_DIR", ".")
    if cfg_runs and cfg_runs != "sync_runs.json":
        return cfg_runs
    mod_runs = globals().get("SYNC_RUNS_FILE")
    if mod_runs and mod_runs != "sync_runs.json":
        return mod_runs
    if data_dir and data_dir != ".":
        return os.path.join(data_dir, "sync_runs.json")
    return cfg_runs or mod_runs or "sync_runs.json"
from app.state import METRICS
from app.markets.global_stocks import (
    WALLSTREET_MACRO_SYMBOLS,
    yahoo_adapter, finnhub_adapter, twelve_data_adapter, fred_adapter
)
from app.engine.categories import resolve_symbol_category
from app.notifier.outbox import enqueue_alert_push
from app.storage import ALERTS_DB, save_alerts_to_disk_async


class CatalogSafetyCeilingExceededError(Exception):
    """Raised when catalog sync exceeds safety boundaries (>5% delist, >10% add, or empty list)."""
    pass


class CatalogLockedError(Exception):
    """Raised when another writer holds the catalog lock or changed the catalog meanwhile."""
    pass


class CatalogSchemaError(Exception):
    """Raised when catalog.json was written by a newer schema than this code understands."""
    pass


class CatalogValidationError(ValueError):
    """Raised when catalog items fail structural, regex, or business rule validation."""
    pass


# -------------------------------------------------------------------------
# VALIDATION CONSTRAINTS (Phase 4 / v3.2.0)
# -------------------------------------------------------------------------
SYMBOL_RE = re.compile(r'^[A-Za-z0-9^][A-Za-z0-9\.\-\=\/\_\s\(\)\&\^]{0,31}$', re.IGNORECASE)
EXCHANGE_RE = re.compile(r'^[a-zA-Z0-9\_\-\s\.\&öäüéèáà]{2,40}$', re.IGNORECASE)
VALID_ASSET_CLASSES = {'stock', 'etf', 'forex', 'index', 'commodity', 'bond', 'macro'}
VALID_CURRENCIES = {'USD', 'EUR', 'GBP', 'JPY', 'CAD', 'CHF', 'AUD', 'NZD', 'CNY', 'HKD', 'AED', 'IRR', 'IRT'}
ALLOWED_PROVIDERS = {'yahoo', 'finnhub', 'twelve_data', 'fred'}
FORBIDDEN_CATEGORIES = {'iran_market', 'crypto'}


# -------------------------------------------------------------------------
# 0. SINGLE-WRITER LOCK (cross-process via flock, in-process via threading.Lock)
# -------------------------------------------------------------------------
try:
    import fcntl  # POSIX only; the production server (Linux) always has it
except ImportError:  # pragma: no cover - Windows dev machines
    fcntl = None

_CATALOG_THREAD_LOCK = threading.Lock()


@contextmanager
def catalog_write_lock():
    """
    Exclusive, NON-blocking write lock on <catalog.json>.lock.
    A second writer (another worker/process or an overlapping job) gets CatalogLockedError immediately
    instead of waiting, so the event loop is never blocked and two syncs can never interleave.
    """
    if not _CATALOG_THREAD_LOCK.acquire(blocking=False):
        raise CatalogLockedError("Catalog write lock is held by another thread.")
    fd = None
    try:
        if fcntl is not None:
            target_cat = get_catalog_file()
            lock_path = f"{target_cat}.lock"
            os.makedirs(os.path.dirname(os.path.abspath(lock_path)), exist_ok=True)
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise CatalogLockedError("Catalog write lock is held by another process.")
        yield
    finally:
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        _CATALOG_THREAD_LOCK.release()


# -------------------------------------------------------------------------
# 1. CATALOG PERSISTENCE, VERSIONING & ROLLBACK SNAPSHOTS
# -------------------------------------------------------------------------
def get_initial_catalog_data() -> Dict[str, Any]:
    """Generates initial seed catalog with catalog_version=1 from global symbols."""
    now_iso = datetime.now(timezone.utc).isoformat()
    symbols = []
    for s in WALLSTREET_MACRO_SYMBOLS:
        if s.get("category") in FORBIDDEN_CATEGORIES:
            continue
        item = dict(s)
        item["is_active"] = 1
        item["delisted_at"] = None
        item["added_at"] = now_iso
        symbols.append(item)
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "catalog_version": 1,
        "app_version": APP_VERSION,
        "last_sync_at": now_iso,
        "total_active": len(symbols),
        "total_symbols": len(symbols),
        "symbols": symbols
    }


def load_catalog() -> Dict[str, Any]:
    """Loads current catalog from disk or initializes it if missing."""
    target_cat = get_catalog_file()
    if os.path.exists(target_cat):
        try:
            with open(target_cat, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "symbols" in data and "catalog_version" in data:
                    file_schema = data.get("schema_version", 1)  # files written before v3.1.0 have no field
                    if isinstance(file_schema, int) and file_schema > CATALOG_SCHEMA_VERSION:
                        raise CatalogSchemaError(
                            f"{target_cat} has schema_version {file_schema} > supported {CATALOG_SCHEMA_VERSION}."
                        )
                    data.setdefault("schema_version", CATALOG_SCHEMA_VERSION)
                    return data
        except CatalogSchemaError:
            raise  # never reinitialize (overwrite) a file written by a newer version
        except Exception as e:
            print(f"⚠️ [CatalogSync] Error reading {target_cat}: {e}. Reinitializing.")

    initial = get_initial_catalog_data()
    save_catalog(initial)
    return initial


def save_catalog(catalog: Dict[str, Any]) -> None:
    """Atomically saves catalog to disk using a temporary file and rename."""
    target_cat = get_catalog_file()
    os.makedirs(os.path.dirname(os.path.abspath(target_cat)), exist_ok=True)
    tmp_path = f"{target_cat}.tmp.{time.time()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, target_cat)


def save_catalog_snapshot(catalog: Dict[str, Any]) -> str:
    """
    Saves a snapshot of current catalog before applying changes.
    Enables guaranteed rollback to previous versions.
    """
    target_dir = get_snapshots_dir()
    os.makedirs(target_dir, exist_ok=True)
    ver = catalog.get("catalog_version", 1)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"snapshot_v{ver}_{ts}.json"
    snapshot_path = os.path.join(target_dir, filename)

    tmp_path = f"{snapshot_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, snapshot_path)
    print(f"📦 [CatalogSync] Snapshot saved: {snapshot_path} (Version: {ver})")
    return snapshot_path


def list_catalog_snapshots() -> List[Dict[str, Any]]:
    """Returns sorted list of available snapshots for rollback."""
    snapshots_dir = get_snapshots_dir()
    if not os.path.exists(snapshots_dir):
        return []
    snapshots = []
    for f in os.listdir(snapshots_dir):
        if f.startswith("snapshot_v") and f.endswith(".json"):
            full = os.path.join(snapshots_dir, f)
            try:
                m = re.search(r'snapshot_v(\d+)_', f)
                if m:
                    ver = int(m.group(1))
                    snapshots.append({
                        "filename": f,
                        "filepath": full,
                        "version": ver,
                        "created_at": os.path.getmtime(full)
                    })
            except Exception:
                continue
    snapshots.sort(key=lambda x: (x["version"], x["created_at"]), reverse=True)
    return snapshots


def rollback_catalog(target_version: Optional[int] = None) -> Dict[str, Any]:
    """
    Rolls back the catalog to a specified previous version snapshot.
    If target_version is None, rolls back to the immediate previous snapshot.
    """
    snapshots = list_catalog_snapshots()
    if not snapshots:
        raise ValueError("No catalog snapshots available for rollback.")

    current = load_catalog()
    current_ver = current.get("catalog_version", 1)

    chosen = None
    if target_version is not None:
        for s in snapshots:
            if s["version"] == target_version:
                chosen = s
                break
        if not chosen:
            raise ValueError(f"Snapshot for version {target_version} not found.")
    else:
        # Pick latest snapshot with version < current_ver
        for s in snapshots:
            if s["version"] < current_ver:
                chosen = s
                break
        if not chosen:
            # If no earlier version found, pick the top snapshot
            chosen = snapshots[0]

    with open(chosen["filepath"], "r", encoding="utf-8") as f:
        restored_data = json.load(f)

    # Save snapshot of current before rollback for safety (single-writer lock held for snapshot + write)
    with catalog_write_lock():
        save_catalog_snapshot(current)
        restored_data.setdefault("schema_version", CATALOG_SCHEMA_VERSION)
        save_catalog(restored_data)
    METRICS["catalog_rollbacks"] = METRICS.get("catalog_rollbacks", 0) + 1
    print(f"⏪ [CatalogSync] Successfully rolled back to Version {restored_data.get('catalog_version')} from {chosen['filename']}")
    return restored_data


def load_sync_runs(filepath: Optional[str] = None) -> Dict[str, Any]:
    """Loads existing sync_runs.json file or initializes structure."""
    target = get_sync_runs_file(filepath)
    if os.path.exists(target):
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "runs" in data:
                    return data
        except Exception as e:
            print(f"⚠️ [CatalogSync] Error loading {target}: {e}")
    return {
        "total_runs": 0,
        "last_run_id": None,
        "last_run_at": None,
        "runs": []
    }


def record_sync_run(run_record: Dict[str, Any], filepath: Optional[str] = None) -> Dict[str, Any]:
    """
    Atomically appends a new run to sync_runs.json.
    Thread-safe and cross-process safe using temporary file and atomic replace.
    """
    target = get_sync_runs_file(filepath)
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    history = load_sync_runs(target)

    runs = list(history.get("runs", []))
    runs.append(run_record)
    history["total_runs"] = len(runs)
    history["last_run_id"] = run_record.get("run_id")
    history["last_run_at"] = run_record.get("timestamp")
    history["runs"] = runs

    tmp_path = f"{target}.tmp.{time.time()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, target)
    print(f"📝 [CatalogSync] Run recorded in {target} (Run ID: {run_record.get('run_id')})")
    return history


def get_catalog_delta(since_version: Optional[int] = None) -> Dict[str, Any]:
    """
    Computes delta sync for mobile and web clients.
    - If since_version is None or 0: returns full catalog with is_delta=False.
    - If since_version == current_catalog_version: returns is_delta=True, has_changes=False, empty delta lists.
    - If since_version < current_catalog_version: loads snapshot for since_version if available,
      computes added/updated/delisted, returns delta.
      If snapshot is missing, falls back to full catalog with reset_cache=True.
    """
    current = load_catalog()
    current_ver = current.get("catalog_version", 1)
    last_sync = current.get("last_sync_at")
    active_symbols = [s for s in current.get("symbols", []) if s.get("is_active", 1)]

    if since_version is None or since_version <= 0:
        return {
            "status": "full_catalog",
            "is_delta": False,
            "has_changes": True,
            "catalog_version": current_ver,
            "last_sync_at": last_sync,
            "total_count": len(active_symbols),
            "total_symbols_in_db": len(current.get("symbols", [])),
            "symbols": active_symbols
        }

    if since_version == current_ver:
        return {
            "status": "up_to_date",
            "is_delta": True,
            "has_changes": False,
            "catalog_version": current_ver,
            "since_version": since_version,
            "last_sync_at": last_sync,
            "total_count": len(active_symbols),
            "added": [],
            "updated": [],
            "delisted": []
        }

    # since_version < current_ver: look for snapshot
    snapshots = list_catalog_snapshots()
    chosen_snap = None
    for s in snapshots:
        if s["version"] == since_version:
            chosen_snap = s
            break

    if chosen_snap and os.path.exists(chosen_snap["filepath"]):
        try:
            with open(chosen_snap["filepath"], "r", encoding="utf-8") as f:
                old_data = json.load(f)
            diff = compute_catalog_diff(old_data, active_symbols)
            return {
                "status": "delta_success",
                "is_delta": True,
                "has_changes": bool(diff["added"] or diff["modified"] or diff["delisted"]),
                "catalog_version": current_ver,
                "since_version": since_version,
                "last_sync_at": last_sync,
                "total_count": len(active_symbols),
                "added": diff["added"],
                "updated": [m["new"] if "new" in m else m for m in diff["modified"]],
                "delisted": [d.get("symbol") for d in diff["delisted"] if d.get("symbol")]
            }
        except Exception as e:
            print(f"⚠️ [CatalogSync] Error diffing snapshot v{since_version}: {e}")

    # Fallback to full catalog if snapshot missing
    return {
        "status": "full_catalog_reset",
        "is_delta": False,
        "reset_cache": True,
        "has_changes": True,
        "catalog_version": current_ver,
        "since_version": since_version,
        "last_sync_at": last_sync,
        "total_count": len(active_symbols),
        "total_symbols_in_db": len(current.get("symbols", [])),
        "symbols": active_symbols
    }


def fetch_sp500_constituents_live() -> List[Dict[str, Any]]:
    """
    Live extraction of S&P 500 constituents from Wikipedia with User-Agent and schema validation.
    Halts and raises CatalogValidationError if table structure or mandatory headers change.
    """
    import urllib.request
    import html

    req = urllib.request.Request(
        WIKIPEDIA_SP500_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        content = resp.read().decode("utf-8")

    # Locate constituents table
    table_match = re.search(r'<table[^>]*id=["\']constituents["\'][^>]*>(.*?)</table>', content, re.DOTALL | re.IGNORECASE)
    if not table_match:
        table_match = re.search(r'<table[^>]*class=["\'][^"\']*wikitable[^"\']*["\'][^>]*>(.*?)</table>', content, re.DOTALL | re.IGNORECASE)
        if not table_match:
            raise CatalogValidationError("S&P 500 table not found in Wikipedia HTML response.")

    table_html = table_match.group(1)
    header_row_match = re.search(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL | re.IGNORECASE)
    if not header_row_match:
        raise CatalogValidationError("Could not extract header row from S&P 500 table.")

    header_cells = re.findall(r'<th[^>]*>(.*?)</th>', header_row_match.group(1), re.DOTALL | re.IGNORECASE)
    clean_headers = [re.sub(r'<[^>]+>', '', h).strip() for h in header_cells]

    expected_mandatory_headers = ["Symbol", "Security"]
    for expected in expected_mandatory_headers:
        if not any(expected.lower() in h.lower() for h in clean_headers):
            raise CatalogValidationError(
                f"S&P 500 table schema changed! Expected header '{expected}' missing from headers: {clean_headers}. Halting execution."
            )

    symbol_idx = -1
    security_idx = -1
    for idx, h in enumerate(clean_headers):
        if "symbol" in h.lower() and symbol_idx == -1:
            symbol_idx = idx
        elif "security" in h.lower() and security_idx == -1:
            security_idx = idx

    if symbol_idx == -1 or security_idx == -1:
        raise CatalogValidationError(f"Unable to resolve Symbol/Security column indices. Headers: {clean_headers}")

    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL | re.IGNORECASE)
    results: List[Dict[str, Any]] = []

    for row_content in rows[1:]:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row_content, re.DOTALL | re.IGNORECASE)
        if len(cells) <= max(symbol_idx, security_idx):
            continue

        raw_sym = re.sub(r'<[^>]+>', '', cells[symbol_idx]).strip()
        raw_name = html.unescape(re.sub(r'<[^>]+>', '', cells[security_idx]).strip())
        if not raw_sym:
            continue

        sym_id = raw_sym.replace('/', '.')
        yf_sym = raw_sym.replace('.', '-')

        results.append({
            "id": sym_id,
            "symbol": sym_id,
            "nameEn": raw_name,
            "nameFa": raw_name,
            "category": "stock",
            "marketName": "NYSE" if "." in sym_id else "NASDAQ",
            "unit": "$",
            "is_active": 1,
            "delisted_at": None,
            "provider_map": {
                "yahoo": {"symbol": yf_sym, "priority": 1},
                "finnhub": {"symbol": sym_id, "priority": 2},
                "twelve_data": {"symbol": sym_id, "priority": 3}
            },
            "source": "live_sp500"
        })

    if len(results) < 400:
        raise CatalogValidationError(f"Extracted only {len(results)} S&P 500 constituents; expected ~500. Table parsing aborted.")

    return results


NASDAQ_TRADER_URL = "http://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"


def fetch_nasdaq_trader_live() -> List[Dict[str, Any]]:
    """
    Live extraction of symbols from Nasdaq Trader directory with User-Agent and structural validation.
    Halts and raises CatalogValidationError if table structure or mandatory headers change.
    """
    import urllib.request
    req = urllib.request.Request(
        NASDAQ_TRADER_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "text/plain"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"⚠️ [CatalogSync] Nasdaq Trader network access skipped/failed: {e}")
        return []

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return []

    header = [h.strip() for h in lines[0].split("|")]
    if not any("symbol" in h.lower() for h in header) or not any("security" in h.lower() for h in header):
        raise CatalogValidationError(
            f"Nasdaq Trader table schema changed! Expected 'Symbol' and 'Security Name', got: {header}. Halting execution."
        )

    sym_idx = -1
    sec_idx = -1
    test_idx = -1
    for idx, h in enumerate(header):
        if "symbol" in h.lower() and sym_idx == -1:
            sym_idx = idx
        elif "security" in h.lower() and sec_idx == -1:
            sec_idx = idx
        elif "test" in h.lower() and test_idx == -1:
            test_idx = idx

    results: List[Dict[str, Any]] = []
    for line in lines[1:]:
        if line.startswith("File Creation Time:"):
            continue
        parts = line.split("|")
        if len(parts) <= max(sym_idx, sec_idx):
            continue
        if test_idx != -1 and len(parts) > test_idx and parts[test_idx].strip().upper() == "Y":
            continue

        raw_sym = parts[sym_idx].strip()
        raw_name = parts[sec_idx].strip()
        if not raw_sym or not raw_name:
            continue

        sym_id = raw_sym.replace('/', '.')
        yf_sym = raw_sym.replace('.', '-')

        results.append({
            "id": sym_id,
            "symbol": sym_id,
            "nameEn": raw_name,
            "nameFa": raw_name,
            "category": "stock",
            "marketName": "NASDAQ",
            "unit": "$",
            "is_active": 1,
            "delisted_at": None,
            "provider_map": {
                "yahoo": {"symbol": yf_sym, "priority": 1},
                "finnhub": {"symbol": sym_id, "priority": 2},
                "twelve_data": {"symbol": sym_id, "priority": 3}
            },
            "source": "live_nasdaq_trader"
        })

    return results


def fetch_candidate_catalog(include_nasdaq_trader: bool = False) -> List[Dict[str, Any]]:
    """
    Stage 1: FETCH
    Fetches raw symbols catalog from live sources instead of a static list:
    - S&P 500 constituents live from Wikipedia with User-Agent & structural validation
    - Nasdaq Trader files when requested with User-Agent & schema validation (column change -> HALT)
    - Registered provider adapters (Yahoo, Finnhub, Twelve Data, FRED)
    - Offline fallback to current catalog symbols if live fetch encounters network timeout
    """
    aggregated: List[Dict[str, Any]] = []

    # 1. Live fetch of S&P 500 constituents
    try:
        sp500_items = fetch_sp500_constituents_live()
        if sp500_items:
            aggregated.extend(sp500_items)
            print(f"📡 [CatalogSync] Successfully fetched {len(sp500_items)} live S&P 500 constituents.")
    except CatalogValidationError:
        # Schema change or column mismatch MUST stop execution
        raise
    except Exception as e:
        print(f"⚠️ [CatalogSync] Live S&P 500 fetch failed: {e}")

    # 2. Live fetch of Nasdaq Trader directory (if enabled)
    if include_nasdaq_trader:
        try:
            nasdaq_items = fetch_nasdaq_trader_live()
            if nasdaq_items:
                aggregated.extend(nasdaq_items)
                print(f"📡 [CatalogSync] Successfully fetched {len(nasdaq_items)} live Nasdaq Trader constituents.")
        except CatalogValidationError:
            raise
        except Exception as e:
            print(f"⚠️ [CatalogSync] Live Nasdaq Trader fetch failed: {e}")

    # 3. Gather from registered adapters
    for adapter in (yahoo_adapter, finnhub_adapter, twelve_data_adapter, fred_adapter):
        try:
            items = adapter.fetch_catalog()
            if items:
                for item in items:
                    c = dict(item)
                    c["source_provider"] = adapter.name
                    aggregated.append(c)
        except Exception as e:
            print(f"⚠️ [CatalogSync] Error fetching from adapter {adapter.name}: {e}")

    # 4. Fallback to current catalog only if all live sources returned empty (offline network fallback)
    if not aggregated:
        current = load_catalog()
        for s in current.get("symbols", []):
            if s.get("is_active", 1):
                aggregated.append(dict(s))

    return aggregated


def normalize_catalog_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stage 2: NORMALIZE
    Standardizes fields, category, casing, Persian text.
    """
    sym = (item.get("symbol") or item.get("id") or "").strip().upper()
    sym_id = (item.get("id") or sym).strip()

    category = item.get("category")
    if not category:
        category = resolve_symbol_category("global_stocks", sym)

    return {
        "id": sym_id,
        "symbol": sym,
        "nameEn": (item.get("nameEn") or item.get("name") or sym).strip(),
        "nameFa": (item.get("nameFa") or item.get("name_fa") or sym).strip(),
        "category": category,
        "marketName": (item.get("marketName") or item.get("market") or "Global").strip(),
        "unit": (item.get("unit") or "$").strip(),
        "is_active": 1,
        "delisted_at": None,
        "source": item.get("source_provider") or item.get("source") or "default"
    }


def validate_candidate_catalog(items: List[Dict[str, Any]], strict: bool = False) -> List[Dict[str, Any]]:
    """
    Stage 3: VALIDATE
    Strictly validates candidate symbols:
    - Enforces SYMBOL_RE ticker format
    - Enforces EXCHANGE_RE code format
    - Validates asset_class / category against VALID_ASSET_CLASSES
    - Rejects isolated markets (Iran domestic & Crypto) from global catalog
    - Validates currency against VALID_CURRENCIES
    - Verifies provider_map (keys restricted to ALLOWED_PROVIDERS)
    - Rejects duplicates and multi-category cross-contamination
    If strict=True, raises CatalogValidationError on first violation.
    """
    valid: Dict[str, Dict[str, Any]] = {}
    symbol_to_category: Dict[str, str] = {}

    for raw in items:
        norm = normalize_catalog_item(raw)
        s = norm.get("symbol", "").strip()
        sym_id = norm.get("id", "").strip()

        # 1. Symbol ID & SYMBOL_RE validation
        if not s or not sym_id:
            msg = f"Candidate missing symbol or id: {raw}"
            if strict:
                raise CatalogValidationError(msg)
            continue

        if not SYMBOL_RE.match(s):
            msg = f"Symbol '{s}' violates SYMBOL_RE pattern."
            if strict:
                raise CatalogValidationError(msg)
            continue

        # 2. Asset class / Category validation
        cat = norm.get("category", "").strip().lower()
        if not cat:
            msg = f"Symbol '{s}' missing category/asset_class."
            if strict:
                raise CatalogValidationError(msg)
            continue

        if cat in FORBIDDEN_CATEGORIES:
            msg = f"Symbol '{s}' category '{cat}' belongs to an isolated market and cannot enter global catalog."
            if strict:
                raise CatalogValidationError(msg)
            continue

        if cat not in VALID_ASSET_CLASSES:
            msg = f"Symbol '{s}' has invalid asset_class/category '{cat}'. Allowed: {sorted(VALID_ASSET_CLASSES)}"
            if strict:
                raise CatalogValidationError(msg)
            continue

        # Check multi-category collision
        s_upper = s.upper()
        if s_upper in symbol_to_category and symbol_to_category[s_upper] != cat:
            msg = f"Symbol '{s}' exists in multiple categories ('{symbol_to_category[s_upper]}' vs '{cat}')."
            if strict:
                raise CatalogValidationError(msg)
            continue
        symbol_to_category[s_upper] = cat

        # 3. Exchange validation
        market = raw.get("exchange") if "exchange" in raw else raw.get("marketName")
        if market is None:
            market = norm.get("marketName", "")
        market = str(market).strip()
        if not market:
            msg = f"Symbol '{s}' missing exchange/marketName."
            if strict:
                raise CatalogValidationError(msg)
            continue
        if not EXCHANGE_RE.match(market):
            msg = f"Symbol '{s}' exchange '{market}' violates EXCHANGE_RE pattern."
            if strict:
                raise CatalogValidationError(msg)
            continue

        # 4. Currency validation
        unit = norm.get("unit", "$").strip()
        curr_map = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "FR": "CHF", "Fr": "CHF", "C$": "CAD", "A$": "AUD", "ت": "IRT", "%": "USD", "pts": "USD", "واحد": "IRR"}
        normalized_curr = curr_map.get(unit, unit.upper())
        if normalized_curr not in VALID_CURRENCIES:
            msg = f"Symbol '{s}' has invalid currency '{unit}'."
            if strict:
                raise CatalogValidationError(msg)
            continue

        # 5. Provider Map validation (if item specifies provider_map)
        prov_map = raw.get("provider_map")
        if prov_map is not None:
            if not isinstance(prov_map, dict) or len(prov_map) == 0:
                msg = f"Symbol '{s}' provider_map must be a non-empty dictionary."
                if strict:
                    raise CatalogValidationError(msg)
                continue
            for prov in prov_map:
                if prov not in ALLOWED_PROVIDERS:
                    msg = f"Symbol '{s}' references unapproved provider '{prov}'. Allowed: {sorted(ALLOWED_PROVIDERS)}"
                    if strict:
                        raise CatalogValidationError(msg)
                    continue

        # 6. Deduplication, prioritizing richer Persian descriptions
        if s_upper not in valid:
            valid[s_upper] = norm
        else:
            if strict:
                raise CatalogValidationError(f"Duplicate symbol '{s}' detected in candidate catalog.")
            existing = valid[s_upper]
            if len(norm.get("nameFa", "")) > len(existing.get("nameFa", "")):
                valid[s_upper] = norm

    return list(valid.values())


def compute_catalog_diff(
    current_catalog: Dict[str, Any],
    candidate_items: List[Dict[str, Any]],
    protect_active_alerts: bool = False,
    require_consecutive_probe_failures: bool = False,
    consecutive_failures_threshold: int = DELIST_CONSECUTIVE_FAILURES_THRESHOLD
) -> Dict[str, Any]:
    """
    Stage 4: DIFF
    Calculates differences: added, modified, delisted, unchanged.
    - Active alert protection: Symbols with active alerts in ALERTS_DB are never automatically delisted (flagged + admin notified).
    - Consecutive failure threshold: Symbols require N consecutive failed probe/sync runs before delisting.
    """
    existing_all = {s["symbol"]: s for s in current_catalog.get("symbols", [])}
    existing_active = {s["symbol"]: s for s in current_catalog.get("symbols", []) if s.get("is_active", 1)}

    candidate_map = {s["symbol"]: s for s in candidate_items}

    added: List[Dict[str, Any]] = []
    modified: List[Dict[str, Any]] = []
    delisted: List[Dict[str, Any]] = []
    unchanged: List[Dict[str, Any]] = []

    # Check candidates for added or modified
    for sym, cand in candidate_map.items():
        if sym not in existing_all:
            added.append(cand)
        elif not existing_all[sym].get("is_active", 1):
            # Was previously delisted, now reactivated
            added.append(cand)
        else:
            old = existing_all[sym]
            # Reset probe failure counter on active candidate
            if "consecutive_probe_failures" in old:
                old["consecutive_probe_failures"] = 0
            # Check if metadata changed
            changed = any(
                old.get(k) != cand.get(k)
                for k in ("nameEn", "nameFa", "category", "marketName", "unit")
            )
            if changed:
                modified.append({
                    "symbol": sym,
                    "old": old,
                    "new": cand
                })
            else:
                unchanged.append(old)

    active_alert_symbols = {a.symbol.upper().strip() for a in ALERTS_DB if getattr(a, "is_active", True)}

    # Check existing active symbols missing in candidates -> DELISTED
    for sym, old in existing_active.items():
        if sym not in candidate_map:
            # 1. Protection for symbols with active alerts: never auto delist, flag and notify admin
            if protect_active_alerts and sym.upper().strip() in active_alert_symbols:
                old_copy = dict(old)
                old_copy["flagged_delist_protected"] = True
                unchanged.append(old_copy)
                trigger_admin_safety_alert(f"نماد {sym} دارای هشدار فعال کاربر است و از حذف خودکار جلوگیری شد.")
                continue

            # 2. Delist only after N consecutive failed probe/sync runs
            if require_consecutive_probe_failures:
                failed_count = old.get("consecutive_probe_failures", 0) + 1
                if failed_count < consecutive_failures_threshold:
                    old_copy = dict(old)
                    old_copy["consecutive_probe_failures"] = failed_count
                    unchanged.append(old_copy)
                    continue
                else:
                    delisted.append(old)
            else:
                delisted.append(old)

    curr_active_count = len(existing_active)
    delisted_ratio = (len(delisted) / curr_active_count) if curr_active_count > 0 else 0.0
    added_ratio = (len(added) / curr_active_count) if curr_active_count > 0 else 0.0

    return {
        "added": added,
        "modified": modified,
        "delisted": delisted,
        "unchanged": unchanged,
        "stats": {
            "current_active_count": curr_active_count,
            "candidate_count": len(candidate_items),
            "added_count": len(added),
            "modified_count": len(modified),
            "delisted_count": len(delisted),
            "unchanged_count": len(unchanged),
            "delisted_ratio": delisted_ratio,
            "added_ratio": added_ratio
        }
    }


def trigger_admin_safety_alert(reason: str) -> None:
    """Emits alert to admin and records metric when sync is halted by safety ceilings."""
    METRICS["catalog_sync_admin_alerts"] = METRICS.get("catalog_sync_admin_alerts", 0) + 1
    METRICS["last_catalog_sync_error"] = reason
    print(f"🚨 [ADMIN ALERT] [CatalogSync Halted] {reason}")
    msg = (
        f"🚨 <b>[هشدار ادمین - همگام‌سازی ناموفق کاتالوگ]</b>\n"
        f"🛑 وضعیت: <b>توقف اضطراری سنک کاتالوگ نمادها</b>\n"
        f"⚠️ علت: <code>{reason}</code>\n"
        f"📦 جهت حفظ سلامت کاتالوگ، سنک لغو شد."
    )
    try:
        from app.notifier.telegram import notify_admin_telegram
        from app.notifier.outbox import _spawn
        _spawn(notify_admin_telegram(msg))
    except Exception:
        pass


def check_sync_safety(stats: Dict[str, Any]) -> None:
    """
    Enforces Safety Ceilings:
    - Empty list -> HALT + ADMIN ALERT
    - Delisted > 5% -> HALT + ADMIN ALERT
    - Added > 10% -> HALT + ADMIN ALERT
    """
    candidate_count = stats.get("candidate_count", 0)
    curr_active = stats.get("current_active_count", 0)
    delisted_ratio = stats.get("delisted_ratio", (stats.get("delisted_count", 0) / max(1, curr_active)) if curr_active > 0 else 0.0)
    added_ratio = stats.get("added_ratio", (stats.get("added_count", 0) / max(1, curr_active)) if curr_active > 0 else 0.0)

    # 1. Empty candidate list ceiling
    if candidate_count == 0:
        msg = "Catalog fetch returned empty list; sync aborted to protect catalog integrity."
        trigger_admin_safety_alert(msg)
        raise CatalogSafetyCeilingExceededError(msg)

    # 2. Safety ceilings relative to current active catalog
    if curr_active > 0:
        if delisted_ratio > 0.05:
            msg = (
                f"Safety ceiling exceeded: {stats['delisted_count']} delistings "
                f"({delisted_ratio * 100:.2f}%) exceeds 5.0% threshold; sync aborted."
            )
            trigger_admin_safety_alert(msg)
            raise CatalogSafetyCeilingExceededError(msg)

        if added_ratio > 0.10:
            msg = (
                f"Safety ceiling exceeded: {stats['added_count']} additions "
                f"({added_ratio * 100:.2f}%) exceeds 10.0% threshold; sync aborted."
            )
            trigger_admin_safety_alert(msg)
            raise CatalogSafetyCeilingExceededError(msg)


async def probe_catalog_prices(items: List[Dict[str, Any]], sample_size: int = 5) -> Dict[str, Any]:
    """
    Stage 5: PRICE PROBE
    Probes price availability for newly added or changed symbols before applying.
    """
    from app.engine.checker import get_cached_price
    results = {}
    subset = items[:sample_size]
    for item in subset:
        sym = item.get("symbol")
        try:
            # Non-blocking probe from cache or quick fetch
            price = await get_cached_price("global_stocks", sym)
            results[sym] = {"status": "ok", "price": price}
        except Exception as e:
            results[sym] = {"status": "probe_failed", "error": str(e)}
    return results


async def notify_users_and_deactivate_delisted(delisted_symbols: List[str]) -> int:
    """
    Stage 7 (User Notification & Deactivation):
    For delisted symbols:
    - Deactivates matching alerts in ALERTS_DB (is_active = False)
    - Enqueues push notification to user via outbox
    - Atomically updates alerts_data.json on disk
    """
    if not delisted_symbols:
        return 0

    delisted_set = {s.upper().strip() for s in delisted_symbols}
    deactivated_count = 0

    for alert in ALERTS_DB:
        if alert.is_active and alert.symbol.upper().strip() in delisted_set:
            alert.is_active = False
            deactivated_count += 1
            print(f"🛑 [CatalogSync] Deactivated alert {alert.id} for delisted symbol: {alert.symbol}")

            # Notify user
            title = f"⚠️ نماد حذف شد: {alert.symbol}"
            body = f"نماد {alert.symbol} از کاتالوگ بازار خارج شد و هشدار مربوطه به صورت خودکار غیرفعال گردید."
            payload = {
                "alert_id": alert.id,
                "symbol": alert.symbol,
                "status": "delisted_deactivated",
                "nature": alert.alert_nature or "price"
            }
            fallback_chat = (alert.telegram_chat_id or "").strip() or None
            try:
                await enqueue_alert_push(
                    alert, title, body, payload,
                    fallback_chat_id=fallback_chat,
                )
            except Exception as pe:
                print(f"⚠️ [CatalogSync] Failed to enqueue delist push for alert {alert.id}: {pe}")

    if deactivated_count > 0:
        await save_alerts_to_disk_async(ALERTS_DB)
        METRICS["delisted_alerts_deactivated"] = METRICS.get("delisted_alerts_deactivated", 0) + deactivated_count

    return deactivated_count


# -------------------------------------------------------------------------
# 3. MASTER TRANSACTION EXECUTION
# -------------------------------------------------------------------------
async def run_weekly_catalog_sync(
    candidate_items: Optional[List[Dict[str, Any]]] = None,
    dry_run: bool = False,
    ignore_safety: bool = False,
    protect_active_alerts: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Executes the 7-stage weekly catalog sync transaction:
    1. fetch -> 2. normalize -> 3. validate -> 4. diff -> 5. probe -> 6. dry-run -> 7. apply in transaction.
    - Soft delete only: (is_active=0, delisted_at=ISO)
    - Safety ceilings: empty list or >5% delist or >10% add -> halt + admin alert
    - User alerts for delisted symbols are automatically deactivated and notified.
    - Increments catalog_version, takes snapshot for rollback.
    """
    # Stage 1: FETCH
    if candidate_items is None:
        raw_candidates = fetch_candidate_catalog()
    else:
        raw_candidates = candidate_items

    # Stage 2 & 3: NORMALIZE & VALIDATE
    valid_candidates = validate_candidate_catalog(raw_candidates)

    current_catalog = load_catalog()

    # Stage 4: DIFF (protect active alerts and enforce consecutive failures threshold on automated sync)
    should_protect = protect_active_alerts if protect_active_alerts is not None else (candidate_items is None)
    diff = compute_catalog_diff(
        current_catalog,
        valid_candidates,
        protect_active_alerts=should_protect,
        require_consecutive_probe_failures=should_protect
    )
    stats = diff["stats"]

    # Stage 5: PRICE PROBE (probe added symbols)
    probe_results = {}
    if diff["added"]:
        probe_results = await probe_catalog_prices(diff["added"], sample_size=10)

    # Safety Check
    if not ignore_safety:
        check_sync_safety(stats)

    report = {
        "status": "dry_run_success" if dry_run else "applied_success",
        "dry_run": dry_run,
        "current_version": current_catalog.get("catalog_version", 1),
        "target_version": current_catalog.get("catalog_version", 1) if dry_run else current_catalog.get("catalog_version", 1) + 1,
        "stats": stats,
        "diff": {
            "added": [s["symbol"] for s in diff["added"]],
            "modified": [s["symbol"] for s in diff["modified"]],
            "delisted": [s["symbol"] for s in diff["delisted"]],
            "unchanged_count": len(diff["unchanged"])
        },
        "probe_results": probe_results,
        "executed_at": datetime.now(timezone.utc).isoformat()
    }

    # Stage 6: DRY-RUN (if dry_run=True, exit without applying)
    if dry_run:
        print(f"🔍 [CatalogSync] Dry-run finished. Changes: +{stats['added_count']}, ~{stats['modified_count']}, -{stats['delisted_count']}")
        return report

    # Stage 7: APPLY IN TRANSACTION (single writer: lock is held until the new catalog is saved)
    with catalog_write_lock():
        return await _apply_catalog_sync(current_catalog, diff, stats, report)


async def _apply_catalog_sync(
    current_catalog: Dict[str, Any],
    diff: Dict[str, Any],
    stats: Dict[str, Any],
    report: Dict[str, Any]
) -> Dict[str, Any]:
    """Stage 7 body; must be called with catalog_write_lock() held."""
    # Re-check under the lock: if another writer bumped the version since stage 1, abort instead of overwriting.
    on_disk_version = load_catalog().get("catalog_version", 1)
    if on_disk_version != current_catalog.get("catalog_version", 1):
        raise CatalogLockedError(
            f"Catalog changed during sync (v{current_catalog.get('catalog_version', 1)} -> v{on_disk_version}); aborting."
        )

    # A. Backup (snapshot) before every apply (Rollback safety)
    snapshot_path = save_catalog_snapshot(current_catalog)
    report["snapshot_path"] = snapshot_path

    # B. Build updated catalog symbols
    now_iso = datetime.now(timezone.utc).isoformat()
    new_version = current_catalog.get("catalog_version", 1) + 1

    # Index existing by symbol
    existing_symbols_map = {s["symbol"]: dict(s) for s in current_catalog.get("symbols", [])}

    # Update modified
    for mod in diff["modified"]:
        sym = mod["symbol"]
        cand = mod["new"]
        if sym in existing_symbols_map:
            existing_symbols_map[sym].update(cand)
            existing_symbols_map[sym]["is_active"] = 1
            existing_symbols_map[sym]["delisted_at"] = None

    # Add new
    for add in diff["added"]:
        sym = add["symbol"]
        item = dict(add)
        item["is_active"] = 1
        item["delisted_at"] = None
        item["added_at"] = now_iso
        existing_symbols_map[sym] = item

    # SOFT DELETE ONLY for delisted
    delisted_syms = []
    for delist in diff["delisted"]:
        sym = delist["symbol"]
        delisted_syms.append(sym)
        if sym in existing_symbols_map:
            # Soft delete: is_active=0, delisted_at=now_iso
            existing_symbols_map[sym]["is_active"] = 0
            existing_symbols_map[sym]["delisted_at"] = now_iso
            print(f"🗑️ [CatalogSync] Soft deleted symbol: {sym} (is_active=0, delisted_at={now_iso})")

    # C. Deactivate matching user alerts & notify via push outbox
    deactivated_count = await notify_users_and_deactivate_delisted(delisted_syms)
    report["deactivated_user_alerts"] = deactivated_count

    # D. Save updated catalog
    all_symbols = list(existing_symbols_map.values())
    active_symbols = [s for s in all_symbols if s.get("is_active", 1)]

    updated_catalog = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "catalog_version": new_version,
        "app_version": APP_VERSION,
        "last_sync_at": now_iso,
        "total_active": len(active_symbols),
        "total_symbols": len(all_symbols),
        "symbols": all_symbols
    }
    save_catalog(updated_catalog)

    # Record sync run in sync_runs.json
    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    run_record = {
        "run_id": run_id,
        "timestamp": now_iso,
        "version_from": current_catalog.get("catalog_version", 1),
        "version_to": new_version,
        "mode": "production",
        "status": "SUCCESS",
        "target_file": get_catalog_file(),
        "snapshot_path": snapshot_path,
        "total_symbols": len(all_symbols),
        "active_symbols": len(active_symbols),
        "added_count": stats.get("added_count", 0),
        "modified_count": stats.get("modified_count", 0),
        "delisted_count": stats.get("delisted_count", 0),
        "diff": {
            "added": [s["symbol"] for s in diff.get("added", [])],
            "modified": [s["symbol"] for s in diff.get("modified", [])],
            "delisted": [s["symbol"] for s in diff.get("delisted", [])]
        }
    }
    record_sync_run(run_record, filepath=get_sync_runs_file())
    report["run_id"] = run_id

    METRICS["catalog_version"] = new_version
    METRICS["last_catalog_sync_at"] = now_iso
    METRICS["total_catalog_syncs"] = METRICS.get("total_catalog_syncs", 0) + 1

    print(f"✅ [CatalogSync] Transaction applied successfully! Version bumped to {new_version}. Active: {len(active_symbols)} symbols.")
    return report


async def weekly_catalog_sync_job():
    """
    Scheduled job executed weekly (Saturday ~06:00 UTC).
    Wraps run_weekly_catalog_sync in try/except with metrics and admin notification.
    """
    print("⏰ [CatalogSync] Weekly scheduled catalog sync triggered.")
    try:
        report = await run_weekly_catalog_sync(dry_run=False)
        print(f"🎉 [CatalogSync] Scheduled sync completed: Version {report['target_version']}")
    except CatalogSafetyCeilingExceededError as se:
        print(f"🚨 [CatalogSync] Scheduled sync halted by safety check: {se}")
    except Exception as e:
        print(f"❌ [CatalogSync] Scheduled sync encountered unexpected error: {e}")
        METRICS["catalog_sync_errors"] = METRICS.get("catalog_sync_errors", 0) + 1
        METRICS["last_catalog_sync_error"] = str(e)
        msg = (
            f"❌ <b>[هشدار ادمین - خطای سنک هفتگی]</b>\n"
            f"⚠️ پیام خطا: <code>{str(e)}</code>\n"
            f"🔄 بررسی وضعیت در اندپوینت /api/admin/catalog/status"
        )
        try:
            from app.notifier.telegram import notify_admin_telegram
            from app.notifier.outbox import _spawn
            _spawn(notify_admin_telegram(msg))
        except Exception:
            pass


def get_last_sync_info() -> Dict[str, Any]:
    """Returns high-level summary of the last catalog sync state for admin monitoring."""
    cat = load_catalog()
    symbols = cat.get("symbols", [])
    active_count = sum(1 for s in symbols if s.get("is_active", 1) == 1)
    delisted_count = sum(1 for s in symbols if s.get("is_active", 1) == 0)
    last_sync = cat.get("last_sync_at") or METRICS.get("last_catalog_sync_at")
    last_err = METRICS.get("last_catalog_sync_error")
    return {
        "version": cat.get("version", 1),
        "last_sync_at": last_sync,
        "total_symbols": len(symbols),
        "active_symbols": active_count,
        "delisted_symbols": delisted_count,
        "total_syncs": METRICS.get("total_catalog_syncs", 0),
        "last_error": last_err,
        "has_error": bool(last_err),
        "admin_alerts_count": METRICS.get("catalog_sync_admin_alerts", 0),
        "status": "ERROR" if last_err else ("HEALTHY" if last_sync else "INITIALIZED")
    }
