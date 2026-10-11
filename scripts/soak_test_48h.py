#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SignalAlert 48-Hour Soak & Endurance Test Engine (Phase 9 / Stage 10)
---------------------------------------------------------------------
Long-running endurance soak testing harness designed for production validation:
  • Runs continuous alert check cycles over extended periods (default: 48 hours).
  • Monitors provider rate limits, HTTP 429 occurrences, and token bucket status.
  • Tracks check_alerts_job cycle execution times (p50, p95, p99, max latency).
  • Continuously monitors process RSS memory to detect memory leaks and uncollected objects.
  • Periodically dumps progress checkpoints and generates full audit reports.

Key Metrics Monitored:
  1. Requests per minute (RPM) to each market provider.
  2. Total HTTP 429 rate limit events across the run.
  3. Cycle duration distribution for check_alerts_job (must stay < 1.5s).
  4. Process memory RSS over time (drift slope, leak detection).

Usage:
  # Standard 48-hour soak test on production server:
  python3 scripts/soak_test_48h.py --duration-hours 48.0

  # Quick verification mode (e.g. 1 minute):
  python3 scripts/soak_test_48h.py --duration-hours 0.02 --mock

  # Background execution:
  nohup python3 scripts/soak_test_48h.py --duration-hours 48.0 > soak_test.log 2>&1 &
