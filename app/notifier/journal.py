import os
import json
import time
from collections import deque
from typing import Dict, Any

from app.config import DATA_DIR
from app.state import METRICS

JOURNAL_FILE = os.path.join(DATA_DIR, "delivery_journal.json") if DATA_DIR != "." else "delivery_journal.json"
JOURNAL_TTL_SECONDS = 24 * 3600  # drop entries older than 24h on load

# Sliding window of the most recent 500 ack latencies (in milliseconds)
ACK_LATENCIES: deque = deque(maxlen=500)


def get_ack_latency_stats() -> Dict[str, Any]:
    """Calculate latency statistics over the sliding window (up to 500 entries)."""
    if not ACK_LATENCIES:
        return {
            "count": 0,
            "avg_ms": None,
            "p95_ms": None,
        }
    items = list(ACK_LATENCIES)
    items.sort()
    n = len(items)
    avg_ms = round(sum(items) / n, 1)
    p95_idx = min(int(round(0.95 * (n - 1))), n - 1)
    p95_ms = items[p95_idx]
    return {
        "count": n,
        "avg_ms": avg_ms,
        "p95_ms": p95_ms,
    }


def _load_journal_from_disk() -> Dict[str, Dict[str, Any]]:
    if os.path.exists(JOURNAL_FILE):
        try:
            with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                now = time.time()
                return {
                    k: v for k, v in data.items()
                    if isinstance(v, dict)
                    and (now - float(v.get("queued_at", now))) <= JOURNAL_TTL_SECONDS
                }
        except Exception as e:
            print(f"⚠️ [Journal] Could not read {JOURNAL_FILE}: {e} (keeping a .bad copy)")
            try:
                os.replace(JOURNAL_FILE, JOURNAL_FILE + ".bad")
            except Exception:
                pass
    return {}


JOURNAL: Dict[str, Dict[str, Any]] = _load_journal_from_disk()


def _save_journal() -> None:
    try:
        payload = json.dumps(JOURNAL, ensure_ascii=False)
        tmp = f"{JOURNAL_FILE}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, JOURNAL_FILE)
    except Exception as e:
        print(f"⚠️ [Journal] Save failed: {e}")


def _update_metrics() -> None:
    acked = sum(1 for e in JOURNAL.values() if e.get("state") == "acked")
    sent = sum(1 for e in JOURNAL.values() if e.get("state") == "sent")
    queued = sum(1 for e in JOURNAL.values() if e.get("state") == "queued")
    unacked = sum(1 for e in JOURNAL.values() if e.get("state") == "unacked")
    METRICS["delivery_acked"] = acked
    METRICS["delivery_sent"] = sent
    METRICS["delivery_queued"] = queued
    METRICS["delivery_unacked"] = unacked
    METRICS["delivery_total"] = len(JOURNAL)
    stats = get_ack_latency_stats()
    METRICS["ack_latency_avg_ms"] = stats["avg_ms"]
    METRICS["ack_latency_p95_ms"] = stats["p95_ms"]


def _purge_expired(now: float) -> None:
    """Drop entries older than JOURNAL_TTL_SECONDS (runtime cleanup)."""
    cutoff = now - JOURNAL_TTL_SECONDS
    expired = [
        k for k, v in JOURNAL.items()
        if isinstance(v, dict) and float(v.get("queued_at", now)) < cutoff
    ]
    for k in expired:
        JOURNAL.pop(k, None)


def record_queued(delivery_id: str, alert_id: str) -> None:
    """Record a delivery in the `queued` state (called before FCM send)."""
    if not delivery_id:
        return
    now = time.time()
    _purge_expired(now)
    JOURNAL[delivery_id] = {
        "alert_id": alert_id,
        "state": "queued",
        "queued_at": now,
        "sent_at": None,
        "acked_at": None,
    }
    _update_metrics()
    _save_journal()


def record_sent(delivery_id: str) -> None:
    """Record that FCM accepted the push (still not acked).

    Only `queued -> sent` is allowed. If the app already acked before FCM's
    callback landed, keep `acked` (do not regress).
    """
    entry = JOURNAL.get(delivery_id)
    if not entry:
        return
    if entry.get("state") == "acked":
        return
    entry["state"] = "sent"
    entry["sent_at"] = time.time()
    _update_metrics()
    _save_journal()


def record_acked(delivery_id: str) -> bool:
    """Record that the app confirmed the banner was shown.

    Returns True for a known delivery_id (idempotent: repeated calls are fine),
    False for an unknown id.
    """
    entry = JOURNAL.get(delivery_id)
    if not entry:
        return False
    if entry.get("state") != "acked":
        now = time.time()
        entry["state"] = "acked"
        entry["acked_at"] = now
        sent_at = entry.get("sent_at")
        if sent_at is not None:
            try:
                latency_ms = max(0, int((now - float(sent_at)) * 1000))
                ACK_LATENCIES.append(latency_ms)
            except (TypeError, ValueError):
                pass
        METRICS["delivery_acked"] = METRICS.get("delivery_acked", 0) + 1
    _update_metrics()
    _save_journal()
    return True


def record_unacked(delivery_id: str) -> None:
    """Mark a delivery as `unacked` (FCM accepted but the app never acked in time)."""
    entry = JOURNAL.get(delivery_id)
    if not entry:
        return
    if entry.get("state") == "acked":
        return
    entry["state"] = "unacked"
    entry["unacked_at"] = time.time()
    _update_metrics()
    _save_journal()

def record_telegram_fallback_sent(delivery_id: str) -> None:
    """Mark that the Telegram fallback was already sent for this delivery."""
    entry = JOURNAL.get(delivery_id)
    if not entry:
        return
    entry["telegram_fallback_sent"] = True
    _save_journal()


def was_telegram_fallback_sent(delivery_id: str) -> bool:
    entry = JOURNAL.get(delivery_id)
    return bool(entry and entry.get("telegram_fallback_sent"))

def clear_telegram_fallback_sent(delivery_id: str) -> None:
    """Remove the telegram_fallback_sent flag so a retry can happen."""
    entry = JOURNAL.get(delivery_id)
    if not entry:
        return
    entry.pop("telegram_fallback_sent", None)
    _save_journal()




def get_status(delivery_id: str) -> str:
    entry = JOURNAL.get(delivery_id)
    return (entry or {}).get("state", "unknown")