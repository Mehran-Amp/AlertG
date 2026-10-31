# -*- coding: utf-8 -*-
"""
AlertG — Dynamic Crypto Exchange Catalog Service (Phase 1 Fix / Version 2).
Manages per-exchange isolated symbol catalogs:
1. One catalog file per exchange in a dedicated directory ('DATA_DIR/crypto_catalog/<exchange>.json'),
   completely separate from catalog.json (zero mutation of catalog.json or general catalog_version).
2. Safety Engine:
   - Rejects catalogs containing fewer than 20 pairs (MIN_PAIRS_CEILING).
   - Rejects catalogs dropping more than 50% compared to previous valid version (MAX_DROP_RATIO).
   - Preserves previous valid catalog on disk, marks it 'is_stale=True', and alerts admin.
   - Atomic writes using temp files and os.replace to prevent file corruption on crash.
3. Isolated execution: failure of one exchange catalog query never halts others.
4. Single Source of Truth: Reads supported exchanges from crypto_registry.py (Rule R5).
5. Staleness by age: Catalogs older than 2 sync intervals (12 hours) automatically flag as stale.
6. Native Symbol & Alias Index Resolver: resolve_pair(exchange, symbol_or_base).
"""

import os
import time
import json
import logging
import tempfile
from typing import Dict, Any, Optional, List, Tuple

import httpx

import app.config as config
from app.markets.crypto_registry import (
    get_crypto_exchange,
    get_supported_exchange_ids,
    is_supported_crypto_exchange,
)

logger = logging.getLogger("signalalert.crypto_catalog")


async def _safe_notify_admin(message: str, client: Optional[httpx.AsyncClient] = None):
    """Safely dispatches admin notification without hard dependency on full storage stack."""
    try:
        from app.notifier.telegram import notify_admin_telegram
        await notify_admin_telegram(message, client=client)
    except Exception as e:
        logger.info(f"ℹ️ [Admin Alert Notice]: {message} (dispatch info: {e})")


def get_supported_crypto_exchanges() -> List[str]:
    """Returns dynamic list of active supported exchange IDs from the registry."""
    return get_supported_exchange_ids(active_only=True)


# Module-level alias for backward compatibility with existing tests and imports
SUPPORTED_CRYPTO_EXCHANGES = get_supported_exchange_ids(active_only=True)
DEFAULT_SYNC_HOURS = 6


class CryptoCatalogSafetyError(Exception):
    """Raised when an incoming catalog fails safety ceiling checks."""
    pass


def get_catalog_dir(override_dir: Optional[str] = None) -> str:
    """Returns absolute path to the crypto catalogs directory (derived from DATA_DIR)."""
    if override_dir:
        return os.path.abspath(override_dir)
    data_dir = getattr(config, "DATA_DIR", ".")
    candidate_1 = os.path.join(data_dir, "crypto_catalog")
    candidate_2 = os.path.join(data_dir, "crypto_catalogs")
    cfg_dir = getattr(config, "CRYPTO_CATALOG_DIR", None)
    if cfg_dir:
        return os.path.abspath(cfg_dir)
    if os.path.exists(candidate_1):
        return os.path.abspath(candidate_1)
    if os.path.exists(candidate_2):
        return os.path.abspath(candidate_2)
    return os.path.abspath(candidate_1)


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
    elif ex == "bybit":
        from app.markets.adapters.bybit import BybitAdapter
        return BybitAdapter()
    elif ex == "bitget":
        from app.markets.adapters.bitget import BitgetAdapter
        return BitgetAdapter()
    return None


