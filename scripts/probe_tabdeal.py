#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tabdeal Read-Only Market Data Probe & Accuracy Gate (Manual Execution Only).
Rule: Never execute this script in automated CI workflows.
DO NOT CALL Nobitex, Wallex, Bitpin, or Ramzinex endpoints here.
"""

import sys
import os
import time
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple
import httpx

TABDEAL_API_BASE = "https://api1.tabdeal.org"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

PAIRS_31 = [
    # Liquid pairs (USDT & IRT)
    ("BTC", "USDT"), ("BTC", "IRT"),
    ("ETH", "USDT"), ("ETH", "IRT"),
    ("SOL", "USDT"), ("SOL", "IRT"),
    ("DOGE", "USDT"), ("DOGE", "IRT"),
    ("XRP", "USDT"), ("XRP", "IRT"),
    ("ADA", "USDT"), ("ADA", "IRT"),
    ("AVAX", "USDT"), ("AVAX", "IRT"),
    ("TRX", "USDT"), ("TRX", "IRT"),
    ("SUI", "USDT"), ("SUI", "IRT"),
    ("BNB", "USDT"), ("BNB", "IRT"),
    # USDT/TMN Anchor
    ("USDT", "IRT"),
    # 6 Verified Cheap coins (< 0.001 USDT)
    ("PEPE", "USDT"), ("PEPE", "IRT"),
    ("SHIB", "USDT"), ("SHIB", "IRT"),
    ("FLOKI", "USDT"), ("FLOKI", "IRT"),
    ("BONK", "USDT"), ("BONK", "IRT"),
    ("BTTC", "USDT"), ("BTTC", "IRT"),
    ("LUNC", "USDT"), ("LUNC", "IRT"),
]

def run_probe():
    print(f"=== Tabdeal Probe & Accuracy Gate started at {datetime.now(timezone.utc).isoformat()} ===")
    
    with httpx.Client(timeout=20.0, headers=HEADERS, follow_redirects=True) as client:
        # Helper for resilient requests
        def safe_get(url: str, retries: int = 2):
            for attempt in range(retries):
                try:
                    t0 = time.time()
                    resp = client.get(url)
                    lat = (time.time() - t0) * 1000
                    return resp, lat
                except Exception as e:
                    if attempt == retries - 1:
                        return None, 0.0
                    time.sleep(0.5)
            return None, 0.0

        # 1. Server Time
        r_time, lat_time = safe_get(f"{TABDEAL_API_BASE}/r/api/v1/time")
        if r_time and r_time.status_code == 200:
            server_time_ms = r_time.json().get("serverTime")
            print(f"1. /r/api/v1/time: Status 200, Latency {lat_time:.1f}ms, ServerTime: {server_time_ms}")
        else:
            print(f"1. /r/api/v1/time: Unavailable or timeout")

        # 2. exchangeInfo (Symbol Inventory & Catalog Data)
        r_info, lat_info = safe_get(f"{TABDEAL_API_BASE}/r/api/v1/exchangeInfo")
        info_symbols = r_info.json() if r_info and r_info.status_code == 200 else []
        print(f"2. /r/api/v1/exchangeInfo: Status {r_info.status_code if r_info else 'N/A'}, Latency {lat_info:.1f}ms, Symbols count: {len(info_symbols)}")

        # 3. market_information (Bulk Ticker & Last Traded Prices)
        latencies = []
        markets_data = []
        for i in range(5):
            r_m, lat = safe_get(f"{TABDEAL_API_BASE}/r/plots/market_information/")
            if lat > 0:
                latencies.append(lat)
            if i == 0 and r_m and r_m.status_code == 200:
                markets_data = r_m.json()
        if latencies:
            latencies.sort()
            median_lat = latencies[len(latencies)//2]
            print(f"3. /r/plots/market_information/: 5-call Median Latency {median_lat:.1f}ms (min: {min(latencies):.1f}ms, max: {max(latencies):.1f}ms), Count: {len(markets_data)}")
        else:
            median_lat = 0.0
            print("3. /r/plots/market_information/: Failed to retrieve latency stats")

        # 4. Inventory Classification
        usdt_pairs = [s for s in info_symbols if s.get("quoteAsset") == "USDT"]
        irt_pairs = [s for s in info_symbols if s.get("quoteAsset") == "IRT"]
        inactive_pairs = [s for s in info_symbols if s.get("status") != "TRADING" or not s.get("isSpotTradingAllowed")]
        print(f"   Inventory breakdown: Total {len(info_symbols)}, Active USDT: {len(usdt_pairs)}, Active IRT (TMN): {len(irt_pairs)}, Inactive: {len(inactive_pairs)}")

        # 5. Accuracy Gate Comparison (31 Pairs)
        print("\n" + "=" * 90)
        print("ACCURACY GATE: Comparing /r/plots/market_information/ vs /r/api/v1/trades (Last Traded Price)")
        print("=" * 90)
        print(f"{'Pair':<14} | {'Bulk Mkt Price':<18} | {'Last Trade Price':<18} | {'Diff %':<9} | {'Status'}")
        print("-" * 90)

        mkt_map = {m["symbol"]: m for m in markets_data}
        diff_list = []
        gate_rows = []

        for base, quote in PAIRS_31:
            tab_sym = f"{base}_{quote}"
            api_sym = f"{base}{quote}"
            m_item = mkt_map.get(tab_sym)
            m_price = float(m_item["price"]) if m_item and m_item.get("price") else None

            # Fetch individual trades
            trade_p = None
            try:
                r_tr = client.get(f"{TABDEAL_API_BASE}/r/api/v1/trades?symbol={api_sym}")
                if r_tr.status_code == 200:
                    tr_list = r_tr.json()
                    if tr_list and len(tr_list) > 0:
                        trade_p = float(tr_list[0]["price"])
            except Exception as e:
                pass

            if m_price is not None and trade_p is not None and trade_p > 0:
                diff_pct = abs(m_price - trade_p) / trade_p * 100.0
                diff_list.append(diff_pct)
                status = "PASS" if diff_pct <= 0.2 else ("ACCEPTABLE" if diff_pct <= 1.0 else "REVIEW")
                print(f"{tab_sym:<14} | {m_price:<18.8g} | {trade_p:<18.8g} | {diff_pct:<8.4f}% | {status}")
                gate_rows.append({
                    "pair": tab_sym,
                    "market_price": m_price,
                    "trade_price": trade_p,
                    "diff_pct": diff_pct,
                    "status": status
                })
            else:
                print(f"{tab_sym:<14} | {str(m_price):<18} | {str(trade_p):<18} | {'N/A':<9} | MISSING")

        print("-" * 90)
        if diff_list:
            diff_list.sort()
            med_diff = diff_list[len(diff_list)//2]
            max_diff = max(diff_list)
            print(f"Accuracy Gate Result: {len(diff_list)} pairs compared.")
            print(f"Median Difference: {med_diff:.4f}% (Threshold: < 0.2000%) -> {'PASS' if med_diff < 0.2 else 'FAIL'}")
            print(f"Maximum Difference: {max_diff:.4f}% (Liquid Threshold: < 1.0000%) -> {'PASS' if max_diff < 1.0 else 'FAIL'}")

        # 6. Monitor-only Cross-check Simulation (USDT Price * Live USDT/TMN rate vs Pair IRT Price)
        print("\n" + "=" * 90)
        print("MONITOR-ONLY CROSS-CHECK (Admin Alert Cross-check, never used for pricing):")
        print("=" * 90)
        usdt_irt_mkt = mkt_map.get("USDT_IRT")
        usdt_tmn_rate = float(usdt_irt_mkt["price"]) if usdt_irt_mkt else 0.0
        print(f"Live Tabdeal USDT/IRT Rate: {usdt_tmn_rate:,.0f} Rials ({usdt_tmn_rate/10:,.0f} Tomans)")
        print(f"{'Coin':<8} | {'USDT Price':<14} | {'Calculated IRT':<18} | {'Actual IRT':<18} | {'Divergence %'}")
        print("-" * 90)
        for base in ["BTC", "ETH", "SOL", "DOGE", "TON", "PEPE"]:
            u_mkt = mkt_map.get(f"{base}_USDT")
            i_mkt = mkt_map.get(f"{base}_IRT")
            if u_mkt and i_mkt:
                p_u = float(u_mkt["price"])
                p_i = float(i_mkt["price"])
                calc_i = p_u * usdt_tmn_rate
                div_pct = abs(calc_i - p_i) / p_i * 100.0 if p_i > 0 else 0.0
                print(f"{base:<8} | {p_u:<14.6g} | {calc_i:<18.8g} | {p_i:<18.8g} | {div_pct:.2f}%")

    return {
        "symbols_count": len(info_symbols),
        "usdt_count": len(usdt_pairs),
        "irt_count": len(irt_pairs),
        "median_lat_ms": median_lat,
        "median_diff_pct": med_diff if diff_list else 0.0,
        "max_diff_pct": max_diff if diff_list else 0.0,
        "gate_rows": gate_rows
    }

if __name__ == "__main__":
    run_probe()
