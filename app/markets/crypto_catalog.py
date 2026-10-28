# -*- coding: utf-8 -*-
"""
AlertG — Dynamic Crypto Exchange Catalog Service (Phase 5).
Manages per-exchange isolated symbol catalogs:
1. One catalog file per exchange in a dedicated directory ('crypto_catalogs/<exchange>.json'),
   completely separate from catalog.json (zero mutation of catalog.json or general catalog_version).
2. Safety Engine:
   - Rejects catalogs containing fewer than 20 pairs (MIN_PAIRS_CEILING).
   - Rejects catalogs dropping more than 50% compared to previous valid version (MAX_DROP_RATIO).
   - Preserves previous valid catalog on disk, marks it 'is_stale=True', and alerts admin.
   - Atomic writes using temp files and os.replace to prevent file corruption on crash.
3. Isolated execution: failure of one exchange catalog query never halts others.
4. Scheduled background synchronization & admin triggering.
"""

import os
import time
import json
import logging
import tempfile
from typing import Dict, Any, Optional, List, Tuple

import httpx

import app.config as config

logger = logging.getLogger("signalalert.crypto_catalog")


async def _safe_notify_admin(message: str, client: Optional[httpx.AsyncClient] = None):
    """Safely dispatches admin notification without hard dependency on full storage stack."""
    try:
        from app.notifier.telegram import notify_admin_telegram
        await notify_admin_telegram(message, client=client)
    except Exception as e:
        logger.info(f"ℹ️ [Admin Alert Notice]: {message} (dispatch info: {e})")


SUPPORTED_CRYPTO_EXCHANGES = [
    "binance",
    "mexc",
    "kucoin",
    "gateio",
    "lbank",
    "okx",
    "kraken",
]

DEFAULT_SYNC_HOURS = 6


class CryptoCatalogSafetyError(Exception):
    """Raised when an incoming catalog fails safety ceiling checks."""
    pass


def get_catalog_dir(override_dir: Optional[str] = None) -> str:
    """Returns absolute path to the crypto catalogs directory."""
    if override_dir:
        return os.path.abspath(override_dir)
    cfg_dir = getattr(config, "CRYPTO_CATALOG_DIR", "crypto_catalogs")
    return os.path.abspath(cfg_dir)


def get_catalog_path(exchange_id: str, override_dir: Optional[str] = None) -> str:
    """Returns absolute file path for a specific exchange catalog."""
    c_dir = get_catalog_dir(override_dir)
    return os.path.join(c_dir, f"{exchange_id.lower().strip()}.json")


def get_exchange_adapter(exchange_id: str):
    """Instantiates the isolated adapter for the given exchange."""
    ex = (exchange_id or "").lower().strip()
    if ex == "binance":
        from app.markets.adapters.binance import BinanceAdapter
        return BinanceAdapter()
    elif ex == "mexc":
        from app.markets.adapters.mexc import MEXCAdapter
        return MEXCAdapter()
    elif ex == "kucoin":
        from app.markets.adapters.kucoin import KuCoinAdapter
        return KuCoinAdapter()
    elif ex in ("gateio", "gate"):
        from app.markets.adapters.gateio import GateioAdapter
        return GateioAdapter()
    elif ex == "lbank":
        from app.markets.adapters.lbank import LBankAdapter
        return LBankAdapter()
    elif ex == "okx":
        from app.markets.adapters.okx import OKXAdapter
        return OKXAdapter()
    elif ex == "kraken":
        from app.markets.adapters.kraken import KrakenAdapter
        return KrakenAdapter()
    return None


