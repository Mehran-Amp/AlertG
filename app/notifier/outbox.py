import os
import json
import time
import uuid
import asyncio
from typing import Dict, Any, Set
from app.config import DATA_DIR
from app.state import METRICS
from app.storage import ALERTS_DB
from app.notifier.fcm import send_fcm_notification_async

# Strong references so fire-and-forget tasks cannot be garbage-collected mid-flight
_BG_TASKS: Set[asyncio.Task] = set()

def _spawn(coro):
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(coro)
        _BG_TASKS.add(task)
        task.add_done_callback(_BG_TASKS.discard)
        return task
    except RuntimeError:
        try:
            coro.close()
        except Exception:
            pass
        return None

OUTBOX_FILE = os.path.join(DATA_DIR, "fcm_outbox.json") if DATA_DIR != "." else "fcm_outbox.json"
ALERT_PUSH_TTL_SECONDS = int(os.getenv("FCM_ALERT_TTL_SECONDS", "86400"))  # how long we keep trying + FCM stores it for an offline phone
_OUTBOX_RETRY_DELAYS = (2, 5, 15, 30, 60, 120, 300)  # seconds; last value repeats

def _load_outbox_from_disk() -> Dict[str, Dict[str, Any]]:
    if os.path.exists(OUTBOX_FILE):
        try:
            with open(OUTBOX_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception as e:
            print(f"⚠️ [Outbox] Could not read {OUTBOX_FILE}: {e} (keeping a .bad copy)")
            try:
                os.replace(OUTBOX_FILE, OUTBOX_FILE + ".bad")
            except Exception:
                pass
    return {}

OUTBOX: Dict[str, Dict[str, Any]] = _load_outbox_from_disk()
_OUTBOX_INFLIGHT: set = set()
_outbox_lock = asyncio.Lock()

async def _save_outbox():
    async with _outbox_lock:
        try:
            payload = json.dumps(OUTBOX, ensure_ascii=False)

            def _write():
                tmp = f"{OUTBOX_FILE}.tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, OUTBOX_FILE)

            await asyncio.get_running_loop().run_in_executor(None, _write)
        except Exception as e:
            print(f"⚠️ [Outbox] Save failed (still retrying from memory): {e}")

def _outbox_current_token(entry: Dict[str, Any]) -> str:
    """Use the newest token the app synced for this alert (handles token rotation mid-retry)."""
    aid = entry.get("alert_id")
    if aid:
        for a in ALERTS_DB:
            if a.id == aid and (a.fcm_token or "").strip():
                return a.fcm_token.strip()
    return entry["token"]

async def enqueue_alert_push(alert, title: str, body: str, data_payload: dict) -> None:
    token = (alert.fcm_token or "").strip()
    if not token:
        print(f"⚠️ [Outbox] Alert {alert.id} has no fcm_token, push skipped.")
        return
    now = time.time()
    eid = uuid.uuid4().hex
    data = {k: ("" if v is None else str(v)) for k, v in (data_payload or {}).items()}
    data["triggered_at"] = str(int(now * 1000))
    OUTBOX[eid] = {
        "id": eid,
        "alert_id": alert.id,
        "token": token,
        "title": str(title),
        "body": str(body),
        "data": data,
        "created_at": now,
        "expires_at": now + ALERT_PUSH_TTL_SECONDS,
        "next_attempt_at": now,
        "attempts": 0,
        "last_error": "",
    }
    _OUTBOX_INFLIGHT.add(eid)
    await _save_outbox()                      # durable first...
    _spawn(_deliver_outbox_entry(eid))        # ...then send immediately (no waiting for the worker tick)

async def _deliver_outbox_entry(eid: str) -> None:
    try:
        entry = OUTBOX.get(eid)
        if not entry:
            return
        now = time.time()
        if now >= entry["expires_at"]:
            OUTBOX.pop(eid, None)
            METRICS["fcm_expired"] = METRICS.get("fcm_expired", 0) + 1
            print(f"⌛ [Outbox] {eid[:8]} expired after {entry['attempts']} attempts: {entry['last_error']}")
            await _save_outbox()
            return

        ok, msg = await send_fcm_notification_async(
            fcm_token=_outbox_current_token(entry),
            title=entry["title"],
            body=entry["body"],
            data_payload=entry["data"],
            ttl_seconds=int(entry["expires_at"] - now),
        )
        if ok:
            OUTBOX.pop(eid, None)
            if entry["attempts"] > 0:
                print(f"✅ [Outbox] {eid[:8]} delivered after {entry['attempts']} retries.")
        else:
            entry["attempts"] += 1
            delay = _OUTBOX_RETRY_DELAYS[min(entry["attempts"] - 1, len(_OUTBOX_RETRY_DELAYS) - 1)]
            entry["next_attempt_at"] = time.time() + delay
            entry["last_error"] = str(msg)[:200]
            print(f"🔁 [Outbox] {eid[:8]} attempt {entry['attempts']} failed ({entry['last_error']}); retry in {delay}s")
        await _save_outbox()
    except Exception as e:
        print(f"❌ [Outbox] unexpected error for {eid[:8]}: {e}")
        entry = OUTBOX.get(eid)
        if entry:
            entry["next_attempt_at"] = time.time() + 5
    finally:
        _OUTBOX_INFLIGHT.discard(eid)

async def outbox_worker_loop():
    """Picks up due entries (also the ones left over from before a restart)."""
    if OUTBOX:
        print(f"📬 [Outbox] Resuming {len(OUTBOX)} undelivered push(es) from disk.")
    while True:
        try:
            now = time.time()
            for eid, entry in list(OUTBOX.items()):
                if eid not in _OUTBOX_INFLIGHT and entry.get("next_attempt_at", 0) <= now:
                    _OUTBOX_INFLIGHT.add(eid)
                    _spawn(_deliver_outbox_entry(eid))
        except Exception as e:
            print(f"⚠️ [Outbox] worker error: {e}")
        await asyncio.sleep(2)
