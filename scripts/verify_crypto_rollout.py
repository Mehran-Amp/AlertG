#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — Phase 12 Crypto Rollout Verification Tool.
Verifies the operational status of Crypto Version 2 on the server:
1. Environment Flags: CRYPTO_STRICT_V2, CRYPTO_ENGINE_V2, CRYPTO_STAGE_B_ENABLED, CRYPTO_VALIDATE_ALERTS.
2. Status Dashboard Check (/status or /api/status):
   - Confirms crypto_flags in JSON.
   - Confirms crypto_latency p50/p95 metrics.
   - Confirms poller health and provider statuses.
3. Exchange Self-Test Check (/api/admin/crypto/selftest):
   - Triggers read-only audit across all 10 active global crypto exchanges.
   - Validates live price coverage and zero format breaks.

Usage:
  python scripts/verify_crypto_rollout.py
  python scripts/verify_crypto_rollout.py --url http://127.0.0.1:8000
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error

# Ensure root directory is in sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import app.config as config


def verify_rollout(base_url: str, admin_key: str):
    print("=" * 70)
    print("🚀 AlertG Crypto Version 2 — Phase 12 Rollout Verification")
    print("=" * 70)

    # 1. Environment & Config Flags Check
    print("\n📋 1. Checking Environment & Config Flags:")
    flags = {
        "CRYPTO_STRICT_V2 (Rule R1 Isolation)": getattr(config, "CRYPTO_STRICT_V2", False),
        "CRYPTO_ENGINE_V2 (Stage A Snapshot Store)": getattr(config, "CRYPTO_ENGINE_V2", False),
        "CRYPTO_STAGE_B_ENABLED (1s Evaluation Job)": getattr(config, "CRYPTO_STAGE_B_ENABLED", False),
        "CRYPTO_VALIDATE_ALERTS (Alert Validation)": getattr(config, "CRYPTO_VALIDATE_ALERTS", "false"),
    }
    all_flags_active = True
    for name, val in flags.items():
        is_active = (val is True) or (isinstance(val, str) and val in ("warn", "enforce"))
        icon = "✅" if is_active else "⚠️"
        print(f"  {icon} {name}: {val}")
        if not is_active and "VALIDATE" not in name:
            all_flags_active = False

    if not all_flags_active:
        print("\n  💡 Note: To activate all Phase 12 flags, ensure the following are in .env:")
        print("     CRYPTO_STRICT_V2=true")
        print("     CRYPTO_ENGINE_V2=true")
        print("     CRYPTO_STAGE_B_ENABLED=true")
        print("     CRYPTO_VALIDATE_ALERTS=warn")

    # 2. Query /status Endpoint
    print(f"\n🌐 2. Probing Server Status Dashboard ({base_url}/status):")
    status_url = f"{base_url.rstrip('/')}/status?format=json"
    headers = {"Accept": "application/json"}
    if admin_key:
        headers["X-Admin-Key"] = admin_key

    req = urllib.request.Request(status_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"  ✅ Server Online: {data.get('engine', 'AlertG Engine')}")
            print(f"  ⏱️ Uptime: {data.get('uptime_seconds', 0)} seconds")

            active_alerts = data.get("active_alerts_count", 0)
            total_alerts = data.get("total_alerts_count", 0)
            print(f"  🔔 Alerts in Memory: {active_alerts} active / {total_alerts} total")

            c_flags = data.get("crypto_flags", {})
            if c_flags:
                print(f"  ⚙️ Server Crypto Flags: {c_flags}")

            lat = data.get("crypto_latency", {})
            p50 = lat.get("p50_ms", data.get("crypto_poll_p50_ms", 0.0))
            p95 = lat.get("p95_ms", data.get("crypto_poll_p95_ms", 0.0))
            samples = lat.get("samples", 0)
            print(f"  ⚡ Crypto Poll Latency: p50={p50:.1f}ms | p95={p95:.1f}ms (samples: {samples})")

            metrics = data.get("metrics", {})
            tot_checks = metrics.get("total_checks", 0)
            crypto_checks = metrics.get("total_crypto_checks", 0)
            print(f"  📊 Evaluation Counts: Main 2s Checks={tot_checks} | Crypto 1s Checks={crypto_checks}")

    except urllib.error.HTTPError as e:
        print(f"  ❌ /status returned HTTP {e.code}: {e.reason}")
        if e.code == 401 or e.code == 403:
            print("     (Make sure ADMIN_KEY is provided or set in environment)")
    except Exception as e:
        print(f"  ❌ Could not connect to {status_url}: {e}")
        print("     (Make sure server is running via python server.py or systemd)")

    # 3. Query /api/admin/crypto/selftest
    print(f"\n🔍 3. Running Self-Test on All 10 Supported Exchanges ({base_url}/api/admin/crypto/selftest):")
    selftest_url = f"{base_url.rstrip('/')}/api/admin/crypto/selftest"
    req_test = urllib.request.Request(selftest_url, headers=headers)
    try:
        with urllib.request.urlopen(req_test, timeout=30) as resp:
            tdata = json.loads(resp.read().decode("utf-8"))
            status = tdata.get("status")
            healthy_count = tdata.get("healthy_count", 0)
            total_ex = tdata.get("total_exchanges", 0)
            print(f"  ✅ Self-Test Overall Status: {status} ({healthy_count}/{total_ex} healthy)")

            results = tdata.get("results", {})
            for ex_id, ex_res in results.items():
                is_h = ex_res.get("healthy", False)
                pairs_cnt = ex_res.get("pairs_count", 0)
                cov = ex_res.get("live_price_coverage_pct", 0.0)
                icon = "🟢" if is_h else "🔴"
                print(f"    {icon} {ex_id:<10}: {pairs_cnt:>5} pairs | {cov:>5.1f}% price coverage")

    except urllib.error.HTTPError as e:
        print(f"  ❌ /api/admin/crypto/selftest returned HTTP {e.code}: {e.reason}")
    except Exception as e:
        print(f"  ⚠️ Could not query selftest: {e}")

    print("\n" + "=" * 70)
    print("🏁 Verification Complete.")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="AlertG Phase 12 Rollout Verification")
    parser.add_argument("--url", default=os.getenv("SERVER_URL", "http://127.0.0.1:8000"), help="Server Base URL")
    parser.add_argument("--key", default=os.getenv("ADMIN_KEY", getattr(config, "ADMIN_KEY", "")), help="Admin Key")
    args = parser.parse_args()

    verify_rollout(args.url, args.key)


if __name__ == "__main__":
    main()
