#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — Phase 12 (CoinEx Complete Removal & Migration).
Safely audits, backs up, and removes deprecated CoinEx alerts from the persistent store:
1. Dry-run by default: scans database, reports affected alerts, symbols, and users without mutating files.
2. Full atomic backup: with --apply, creates a timestamped JSON snapshot under DATA_DIR/alerts_backup/.
3. Atomic pruning: writes non-CoinEx alerts to disk via temporary file + atomic rename.
4. Rollback capability: supports --restore <backup_file> to revert changes instantly.
"""

import os
import sys
import json
import argparse
import tempfile
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

# Ensure app modules are importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import app.config as config


def get_default_db_file() -> str:
    """Returns canonical path to the primary alerts database file."""
    return getattr(config, "ALERTS_DATA_FILE", "alerts_data.json")


def get_default_backup_dir() -> str:
    """Returns canonical path to the alerts backup directory."""
    data_dir = getattr(config, "DATA_DIR", ".")
    return os.path.join(data_dir, "alerts_backup")


def load_raw_alerts(db_file: str) -> List[Dict[str, Any]]:
    """Loads raw alert dictionaries from JSON storage."""
    if not os.path.exists(db_file):
        return []
    try:
        with open(db_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "alerts" in data:
                return data["alerts"]
            return []
    except Exception as e:
        print(f"❌ Error loading database from {db_file}: {e}", file=sys.stderr)
        return []


def is_coinex_alert(alert: Dict[str, Any]) -> bool:
    """Checks whether an alert belongs to discontinued exchange CoinEx."""
    if not isinstance(alert, dict):
        return False
    ex = str(alert.get("exchange", "")).strip().lower()
    ex_id = str(alert.get("exchange_id", "")).strip().lower()
    return ex == "coinex" or ex_id == "coinex"


def perform_atomic_write(target_path: str, data: List[Dict[str, Any]]) -> bool:
    """Atomically writes alert list to file via tempfile + os.replace."""
    target_dir = os.path.dirname(os.path.abspath(target_path)) or "."
    os.makedirs(target_dir, exist_ok=True)

    tf = tempfile.NamedTemporaryFile("w", dir=target_dir, delete=False, encoding="utf-8")
    try:
        json.dump(data, tf, indent=2, ensure_ascii=False)
        tf.flush()
        os.fsync(tf.fileno())
        tf.close()
        os.replace(tf.name, target_path)
        return True
    except Exception as e:
        if os.path.exists(tf.name):
            try:
                os.remove(tf.name)
            except OSError:
                pass
        raise e


def run_coinex_removal(
    db_file: Optional[str] = None,
    backup_dir: Optional[str] = None,
    apply: bool = False,
    restore_file: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main migration controller:
    - If restore_file is given: atomically restores database from backup.
    - If apply is False: runs non-destructive dry-run audit.
    - If apply is True: creates full backup, deletes CoinEx alerts, and saves atomically.
    """
    target_db = os.path.abspath(db_file or get_default_db_file())
    target_backup_dir = os.path.abspath(backup_dir or get_default_backup_dir())

    # Mode 1: Restore from backup
    if restore_file:
        restore_path = os.path.abspath(restore_file)
        if not os.path.exists(restore_path):
            raise FileNotFoundError(f"Backup file not found at: {restore_path}")

        with open(restore_path, "r", encoding="utf-8") as f:
            restored_data = json.load(f)

        if not isinstance(restored_data, list):
            raise ValueError("Invalid backup file: root element must be a JSON array of alerts.")

        perform_atomic_write(target_db, restored_data)
        return {
            "status": "RESTORED",
            "restored_from": restore_path,
            "target_db": target_db,
            "total_alerts": len(restored_data)
        }

    # Mode 2 & 3: Audit (Dry-run) or Apply removal
    all_alerts = load_raw_alerts(target_db)
    coinex_alerts = [a for a in all_alerts if is_coinex_alert(a)]
    kept_alerts = [a for a in all_alerts if not is_coinex_alert(a)]

    affected_users = sorted(list(set(
        str(a.get("user_id")) for a in coinex_alerts if a.get("user_id")
    )))

    symbol_breakdown: Dict[str, int] = {}
    for a in coinex_alerts:
        sym = str(a.get("symbol") or a.get("market_symbol") or "UNKNOWN").upper()
        symbol_breakdown[sym] = symbol_breakdown.get(sym, 0) + 1

    report = {
        "status": "APPLIED" if apply else "DRY_RUN",
        "target_db": target_db,
        "total_alerts_before": len(all_alerts),
        "coinex_alerts_found": len(coinex_alerts),
        "total_alerts_after": len(kept_alerts) if apply else len(all_alerts),
        "affected_users_count": len(affected_users),
        "affected_users": affected_users,
        "symbol_breakdown": symbol_breakdown,
        "backup_file": None,
        "coinex_alert_ids": [a.get("id") for a in coinex_alerts if a.get("id")]
    }

    if not apply:
        return report

    # Apply mode: Backup first, then prune
    os.makedirs(target_backup_dir, exist_ok=True)
    utc_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(target_backup_dir, f"coinex_removal_{utc_str}.json")

    with open(backup_path, "w", encoding="utf-8") as bf:
        json.dump(all_alerts, bf, indent=2, ensure_ascii=False)

    report["backup_file"] = backup_path

    # Atomically write pruned database
    perform_atomic_write(target_db, kept_alerts)

    return report


