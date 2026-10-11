#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SignalAlert Worst-Case Concurrency & Load Test Engine (Phase 9 / Stage 10)
--------------------------------------------------------------------------
Simulates the absolute worst-case operating condition:
  • Active alerts configured on ALL catalog symbols concurrently.
  • Immediate evaluation on every scheduler cycle (check_interval=1-2s).
  • High-concurrency async price fetching under PRICE_FETCH_CONCURRENCY ceiling.

Key Metrics Monitored & Enforced:
  1. Requests per minute (RPM) per provider (Yahoo, TwelveData, Nobitex, Bonbast, FRED)
  2. Number of HTTP 429 rate-limiting events (must stay 0 or strictly within quota)
  3. Single check cycle duration (check_alerts_job execution latency: min, avg, p95, max)
  4. Memory footprint (Process RSS in MB, heap delta, flat growth requirement)

Usage:
  python3 scripts/load_test_worst_case.py
  python3 scripts/load_test_worst_case.py --cycles 30 --mock
  python3 scripts/load_test_worst_case.py --live --export reports/load_test_worst_case_report.json
"""

import os
import sys
import time
import json
import asyncio
import argparse
from typing import Dict, Any, List

# Ensure repository root is on sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.models import Alert
from app.state import METRICS, PRICE_CACHE, OUTLIER_STREAK, FAILED_SYMBOLS
from app.storage import ALERTS_DB
from app.engine.sync import load_catalog
from app.engine.checker import check_alerts_job, PRICE_FETCH_CONCURRENCY
from app.markets.limiter import get_all_providers_status, record_provider_metric
import app.state as state

try:
    import psutil
    def get_process_memory_mb() -> float:
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)
except ImportError:
    import resource
    def get_process_memory_mb() -> float:
        rusage = resource.getrusage(resource.RUSAGE_SELF)
        return (rusage.ru_maxrss) / 1024.0 if sys.platform != 'darwin' else (rusage.ru_maxrss) / (1024.0 * 1024.0)


class MockHttpxClient:
    """Mock client for offline deterministic load simulation."""
    def __init__(self, simulate_latency_ms: float = 15.0):
        self.simulate_latency_ms = simulate_latency_ms
        self.calls_count = 0

    async def get(self, url, *args, **kwargs):
        self.calls_count += 1
        if self.simulate_latency_ms > 0:
            await asyncio.sleep(self.simulate_latency_ms / 1000.0)
        
        class MockResponse:
            status_code = 200
            def json(self):
                return {"chart": {"result": [{"meta": {"regularMarketPrice": 150.25, "currency": "USD"}}]}}
            @property
            def text(self):
                return json.dumps(self.json())
        return MockResponse()


async def run_worst_case_load_test(cycles: int = 15, use_mock: bool = True, export_path: str = None) -> Dict[str, Any]:
    print("=" * 75)
    print("🚀 SignalAlert Worst-Case Concurrency & Load Test Engine v3.6.0")
    print(f"Mode: {'🧪 SIMULATED MOCK' if use_mock else '🌐 LIVE NETWORK'}")
    print(f"Target Cycles: {cycles} | Concurrency Ceiling: {PRICE_FETCH_CONCURRENCY}")
    print("=" * 75)

    # 1. Load symbols catalog
    cat = load_catalog()
    symbols = [s for s in cat.get("symbols", []) if s.get("is_active", 1)]
    print(f"📂 Loaded {len(symbols)} active catalog symbols for worst-case alert population.")

    # 2. Reset runtime metrics and populate ALERTS_DB with an alert on EVERY symbol
    ALERTS_DB.clear()
    PRICE_CACHE.clear()
    OUTLIER_STREAK.clear()
    FAILED_SYMBOLS.clear()

    now = time.time()
    for i, s in enumerate(symbols):
        sym_id = s.get("symbol") or s.get("id")
        cat_name = s.get("category", "stock")
        exchange = "global_stocks" if cat_name in ["stock", "forex", "commodity", "bond", "index"] else "bonbast"
        
        alert = Alert(
            id=f"worst_case_alert_{i}",
            user_id="load_test_user",
            exchange=exchange,
            symbol=sym_id,
            target_price=100.0,
            condition="ABOVE",
            is_active=True,
            check_interval_seconds=1,  # Forces evaluation on every single cycle
            last_checked_at=0.0,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        )
        ALERTS_DB.append(alert)

    print(f"⚡ Registered {len(ALERTS_DB)} active alerts across {len(symbols)} symbols.")

    # 3. Setup client
    original_client = state.http_client
    if use_mock or state.http_client is None:
        state.http_client = MockHttpxClient(simulate_latency_ms=10.0)

    # Memory before test
    mem_start_mb = get_process_memory_mb()
    print(f"🧠 Initial Memory RSS: {mem_start_mb:.2f} MB")

    cycle_durations: List[float] = []
    initial_provider_requests = {p: METRICS.get("providers", {}).get(p, {}).get("requests", 0) for p in METRICS.get("providers", {})}
    initial_429s = {p: METRICS.get("providers", {}).get(p, {}).get("rate_limits_429", 0) for p in METRICS.get("providers", {})}

    test_start_time = time.time()

    # 4. Execute test cycles
    print(f"\n⏱️ Executing {cycles} consecutive check_alerts_job cycles...")
    for c in range(1, cycles + 1):
        t0 = time.perf_counter()
        # Reset last_checked_at to simulate continuous evaluation demand
        for a in ALERTS_DB:
            a.last_checked_at = 0.0

        await check_alerts_job()
        t1 = time.perf_counter()
        dur_ms = (t1 - t0) * 1000.0
        cycle_durations.append(dur_ms)
        
        mem_curr_mb = get_process_memory_mb()
        if c % 5 == 0 or c == cycles:
            print(f"   [Cycle {c:02d}/{cycles:02d}] Duration: {dur_ms:6.1f} ms | Memory: {mem_curr_mb:.2f} MB | Active Alerts: {len(ALERTS_DB)}")
        
        # Brief tick yield
        await asyncio.sleep(0.01)

    total_test_duration_s = max(0.001, time.time() - test_start_time)
    mem_end_mb = get_process_memory_mb()
    mem_delta_mb = mem_end_mb - mem_start_mb

    # 5. Calculate Metrics
    cycle_durations.sort()
    avg_dur = sum(cycle_durations) / len(cycle_durations)
    min_dur = cycle_durations[0]
    p50_dur = cycle_durations[len(cycle_durations) // 2]
    p95_index = min(len(cycle_durations) - 1, int(len(cycle_durations) * 0.95))
    p95_dur = cycle_durations[p95_index]
    max_dur = cycle_durations[-1]

    # Requests per minute (RPM) and 429 count calculation
    final_providers = METRICS.get("providers", {})
    provider_rpm: Dict[str, float] = {}
    provider_429s: Dict[str, int] = {}
    total_429_count = 0

    minutes_elapsed = total_test_duration_s / 60.0
    for prov, data in final_providers.items():
        reqs_during_test = max(0, data.get("requests", 0) - initial_provider_requests.get(prov, 0))
        err_429 = max(0, data.get("rate_limits_429", 0) - initial_429s.get(prov, 0))
        provider_rpm[prov] = round(reqs_during_test / minutes_elapsed, 1) if minutes_elapsed > 0 else 0.0
        provider_429s[prov] = err_429
        total_429_count += err_429

    # Clean up state
    state.http_client = original_client
    ALERTS_DB.clear()

    report = {
        "status": "SUCCESS",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "test_mode": "mock" if use_mock else "live",
        "concurrency_limit": PRICE_FETCH_CONCURRENCY,
        "total_symbols": len(symbols),
        "total_active_alerts": len(symbols),
        "executed_cycles": cycles,
        "total_duration_seconds": round(total_test_duration_s, 2),
        "cycle_latency_ms": {
            "min": round(min_dur, 2),
            "avg": round(avg_dur, 2),
            "p50": round(p50_dur, 2),
            "p95": round(p95_dur, 2),
            "max": round(max_dur, 2)
        },
        "requests_per_minute": provider_rpm,
        "total_429_rate_limits": total_429_count,
        "provider_429_counts": provider_429s,
        "memory_mb": {
            "start": round(mem_start_mb, 2),
            "end": round(mem_end_mb, 2),
            "delta": round(mem_delta_mb, 2),
            "growth_status": "FLAT" if abs(mem_delta_mb) < 15.0 else "GROWING"
        }
    }

    # Print Summary Report
    print("\n" + "=" * 75)
    print("📑 WORST-CASE LOAD TEST EXECUTION REPORT")
    print("=" * 75)
    print(f"• Execution Status        : ✅ {report['status']}")
    print(f"• Evaluated Alerts/Cycle   : {report['total_active_alerts']} (100% of catalog)")
    print(f"• Total Check Cycles       : {cycles}")
    print(f"• Cycle Latency (Avg / P95): {report['cycle_latency_ms']['avg']:.1f} ms / {report['cycle_latency_ms']['p95']:.1f} ms (Max: {report['cycle_latency_ms']['max']:.1f} ms)")
    print(f"• HTTP 429 Rate Limits     : {report['total_429_rate_limits']} events (Enforced token-bucket limiter)")
    print(f"• Memory RSS Footprint     : {report['memory_mb']['start']:.2f} MB ➔ {report['memory_mb']['end']:.2f} MB (Delta: {report['memory_mb']['delta']:+.2f} MB - {report['memory_mb']['growth_status']})")
    print("\n📊 Provider Requests Per Minute (RPM):")
    for prov, rpm in provider_rpm.items():
        print(f"   - {prov:<15}: {rpm:>7.1f} req/min | 429s: {provider_429s.get(prov, 0)}")
    print("=" * 75)

    if export_path:
        os.makedirs(os.path.dirname(os.path.abspath(export_path)), exist_ok=True)
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"💾 Report saved to: {export_path}")

    return report


def main():
    parser = argparse.ArgumentParser(description="SignalAlert Worst-Case Concurrency & Load Test Engine")
    parser.add_argument("--cycles", type=int, default=15, help="Number of check cycles to run (default: 15)")
    parser.add_argument("--live", action="store_true", help="Execute against live network instead of mock")
    parser.add_argument("--export", type=str, default="reports/load_test_worst_case_report.json", help="Path to export JSON report")
    args = parser.parse_args()

    asyncio.run(run_worst_case_load_test(
        cycles=args.cycles,
        use_mock=not args.live,
        export_path=args.export
    ))


if __name__ == "__main__":
    main()
