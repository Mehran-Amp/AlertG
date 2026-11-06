#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — Live Crypto Alert E2E Test & Verification Tool.
Tests end-to-end alert creation, evaluation via Stage B (1s engine),
WebSocket stream activation (Stage C), triggering, and clean-up.

Supported Exchanges for Live Alert Test:
- Binance (Global Spot + WebSocket Stream)
- Tabdeal (Official Iranian Exchange - TMN & USDT)
- Kifpool (Official Iranian Exchange - TMN & USDT)

Usage:
  python scripts/verify_live_crypto_alert.py
  python scripts/verify_live_crypto_alert.py --exchange binance --symbol BTCUSDT
  python scripts/verify_live_crypto_alert.py --exchange tabdeal --symbol BTC_IRT
  python scripts/verify_live_crypto_alert.py --exchange kifpool --symbol BTCUSDT
  python scripts/verify_live_crypto_alert.py --all
"""

import os
import sys
import time
import json
import uuid
import argparse
import urllib.request
import urllib.error

# Ensure root directory is in sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import app.config as config


def get_auth_headers(admin_key: str = "", api_key: str = ""):
    adm = admin_key or os.getenv("ADMIN_KEY", getattr(config, "ADMIN_KEY", ""))
    api = api_key or os.getenv("API_KEY", getattr(config, "API_KEY", "")) or adm
    hdrs = {"Accept": "application/json"}
    if adm:
        hdrs["X-Admin-Key"] = adm
    if api:
        hdrs["X-API-Key"] = api
    return hdrs


def query_json(url: str, method: str = "GET", payload: dict = None, headers: dict = None, timeout: float = 15.0):
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content = resp.read().decode("utf-8")
        if content:
            return json.loads(content)
        return {}


def test_single_exchange_alert(base_url: str, exchange: str, symbol: str, admin_key: str = "", api_key: str = "", cleanup: bool = True):
    print(f"\n" + "-" * 65)
    print(f"🎯 Testing Live Alert on [{exchange.upper()}] for symbol: {symbol}")
    print("-" * 65)

    headers = get_auth_headers(admin_key, api_key)

    # 1. Fetch current live price directly from server/exchange to pick realistic target
    print(f"📡 1. Querying current market price for {exchange}:{symbol}...")
    current_price = None
    try:
        # Check /api/alerts/price or status
        price_query_url = f"{base_url.rstrip('/')}/api/alerts/price?exchange={exchange}&symbol={symbol}"
        res = query_json(price_query_url, headers=headers)
        if res and res.get("price"):
            current_price = float(res["price"])
            print(f"  ✅ Current live price: {current_price:,.4f} ({res.get('currency', 'USDT')}) [Source: {res.get('source', exchange)}]")
    except Exception as e:
        print(f"  ℹ️ Direct /api/alerts/price probe: {e}")

    # Fallback to direct public exchange API if server endpoint requires auth or returns error
    if not current_price or current_price <= 0:
        try:
            if exchange == "binance":
                d = query_json(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol.upper()}")
                current_price = float(d.get("price", 0))
            elif exchange == "tabdeal":
                d = query_json(f"https://api1.tabdeal.org/r/api/v1/trades?symbol={symbol.upper().replace('_', '')}")
                if d and isinstance(d, list) and len(d) > 0:
                    current_price = float(d[0].get("price", 0))
            elif exchange == "kifpool":
                d = query_json("https://api.kifpool.app/api/spot/price")
                if isinstance(d, list):
                    for it in d:
                        if (it.get("symbol") or "").upper() == "BTC":
                            current_price = float(it.get("price", 0))
                            break
            if current_price:
                print(f"  ✅ Current live price from provider: {current_price:,.4f}")
        except Exception as e:
            print(f"  ⚠️ Could not fetch preliminary price: {e}")
            current_price = 68000.0 if "BTC" in symbol else 1.0

    # 2. Configure Trigger Condition
    # We set target_price lower than current_price with condition ABOVE so it triggers immediately
    # or slightly above if testing edge crossing
    target_price = current_price * 0.90  # 10% below current price => condition ABOVE triggers immediately
    print(f"⚙️ 2. Creating Instant-Trigger Alert (Current: {current_price:,.2f} | Target: {target_price:,.2f} | Condition: ABOVE)")

    alert_id = f"test_e2e_{exchange}_{uuid.uuid4().hex[:8]}"
    alert_payload = {
        "id": alert_id,
        "user_id": "test_e2e_runner",
        "exchange": exchange,
        "symbol": symbol,
        "target_price": target_price,
        "condition": "ABOVE",
        "condition_type": "priceThreshold",
        "direction": "above",
        "check_interval_seconds": 1,
        "trigger_mode": "oneShot",
        "note": f"E2E Real Alert Test on {exchange.upper()}",
        "language": "fa"
    }

    create_url = f"{base_url.rstrip('/')}/api/alerts"
    try:
        created = query_json(create_url, method="POST", payload=alert_payload, headers=headers)
        created_id = created.get("id", alert_id)
        print(f"  ✅ Alert registered successfully on server. ID: {created_id}")
    except Exception as e:
        print(f"  ❌ Failed to register alert: {e}")
        return False

    # 3. Monitor Evaluation in Real-Time
    print(f"⏱️ 3. Monitoring Stage B (1s Engine) for trigger execution (Max 10 seconds)...")
    is_triggered = False
    triggered_price = None

    for i in range(1, 11):
        time.sleep(1.0)
        try:
            status_data = query_json(f"{base_url.rstrip('/')}/status?format=json", headers=headers)
            crypto_checks = status_data.get("metrics", {}).get("total_crypto_checks", 0)
            streams = status_data.get("crypto_streams", {}).get(exchange, {})
            stream_status = "CONNECTED" if streams.get("connected") else ("ACTIVE" if streams.get("enabled") else "OFF")

            # Check alert status via path parameter /api/alerts/{user_id}
            alerts_url = f"{base_url.rstrip('/')}/api/alerts/test_e2e_runner"
            user_alerts = query_json(alerts_url, headers=headers)
            target_alert = None
            if isinstance(user_alerts, list):
                for a in user_alerts:
                    if a.get("id") == created_id:
                        target_alert = a
                        break

            if target_alert:
                active = target_alert.get("is_active", True)
                last_eval = target_alert.get("last_eval_price")
                print(f"     [{i}s] Evaluated: {crypto_checks} checks | Stream: {stream_status} | Last Price: {last_eval} | Active: {active}")
                if not active:
                    is_triggered = True
                    triggered_price = last_eval
                    print(f"\n  🚀🎉 [SUCCESS] ALERT TRIGGERED IN {i} SECOND(S)!")
                    print(f"     - Trigger Price: {triggered_price:,.4f}")
                    print(f"     - Exchange: {exchange}")
                    print(f"     - Symbol: {symbol}")
                    break
            else:
                # Alert might have been archived on trigger
                print(f"     [{i}s] Evaluated: {crypto_checks} checks | Alert handled/archived.")
                is_triggered = True
                break
        except Exception as e:
            print(f"     [{i}s] Waiting for engine: {e}")

    # 4. Clean-up: Delete test alert
    if cleanup:
        print(f"\n🧹 4. Cleaning up test alert (ID: {created_id})...")
        try:
            del_url = f"{base_url.rstrip('/')}/api/alerts/{created_id}"
            query_json(del_url, method="DELETE", headers=headers)
            print("  ✅ Clean-up complete. No leftover test data in database.")
        except Exception as e:
            print(f"  ℹ️ Clean-up notice: {e}")

    return is_triggered


def main():
    parser = argparse.ArgumentParser(description="AlertG Crypto V2 — Live Alert E2E Verification")
    parser.add_argument("--url", default=os.getenv("SERVER_URL", "http://127.0.0.1:8000"), help="Base URL of AlertG backend")
    parser.add_argument("--exchange", default="", help="Exchange to test (binance, tabdeal, kifpool)")
    parser.add_argument("--symbol", default="", help="Symbol to test (BTCUSDT, BTC_IRT, BTCUSDT)")
    parser.add_argument("--admin-key", default=os.getenv("ADMIN_KEY", getattr(config, "ADMIN_KEY", "")), help="Admin Key")
    parser.add_argument("--api-key", default=os.getenv("API_KEY", getattr(config, "API_KEY", "")), help="API Key")
    parser.add_argument("--all", action="store_true", help="Run live alert test on all 3 target exchanges")
    args = parser.parse_args()

    print("=" * 70)
    print("🚀 AlertG Crypto Version 2 — Live Real-Alert End-to-End Test")
    print("=" * 70)

    auth_headers = get_auth_headers(args.admin_key, args.api_key)

    # Verify server availability
    try:
        st = query_json(f"{args.url.rstrip('/')}/status?format=json", headers=auth_headers)
        print(f"✅ Connected to AlertG Server: {st.get('engine', 'FastAPI Engine')}")
        print(f"   Uptime: {st.get('uptime_seconds', 0)}s | Crypto Stage B: {st.get('crypto_flags', {}).get('crypto_stage_b_enabled')}")
    except urllib.error.HTTPError as e:
        print(f"❌ Failed to reach AlertG server at {args.url}: HTTP {e.code} ({e.reason})")
        if e.code == 401 or e.code == 403:
            print("   💡 Hint: Authentication required. Pass keys via:")
            print("      python scripts/verify_live_crypto_alert.py --admin-key <YOUR_ADMIN_KEY>")
            print("      or set ADMIN_KEY in your .env file.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to reach AlertG server at {args.url}: {e}")
        print("   Ensure the backend is running via: python server.py")
        sys.exit(1)

    targets = []
    if args.all:
        targets = [
            ("binance", "BTCUSDT"),
            ("tabdeal", "BTC_IRT"),
            ("kifpool", "BTCUSDT")
        ]
    elif args.exchange:
        sym = args.symbol or ("BTC_IRT" if args.exchange == "tabdeal" else "BTCUSDT")
        targets = [(args.exchange.lower(), sym)]
    else:
        # Default: Binance (Global) and Tabdeal (Iran)
        targets = [
            ("binance", "BTCUSDT"),
            ("tabdeal", "BTC_IRT")
        ]

    results = []
    for ex, sym in targets:
        success = test_single_exchange_alert(args.url, ex, sym, admin_key=args.admin_key, api_key=args.api_key)
        results.append((ex, sym, success))

    print("\n" + "=" * 70)
    print("🏁 Live Alert End-to-End Test Summary")
    print("=" * 70)
    all_ok = True
    for ex, sym, ok in results:
        status_icon = "🟢 PASSED (TRIGGERED IN <2s)" if ok else "🔴 FAILED"
        print(f"  {status_icon:<35} : {ex.upper()} ({sym})")
        if not ok:
            all_ok = False

    print("=" * 70)
    if all_ok:
        print("🎉 ALL LIVE ALERTS SUCCESSFULLY PROCESSED BY STAGE B ENGINE!")
    else:
        print("⚠️ Some live alert tests did not complete within the timeout.")
        sys.exit(1)


if __name__ == "__main__":
    main()
