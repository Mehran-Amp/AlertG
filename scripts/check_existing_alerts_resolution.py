#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SignalAlert Existing Alerts Resolution Checker (Phase 5 / v3.3.0)
Validates that ALL alerts in alerts_data.json resolve properly across provider maps.
Reports any unresolved alerts with detailed diagnostics, reason, and suggested canonical alias.
Exit code:
  0 = 100% of alerts resolved successfully
  1 = At least one unresolved alert found (execution blocked)
"""

import os
import sys
import json
import argparse
import asyncio
from typing import List, Dict, Any, Optional, Tuple

# Ensure project root is in sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = ROOT_DIR
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    import httpx
except ImportError:
    httpx = None

from app.config import APP_VERSION, CATALOG_FILE
from app.models import Alert
from app.storage import load_alerts_from_disk, DB_FILE
from app.markets.global_stocks import (
    resolve_yf_symbol,
    resolve_symbol_alias,
    resolve_symbol_category,
    yahoo_adapter,
    finnhub_adapter,
    twelve_data_adapter,
    fred_adapter,
    WALLSTREET_MACRO_SYMBOLS,
    EXACT_YF_MAP,
    FOREX_PAIRS,
    FRED_ONLY_SYMBOLS,
    FRED_SERIES_FREQUENCY,
)
from app.markets.iran import (
    BONBAST_MAP, TSETMC_INDEX_MAP, TSETMC_GOLD_FUNDS_MAP, TSETMC_INSTRUMENTS_MAP
)
from app.markets.base import fetch_price_with_trace


def load_catalog_symbols() -> set:
    """Loads all known symbols from catalog.json, seed files, and macro list."""
    symbols = set()
    for s in WALLSTREET_MACRO_SYMBOLS:
        if s.get('id'):
            symbols.add(s['id'].upper())
        if s.get('symbol'):
            symbols.add(s['symbol'].upper())
            symbols.add(s['symbol'].upper().replace('/', ''))

    if os.path.exists(CATALOG_FILE):
        try:
            with open(CATALOG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data.get('symbols', []):
                    if item.get('id'):
                        symbols.add(item['id'].upper())
                    if item.get('symbol'):
                        symbols.add(item['symbol'].upper())
                        symbols.add(item['symbol'].upper().replace('/', ''))
        except Exception:
            pass

    seed_dir = os.path.join(PROJECT_ROOT, 'seed')
    if os.path.exists(seed_dir) and os.path.isdir(seed_dir):
        for fname in os.listdir(seed_dir):
            if fname.endswith('.json'):
                try:
                    with open(os.path.join(seed_dir, fname), 'r', encoding='utf-8') as f:
                        sdata = json.load(f)
                        for item in sdata.get('symbols', []):
                            if item.get('id'):
                                symbols.add(item['id'].upper())
                            if item.get('symbol'):
                                symbols.add(item['symbol'].upper())
                except Exception:
                    pass
    return symbols


def resolve_symbol_offline(exchange: str, symbol: str, catalog_symbols: set) -> Tuple[bool, str, Optional[str]]:
    """
    Offline validation check: Verifies if a symbol has a confirmed mapping across providers.
    Returns: (is_resolved, reason, suggested_canonical)
    """
    clean_sym = (symbol or '').strip().upper()
    canonical = resolve_symbol_alias(clean_sym)
    ex = (exchange or '').strip().lower()

    if not clean_sym:
        return False, "Empty symbol string", None

    LEGACY_CRYPTO_METRICS = frozenset({'TOTAL', 'TOTAL2', 'TOTAL3', 'BTC.D', 'USDT.D', 'ETH.D'})
    if clean_sym in LEGACY_CRYPTO_METRICS or canonical in LEGACY_CRYPTO_METRICS:
        return True, "Legacy crypto-metric (unsupported_legacy warning)", canonical

    if ex in ('global_stocks', 'stocks', 'macro', 'forex'):
        # 1. Direct or alias in exact YF map
        if clean_sym in EXACT_YF_MAP or canonical in EXACT_YF_MAP:
            return True, "Exact YF mapping verified", canonical

        # 2. Forex pair
        s_no_slash = clean_sym.replace('/', '')
        if s_no_slash in FOREX_PAIRS:
            return True, "Major Forex pair verified", f"{s_no_slash[:3]}/{s_no_slash[3:]}"

        # 3. FRED macro series
        if clean_sym in fred_adapter.FRED_SERIES_MAP or canonical in fred_adapter.FRED_SERIES_MAP or clean_sym in FRED_SERIES_FREQUENCY:
            return True, "FRED macroeconomic series verified", canonical

        # 4. Catalog or Seed presence
        yf_mapped = resolve_yf_symbol(clean_sym)
        if (clean_sym in catalog_symbols or 
            canonical in catalog_symbols or 
            yf_mapped in catalog_symbols or 
            s_no_slash in catalog_symbols):
            return True, "Present in catalog / seed database", canonical

        return False, "Symbol not found in any provider map or catalog", canonical

    elif ex in ('iran', 'bonbast', 'tsetmc', 'nobitex', 'wallex'):
        if clean_sym in BONBAST_MAP or canonical in BONBAST_MAP:
            return True, "Bonbast currency/gold mapping verified", canonical
        if clean_sym in TSETMC_INDEX_MAP or clean_sym in TSETMC_GOLD_FUNDS_MAP or clean_sym in TSETMC_INSTRUMENTS_MAP:
            return True, "TSETMC Tehran exchange mapping verified", canonical
        if clean_sym in ('USDT_NOBITEX', 'GOLD_NOBITEX', 'USDT_WALLEX', 'GOLD_WALLEX'):
            return True, "Direct Iranian exchange ticker verified", canonical

        return False, "Iranian domestic asset not found in Bonbast or TSETMC maps", canonical

    elif ex in ('binance', 'crypto', 'coingecko'):
        # Basic cryptocurrency pair structure check
        if any(clean_sym.endswith(q) for q in ('USDT', 'USDC', 'BUSD', 'BTC', 'ETH', 'EUR', 'TRY')):
            return True, "Crypto pair structure verified", canonical
        return False, "Unknown crypto pair format", canonical

    else:
        # Unknown exchange
        return False, f"Unsupported exchange '{exchange}'", None


async def check_alerts(
    alerts: List[Alert],
    offline: bool = False,
    timeout_sec: float = 8.0
) -> Tuple[int, int, List[Dict[str, Any]]]:
    """
    Checks all alerts and classifies them into resolved and unresolved.
    """
    catalog_symbols = load_catalog_symbols()
    resolved_count = 0
    unresolved_count = 0
    diagnostics = []

    if offline:
        for idx, alert in enumerate(alerts, 1):
            ex = alert.exchange
            sym = alert.symbol
            clean_sym = sym.strip().upper()
            canonical = resolve_symbol_alias(clean_sym)
            is_res, reason, sug = resolve_symbol_offline(ex, sym, catalog_symbols)
            if is_res:
                resolved_count += 1
            else:
                unresolved_count += 1
                diagnostics.append({
                    'index': idx,
                    'id': alert.id,
                    'user_id': str(alert.user_id)[:4] + '***' if alert.user_id else 'None',
                    'exchange': ex,
                    'symbol': sym,
                    'canonical': canonical,
                    'reason': reason,
                    'suggested_fix': sug or canonical
                })
        return resolved_count, unresolved_count, diagnostics

    if httpx is None:
        raise RuntimeError("httpx module is required for live network checks. Run with --offline or install httpx.")

    limits = httpx.Limits(max_keepalive_connections=20, max_connections=30)
    timeout = httpx.Timeout(timeout_sec, connect=4.0)

    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        for idx, alert in enumerate(alerts, 1):
            ex = alert.exchange
            sym = alert.symbol
            clean_sym = sym.strip().upper()
            canonical = resolve_symbol_alias(clean_sym)
            # Live network test
            t0 = asyncio.get_event_loop().time()
            try:
                price, traces = await fetch_price_with_trace(client, ex, sym, collect_all_traces=False)
                latency = round((asyncio.get_event_loop().time() - t0) * 1000, 1)

                if price is not None and price > 0:
                    resolved_count += 1
                elif clean_sym in LEGACY_CRYPTO_METRICS or canonical in LEGACY_CRYPTO_METRICS or any(t.get('state') == 'unsupported_legacy' for t in traces):
                    # Legacy crypto metric: treated as warning, not blocking unresolved
                    resolved_count += 1
                else:
                    # Try canonical alias as backup check
                    if canonical != clean_sym:
                        p_alt, _ = await fetch_price_with_trace(client, ex, canonical, collect_all_traces=False)
                        if p_alt is not None and p_alt > 0:
                            resolved_count += 1
                            continue

                    unresolved_count += 1
                    last_err = traces[-1].get('error') if traces else "Price returned None"
                    diagnostics.append({
                        'index': idx,
                        'id': alert.id,
                        'user_id': str(alert.user_id)[:4] + '***' if alert.user_id else 'None',
                        'exchange': ex,
                        'symbol': sym,
                        'canonical': canonical,
                        'reason': f"Live fetch failed ({last_err}) [{latency}ms]",
                        'suggested_fix': canonical
                    })
            except Exception as e:
                unresolved_count += 1
                diagnostics.append({
                    'index': idx,
                    'id': alert.id,
                    'user_id': str(alert.user_id)[:4] + '***' if alert.user_id else 'None',
                    'exchange': ex,
                    'symbol': sym,
                    'canonical': canonical,
                    'reason': f"Exception during fetch: {str(e)}",
                    'suggested_fix': canonical
                })

    return resolved_count, unresolved_count, diagnostics


def main():
    parser = argparse.ArgumentParser(description=f"SignalAlert v{APP_VERSION} Existing Alerts Resolution Checker")
    parser.add_argument("--file", default=None, help="Path to alerts_data.json (default: app.storage.DB_FILE)")
    parser.add_argument("--offline", action="store_true", help="Run offline structural/mapping verification without network calls")
    parser.add_argument("--timeout", type=float, default=8.0, help="Per-request timeout in seconds for live check")
    args = parser.parse_args()

    print("=" * 75)
    print(f"SignalAlert Alerts Resolution Checker v{APP_VERSION}")
    print(f"Mode: {'OFFLINE (MAPPINGS & CATALOG CHECK)' if args.offline else 'LIVE (REAL DATA & APIS)'}")
    print("=" * 75)

    alerts = []
    target_file = args.file or DB_FILE
    if args.file and os.path.exists(args.file):
        try:
            with open(target_file, 'r', encoding='utf-8') as f:
                raw = json.load(f)
                if isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, dict):
                            alerts.append(Alert(**item))
                elif isinstance(raw, dict):
                    for v in raw.values():
                        if isinstance(v, dict):
                            alerts.append(Alert(**v))
        except Exception as e:
            print(f"❌ Error reading alerts file '{target_file}': {e}")
            sys.exit(1)
    else:
        # Load alerts cleanly via storage module
        alerts = load_alerts_from_disk()

    if not alerts:
        print(f"ℹ️ No alerts found in '{target_file}'. Database is empty or clean.")
        print("✅ [SUCCESS] 0 alerts to check. All clean.")
        sys.exit(0)

    print(f"📁 Loaded {len(alerts)} alerts from '{target_file}'. Checking resolution...")
    print("-" * 75)

    resolved, unresolved, failed_items = asyncio.run(
        check_alerts(alerts, offline=args.offline, timeout_sec=args.timeout)
    )

    legacy_metrics = frozenset({'TOTAL', 'TOTAL2', 'TOTAL3', 'BTC.D', 'USDT.D', 'ETH.D'})
    legacy_alerts = [a for a in alerts if a.symbol.strip().upper() in legacy_metrics or resolve_symbol_alias(a.symbol.strip().upper()) in legacy_metrics]
    legacy_count = len(legacy_alerts)

    print(f"📊 SUMMARY:")
    print(f"   • Total Alerts:     {len(alerts)}")
    print(f"   • Resolved:         {resolved} ({(resolved / len(alerts) * 100):.1f}%)")
    print(f"   • Unresolved:       {unresolved} ({(unresolved / len(alerts) * 100):.1f}%)")
    if legacy_count > 0:
        print(f"   • Legacy Warnings:  {legacy_count} (unsupported_legacy non-blocking)")
    print("-" * 75)

    if unresolved > 0:
        print(f"❌ [BLOCKED] {unresolved} alert(s) failed to resolve:")
        print(f"{'Idx':<4} | {'Alert ID':<14} | {'Exchange':<14} | {'Symbol':<12} | {'Canonical':<10} | {'Reason'}")
        print("-" * 75)
        for item in failed_items:
            print(f"{item['index']:<4} | {item['id']:<14} | {item['exchange']:<14} | {item['symbol']:<12} | {item['canonical']:<10} | {item['reason']}")
            if item.get('suggested_fix'):
                print(f"     💡 Suggested Resolution: Map '{item['symbol']}' -> '{item['suggested_fix']}'")
        print("=" * 75)
        print("🛑 STOPPING: Unresolved alerts exist. Fix mappings or update legacy alert records before proceeding.")
        sys.exit(1)
    else:
        print("🎉 [SUCCESS] 100% of alerts resolved successfully! Zero broken alerts.")
        print("=" * 75)
        sys.exit(0)


if __name__ == '__main__':
    main()
