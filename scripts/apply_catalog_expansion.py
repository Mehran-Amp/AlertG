#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SignalAlert Phase 2 Catalog Expansion Engine (v3.9.1)

Applies verified candidate symbols (ETFs and Stocks) to the primary catalog:
- Custom safety limits (added <= 300, 0 modified, 0 delisted, 0 id/symbol collisions)
- Preserves all 571 existing catalog symbols without modification
- Creates pre-apply snapshot v2 in catalog_snapshots/
- Sets catalog_version=3, app_version=APP_VERSION (3.9.1), total_symbols=772, total_active=772
- Standardizes schema: unit ($ for stocks, USD for ETFs), nameFa=nameEn, removes exchange/asset_class
- Injects verification metadata: source, verified_provider, last_verified_at
"""

import os
import sys
import json
import asyncio
import argparse
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.config import (
    APP_VERSION, CATALOG_SCHEMA_VERSION, CATALOG_FILE, CATALOG_SNAPSHOTS_DIR
)
from app.engine.sync import (
    load_catalog, save_catalog, save_catalog_snapshot,
    catalog_write_lock, compute_catalog_diff, _apply_catalog_sync,
    CatalogLockedError, get_catalog_file
)


class ExpansionSafetyViolation(Exception):
    """Raised when safety limits or invariants for catalog expansion are violated."""
    pass


def parse_args():
    parser = argparse.ArgumentParser(
        description="SignalAlert Catalog Expansion Engine v3.9.1"
    )
    parser.add_argument(
        "--candidate",
        type=str,
        default=os.path.join(ROOT, "candidate_catalog_phase2.json"),
        help="Path to candidate catalog JSON file (default: candidate_catalog_phase2.json)"
    )
    parser.add_argument(
        "--exclude",
        type=str,
        default="SPLG",
        help="Comma-separated ticker symbols to exclude from candidate expansion (default: SPLG)"
    )
    parser.add_argument(
        "--verified-at",
        type=str,
        default=None,
        help="Probe verification UTC ISO timestamp (default: current UTC time or candidate fetched_at)"
    )
    parser.add_argument(
        "--verified-provider",
        type=str,
        default="yahoo",
        help="Provider that verified the candidate symbols (default: yahoo)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the expansion without modifying catalog.json or saving snapshots."
    )
    return parser.parse_args()


def transform_candidate_symbol(
    cand: Dict[str, Any],
    verified_at: str,
    verified_provider: str
) -> Dict[str, Any]:
    """
    Standardizes candidate symbol according to Catalog v3 schema:
    - Retains: id, symbol, nameEn, nameFa (= nameEn), category, marketName, currency
    - Sets: unit ('$' for stock, 'USD' for etf)
    - Sets: tier ('popular'), data_frequency ('live'), is_delayed (False), is_active (1), delisted_at (None)
    - Retains: provider_map
    - For stocks: retains is_adr and country
    - Strips: exchange and asset_class (redundant with marketName and category)
    - Adds: source ('curated owner list 2026-10-20'), verified_provider, last_verified_at
    """
    sym = (cand.get("symbol") or cand.get("id") or "").strip()
    sym_id = (cand.get("id") or sym).strip()
    name_en = (cand.get("nameEn") or sym).strip()
    category = (cand.get("category") or cand.get("asset_class") or "").strip().lower()
    market = (cand.get("marketName") or cand.get("exchange") or "Global").strip()
    currency = (cand.get("currency") or "USD").strip().upper()

    if category == "stock":
        unit = "$"
    elif category == "etf":
        unit = "USD"
    else:
        unit = (cand.get("unit") or "$").strip()

    provider_map = cand.get("provider_map")
    if not provider_map or not isinstance(provider_map, dict):
        provider_map = {
            verified_provider: {"symbol": sym, "priority": 1}
        }

    transformed: Dict[str, Any] = {
        "id": sym_id,
        "symbol": sym,
        "nameEn": name_en,
        "nameFa": name_en,  # Strictly nameEn to avoid guessed translations
        "category": category,
        "marketName": market,
        "unit": unit,
        "currency": currency,
        "is_active": 1,
        "delisted_at": None,
        "tier": cand.get("tier", "popular"),
        "provider_map": provider_map,
        "data_frequency": cand.get("data_frequency", "live"),
        "is_delayed": bool(cand.get("is_delayed", False)),
        "source": "curated owner list 2026-10-20",
        "verified_provider": verified_provider,
        "last_verified_at": verified_at
    }

    if category == "stock":
        transformed["is_adr"] = bool(cand.get("is_adr", False))
        transformed["country"] = (cand.get("country") or "United States").strip()

    return transformed


def load_and_filter_candidates(
    candidate_path: str,
    exclude_symbols: List[str],
    verified_at: str,
    verified_provider: str
) -> Tuple[List[Dict[str, Any]], str]:
    """Loads candidates from file, filters out excluded symbols, and transforms schema."""
    if not os.path.exists(candidate_path):
        raise FileNotFoundError(f"Candidate file not found: {candidate_path}")

    with open(candidate_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    raw_symbols = data.get("symbols", []) if isinstance(data, dict) else data
    fallback_verified_at = verified_at or (data.get("fetched_at") if isinstance(data, dict) else None)
    eff_verified_at = fallback_verified_at or datetime.now(timezone.utc).isoformat()

    exclude_set = {s.upper().strip() for s in exclude_symbols if s.strip()}

    filtered_and_transformed: List[Dict[str, Any]] = []
    seen_ids = set()
    seen_syms = set()

    for item in raw_symbols:
        s_id = (item.get("id") or item.get("symbol") or "").strip().upper()
        s_sym = (item.get("symbol") or item.get("id") or "").strip().upper()

        if s_id in exclude_set or s_sym in exclude_set:
            continue

        if s_id in seen_ids or s_sym in seen_syms:
            raise ExpansionSafetyViolation(f"Duplicate candidate detected in candidate file: {s_id}")

        seen_ids.add(s_id)
        seen_syms.add(s_sym)

        transformed = transform_candidate_symbol(item, eff_verified_at, verified_provider)
        filtered_and_transformed.append(transformed)

    return filtered_and_transformed, eff_verified_at


def apply_expansion(
    candidate_path: Optional[str] = None,
    exclude: Optional[str] = "SPLG",
    verified_at: Optional[str] = None,
    verified_provider: str = "yahoo",
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Executes the catalog expansion under lock with strict safety boundaries:
    - Safety: added <= 300, 0 modified, 0 delisted, 0 existing collisions
    - Pre-apply snapshot v2 created
    - catalog_version incremented from 2 to 3
    - app_version = APP_VERSION (3.9.1)
    """
    target_candidate = candidate_path or os.path.join(ROOT, "candidate_catalog_phase2.json")
    exclude_list = [s.strip() for s in (exclude or "").split(",") if s.strip()]

    # 1. Load current catalog
    current_catalog = load_catalog()
    current_ver = current_catalog.get("catalog_version", 1)
    existing_symbols = current_catalog.get("symbols", [])
    active_existing = [s for s in existing_symbols if s.get("is_active", 1)]

    # 2. Load & filter candidates
    candidates, eff_verified_at = load_and_filter_candidates(
        target_candidate, exclude_list, verified_at, verified_provider
    )

    # 3. Collision check against existing catalog (IDs and symbols)
    existing_ids = {s.get("id", "").upper().strip() for s in existing_symbols if s.get("id")}
    existing_syms = {s.get("symbol", "").upper().strip() for s in existing_symbols if s.get("symbol")}

    collisions = []
    for cand in candidates:
        c_id = cand["id"].upper().strip()
        c_sym = cand["symbol"].upper().strip()
        if c_id in existing_ids:
            collisions.append(f"ID collision: {cand['id']}")
        if c_sym in existing_syms:
            collisions.append(f"Symbol collision: {cand['symbol']}")

    if collisions:
        raise ExpansionSafetyViolation(
            f"Candidate collision with existing catalog symbols: {', '.join(collisions[:5])}"
        )

    # 4. Compute diff against universe of (existing active + candidates)
    universe = [dict(s) for s in active_existing] + candidates
    diff = compute_catalog_diff(
        current_catalog=current_catalog,
        candidate_items=universe,
        protect_active_alerts=False,
        require_consecutive_probe_failures=False
    )
    stats = diff["stats"]

    # 5. Strict safety ceilings
    added_count = len(diff["added"])
    modified_count = len(diff["modified"])
    delisted_count = len(diff["delisted"])

    if added_count == 0:
        raise ExpansionSafetyViolation("Expansion aborted: 0 symbols to add.")
    if added_count > 300:
        raise ExpansionSafetyViolation(
            f"Expansion safety ceiling exceeded: {added_count} symbols to add exceeds max 300."
        )
    if modified_count > 0:
        raise ExpansionSafetyViolation(
            f"Expansion safety violation: {modified_count} existing symbols modified; must be 0."
        )
    if delisted_count > 0:
        raise ExpansionSafetyViolation(
            f"Expansion safety violation: {delisted_count} existing symbols delisted; must be 0."
        )

    target_total = len(existing_symbols) + added_count

    report: Dict[str, Any] = {
        "status": "dry_run_success" if dry_run else "applied_success",
        "dry_run": dry_run,
        "current_version": current_ver,
        "target_version": current_ver + 1,
        "app_version": APP_VERSION,
        "verified_provider": verified_provider,
        "verified_at": eff_verified_at,
        "added_count": added_count,
        "modified_count": modified_count,
        "delisted_count": delisted_count,
        "total_active_before": len(active_existing),
        "total_active_after": len(active_existing) + added_count,
        "total_symbols_after": target_total,
        "added_symbols": [s["symbol"] for s in diff["added"]],
        "executed_at": datetime.now(timezone.utc).isoformat()
    }

    if dry_run:
        print(f"🔍 [CatalogExpansion] Dry-run completed successfully.")
        print(f"   Version: v{current_ver} -> v{current_ver + 1}")
        print(f"   Added: {added_count}, Modified: {modified_count}, Delisted: {delisted_count}")
        print(f"   Total Symbols: {len(existing_symbols)} -> {target_total}")
        return report

    # 6. Apply in transaction under catalog_write_lock
    with catalog_write_lock():
        result = asyncio.run(_apply_catalog_sync(current_catalog, diff, stats, report))
        print(f"✅ [CatalogExpansion] Applied {added_count} symbols to catalog.json successfully!")
        print(f"   Catalog Version: v{result.get('target_version')}")
        print(f"   App Version: {APP_VERSION}")
        print(f"   Total Active: {result.get('total_active_after')}")
        print(f"   Snapshot Path: {result.get('snapshot_path')}")
        return result


def main():
    args = parse_args()
    try:
        res = apply_expansion(
            candidate_path=args.candidate,
            exclude=args.exclude,
            verified_at=args.verified_at,
            verified_provider=args.verified_provider,
            dry_run=args.dry_run
        )
        print(json.dumps({
            "status": res.get("status"),
            "added_count": res.get("added_count"),
            "current_version": res.get("current_version"),
            "target_version": res.get("target_version"),
            "snapshot_path": res.get("snapshot_path")
        }, indent=2))
    except Exception as e:
        print(f"❌ [CatalogExpansion Failed] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
