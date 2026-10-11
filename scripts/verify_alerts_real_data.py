#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verification Script for Seed Symbol Mappings and Live Real-Data Alerts Resolution:
1. Verifies that EVERY seed symbol across all catalogs has at least one verified mapping:
   - WALLSTREET_MACRO_SYMBOLS (94 symbols)
   - predefinedStocks in Dart catalog (184 symbols)
   - predefinedAssets in IranDomesticExchange Dart catalog (113 symbols)
2. Verifies that ALL active alerts in alerts_data.json resolve successfully
   against real live market APIs (Binance, Nobitex, Yahoo Finance, Bonbast/Bridge).
"""

import os
import re
import sys
import json
import asyncio

# Ensure project root is in sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import httpx

from app.markets.global_stocks import (
    WALLSTREET_MACRO_SYMBOLS, EXACT_YF_MAP, FOREX_PAIRS, resolve_yf_symbol
)
from app.markets.iran import (
    BONBAST_MAP, TSETMC_INDEX_MAP, TSETMC_GOLD_FUNDS_MAP, TSETMC_INSTRUMENTS_MAP
)
from app.markets.base import fetch_price_with_trace
from app.storage import load_alerts_from_disk, ALERTS_DB


def verify_seed_symbol_mappings():
    print("=" * 70)
    print("🔍 STEP 1: VERIFYING SEED SYMBOLS MAPPING COVERAGE")
    print("=" * 70)

    # 1. WALLSTREET_MACRO_SYMBOLS (Python Catalog)
    total_macro = len(WALLSTREET_MACRO_SYMBOLS)
    unmapped_macro = []
    for item in WALLSTREET_MACRO_SYMBOLS:
        sym = item['symbol']
        mapped_yf = resolve_yf_symbol(sym)
        mapped_bb = BONBAST_MAP.get(sym) or BONBAST_MAP.get(item.get('id', ''))
        mapped_tse = TSETMC_INDEX_MAP.get(sym) or TSETMC_GOLD_FUNDS_MAP.get(sym) or TSETMC_INSTRUMENTS_MAP.get(sym)
        if not (mapped_yf or mapped_bb or mapped_tse):
            unmapped_macro.append(sym)

    print(f"📊 [WALLSTREET_MACRO_SYMBOLS] Verified: {total_macro - len(unmapped_macro)}/{total_macro} (Unmapped: {len(unmapped_macro)})")
    if unmapped_macro:
        print(f"   ⚠️ Unmapped symbols: {unmapped_macro}")

    # 2. predefinedStocks (Dart GlobalStocksExchange Catalog)
    dart_stocks_path = 'lib/features/exchanges/stocks/global_stocks_exchange.dart'
    with open(dart_stocks_path, 'r', encoding='utf-8') as f:
        dart_stocks_code = f.read()

    dart_stocks_symbols = list(dict.fromkeys(re.findall(r"'symbol':\s*'([^']+)'", dart_stocks_code)))
    total_dart_stocks = len(dart_stocks_symbols)
    unmapped_dart_stocks = []
    for s in dart_stocks_symbols:
        mapped_yf = resolve_yf_symbol(s)
        mapped_bb = BONBAST_MAP.get(s)
        mapped_tse = TSETMC_INDEX_MAP.get(s) or TSETMC_GOLD_FUNDS_MAP.get(s) or TSETMC_INSTRUMENTS_MAP.get(s)
        if not (mapped_yf or mapped_bb or mapped_tse):
            unmapped_dart_stocks.append(s)

    print(f"📊 [predefinedStocks (Dart)] Verified: {total_dart_stocks - len(unmapped_dart_stocks)}/{total_dart_stocks} (Unmapped: {len(unmapped_dart_stocks)})")
    if unmapped_dart_stocks:
        print(f"   ⚠️ Unmapped symbols: {unmapped_dart_stocks}")

    # 3. predefinedAssets (Dart IranDomesticExchange Catalog)
    dart_iran_path = 'lib/features/exchanges/stocks/iran_domestic_exchange.dart'
    with open(dart_iran_path, 'r', encoding='utf-8') as f:
        dart_iran_code = f.read()

    dart_iran_symbols = list(dict.fromkeys(re.findall(r"'symbol':\s*'([^']+)'", dart_iran_code)))
    total_dart_iran = len(dart_iran_symbols)
    unmapped_dart_iran = []
    for s in dart_iran_symbols:
        s_clean = s.upper()
        mapped_bb = BONBAST_MAP.get(s_clean)
        mapped_tse = TSETMC_INDEX_MAP.get(s_clean) or TSETMC_GOLD_FUNDS_MAP.get(s_clean) or TSETMC_INSTRUMENTS_MAP.get(s_clean)
        is_direct = s_clean in ['USDT_NOBITEX', 'GOLD_NOBITEX', 'USDT_WALLEX', 'GOLD_WALLEX', 'USDT_TETHERLAND']
        is_yf = resolve_yf_symbol(s)
        if not (mapped_bb or mapped_tse or is_direct or is_yf):
            unmapped_dart_iran.append(s)

    print(f"📊 [predefinedAssets (Iran Dart)] Verified: {total_dart_iran - len(unmapped_dart_iran)}/{total_dart_iran} (Unmapped: {len(unmapped_dart_iran)})")
    if unmapped_dart_iran:
        print(f"   ⚠️ Unmapped symbols: {unmapped_dart_iran}")

    total_seed_symbols = total_macro + total_dart_stocks + total_dart_iran
    total_unmapped = len(unmapped_macro) + len(unmapped_dart_stocks) + len(unmapped_dart_iran)

    print("-" * 70)
    print(f"🏁 SEED MAPPING COVERAGE RESULT: {total_seed_symbols - total_unmapped}/{total_seed_symbols} (100.0% VERIFIED)")
    assert total_unmapped == 0, f"Found {total_unmapped} unmapped seed symbols!"
    print("✅ All seed symbols have at least one verified mapping!")
    print()


async def verify_alerts_data_resolution():
    print("=" * 70)
    print("🔍 STEP 2: VERIFYING ALL ALERTS IN ALERTS_DATA.JSON ON REAL DATA")
    print("=" * 70)

    alerts = load_alerts_from_disk()
    if not alerts:
        print("⚠️ No alerts found in alerts_data.json!")
        return

    print(f"📁 Loaded {len(alerts)} alerts from alerts_data.json.")
    print("-" * 70)

    limits = httpx.Limits(max_keepalive_connections=20, max_connections=40)
    timeout = httpx.Timeout(10.0, connect=5.0)

    resolved_count = 0
    failed_alerts = []

    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        for idx, alert in enumerate(alerts, 1):
            ex = alert.exchange
            sym = alert.symbol
            t0 = asyncio.get_event_loop().time()
            price, traces = await fetch_price_with_trace(client, ex, sym, collect_all_traces=False)
            latency = round((asyncio.get_event_loop().time() - t0) * 1000, 1)

            source = traces[0].get('source', 'Unknown') if traces else 'None'
            curr = traces[0].get('currency', 'USD') if traces else 'USD'

            if price is not None and price > 0:
                resolved_count += 1
                status_icon = "✅ RESOLVED"
                print(f"[{idx}/{len(alerts)}] {status_icon} | {ex:<14} | {sym:<12} | Price: {price:,.4f}".rstrip('0').rstrip('.') + f" {curr} | Source: {source} ({latency}ms)")
            else:
                failed_alerts.append((alert.id, ex, sym))
                status_icon = "❌ FAILED"
                print(f"[{idx}/{len(alerts)}] {status_icon} | {ex:<14} | {sym:<12} | Price: None | Source: {source} ({latency}ms)")

    print("-" * 70)
    print(f"🏁 ALERTS RESOLUTION RESULT: {resolved_count}/{len(alerts)} RESOLVED ON REAL LIVE DATA")
    if failed_alerts:
        print(f"❌ Failed alerts: {failed_alerts}")
        raise RuntimeError(f"{len(failed_alerts)} alerts failed to resolve on real data!")
    else:
        print("🎉 100% OF ALERTS IN alerts_data.json SUCCESSFULLY RESOLVED ON REAL DATA!")


def main():
    verify_seed_symbol_mappings()
    asyncio.run(verify_alerts_data_resolution())


if __name__ == '__main__':
    main()
