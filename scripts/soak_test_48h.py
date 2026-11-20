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

  # Crypto V2 48-hour soak test across all 18 canonical crypto exchanges (no bonbast/stocks):
  nohup python3 scripts/soak_test_48h.py --crypto-only --duration-hours 48.0 --interval-seconds 1.0 --server-pid $(cat server.pid) > soak_test.log 2>&1 &

  # Quick verification mode (e.g. 1 minute):
  python3 scripts/soak_test_48h.py --duration-hours 0.02 --mock

  # Background execution, also measuring the real server process memory:
  nohup python3 scripts/soak_test_48h.py --duration-hours 48.0 --server-pid $(cat server.pid) > soak_test.log 2>&1 &
"""

import os
import sys
import time
import json
import signal
import asyncio
import argparse
from typing import Dict, Any, List, Optional, Tuple

# Force UTF-8 stdout/stderr on Windows consoles (cp1252 crashes on emoji prints)
try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Ensure repository root is on sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from _soak_common import (
    isolate_data_dir, require_isolated_data_dir, build_live_http_client, sample_pid_memory_mb,
    compute_memory_slope_mb_per_hour, memory_verdict, UNREACHABLE_TARGET_PRICE,
)

# app.* is imported lazily by _load_app(): main() runs isolate_data_dir() first, so the soak can never read or
# write the real alerts_data.json / user_profiles.json / fcm_outbox.json.
Alert = METRICS = ALERTS_DB = load_catalog = check_alerts_job = check_crypto_alerts_job = PRICE_FETCH_CONCURRENCY = state = config = None


def _load_app() -> None:
    global Alert, METRICS, ALERTS_DB, load_catalog, check_alerts_job, check_crypto_alerts_job, PRICE_FETCH_CONCURRENCY, state, config
    import app.config as _config
    from app.models import Alert as _Alert
    from app.state import METRICS as _METRICS
    from app.storage import ALERTS_DB as _ALERTS_DB
    from app.engine.sync import load_catalog as _load_catalog
    from app.engine.checker import (
        check_alerts_job as _check,
        check_crypto_alerts_job as _check_crypto,
        PRICE_FETCH_CONCURRENCY as _conc,
    )
    import app.state as _state
    config = _config
    Alert, METRICS, ALERTS_DB, load_catalog = _Alert, _METRICS, _ALERTS_DB, _load_catalog
    check_alerts_job, check_crypto_alerts_job, PRICE_FETCH_CONCURRENCY, state = _check, _check_crypto, _conc, _state

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


def make_client(use_mock: bool):
    """Mock only when explicitly requested; otherwise always a real httpx client (never a silent fallback)."""
    return SoakMockClient() if use_mock else build_live_http_client()


def _build_crypto_soak_alerts(
    crypto_symbols: List[str],
    target_price: float,
    cycle_interval_seconds: float,
) -> Tuple[List[Any], List[str], Dict[str, List[str]]]:
    """
    Constructs synthetic unreachable alerts across all canonical Crypto V2 exchanges
    registered in app.markets.crypto_registry (18 exchanges).
    Returns: (alerts, exchange_ids, exchange_native_symbols_map).
    """
    from app.markets.crypto_registry import get_supported_exchange_ids
    from app.markets.crypto_catalog import get_exchange_adapter

    exchange_ids = list(get_supported_exchange_ids())
    alerts: List[Any] = []
    native_map: Dict[str, List[str]] = {}
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    interval = max(1, int(cycle_interval_seconds))

    idx = 0
    for ex in exchange_ids:
        adapter = get_exchange_adapter(ex)
        native_syms: List[str] = []
        for base in crypto_symbols:
            clean_base = (base or "").strip().upper()
            if not clean_base:
                continue
            native_sym = adapter.to_native_symbol(clean_base) if adapter else f"{clean_base}USDT"
            if native_sym:
                native_syms.append(native_sym)
            alerts.append(Alert(
                id=f"soak_crypto_{ex}_{idx}",
                user_id="soak_test_runner",
                exchange=ex,
                symbol=f"{clean_base}USDT",
                base_currency=clean_base,
                counter_currency="USDT",
                market_symbol=native_sym or None,
                target_price=target_price,
                condition="ABOVE",
                is_active=True,
                check_interval_seconds=interval,
                last_checked_at=0.0,
                created_at=created_at,
            ))
            idx += 1
        native_map[ex] = native_syms
    return alerts, exchange_ids, native_map


async def run_soak_test(
    duration_hours: float = 48.0,
    cycle_interval_seconds: float = 2.0,
    use_mock: bool = False,
    checkpoint_interval_seconds: float = 300.0,
    max_cycles: Optional[int] = None,
    total_target_seconds: Optional[float] = None,
    report_file: str = "reports/soak_test_48h_report.json",
    checkpoint_file: str = "reports/soak_test_checkpoint.json",
    target_price: float = UNREACHABLE_TARGET_PRICE,
    server_pid: Optional[int] = None,
    leak_threshold_mb_per_hour: float = 0.5,
    sample_interval_seconds: Optional[float] = None,
    crypto_only: bool = False,
    include_crypto: bool = False,
    skip_bonbast: bool = False,
    crypto_symbols: Optional[List[str]] = None,
    suppress_admin_alerts: bool = True,
) -> Dict[str, Any]:
    global _STOP_REQUESTED
    _STOP_REQUESTED = False
    require_isolated_data_dir()
    _load_app()
    signal.signal(signal.SIGINT, handle_interrupt)
    signal.signal(signal.SIGTERM, handle_interrupt)

    # Save & optionally suppress admin Telegram notifications so soak runs never spam admin chat
    orig_admin_chat_id = getattr(config, "TELEGRAM_ADMIN_CHAT_ID", "")
    orig_bot_token = getattr(config, "TELEGRAM_BOT_TOKEN", "")
    if suppress_admin_alerts:
        config.TELEGRAM_ADMIN_CHAT_ID = ""
        config.TELEGRAM_BOT_TOKEN = ""

    use_crypto = bool(crypto_only or include_crypto)
    soak_profile = "crypto_only" if crypto_only else ("mixed_with_crypto" if include_crypto else "catalog_default")
    parsed_crypto_symbols = [s.strip().upper() for s in (crypto_symbols or ["BTC", "ETH"]) if s and s.strip()]
    if not parsed_crypto_symbols:
        parsed_crypto_symbols = ["BTC", "ETH"]

    if total_target_seconds is None:
        total_target_seconds = duration_hours * 3600.0
    else:
        duration_hours = total_target_seconds / 3600.0

    # Auto-adjust checkpoint interval for shorter runs so checkpoints fire
    if checkpoint_interval_seconds > total_target_seconds:
        checkpoint_interval_seconds = max(5.0, total_target_seconds / 3.0)

    print_every = 1 if (max_cycles and max_cycles <= 20) or total_target_seconds <= 60 else (2 if total_target_seconds <= 300 else 5)

    print("=" * 78)
    print("⏳ SignalAlert 48-Hour Soak & Endurance Test Engine v3.9.2")
    print(f"Soak Profile          : {soak_profile} | Admin Alerts Suppressed: {suppress_admin_alerts}")
    if max_cycles:
        print(f"Target Cycles         : {max_cycles} cycles")
    print(f"Target Duration       : {duration_hours:.4f} hours ({total_target_seconds:.1f} seconds)")
    print(f"Cycle Interval        : {cycle_interval_seconds:.1f} s | Concurrency Limit: {PRICE_FETCH_CONCURRENCY}")
    print(f"Network Mode          : {'🧪 MOCK SIMULATION' if use_mock else '🌐 LIVE PROVIDERS (real httpx client)'}")
    if server_pid:
        print(f"Server PID monitored  : {server_pid}")
    print(f"Heartbeat Cadence     : Every {print_every} cycle(s)")
    print(f"Report Output         : {report_file}")
    print("=" * 78)

    # 1. Populate Alert DB according to soak profile
    ALERTS_DB.clear()
    catalog_alert_count = 0
    if not crypto_only:
        cat = load_catalog()
        symbols = [s for s in cat.get("symbols", []) if s.get("is_active", 1)]
        skipped_bonbast = 0
        for i, s in enumerate(symbols):
            sym_id = s.get("symbol") or s.get("id")
            cat_name = s.get("category", "stock")
            exchange = "global_stocks" if cat_name in ["stock", "forex", "commodity", "bond", "index"] else "bonbast"
            if skip_bonbast and exchange == "bonbast":
                skipped_bonbast += 1
                continue
            alert = Alert(
                id=f"soak_alert_{i}",
                user_id="soak_test_runner",
                exchange=exchange,
                symbol=sym_id,
                target_price=target_price,
                condition="ABOVE",
                is_active=True,
                check_interval_seconds=max(1, int(cycle_interval_seconds)),
                last_checked_at=0.0,
                created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            )
            ALERTS_DB.append(alert)
            catalog_alert_count += 1
        extra_note = f" (skipped {skipped_bonbast} bonbast)" if skipped_bonbast else ""
        print(f"📂 Loaded {catalog_alert_count} catalog alerts{extra_note}.")

    crypto_exchanges: List[str] = []
    crypto_native_map: Dict[str, List[str]] = {}
    if use_crypto:
        crypto_alerts, crypto_exchanges, crypto_native_map = _build_crypto_soak_alerts(
            crypto_symbols=parsed_crypto_symbols,
            target_price=target_price,
            cycle_interval_seconds=cycle_interval_seconds,
        )
        ALERTS_DB.extend(crypto_alerts)
        print(
            f"🪙 Loaded {len(crypto_alerts)} Crypto V2 alerts across "
            f"{len(crypto_exchanges)} canonical exchanges ({', '.join(parsed_crypto_symbols)})."
        )

    original_client = state.http_client
    # Mock ONLY when explicitly requested. Live mode always gets a real client (the old
    # "or state.http_client is None" fallback silently mocked every standalone run).
    soak_client = make_client(use_mock)
    state.http_client = soak_client
    print(f"🔌 HTTP client in use  : {type(soak_client).__name__}")

    # Start isolated Crypto V2 Stage A poller (live) or seed mock snapshots (mock)
    poller_started = False
    if use_crypto:
        from app.markets.crypto_snapshot import update_exchange_snapshot, clear_snapshot_store
        if use_mock:
            clear_snapshot_store()
            now_seed = time.time()
            for ex, nsyms in crypto_native_map.items():
                mock_prices = {ns: 50000.0 + idx * 10.0 for idx, ns in enumerate(nsyms)}
                update_exchange_snapshot(ex, mock_prices, status="OK", latency_ms=5.0, as_of=now_seed, source="mock")
            print(f"🧪 Seeded mock Crypto V2 snapshots for {len(crypto_native_map)} exchanges.")
        else:
            from app.markets.crypto_poller import CRYPTO_POLLER
            CRYPTO_POLLER.start()
            poller_started = True
            warmup_wait = min(3.0, max(0.5, total_target_seconds / 4.0))
            print(f"⚡ Crypto V2 Stage A Poller started (isolated lock in DATA_DIR). Warming up {warmup_wait:.1f}s...")
            await asyncio.sleep(warmup_wait)

    if sample_interval_seconds is None:
        sample_interval_seconds = max(1.0, min(60.0, total_target_seconds / 30.0))
    warmup_seconds = min(600.0, total_target_seconds * 0.1)
    server_mem_initial = sample_pid_memory_mb(server_pid) if server_pid else None  # fail fast on bad pid

    start_time = time.time()
    last_sample_time = start_time
    last_checkpoint_time = start_time
    mem_initial_mb = get_process_memory_mb()
    mem_peak_mb = mem_initial_mb

    cycle_durations: List[float] = []
    memory_samples: List[Dict[str, Any]] = [{"time_s": 0, "mem_mb": mem_initial_mb}]
    server_samples: List[Dict[str, Any]] = [{"time_s": 0, "mem_mb": server_mem_initial}] if server_pid else []
    completed_cycles = 0

    print(f"🧠 Initial Process RSS Memory: {mem_initial_mb:.2f} MB")
    print("🚀 Soak test started...\n")

    try:
        while not _STOP_REQUESTED:
            elapsed_total = time.time() - start_time
            if total_target_seconds and elapsed_total >= total_target_seconds:
                print(f"\n🎯 Reached target duration of {total_target_seconds:.1f}s ({duration_hours:.2f}h)!")
                break
            if max_cycles and completed_cycles >= max_cycles:
                print(f"\n🎯 Reached target limit of {max_cycles} cycles!")
                break

            # Refresh mock crypto snapshots so they never go stale during long mock runs
            if use_crypto and use_mock:
                from app.markets.crypto_snapshot import update_exchange_snapshot
                now_seed = time.time()
                for ex, nsyms in crypto_native_map.items():
                    mock_prices = {ns: 50000.0 + idx * 10.0 for idx, ns in enumerate(nsyms)}
                    update_exchange_snapshot(ex, mock_prices, status="OK", latency_ms=5.0, as_of=now_seed, source="mock")

            # Execute single alert check cycle
            c_start = time.perf_counter()
            # Force alerts to be due
            now_ts = time.time()
            for a in ALERTS_DB:
                a.last_checked_at = now_ts - a.check_interval_seconds - 1

            if use_crypto:
                # Stage B 1s evaluator handles the 16 'crypto' exchanges;
                # main evaluator with skip_crypto=True handles 'iran_crypto' (tabdeal, kifpool) + any catalog alerts.
                await check_crypto_alerts_job()
                await check_alerts_job(skip_crypto=True)
            else:
                await check_alerts_job()
            c_end = time.perf_counter()

            c_dur_ms = (c_end - c_start) * 1000.0
            cycle_durations.append(c_dur_ms)
            completed_cycles += 1

            # Memory tracking
            current_mem_mb = get_process_memory_mb()
            if current_mem_mb > mem_peak_mb:
                mem_peak_mb = current_mem_mb

            # Periodic memory sampling (own process + optional server process) for the leak slope
            if (time.time() - last_sample_time) >= sample_interval_seconds:
                last_sample_time = time.time()
                memory_samples.append({"time_s": round(elapsed_total, 1), "mem_mb": round(current_mem_mb, 2)})
                if server_pid:
                    server_samples.append({"time_s": round(elapsed_total, 1),
                                           "mem_mb": round(sample_pid_memory_mb(server_pid), 2)})

            # Live heartbeat output
            if completed_cycles % print_every == 0:
                print(f"   [Cycle {completed_cycles:04d}] Latency: {c_dur_ms:6.1f} ms | Mem: {current_mem_mb:5.1f} MB | Elapsed: {elapsed_total:5.1f}s")

            # Periodic checkpointing
            if (time.time() - last_checkpoint_time) >= checkpoint_interval_seconds:
                last_checkpoint_time = time.time()

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
                    "server_mem_mb": server_samples[-1]["mem_mb"] if server_samples else None,
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
        # Capture Crypto V2 snapshot/poller telemetry before tearing down
        crypto_report = None
        if use_crypto:
            try:
                from app.markets.crypto_snapshot import get_all_snapshots_status, clear_snapshot_store
                from app.markets.crypto_poller import get_crypto_latency_percentiles, CRYPTO_POLLER
                snaps = get_all_snapshots_status()
                healthy_ex = sum(1 for s in snaps.values() if s.get("status") == "OK" and not s.get("is_stale"))
                crypto_report = {
                    "exchanges_tested": crypto_exchanges,
                    "exchanges_count": len(crypto_exchanges),
                    "healthy_snapshots": healthy_ex,
                    "crypto_symbols_per_exchange": parsed_crypto_symbols,
                    "total_crypto_checks": METRICS.get("total_crypto_checks", 0),
                    "poll_latency": get_crypto_latency_percentiles(),
                    "snapshots": snaps,
                }
                if poller_started:
                    CRYPTO_POLLER.stop()
                    if CRYPTO_POLLER._client and not CRYPTO_POLLER._client.is_closed:
                        await CRYPTO_POLLER._client.aclose()
                        CRYPTO_POLLER._client = None
                clear_snapshot_store()
            except Exception as ce:
                crypto_report = {"error": str(ce)}

        state.http_client = original_client
        ALERTS_DB.clear()
        if suppress_admin_alerts:
            config.TELEGRAM_ADMIN_CHAT_ID = orig_admin_chat_id
            config.TELEGRAM_BOT_TOKEN = orig_bot_token
        if not use_mock:
            await soak_client.aclose()

    # Final calculations
    total_elapsed_s = max(0.001, time.time() - start_time)
    mem_final_mb = get_process_memory_mb()
    mem_growth_mb = mem_final_mb - mem_initial_mb
    memory_samples.append({"time_s": round(total_elapsed_s, 1), "mem_mb": round(mem_final_mb, 2)})
    own_slope = compute_memory_slope_mb_per_hour(memory_samples, warmup_seconds)
    server_report = None
    if server_pid:
        server_final = sample_pid_memory_mb(server_pid)
        server_samples.append({"time_s": round(total_elapsed_s, 1), "mem_mb": round(server_final, 2)})
        server_slope = compute_memory_slope_mb_per_hour(server_samples, warmup_seconds)
        server_report = {
            "pid": server_pid,
            "initial": round(server_mem_initial, 2),
            "final": round(server_final, 2),
            "peak": round(max(s["mem_mb"] for s in server_samples), 2),
            "growth_delta": round(server_final - server_mem_initial, 2),
            "slope_mb_per_hour": None if server_slope is None else round(server_slope, 3),
            "leak_assessment": memory_verdict(server_slope, total_elapsed_s, leak_threshold_mb_per_hour),
        }

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

    leak_status = memory_verdict(own_slope, total_elapsed_s, leak_threshold_mb_per_hour)

    report = {
        "status": "COMPLETED",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "soak_profile": soak_profile,
        "admin_alerts_suppressed": suppress_admin_alerts,
        "duration_hours": round(total_elapsed_s / 3600.0, 3),
        "target_hours": duration_hours,
        "completed_cycles": completed_cycles,
        "network_mode": "mock" if use_mock else "live",
        "http_client": type(soak_client).__name__,
        "cycle_latency_ms": {
            "min": round(min_dur, 2),
            "avg": round(avg_dur, 2),
            "p50": round(p50_dur, 2),
            "p95": round(p95_dur, 2),
            "p99": round(p99_dur, 2),
            "max": round(max_dur, 2)
        },
        "provider_metrics": provider_report,
        "crypto_metrics": crypto_report,
        "total_429_errors": total_429s,
        "memory_profile_mb": {
            "initial": round(mem_initial_mb, 2),
            "final": round(mem_final_mb, 2),
            "peak": round(mem_peak_mb, 2),
            "growth_delta": round(mem_growth_mb, 2),
            "slope_mb_per_hour": None if own_slope is None else round(own_slope, 3),
            "leak_assessment": leak_status,
            "scope": "soak script process (NOT the server) - see server_memory_mb"
        },
        "server_memory_mb": server_report,
        "memory_samples_count": len(memory_samples)
    }

    # Print Report
    print("\n" + "=" * 78)
    print("📑 48-HOUR SOAK & ENDURANCE TEST FINAL REPORT")
    print("=" * 78)
    print(f"• Execution Status      : ✅ {report['status']} (profile: {soak_profile})")
    print(f"• Elapsed Time          : {report['duration_hours']:.2f} hours ({completed_cycles} cycles completed)")
    print(f"• Cycle Latency (Avg)   : {report['cycle_latency_ms']['avg']:.1f} ms (p95: {report['cycle_latency_ms']['p95']:.1f} ms, max: {report['cycle_latency_ms']['max']:.1f} ms)")
    print(f"• Total HTTP 429 Errors : {report['total_429_errors']}")
    print(f"• Memory Stability      : {report['memory_profile_mb']['initial']:.1f} MB ➔ {report['memory_profile_mb']['final']:.1f} MB (Peak: {report['memory_profile_mb']['peak']:.1f} MB, Delta: {report['memory_profile_mb']['growth_delta']:+.1f} MB)")
    print(f"• Memory Leak Verdict   : 🛡️ {report['memory_profile_mb']['leak_assessment']} [soak process only]")
    if server_report:
        print(f"• Server RSS (PID {server_report['pid']}) : {server_report['initial']:.1f} MB ➔ {server_report['final']:.1f} MB (Peak: {server_report['peak']:.1f} MB) | {server_report['leak_assessment']}")
    else:
        print("• Server RSS            : not monitored (pass --server-pid $(cat server.pid) to measure the real server)")
    if crypto_report and "error" not in crypto_report:
        pl = crypto_report.get("poll_latency", {})
        print(
            f"• Crypto V2 Snapshots   : {crypto_report['healthy_snapshots']}/{crypto_report['exchanges_count']} healthy | "
            f"Stage B Checks: {crypto_report['total_crypto_checks']} | "
            f"Poller p50={pl.get('p50_ms', 0.0)}ms p95={pl.get('p95_ms', 0.0)}ms (samples={pl.get('samples', 0)})"
        )
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
    parser.add_argument("--duration-hours", type=float, default=None, help="Total duration in hours (e.g. 48.0 or 0.5)")
    parser.add_argument("--duration-minutes", type=float, default=None, help="Total duration in minutes (e.g. 1.0 or 5.0)")
    parser.add_argument("--duration-seconds", type=float, default=None, help="Total duration in seconds (e.g. 30.0)")
    parser.add_argument("--cycles", type=int, default=None, help="Target total cycles before terminating (e.g. 10 or 20)")
    parser.add_argument("--interval-seconds", type=float, default=2.0, help="Interval between cycles in seconds (default: 2.0)")
    parser.add_argument("--mock", action="store_true", help="Run with simulated mock responses")
    parser.add_argument("--checkpoint-seconds", type=float, default=300.0, help="Checkpoint interval in seconds (default: 300)")
    parser.add_argument("--export", type=str, default="reports/soak_test_48h_report.json", help="Path to final JSON report")
    parser.add_argument("--target-price", type=float, default=UNREACHABLE_TARGET_PRICE,
                        help="ABOVE target of the synthetic alerts (default: unreachable, so they never trigger/deactivate)")
    parser.add_argument("--server-pid", type=int, default=None, help="PID of the running server whose RSS is sampled (e.g. $(cat server.pid))")
    parser.add_argument("--leak-threshold-mb-per-hour", type=float, default=0.5, help="Max accepted memory growth slope (default: 0.5)")
    parser.add_argument("--sample-seconds", type=float, default=None, help="Memory sampling interval (default: auto, max 60 s)")
    parser.add_argument("--crypto-only", action="store_true",
                        help="Test ONLY the 18 canonical Crypto V2 exchanges (skips catalog stocks/bonbast)")
    parser.add_argument("--include-crypto", action="store_true",
                        help="Include the 18 canonical Crypto V2 exchanges alongside catalog symbols")
    parser.add_argument("--skip-bonbast", action="store_true",
                        help="Exclude bonbast/Iran currency symbols (useful when running from EU/Germany servers)")
    parser.add_argument("--crypto-symbols", type=str, default="BTC,ETH",
                        help="Comma-separated base crypto symbols per exchange (default: BTC,ETH)")
    parser.add_argument("--allow-admin-alerts", action="store_true",
                        help="Allow admin Telegram outage/quota alerts during soak (suppressed by default)")
    parser.add_argument("--no-admin-alerts", action="store_true",
                        help="Suppress admin Telegram alerts during soak (already default)")
    args = parser.parse_args()

    # Determine total seconds
    if args.duration_seconds is not None:
        total_seconds = args.duration_seconds
        hours = total_seconds / 3600.0
    elif args.duration_minutes is not None:
        total_seconds = args.duration_minutes * 60.0
        hours = total_seconds / 3600.0
    elif args.duration_hours is not None:
        hours = args.duration_hours
        total_seconds = hours * 3600.0
    elif args.cycles is not None:
        hours = (args.cycles * args.interval_seconds) / 3600.0
        total_seconds = args.cycles * args.interval_seconds
    else:
        hours = 48.0
        total_seconds = 48.0 * 3600.0

    suppress_admin = not args.allow_admin_alerts
    if suppress_admin:
        # Must be set BEFORE app.config imports .env so _load_env_file() will not populate them
        os.environ["TELEGRAM_ADMIN_CHAT_ID"] = ""
        os.environ["TELEGRAM_BOT_TOKEN"] = ""

    if args.crypto_only or args.include_crypto:
        # Ensure Crypto V2 engine flags are active inside the isolated soak harness
        os.environ.setdefault("CRYPTO_STRICT_V2", "1")
        os.environ.setdefault("CRYPTO_ENGINE_V2", "1")
        os.environ.setdefault("CRYPTO_STAGE_B_ENABLED", "1")

    data_dir = isolate_data_dir(ROOT_DIR)  # MUST run before any app.* import
    print(f"🛡️ Isolated data dir: {data_dir} (real alerts/profiles/outbox are not touched)")
    if suppress_admin:
        print("🔕 Admin Telegram outage/quota alerts suppressed for this soak run.")

    crypto_syms = [s.strip().upper() for s in (args.crypto_symbols or "").split(",") if s.strip()]

    asyncio.run(run_soak_test(
        duration_hours=hours,
        cycle_interval_seconds=args.interval_seconds,
        use_mock=args.mock,
        checkpoint_interval_seconds=args.checkpoint_seconds,
        max_cycles=args.cycles,
        total_target_seconds=total_seconds,
        report_file=args.export,
        target_price=args.target_price,
        server_pid=args.server_pid,
        leak_threshold_mb_per_hour=args.leak_threshold_mb_per_hour,
        sample_interval_seconds=args.sample_seconds,
        crypto_only=args.crypto_only,
        include_crypto=args.include_crypto,
        skip_bonbast=args.skip_bonbast,
        crypto_symbols=crypto_syms or ["BTC", "ETH"],
        suppress_admin_alerts=suppress_admin,
    ))


if __name__ == "__main__":
    main()
