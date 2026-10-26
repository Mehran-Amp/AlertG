#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Manual Catalog Sync Runner (CLI Tool)
Usage:
    python3 scripts/run_catalog_sync.py --dry-run
    python3 scripts/run_catalog_sync.py --candidate candidate_catalog_phase2.json --dry-run
    python3 scripts/run_catalog_sync.py --production
"""

import os
import sys
import json
import asyncio
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.engine.sync import (
    run_weekly_catalog_sync,
    CatalogSafetyCeilingExceededError,
    CatalogLockedError,
    CatalogSchemaError,
    CatalogValidationError
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="SignalAlert Manual Catalog Sync Runner"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Simulate the sync run without writing changes or snapshots."
    )
    parser.add_argument(
        "--production",
        action="store_true",
        default=False,
        help="Explicit confirmation to apply changes to production catalog."
    )
    parser.add_argument(
        "--candidate",
        type=str,
        default=None,
        help="Optional path to candidate JSON file. If omitted, default sources are fetched."
    )
    parser.add_argument(
        "--ignore-safety",
        action="store_true",
        default=False,
        help="Bypass safety ceiling checks (delist >5%%, add >10%%)."
    )
    return parser.parse_args()


def main():
    args = parse_args()
    
    # If neither --production nor --dry-run is specified, default to safe dry-run
    dry_run = args.dry_run
    if not dry_run and not args.production:
        print("⚠️ Neither --production nor --dry-run specified. Defaulting to safe --dry-run mode.")
        dry_run = True

    candidate_items = None
    if args.candidate:
        if not os.path.exists(args.candidate):
            print(f"❌ Candidate file not found: {args.candidate}")
            sys.exit(1)
        with open(args.candidate, "r", encoding="utf-8") as f:
            data = json.load(f)
            candidate_items = data.get("symbols", data) if isinstance(data, dict) else data
        print(f"📦 Loaded {len(candidate_items)} candidate items from {args.candidate}")

    mode_label = "DRY-RUN (Simulated)" if dry_run else "PRODUCTION (Live Apply)"
    print(f"🚀 Starting Manual Catalog Sync in [{mode_label}] mode...")

    try:
        report = asyncio.run(
            run_weekly_catalog_sync(
                candidate_items=candidate_items,
                dry_run=dry_run,
                ignore_safety=args.ignore_safety
            )
        )
        print("✅ Sync finished successfully!")
        print(f"   Status: {report.get('status')}")
        print(f"   Current Version: {report.get('current_version')}")
        print(f"   Target Version:  {report.get('target_version')}")
        stats = report.get("stats", {})
        print(f"   Stats: Added={stats.get('added_count', 0)}, Modified={stats.get('modified_count', 0)}, Delisted={stats.get('delisted_count', 0)}")
        if report.get("snapshot_path"):
            print(f"   Pre-apply Snapshot: {report.get('snapshot_path')}")
        if report.get("run_id"):
            print(f"   Audit Run ID: {report.get('run_id')}")
        sys.exit(0)
    except CatalogSafetyCeilingExceededError as se:
        print(f"🚨 [Safety Check Failed] {se}")
        sys.exit(2)
    except CatalogLockedError as le:
        print(f"🔒 [Catalog Locked] Another process is modifying the catalog: {le}")
        sys.exit(3)
    except Exception as e:
        print(f"❌ [Error] Sync failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