def load_exchange_catalog(exchange_id: str, override_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Loads exchange catalog from disk.
    If the file does not exist, returns empty structure with empty pairs.
    """
    path = get_catalog_path(exchange_id, override_dir)
    if not os.path.exists(path):
        return {
            "exchange": exchange_id,
            "updated_at": 0,
            "total_pairs": 0,
            "is_stale": True,
            "error": "Catalog file does not exist",
            "pairs": [],
        }

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {
                "exchange": exchange_id,
                "updated_at": 0,
                "total_pairs": 0,
                "is_stale": True,
                "error": "Invalid format on disk",
                "pairs": [],
            }
    except Exception as e:
        logger.error(f"Failed to read crypto catalog for {exchange_id} from {path}: {e}")
        return {
            "exchange": exchange_id,
            "updated_at": 0,
            "total_pairs": 0,
            "is_stale": True,
            "error": f"Read error: {e}",
            "pairs": [],
        }


def save_exchange_catalog_atomic(
    exchange_id: str,
    catalog_data: Dict[str, Any],
    override_dir: Optional[str] = None
) -> str:
    """
    Atomically writes the catalog payload to disk using a temporary file and os.replace.
    Ensures that power loss or worker kill never leaves a corrupted/empty JSON file.
    """
    c_dir = get_catalog_dir(override_dir)
    os.makedirs(c_dir, exist_ok=True)
    target_path = get_catalog_path(exchange_id, override_dir)

    temp_fd, temp_path = tempfile.mkstemp(
        dir=c_dir,
        prefix=f"{exchange_id}_catalog_tmp_",
        suffix=".json"
    )
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            json.dump(catalog_data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_path, target_path)
        logger.info(
            f"✅ [Catalog Storage] Atomically persisted {exchange_id} catalog: "
            f"{catalog_data.get('total_pairs', len(catalog_data.get('pairs', [])))} pairs at {target_path}"
        )
        return target_path
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise e


MIN_PAIRS_CEILING = 20
MAX_DROP_RATIO = 0.50


def validate_catalog_safety(
    exchange_id: str,
    incoming_pairs: List[Dict[str, Any]],
    existing_catalog: Optional[Dict[str, Any]],
    ignore_safety: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    Validates incoming pairs against safety ceilings:
    1. Rejects if incoming count < MIN_PAIRS_CEILING (20 pairs).
    2. Rejects if incoming count drops > 50% from previously recorded valid catalog.
    """
    if ignore_safety:
        return True, None

    new_count = len(incoming_pairs)

    # 1. Minimum ceiling check
    if new_count < MIN_PAIRS_CEILING:
        reason = (
            f"Catalog for '{exchange_id}' contains only {new_count} pairs, "
            f"which is below minimum ceiling of {MIN_PAIRS_CEILING}."
        )
        return False, reason

    # 2. Maximum drop check
    if existing_catalog:
        prev_pairs = existing_catalog.get("pairs", [])
        prev_count = len(prev_pairs)
        if prev_count >= MIN_PAIRS_CEILING:
            drop_ratio = (prev_count - new_count) / float(prev_count)
            if drop_ratio > MAX_DROP_RATIO:
                drop_pct = round(drop_ratio * 100, 1)
                drop_int = int(drop_pct)
                reason = (
                    f"Catalog for '{exchange_id}' dropped by {drop_int}% "
                    f"({prev_count} -> {new_count} pairs). Exceeds MAX_DROP_RATIO of 50%."
                )
                return False, reason

    return True, None


async def sync_exchange_catalog(
    exchange_id: str,
    client: Optional[httpx.AsyncClient] = None,
    ignore_safety: bool = False,
    override_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Queries exchange public API, validates data, and updates catalog atomically.
    If safety checks fail or network fails, keeps previous valid version on disk with is_stale=True.
    """
    ex_id = (exchange_id or "").lower().strip()
    adapter = get_exchange_adapter(ex_id)
    if not adapter:
        return {
            "exchange": ex_id,
            "success": False,
            "error_code": "UNKNOWN_EXCHANGE",
            "error": f"No adapter registered for exchange '{ex_id}'",
            "is_stale": True
        }

    own_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))
        own_client = True

    try:
        # Load existing catalog to check for drops
        existing_catalog = load_exchange_catalog(ex_id, override_dir)

        # Fetch market symbols
        symbols, err_code, err_msg = await adapter.fetch_symbols(client)

        if err_code or not symbols:
            # Mark existing catalog as stale
            if existing_catalog and existing_catalog.get("pairs"):
                existing_catalog["is_stale"] = True
                existing_catalog["error"] = f"Sync failed: {err_code} — {err_msg}"
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

        # Format symbols to catalog pair format with alias index (Task 6)
        new_pairs = [
            {
                "symbol": f"{s.base}{s.quote}",
                "base": s.base,
                "quote": s.quote,
                "native_symbol": s.market_symbol,
                "is_active": s.is_active,
                "is_leveraged": s.is_etf,
                "is_etf": s.is_etf,
                "aliases": [
                    f"{s.base}{s.quote}",
                    s.market_symbol,
                    s.base,
                    s.market_symbol.upper(),
                    s.market_symbol.lower(),
                ],
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
                f"Alert: {safety_reason}\n"
                f"<i>Previous catalog preserved on disk with is_stale=True.</i>"
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


sync_single_exchange_catalog = sync_exchange_catalog


async def sync_all_crypto_catalogs(
    client: Optional[httpx.AsyncClient] = None,
    ignore_safety: bool = False,
    override_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Synchronizes symbol catalogs for all supported active crypto exchanges.
    Strict failure isolation: an exception or error in one exchange NEVER impedes others.
    """
    results: Dict[str, Any] = {}
    success_count = 0
    supported = get_supported_crypto_exchanges()

    own_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))
        own_client = True

    try:
        for ex_id in supported:
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
            "total_exchanges": len(supported),
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
    Returns high-level health and status of all active exchange catalogs on disk.
    Enforces Staleness by Age: Catalogs older than 2 sync intervals (12 hours) are flagged is_stale=True.
    """
    c_dir = get_catalog_dir(override_dir)
    status_map: Dict[str, Any] = {}
    supported = get_supported_crypto_exchanges()
    now_ts = int(time.time())
    max_age_seconds = getattr(config, "CRYPTO_CATALOG_MAX_AGE_SECONDS", DEFAULT_SYNC_HOURS * 2 * 3600)

    for ex_id in supported:
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
        updated_at = cat.get("updated_at")
        is_stale_flag = cat.get("is_stale", False)
        is_stale_by_age = False
        if updated_at:
            try:
                age_sec = now_ts - int(updated_at)
                if age_sec > max_age_seconds:
                    is_stale_by_age = True
            except (ValueError, TypeError):
                is_stale_by_age = True

        status_map[ex_id] = {
            "file_exists": True,
            "total_pairs": cat.get("total_pairs", len(cat.get("pairs", []))),
            "updated_at": updated_at,
            "is_stale": is_stale_flag or is_stale_by_age,
            "error": cat.get("error") or ("Catalog data is stale by age (> 12h)" if is_stale_by_age else None)
        }

    return {
        "catalogs_dir": c_dir,
        "total_exchanges": len(supported),
        "exchanges": status_map
    }


get_all_catalogs_status = get_crypto_catalogs_status


def resolve_pair(
    exchange_id: str,
    symbol_or_base: str,
    override_dir: Optional[str] = None,
    base_currency: Optional[str] = None,
    counter_currency: Optional[str] = None,
    market_symbol: Optional[str] = None,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Resolves an alert symbol or base currency to its exact exchange catalog pair.
    Uses the exchange's catalog alias index (Rule R1 / Task 6).
    Prioritizes market_symbol and base_currency with symbol_or_base as fallback (Phase 4 / F4).
    Returns: (status, pair_dict)
    status: 'OK' | 'UNKNOWN_EXCHANGE' | 'SYMBOL_NOT_LISTED'
    """
    ex_meta = get_crypto_exchange(exchange_id)
    if not ex_meta:
        return "UNKNOWN_EXCHANGE", None

    ex_id = ex_meta.id

    # If quote currency is specified and is non-USDT, reject for spot crypto
    if counter_currency and str(counter_currency).strip().upper() != "USDT":
        return "SYMBOL_NOT_LISTED", None

    query = (symbol_or_base or "").strip()
    m_sym = (market_symbol or "").strip()
    b_curr = (base_currency or "").strip()

    if not query and not m_sym and not b_curr:
        return "SYMBOL_NOT_LISTED", None

    # 1. Lookup in persisted catalog if present
    cat = load_exchange_catalog(ex_id, override_dir)
    pairs = cat.get("pairs", [])
    if pairs:
        q_upper = query.upper()
        q_lower = query.lower()
        q_norm = q_upper.replace("-", "").replace("_", "").replace("/", "")

        m_upper = m_sym.upper() if m_sym else ""
        m_lower = m_sym.lower() if m_sym else ""
        b_upper = b_curr.upper() if b_curr else ""

        for p in pairs:
            native = str(p.get("native_symbol", ""))
            base = str(p.get("base", ""))
            sym = str(p.get("symbol", f"{base}USDT"))
            aliases = p.get("aliases", [])

            # Match priority: market_symbol -> base_currency -> query
            matched = False
            if m_sym and (m_sym == native or m_upper == native.upper() or m_lower == native.lower()):
                matched = True
            elif b_curr and (b_upper == base.upper() or b_curr == base):
                matched = True
            elif query and (
                query == native or
                q_upper == sym or
                q_upper == base or
                q_lower == native.lower() or
                q_upper == native.upper() or
                q_norm == sym or
                query in aliases or
                q_upper in aliases or
                q_lower in aliases
            ):
                matched = True

            if matched:
                return "OK", {
                    "symbol": sym,
                    "base": base,
                    "quote": p.get("quote", "USDT"),
                    "native_symbol": native,
                    "is_leveraged": bool(p.get("is_leveraged", p.get("is_etf", False))),
                }

        return "SYMBOL_NOT_LISTED", None

    # 2. Fallback when catalog has not been seeded yet on disk
    adapter = get_exchange_adapter(ex_id)
    if adapter:
        if m_sym:
            native = m_sym
            base = adapter.to_canonical_base(native)
        elif b_curr:
            base = b_curr.upper()
            native = adapter.to_native_symbol(base)
        else:
            native = adapter.to_native_symbol(query)
            base = adapter.to_canonical_base(native)

        sym = f"{base}USDT"
        from app.markets.adapters.base import is_leveraged_token
        return "OK", {
            "symbol": sym,
            "base": base,
            "quote": "USDT",
            "native_symbol": native,
            "is_leveraged": is_leveraged_token(base),
        }

    if ex_meta.status == 'pending_adapter':
        q_clean = query.upper().replace("-", "").replace("_", "").replace("/", "")
        base = q_clean[:-4] if q_clean.endswith("USDT") and len(q_clean) > 4 else q_clean
        sym = f"{base}USDT"
        return "OK", {
            "symbol": sym,
            "base": base,
            "quote": "USDT",
            "native_symbol": sym,
            "is_leveraged": False,
        }

    return "SYMBOL_NOT_LISTED", None


async def crypto_catalog_sync_job():
    """Periodic job called by background scheduler."""
    logger.info("⏰ [Scheduler] Starting periodic crypto catalog sync...")
    try:
        report = await sync_all_crypto_catalogs()
        logger.info(
            f"✅ [Scheduler] Crypto catalog sync finished: {report['success_count']}/{report['total_exchanges']} succeeded."
        )
        # Phase 9: Delisted coin check & notification dispatch
        try:
            from app.markets.crypto_lifecycle import check_and_process_delisted_crypto_alerts
            await check_and_process_delisted_crypto_alerts()
        except Exception as le:
            logger.warning(f"⚠️ [Lifecycle] Warning running delisted crypto alerts check: {le}")
    except Exception as e:
        logger.exception(f"❌ [Scheduler] Crypto catalog sync job failed: {e}")