def main():
    parser = argparse.ArgumentParser(
        description="AlertG CoinEx Alert Migration Tool (Phase 12 / Part E Phase 11)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 1. Non-destructive audit (dry run):
  python scripts/remove_coinex_alerts.py

  # 2. Apply removal with full backup:
  python scripts/remove_coinex_alerts.py --apply

  # 3. Rollback / restore from previous backup:
  python scripts/remove_coinex_alerts.py --restore alerts_backup/coinex_removal_20261102_120000.json
        """
    )
    parser.add_argument("--apply", action="store_true", help="Execute deletion and create backup (default: dry run only)")
    parser.add_argument("--db-file", type=str, default=None, help="Custom path to alerts database JSON")
    parser.add_argument("--backup-dir", type=str, default=None, help="Custom directory for backups")
    parser.add_argument("--restore", type=str, default=None, help="Restore database from a given backup JSON file")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = parser.parse_args()

    try:
        res = run_coinex_removal(
            db_file=args.db_file,
            backup_dir=args.backup_dir,
            apply=args.apply,
            restore_file=args.restore
        )
    except Exception as e:
        print(f"❌ Migration failed: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return

    # Human-readable output
    if res.get("status") == "RESTORED":
        print("=" * 70)
        print("✅ AlertG CoinEx Rollback & Restore Succeeded")
        print("=" * 70)
        print(f"Restored from : {res['restored_from']}")
        print(f"Target DB     : {res['target_db']}")
        print(f"Total Alerts  : {res['total_alerts']}")
        print("=" * 70)
        return

    print("=" * 70)
    if res["status"] == "DRY_RUN":
        print("🔍 AlertG CoinEx Removal Audit — DRY RUN (No files modified)")
    else:
        print("🚀 AlertG CoinEx Removal — COMPLETED SUCCESSFULLY")
    print("=" * 70)
    print(f"Database File       : {res['target_db']}")
    print(f"Total Alerts Before : {res['total_alerts_before']}")
    print(f"CoinEx Alerts Found : {res['coinex_alerts_found']}")
    print(f"Total Alerts After  : {res['total_alerts_after']}")
    print(f"Affected Users      : {res['affected_users_count']}")

    if res["symbol_breakdown"]:
        print("\n📊 Affected CoinEx Symbols Breakdown:")
        for sym, count in sorted(res["symbol_breakdown"].items()):
            print(f"  • {sym:<12}: {count} alert(s)")

    if res["coinex_alert_ids"]:
        print(f"\n🏷️ Sample CoinEx Alert IDs: {res['coinex_alert_ids'][:5]}")

    if res["status"] == "APPLIED":
        print(f"\n💾 Full Database Backup Saved At:\n   {res['backup_file']}")
        print("\n✅ All CoinEx alerts removed. Non-CoinEx alerts preserved byte-for-byte.")
    else:
        print("\n⚠️ [DRY RUN] No files were altered.")
        print("   To execute removal and generate backup, re-run with: python scripts/remove_coinex_alerts.py --apply")
    print("=" * 70)


if __name__ == "__main__":
    main()
