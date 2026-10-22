import os
import json
import time
from typing import Dict, Any

from app.config import DATA_DIR
from app.state import METRICS

JOURNAL_FILE = os.path.join(DATA_DIR, "delivery_journal.json") if DATA_DIR != "." else "delivery_journal.json"
JOURNAL_TTL_SECONDS = 24 * 3600  # drop entries older than 24h on load


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
    METRICS["delivery_acked"] = acked
    METRICS["delivery_sent"] = sent
    METRICS["delivery_queued"] = queued
    METRICS["delivery_total"] = len(JOURNAL)


def record_queued(delivery_id: str, alert_id: str) -> None:
    """Record a delivery in the `queued` state (called before FCM send)."""
    if not delivery_id:
        return
    now = time.time()
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
    """Record that FCM accepted the push (still not acked)."""
    entry = JOURNAL.get(delivery_id)
    if not entry:
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
        entry["state"] = "acked"
        entry["acked_at"] = time.time()
        METRICS["delivery_acked"] = METRICS.get("delivery_acked", 0) + 1
    _update_metrics()
    _save_journal()
    return True


def get_status(delivery_id: str) -> str:
    entry = JOURNAL.get(delivery_id)
    return (entry or {}).get("state", "unknown")