def load_exchange_catalog(exchange_id: str, override_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Loads exchange catalog from disk.
    Returns empty dict if file does not exist or cannot be parsed.
    """
    path = get_catalog_path(exchange_id, override_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        logger.warning(f"Failed to load catalog from {path}: {e}")
    return {}


def save_exchange_catalog_atomic(
    exchange_id: str,
    data: Dict[str, Any],
    override_dir: Optional[str] = None
) -> str:
    """
    Atomically writes exchange catalog to disk.
    Uses tempfile in the target directory and os.replace to guarantee atomic commit.
    """
    c_dir = get_catalog_dir(override_dir)
    os.makedirs(c_dir, exist_ok=True)
    target_path = get_catalog_path(exchange_id, override_dir)

    temp_fd, temp_path = tempfile.mkstemp(
        prefix=f".tmp_{exchange_id}_",
        suffix=".json",
        dir=c_dir
    )
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, target_path)
        return target_path
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise


def validate_catalog_safety(
    exchange_id: str,
    new_pairs: List[Dict[str, Any]],
    existing_catalog: Dict[str, Any],
    ignore_safety: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    Validates safety rules for incoming catalog data:
    1. Minimum pair ceiling: new_pairs >= MIN_PAIRS_CEILING (default 20).
    2. Drop ceiling: if existing catalog has >= MIN_PAIRS_CEILING, new_pairs must not drop
       below (prev_count * MAX_DROP_RATIO) (default 50% drop ceiling).
    """
    if ignore_safety:
        return True, None

    min_pairs = int(getattr(config, "CRYPTO_CATALOG_MIN_PAIRS", 20))
    max_drop_ratio = float(getattr(config, "CRYPTO_CATALOG_MAX_DROP_RATIO", 0.50))

    new_count = len(new_pairs)
    if new_count < min_pairs:
        msg = f"Catalog rejected for '{exchange_id}': incoming pairs ({new_count}) is below minimum ceiling ({min_pairs})."
        return False, msg

    prev_pairs = existing_catalog.get("pairs", [])
    prev_count = len(prev_pairs)
    if prev_count >= min_pairs:
        min_allowed = int(prev_count * max_drop_ratio)
        if new_count < min_allowed:
            pct_drop = int((1.0 - (new_count / prev_count)) * 100)
            msg = (
                f"Catalog rejected for '{exchange_id}': pair count dropped by {pct_drop}% "
                f"from {prev_count} to {new_count} (exceeds {int((1.0 - max_drop_ratio)*100)}% maximum allowed drop)."
            )
            return False, msg

    return True, None


async def sync_exchange_catalog(
    exchange_id: str,
    client: Optional[httpx.AsyncClient] = None,
    ignore_safety: bool = False,
    override_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Scrapes and synchronizes the symbol catalog for a single exchange.
    Enforces isolation, safety ceiling, and atomic storage.
    """
    ex_id = exchange_id.lower().strip()
    if ex_id not in SUPPORTED_CRYPTO_EXCHANGES:
        return {
            "exchange": ex_id,
            "success": False,
            "error_code": "UNKNOWN_EXCHANGE",
            "error": f"Exchange '{ex_id}' is not in supported crypto exchanges list."
        }

    adapter = get_exchange_adapter(ex_id)
    if not adapter:
        return {
            "exchange": ex_id,
            "success": False,
            "error_code": "ADAPTER_NOT_FOUND",
            "error": f"No adapter found for exchange '{ex_id}'."
        }

    existing_catalog = load_exchange_catalog(ex_id, override_dir)

    own_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))
        own_client = True

    try:
        symbols, err_code, err_msg = await adapter.fetch_symbols(client)
        if err_code:
            # Mark existing catalog as stale if available
            if existing_catalog:
                existing_catalog["is_stale"] = True
                existing_catalog["error"] = f"Sync failed: {err_msg}"
                save_exchange_catalog_atomic(ex_id, existing_catalog, override_dir)

            admin_msg = (
                f"⚠️ <b>[Crypto Catalog Sync Error]</b>\n"
                f"Exchange: <b>{adapter.display_name}</b>\n"
                f"Error: {err_code} — {err_msg}"
            )
            await _safe_notify_admin(admin_msg, client=client)

            return {
                "exchange": ex_id,
                "success": False,
                "error_code": err_code,
                "error": err_msg,
                "is_stale": True,
                "pairs_count": len(existing_catalog.get("pairs", [])) if existing_catalog else 0
            }

        # Format symbols to catalog pair format
        new_pairs = [
            {
                "base": s.base,
                "quote": s.quote,
                "native_symbol": s.market_symbol,
                "is_active": s.is_active,
                "is_etf": s.is_etf,
                "min_price": s.min_price,
                "min_qty": s.min_qty,
            }
            for s in symbols
        ]

        # Verify safety rules
        is_safe, safety_reason = validate_catalog_safety(
            ex_id, new_pairs, existing_catalog, ignore_safety=ignore_safety
        )

        if not is_safe:
            # Reject replacement; retain previous catalog on disk but flag as stale
            if existing_catalog:
                existing_catalog["is_stale"] = True
                existing_catalog["error"] = safety_reason
                save_exchange_catalog_atomic(ex_id, existing_catalog, override_dir)

            admin_alert = (
                f"🚨 <b>[Crypto Catalog Safety Ceiling Breach]</b>\n"
                f"Exchange: <b>{adapter.display_name}</b>\n"
                f"Reason: {safety_reason}\n"
                f"Action: Existing catalog preserved and flagged STALE."
            )
            await _safe_notify_admin(admin_alert, client=client)

            return {
                "exchange": ex_id,
                "success": False,
                "safety_rejected": True,
                "reason": safety_reason,
                "is_stale": True,
                "pairs_count": len(existing_catalog.get("pairs", [])) if existing_catalog else 0
            }

        # Safety checks passed -> Save atomically
        now_ts = int(time.time())
        catalog_payload = {
            "exchange": ex_id,
            "display_name": adapter.display_name,
            "updated_at": now_ts,
            "total_pairs": len(new_pairs),
            "is_stale": False,
            "error": None,
            "pairs": new_pairs,
        }
        saved_path = save_exchange_catalog_atomic(ex_id, catalog_payload, override_dir)

        return {
            "exchange": ex_id,
            "display_name": adapter.display_name,
            "success": True,
            "total_pairs": len(new_pairs),
            "is_stale": False,
            "updated_at": now_ts,
            "saved_path": saved_path,
        }

    finally:
        if own_client and hasattr(client, "aclose"):
            res = client.aclose()
            if hasattr(res, "__await__"):
                await res



async def sync_all_crypto_catalogs(
    client: Optional[httpx.AsyncClient] = None,
    ignore_safety: bool = False,
    override_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Synchronizes symbol catalogs for all supported crypto exchanges.
    Strict failure isolation: an exception or error in one exchange NEVER impedes others.
    """
    results: Dict[str, Any] = {}
    success_count = 0

    own_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))
        own_client = True

    try:
        for ex_id in SUPPORTED_CRYPTO_EXCHANGES:
            try:
                res = await sync_exchange_catalog(
                    ex_id,
                    client=client,
                    ignore_safety=ignore_safety,
                    override_dir=override_dir
                )
                results[ex_id] = res
                if res.get("success"):
                    success_count += 1
            except Exception as e:
                logger.exception(f"Unexpected error while syncing catalog for {ex_id}: {e}")
                results[ex_id] = {
                    "exchange": ex_id,
                    "success": False,
                    "error_code": "INTERNAL_ERROR",
                    "error": str(e),
                    "is_stale": True
                }

        return {
            "timestamp": int(time.time()),
            "total_exchanges": len(SUPPORTED_CRYPTO_EXCHANGES),
            "success_count": success_count,
            "results": results
        }
    finally:
        if own_client and hasattr(client, "aclose"):
            res = client.aclose()
            if hasattr(res, "__await__"):
                await res