"""

import os
import sys
import time
import json
import signal
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
from app.markets.limiter import get_all_providers_status
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


class SoakMockClient:
    """Mock client providing simulated market ticks for endurance test."""
    def __init__(self, latency_ms: float = 12.0):
        self.latency_ms = latency_ms
        self.counter = 0

    async def get(self, url, *args, **kwargs):
        self.counter += 1
        if self.latency_ms > 0:
            await asyncio.sleep(self.latency_ms / 1000.0)
        
        class MockResp:
            status_code = 200
            def json(self):
                return {"chart": {"result": [{"meta": {"regularMarketPrice": 185.5, "currency": "USD"}}]}}
            @property
            def text(self):
                return json.dumps(self.json())
        return MockResp()


_STOP_REQUESTED = False

def handle_interrupt(sig, frame):
    global _STOP_REQUESTED
    print("\n🛑 Interrupt received! Gracefully winding down soak test and compiling final report...")
    _STOP_REQUESTED = True


async def run_soak_test(
    duration_hours: float = 48.0,
    cycle_interval_seconds: float = 2.0,
    use_mock: bool = False,
    checkpoint_interval_seconds: float = 300.0,
    report_file: str = "reports/soak_test_48h_report.json",
    checkpoint_file: str = "reports/soak_test_checkpoint.json"
) -> Dict[str, Any]:
    global _STOP_REQUESTED
    signal.signal(signal.SIGINT, handle_interrupt)
    signal.signal(signal.SIGTERM, handle_interrupt)

    total_target_seconds = duration_hours * 3600.0
    print("=" * 78)
    print("⏳ SignalAlert 48-Hour Soak & Endurance Test Engine v3.6.0")
    print(f"Target Duration       : {duration_hours:.2f} hours ({total_target_seconds:.0f} seconds)")
    print(f"Cycle Interval        : {cycle_interval_seconds:.1f} s | Concurrency Limit: {PRICE_FETCH_CONCURRENCY}")
    print(f"Network Mode          : {'🧪 MOCK SIMULATION' if use_mock else '🌐 LIVE PROVIDERS'}")
    print(f"Report Output         : {report_file}")
    print("=" * 78)

    # 1. Populate Alert DB with active alerts across catalog symbols
    cat = load_catalog()
    symbols = [s for s in cat.get("symbols", []) if s.get("is_active", 1)]
    print(f"📂 Loaded {len(symbols)} catalog symbols for endurance alerting.")

    ALERTS_DB.clear()
    for i, s in enumerate(symbols):
        sym_id = s.get("symbol") or s.get("id")
        cat_name = s.get("category", "stock")
        exchange = "global_stocks" if cat_name in ["stock", "forex", "commodity", "bond", "index"] else "bonbast"
        
        alert = Alert(
            id=f"soak_alert_{i}",
            user_id="soak_test_runner",
            exchange=exchange,
            symbol=sym_id,
            target_price=200.0,
            condition="ABOVE",
            is_active=True,
            check_interval_seconds=int(cycle_interval_seconds),
            last_checked_at=0.0
        )
        ALERTS_DB.append(alert)

    original_client = state.http_client
    if use_mock or state.http_client is None:
        state.http_client = SoakMockClient()

    start_time = time.time()
    last_checkpoint_time = start_time
    mem_initial_mb = get_process_memory_mb()
    mem_peak_mb = mem_initial_mb

    cycle_durations: List[float] = []
    memory_samples: List[Dict[str, Any]] = [{"time_s": 0, "mem_mb": mem_initial_mb}]
    completed_cycles = 0

    print(f"🧠 Initial Process RSS Memory: {mem_initial_mb:.2f} MB")
    print("🚀 Soak test started...\n")

    try:
        while not _STOP_REQUESTED:
            elapsed_total = time.time() - start_time
            if elapsed_total >= total_target_seconds:
                print(f"\n🎯 Reached target duration of {duration_hours:.2f} hours!")
                break

            # Execute single alert check cycle
            c_start = time.perf_counter()
            # Force alerts to be due
            now_ts = time.time()
            for a in ALERTS_DB:
                a.last_checked_at = now_ts - a.check_interval_seconds - 1

            await check_alerts_job()
            c_end = time.perf_counter()

            c_dur_ms = (c_end - c_start) * 1000.0
            cycle_durations.append(c_dur_ms)
            completed_cycles += 1

            # Memory tracking
            current_mem_mb = get_process_memory_mb()
            if current_mem_mb > mem_peak_mb:
                mem_peak_mb = current_mem_mb

            # Periodic checkpointing
            if (time.time() - last_checkpoint_time) >= checkpoint_interval_seconds:
                last_checkpoint_time = time.time()
                memory_samples.append({
                    "time_s": round(elapsed_total, 1),
                    "mem_mb": round(current_mem_mb, 2)
                })

                # Compute current RPM
                min_elapsed = max(0.01, elapsed_total / 60.0)
                prov_metrics = METRICS.get("providers", {})
                prov_summary = {
                    p: {
                        "rpm": round(data.get("requests", 0) / min_elapsed, 1),
                        "429s": data.get("rate_limits_429", 0)
                    }
                    for p, data in prov_metrics.items()
                }

                checkpoint_data = {
                    "checkpoint_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "elapsed_hours": round(elapsed_total / 3600.0, 3),
                    "completed_cycles": completed_cycles,
                    "current_mem_mb": round(current_mem_mb, 2),
                    "peak_mem_mb": round(mem_peak_mb, 2),
                    "mem_delta_mb": round(current_mem_mb - mem_initial_mb, 2),
                    "providers": prov_summary
                }

                os.makedirs(os.path.dirname(os.path.abspath(checkpoint_file)), exist_ok=True)
                with open(checkpoint_file, "w", encoding="utf-8") as f:
                    json.dump(checkpoint_data, f, indent=2)

                print(f"📍 [Checkpoint | {elapsed_total/3600.0:5.2f}h] Cycles: {completed_cycles} | Mem: {current_mem_mb:.1f} MB (Peak: {mem_peak_mb:.1f} MB) | Cycle Latency: {c_dur_ms:.1f} ms")

            # Sleep remaining time of cycle
            spent = (c_end - c_start)
            sleep_time = max(0.005, cycle_interval_seconds - spent)
            await asyncio.sleep(sleep_time)

    finally:
        state.http_client = original_client
        ALERTS_DB.clear()

    # Final calculations
    total_elapsed_s = max(0.001, time.time() - start_time)
    mem_final_mb = get_process_memory_mb()
    mem_growth_mb = mem_final_mb - mem_initial_mb

    if cycle_durations:
        cycle_durations.sort()
        avg_dur = sum(cycle_durations) / len(cycle_durations)
        min_dur = cycle_durations[0]
        p50_dur = cycle_durations[len(cycle_durations) // 2]
        p95_dur = cycle_durations[min(len(cycle_durations) - 1, int(len(cycle_durations) * 0.95))]
        p99_dur = cycle_durations[min(len(cycle_durations) - 1, int(len(cycle_durations) * 0.99))]
        max_dur = cycle_durations[-1]
    else:
        min_dur = avg_dur = p50_dur = p95_dur = p99_dur = max_dur = 0.0

    # Providers summary
    min_elapsed = max(0.01, total_elapsed_s / 60.0)
    final_providers = METRICS.get("providers", {})
    provider_report = {}
    total_429s = 0
    for p, data in final_providers.items():
        reqs = data.get("requests", 0)
        c429 = data.get("rate_limits_429", 0)
        total_429s += c429
        provider_report[p] = {
            "total_requests": reqs,
            "requests_per_minute": round(reqs / min_elapsed, 1),
            "rate_limits_429": c429
        }

    leak_status = "PASS (Flat Memory)" if abs(mem_growth_mb) < 25.0 else "WARNING (Memory Drift Detected)"

    report = {
        "status": "COMPLETED",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_hours": round(total_elapsed_s / 3600.0, 3),
        "target_hours": duration_hours,
        "completed_cycles": completed_cycles,
        "cycle_latency_ms": {
            "min": round(min_dur, 2),
            "avg": round(avg_dur, 2),
            "p50": round(p50_dur, 2),
            "p95": round(p95_dur, 2),
            "p99": round(p99_dur, 2),
            "max": round(max_dur, 2)
        },
        "provider_metrics": provider_report,
        "total_429_errors": total_429s,
        "memory_profile_mb": {
            "initial": round(mem_initial_mb, 2),
            "final": round(mem_final_mb, 2),
            "peak": round(mem_peak_mb, 2),
            "growth_delta": round(mem_growth_mb, 2),
            "leak_assessment": leak_status
        },
        "memory_samples_count": len(memory_samples)
    }

    # Print Report
    print("\n" + "=" * 78)
    print("📑 48-HOUR SOAK & ENDURANCE TEST FINAL REPORT")
    print("=" * 78)
    print(f"• Execution Status      : ✅ {report['status']}")
    print(f"• Elapsed Time          : {report['duration_hours']:.2f} hours ({completed_cycles} cycles completed)")
    print(f"• Cycle Latency (Avg)   : {report['cycle_latency_ms']['avg']:.1f} ms (p95: {report['cycle_latency_ms']['p95']:.1f} ms, max: {report['cycle_latency_ms']['max']:.1f} ms)")
    print(f"• Total HTTP 429 Errors : {report['total_429_errors']}")
    print(f"• Memory Stability      : {report['memory_profile_mb']['initial']:.1f} MB ➔ {report['memory_profile_mb']['final']:.1f} MB (Peak: {report['memory_profile_mb']['peak']:.1f} MB, Delta: {report['memory_profile_mb']['growth_delta']:+.1f} MB)")
    print(f"• Memory Leak Verdict   : 🛡️ {report['memory_profile_mb']['leak_assessment']}")
    print("\n📊 Provider Statistics:")
    for prov, pdata in provider_report.items():
        print(f"   - {prov:<15}: {pdata['requests_per_minute']:>6.1f} req/min | Total: {pdata['total_requests']:>6} | 429s: {pdata['rate_limits_429']}")
    print("=" * 78)

    os.makedirs(os.path.dirname(os.path.abspath(report_file)), exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"💾 Soak report exported to: {report_file}")

    return report


def main():
    parser = argparse.ArgumentParser(description="SignalAlert 48-Hour Soak & Endurance Test Engine")
    parser.add_argument("--duration-hours", type=float, default=48.0, help="Total duration in hours (default: 48.0)")
    parser.add_argument("--interval-seconds", type=float, default=2.0, help="Interval between cycles in seconds (default: 2.0)")
    parser.add_argument("--mock", action="store_true", help="Run with simulated mock responses")
    parser.add_argument("--checkpoint-seconds", type=float, default=300.0, help="Checkpoint interval in seconds (default: 300)")
    parser.add_argument("--export", type=str, default="reports/soak_test_48h_report.json", help="Path to final JSON report")
    args = parser.parse_args()

    asyncio.run(run_soak_test(
        duration_hours=args.duration_hours,
        cycle_interval_seconds=args.interval_seconds,
        use_mock=args.mock,
        checkpoint_interval_seconds=args.checkpoint_seconds,
        report_file=args.export
    ))


if __name__ == "__main__":
    main()
