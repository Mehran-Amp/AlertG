#!/usr/bin/env python3
"""
Phase 5A-2: Soak test for the delivery pipeline.

Sends N synthetic alerts over D minutes through the outbox pipeline,
then reports: sent, acked, unacked, ack latency avg/p95, outbox len.

By default FCM is MOCKED (auto-ack, no real device). Pass --live to use
the real outbox pipeline with real FCM (requires a configured Firebase app).

Usage:
  python scripts/soak_delivery.py --alerts 200 --duration 600
  python scripts/soak_delivery.py --alerts 50 --duration 30 --live

Exit code: 0 = all alerts acked, 1 = any unacked or error.
"""
import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--alerts", type=int, default=200)
    p.add_argument("--duration", type=int, default=600, help="seconds")
    p.add_argument("--live", action="store_true", help="use real FCM instead of mock")
    return p.parse_args()


def _make_entry(eid: str, idx: int) -> dict:
    now = time.time()
    return {
        "id": eid,
        "alert_id": f"soak_{idx}",
        "user_id": f"soak_user_{idx % 10}",
        "fallback_chat_id": None,
        "token": "x" * 60,
        "title": f"🧪 Soak alert #{idx}",
        "body": f"synthetic alert {idx}",
        "data": {
            "alert_id": f"soak_{idx}",
            "symbol": "BTCUSDT",
            "price": "1.0",
            "delivery_id": eid,
        },
        "created_at": now,
        "expires_at": now + 86400,
        "next_attempt_at": now,
        "next_retry_at": now,
        "attempts": 0,
        "resend_count": 0,
        "ack_supported": True,
        "ack_waits": (45, 90, 180),
        "last_error": "",
        "blocked_token": None,
    }


async def _run(alerts: int, duration: int, live: bool) -> int:
    from app.notifier import outbox, journal
    from app.state import METRICS

    # Isolate: clear outbox and journal from previous runs
    outbox.OUTBOX.clear()
    journal.JOURNAL.clear()
    try:
        await outbox._save_outbox()
        journal._save_journal()
    except Exception:
        pass

    if not live:
        # Mock: succeed + immediate ack. No FCM, no ack endpoint, no race.
        async def fake_deliver(eid):
            entry = outbox.OUTBOX.get(eid)
            if not entry:
                return
            journal.record_sent(eid)
            journal.record_acked(eid)
            outbox.OUTBOX.pop(eid, None)
        outbox._deliver_outbox_entry = fake_deliver  # type: ignore

    print(f"⏱  Soaking {alerts} alerts over {duration}s (live={live})...")
    sent_ids = []
    interval = duration / max(1, alerts)

    for i in range(alerts):
        eid = uuid.uuid4().hex
        outbox.OUTBOX[eid] = _make_entry(eid, i)
        journal.record_queued(eid, f"soak_{i}")
        sent_ids.append(eid)
        await outbox._deliver_outbox_entry(eid)
        if (i + 1) % 20 == 0:
            print(f"  queued+acked {i + 1}/{alerts} (outbox_len={len(outbox.OUTBOX)})")
        await asyncio.sleep(interval)

    # Wait for the outbox to drain (live mode may still have in-flight entries)
    drain_deadline = time.time() + 60
    print(f"⏳ Draining outbox (deadline: 60s)...")
    while time.time() < drain_deadline:
        if len(outbox.OUTBOX) == 0:
            break
        await asyncio.sleep(1)

    acked = 0
    unacked = 0
    latencies = []
    for eid in sent_ids:
        st = journal.get_status(eid)
        if st == "acked":
            acked += 1
            entry = journal.JOURNAL.get(eid, {})
            sent_at = entry.get("sent_at")
            acked_at = entry.get("acked_at")
            if sent_at and acked_at:
                latencies.append(int((acked_at - sent_at) * 1000))
        elif st == "unacked":
            unacked += 1

    latencies.sort()
    n = len(latencies)
    avg = round(sum(latencies) / n, 1) if n else None
    p95 = latencies[min(int(0.95 * (n - 1)), n - 1)] if n else None

    report = {
        "alerts": alerts,
        "duration_s": duration,
        "live": live,
        "outbox_len_end": len(outbox.OUTBOX),
        "acked": acked,
        "unacked": unacked,
        "no_status": alerts - acked - unacked,
        "ack_latency_avg_ms": avg,
        "ack_latency_p95_ms": p95,
        "metrics_outbox_len": METRICS.get("outbox_len"),
        "metrics_fcm_unacked": METRICS.get("fcm_unacked"),
        "metrics_fcm_acked": METRICS.get("fcm_acked"),
    }
    print("\n=== SOAK REPORT ===")
    print(json.dumps(report, indent=2))
    return 0 if unacked == 0 and acked == alerts else 1


if __name__ == "__main__":
    args = _parse_args()
    rc = asyncio.run(_run(args.alerts, args.duration, args.live))
    sys.exit(rc)