def get_crypto_catalogs_status(override_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns high-level health and status of all exchange catalogs on disk.
    """
    c_dir = get_catalog_dir(override_dir)
    status_map: Dict[str, Any] = {}

    for ex_id in SUPPORTED_CRYPTO_EXCHANGES:
        path = get_catalog_path(ex_id, override_dir)
        if not os.path.exists(path):
            status_map[ex_id] = {
                "file_exists": False,
                "total_pairs": 0,
                "updated_at": None,
                "is_stale": True,
                "error": "Catalog file does not exist yet"
            }
            continue

        cat = load_exchange_catalog(ex_id, override_dir)
        status_map[ex_id] = {
            "file_exists": True,
            "total_pairs": cat.get("total_pairs", len(cat.get("pairs", []))),
            "updated_at": cat.get("updated_at"),
            "is_stale": cat.get("is_stale", False),
            "error": cat.get("error")
        }

    return {
        "catalogs_dir": c_dir,
        "total_exchanges": len(SUPPORTED_CRYPTO_EXCHANGES),
        "exchanges": status_map
    }


async def crypto_catalog_sync_job():
    """Periodic job called by background scheduler."""
    logger.info("⏰ [Scheduler] Starting periodic crypto catalog sync...")
    try:
        report = await sync_all_crypto_catalogs()
        logger.info(
            f"✅ [Scheduler] Crypto catalog sync finished: {report['success_count']}/{report['total_exchanges']} succeeded."
        )
    except Exception as e:
        logger.exception(f"❌ [Scheduler] Crypto catalog sync job failed: {e}")
