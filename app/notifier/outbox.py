import os
import json
import time
import uuid
import asyncio
from typing import Dict, Any, Set
from app.config import DATA_DIR
from app.state import METRICS
import app.storage as storage
from app.notifier.fcm import send_fcm_notification_async
from app.notifier import journal
from app.notifier.telegram import send_telegram_alert, notify_admin_telegram
import app.state as state

# Phase 2C-3: repeated FCM auth error tracking and rate-limited admin notification
_CONSECUTIVE_FCM_AUTH_ERRORS: int = 0
_LAST_FCM_AUTH_ADMIN_ALERT_TS: float = 0.0
_FCM_AUTH_ALERT_RATE_LIMIT_SECONDS: float = 1800.0  # 30 minutes

# Blocked / Dead FCM Tokens: set of tokens flagged as UNREGISTERED or INVALID_TOKEN_FORMAT
DEAD_TOKENS: Set[str] = set()

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
# Phase 2: bounded resend schedule for ack-capable entries (seconds).
# Falls back to the default if the env value is invalid/empty.
def _parse_ack_waits(raw: str) -> tuple:
    try:
        parsed = tuple(int(x) for x in raw.split(",") if x.strip())
    except (ValueError, TypeError):
        return (45, 90, 180)
    return parsed if parsed else (45, 90, 180)

ACK_WAITS = _parse_ack_waits(os.getenv("ACK_WAITS", "45,90,180"))
# Phase 3A-3: Shortened ack waits for silent devices (last heartbeat > 45 minutes ago)
SILENT_ACK_WAITS = (15, 30)
SILENT_DEVICE_AGE_SECONDS = 45 * 60  # 45 minutes

def _load_outbox_from_disk() -> Dict[str, Dict[str, Any]]:
    if os.path.exists(OUTBOX_FILE):
        try:
            with open(OUTBOX_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                now = time.time()
                # Discard entries whose expires_at has passed
                return {
                    k: v for k, v in data.items()
                    if isinstance(v, dict) and v.get("expires_at", float("inf")) > now
                }
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

def _update_outbox_metrics():
    METRICS["outbox_blocked"] = sum(1 for e in OUTBOX.values() if e.get("blocked_token"))
    METRICS["outbox_len"] = len(OUTBOX)

_update_outbox_metrics()

async def _save_outbox():
    _update_outbox_metrics()
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
        for a in storage.ALERTS_DB:
            if a.id == aid and (a.fcm_token or "").strip():
                return a.fcm_token.strip()
    return entry.get("token", "")

def on_alert_token_updated(alert_id: str, new_token: str) -> None:
    """When the alert's token changes (new sync), clear blocked_token and send immediately."""
    now = time.time()
    new_t = (new_token or "").strip()

    # Clear blocked_token on matching outbox entries and trigger immediate send
    for eid, entry in list(OUTBOX.items()):
        if entry.get("alert_id") == alert_id:
            old_blocked = entry.get("blocked_token")
            if old_blocked and old_blocked != new_t:
                entry["blocked_token"] = None
                entry["next_attempt_at"] = now
                entry["next_retry_at"] = now
                if eid not in _OUTBOX_INFLIGHT:
                    _OUTBOX_INFLIGHT.add(eid)
                    _spawn(_deliver_outbox_entry(eid))

    # Discard a token from DEAD_TOKENS only if no other alert in storage.ALERTS_DB still uses it
    active_tokens = {(getattr(a, "fcm_token", None) or "").strip() for a in storage.ALERTS_DB}
    for dead_tok in list(DEAD_TOKENS):
        if dead_tok not in active_tokens:
            DEAD_TOKENS.discard(dead_tok)

async def enqueue_alert_push(alert, title: str, body: str, data_payload: dict, fallback_chat_id: str = None) -> None:
    token = (alert.fcm_token or "").strip()
    if not token:
        print(f"⚠️ [Outbox] Alert {alert.id} has no fcm_token, push skipped.")
        return
    now = time.time()
    eid = uuid.uuid4().hex
    delivery_id = eid
    data = {k: ("" if v is None else str(v)) for k, v in (data_payload or {}).items()}
    data["triggered_at"] = str(int(now * 1000))
    data["delivery_id"] = delivery_id

    is_dead = token in DEAD_TOKENS
    blocked_token = token if is_dead else None
    next_attempt = now + 60.0 if is_dead else now

    # Phase 3A-3: Silent device detection
    # If user previously had a heartbeat, but last one is > 45 minutes old,
    # shorten ack waits to (15, 30) seconds to trigger Telegram fallback much sooner.
    uid = getattr(alert, "user_id", None)
    if not uid:
        for a in storage.ALERTS_DB:
            if a.id == alert.id:
                uid = getattr(a, "user_id", None)
                break

    entry_ack_waits = ACK_WAITS
    if uid:
        try:
            from app.routes.devices import get_user_device_health
            health = get_user_device_health(uid)
            if health and health.get("received_at"):
                age_seconds = now - float(health["received_at"])
                if age_seconds > SILENT_DEVICE_AGE_SECONDS:
                    entry_ack_waits = SILENT_ACK_WAITS
                    print(f"⚠️ [Outbox] Silent device detected for user '{uid}' (last heartbeat {int(age_seconds)}s ago). Shortened ack waits to {SILENT_ACK_WAITS}.")
        except Exception as e:
            print(f"⚠️ [Outbox] Device health check error: {e}")

    OUTBOX[eid] = {
        "id": eid,
        "alert_id": alert.id,
        "user_id": uid or getattr(alert, "user_id", None),
        "fallback_chat_id": (fallback_chat_id or "").strip() or None,
        "token": token,
        "title": str(title),
        "body": str(body),
        "data": data,
        "created_at": now,
        "expires_at": now + ALERT_PUSH_TTL_SECONDS,
        "next_attempt_at": next_attempt,
        "next_retry_at": next_attempt,
        "attempts": 0,
        "resend_count": 0,
        "ack_supported": bool(getattr(alert, "ack_supported", False)),
        "ack_waits": entry_ack_waits,
        "last_error": "",
        "blocked_token": blocked_token,
    }
    _update_outbox_metrics()
    journal.record_queued(delivery_id, alert.id)
    await _save_outbox()                      # durable first...
    if not is_dead:
        _OUTBOX_INFLIGHT.add(eid)
        _spawn(_deliver_outbox_entry(eid))        # ...then send immediately (no waiting for the worker tick)

async def _deliver_outbox_entry(eid: str) -> None:
    try:
        entry = OUTBOX.get(eid)
        if not entry:
            return
        now = time.time()
        if now >= entry.get("expires_at", float("inf")):
            OUTBOX.pop(eid, None)
            METRICS["fcm_expired"] = METRICS.get("fcm_expired", 0) + 1
            print(f"⌛ [Outbox] {eid[:8]} expired after {entry.get('attempts', 0)} attempts: {entry.get('last_error', '')}")
            await _save_outbox()
            return
        # Phase 2: awaiting ack phase. Either resend (if still within budget)
        # or mark unacked after the last deadline.
        if entry.get("phase") == "awaiting_ack":
            due = entry.get("ack_due_at", 0)
            if now < due:
                entry["next_attempt_at"] = due
                entry["next_retry_at"] = due
                _update_outbox_metrics()
                await _save_outbox()
                return

            waits = entry.get("ack_waits", ACK_WAITS)
            resend_count = int(entry.get("resend_count", 0))
            if resend_count < len(waits) - 1:
                # Resend the same delivery_id with the same payload.
                entry["resend_count"] = resend_count + 1
                entry["attempts"] = 0
                entry["phase"] = "resending"
                entry["next_attempt_at"] = now
                entry["next_retry_at"] = now
                print(f"🔁 [Outbox] {eid[:8]} resending (attempt {entry['resend_count']}/{len(waits) - 1})")
                _update_outbox_metrics()
                await _save_outbox()
                # Fall through to send FCM again.
            else:
                # Budget exhausted: mark unacked and drop.
                fallback_chat = entry.get("fallback_chat_id")
                title_text = entry.get("title") or ""
                body_text = entry.get("body") or ""
                OUTBOX.pop(eid, None)
                journal.record_unacked(eid)
                METRICS["fcm_unacked"] = METRICS.get("fcm_unacked", 0) + 1
                print(f"⌛ [Outbox] {eid[:8]} not acked after {len(waits)} waits; marked unacked")
                _update_outbox_metrics()
                await _save_outbox()

                # Phase 2: one-shot Telegram fallback (never blocks the worker).
                if fallback_chat and not journal.was_telegram_fallback_sent(eid):
                    _spawn(_send_telegram_fallback(eid, fallback_chat, title_text, body_text))
                return

        current_token = _outbox_current_token(entry)

        # Check if currently blocked
        blocked = entry.get("blocked_token")
        if blocked:
            if current_token == blocked:
                # Next delivery attempts MUST SKIP calling FCM if alert.fcm_token == entry.get("blocked_token") and just re-arm next_retry_at = now + 60.0
                entry["next_attempt_at"] = now + 60.0
                entry["next_retry_at"] = now + 60.0
                _update_outbox_metrics()
                await _save_outbox()
                return
            else:
                # When alert.fcm_token changes, entry["blocked_token"] is cleared
                entry["blocked_token"] = None
                still_used = any(
                    (getattr(a, "fcm_token", None) or "").strip() == blocked
                    for a in storage.ALERTS_DB
                    if a.id != entry.get("alert_id")
                )
                if not still_used:
                    DEAD_TOKENS.discard(blocked)

        # Phase 4A-2: If user is connected via WebSocket, send alert with identical delivery_id
        target_uid = entry.get("user_id")
        if not target_uid and entry.get("alert_id"):
            for a in storage.ALERTS_DB:
                if a.id == entry.get("alert_id"):
                    target_uid = getattr(a, "user_id", None)
                    break
        if target_uid:
            try:
                from app.routes.ws import manager as ws_manager
                if ws_manager.is_user_connected(target_uid):
                    ws_msg = {
                        "type": "alert",
                        "delivery_id": eid,
                        "title": entry["title"],
                        "body": entry["body"],
                        "data": entry["data"],
                    }
                    await ws_manager.send_to_user(target_uid, ws_msg)
                    METRICS["ws_sent"] = METRICS.get("ws_sent", 0) + 1
            except Exception as ws_err:
                print(f"⚠️ [Outbox WS] Error dispatching on WebSocket: {ws_err}")

        ok, msg = await send_fcm_notification_async(
            fcm_token=current_token,
            title=entry["title"],
            body=entry["body"],
            data_payload=entry["data"],
            ttl_seconds=int(entry["expires_at"] - now),
        )
        if ok:
            global _CONSECUTIVE_FCM_AUTH_ERRORS
            _CONSECUTIVE_FCM_AUTH_ERRORS = 0
            METRICS["last_fcm_ok_ts"] = now
            journal.record_sent(eid)

            # Phase 2: keep the entry until the app acks if the alert is ack-capable.
            # Read the snapshot captured at enqueue time so a later sync/edit/delete
            # of the alert does not change this decision.
            ack_capable = bool(entry.get("ack_supported", False))

            if ack_capable:
                entry["phase"] = "awaiting_ack"
                # First wait for a new entry; for a resend use the next slot.
                waits = entry.get("ack_waits", ACK_WAITS)
                idx = min(int(entry.get("resend_count", 0)), len(waits) - 1)
                wait = waits[idx]
                entry["ack_due_at"] = now + wait
                entry["next_attempt_at"] = entry["ack_due_at"]
                entry["next_retry_at"] = entry["ack_due_at"]
                entry["attempts"] = 0
                print(f"📨 [Outbox] {eid[:8]} FCM accepted; awaiting ack for {wait}s (resend {entry.get('resend_count', 0)}/{len(waits) - 1})")
            else:
                OUTBOX.pop(eid, None)
                if entry.get("attempts", 0) > 0:
                    print(f"✅ [Outbox] {eid[:8]} delivered after {entry['attempts']} retries.")
        else:
            if msg in ("UNREGISTERED", "INVALID_TOKEN_FORMAT"):
                # UNREGISTERED / INVALID_TOKEN_FORMAT: do NOT drop the entry and do NOT blank alert.fcm_token.
                # Set entry["blocked_token"] = target_token, entry["last_error"] = msg, entry["attempts"] += 1, entry["next_retry_at"] = now + 60.0. Log at WARNING.
                entry["blocked_token"] = current_token
                entry["last_error"] = str(msg)
                entry["attempts"] = entry.get("attempts", 0) + 1
                entry["next_attempt_at"] = now + 60.0
                entry["next_retry_at"] = now + 60.0
                METRICS["fcm_invalid_token"] = METRICS.get("fcm_invalid_token", 0) + 1
                DEAD_TOKENS.add(current_token)
                aid = entry.get("alert_id") or ""
                tok_suffix = current_token[-6:] if len(current_token) >= 6 else current_token
                print(f"⚠️ [Outbox Warning] Alert {aid} token blocked (...{tok_suffix}): {msg}")
            elif msg == "INVALID_PAYLOAD":
                # INVALID_PAYLOAD: never wipe the token; log the full error once, METRICS["fcm_failed"]+=1, keep retrying with the normal backoff (it is a server bug, not a user problem).
                entry["attempts"] = entry.get("attempts", 0) + 1
                delay = _OUTBOX_RETRY_DELAYS[min(entry["attempts"] - 1, len(_OUTBOX_RETRY_DELAYS) - 1)]
                entry["next_attempt_at"] = now + delay
                entry["next_retry_at"] = now + delay
                entry["last_error"] = str(msg)
                METRICS["fcm_failed"] = METRICS.get("fcm_failed", 0) + 1
                aid = entry.get("alert_id") or ""
                print(f"⚠️ [Outbox Error] Invalid payload for alert {aid}: {msg} (retrying in {delay}s, attempt {entry['attempts']})")
            elif msg == "FCM_AUTH_ERROR":
                # FCM_AUTH_ERROR (Phase 2C-2 & 2C-3): retry like a transient error, METRICS["fcm_auth_error"]+=1, do NOT block the token.
                global _LAST_FCM_AUTH_ADMIN_ALERT_TS
                _CONSECUTIVE_FCM_AUTH_ERRORS += 1
                entry["attempts"] = entry.get("attempts", 0) + 1
                delay = _OUTBOX_RETRY_DELAYS[min(entry["attempts"] - 1, len(_OUTBOX_RETRY_DELAYS) - 1)]
                entry["next_attempt_at"] = now + delay
                entry["next_retry_at"] = now + delay
                entry["last_error"] = str(msg)
                METRICS["fcm_auth_error"] = METRICS.get("fcm_auth_error", 0) + 1
                METRICS["fcm_failed"] = METRICS.get("fcm_failed", 0) + 1
                aid = entry.get("alert_id") or ""
                print(f"⚠️ [Outbox Auth Error] Alert {aid}: FCM auth failed (consecutive: {_CONSECUTIVE_FCM_AUTH_ERRORS}, retrying in {delay}s, attempt {entry['attempts']})")

                # Phase 2C-3: alert admin on 3 consecutive FCM auth errors (rate-limited to once every 30m)
                if _CONSECUTIVE_FCM_AUTH_ERRORS >= 3:
                    if (now - _LAST_FCM_AUTH_ADMIN_ALERT_TS) >= _FCM_AUTH_ALERT_RATE_LIMIT_SECONDS:
                        _LAST_FCM_AUTH_ADMIN_ALERT_TS = now
                        admin_msg = (
                            f"🚨 <b>CRITICAL: FCM AUTH FAILURE</b>\n\n"
                            f"<blockquote>"
                            f"Firebase Cloud Messaging has encountered <b>{_CONSECUTIVE_FCM_AUTH_ERRORS}</b> consecutive authentication/permission errors.\n"
                            f"Please verify Firebase project credentials and service account permissions."
                            f"</blockquote>"
                        )
                        try:
                            client = getattr(state, "http_client", None)
                            await notify_admin_telegram(admin_msg, client=client)
                        except Exception as admin_err:
                            print(f"⚠️ [Outbox] Failed to notify admin: {admin_err}")
            else:
                # Transient error (including FIREBASE_UNAVAILABLE): outbox treats it like a transient error with attempts incremented.
                entry["attempts"] = entry.get("attempts", 0) + 1
                delay = _OUTBOX_RETRY_DELAYS[min(entry["attempts"] - 1, len(_OUTBOX_RETRY_DELAYS) - 1)]
                entry["next_attempt_at"] = now + delay
                entry["next_retry_at"] = now + delay
                entry["last_error"] = str(msg)[:200]
                METRICS["fcm_failed"] = METRICS.get("fcm_failed", 0) + 1
                print(f"🔁 [Outbox] {eid[:8]} attempt {entry['attempts']} failed ({entry['last_error']}); retry in {delay}s")
        _update_outbox_metrics()
        await _save_outbox()
    except Exception as e:
        print(f"❌ [Outbox] unexpected error for {eid[:8]}: {e}")
        entry = OUTBOX.get(eid)
        if entry:
            entry["next_attempt_at"] = time.time() + 5
    finally:
        _OUTBOX_INFLIGHT.discard(eid)

async def on_delivery_acked(delivery_id: str) -> bool:
    """Phase 2: called by the ack endpoint. Removes the outbox entry.

    Returns True if the entry existed and was removed.
    """
    if not delivery_id:
        return False
    entry = OUTBOX.get(delivery_id)
    if not entry:
        return False
    OUTBOX.pop(delivery_id, None)
    _update_outbox_metrics()
    await _save_outbox()
    return True

async def _send_telegram_fallback(eid: str, chat_id: str, title: str, body: str) -> None:
    """Phase 2: send a short diagnostic via Telegram when the push is never acked."""
    if journal.was_telegram_fallback_sent(eid):
        return
    client = getattr(state, "http_client", None)
    if client is None:
        METRICS["telegram_fallback_failed"] = METRICS.get("telegram_fallback_failed", 0) + 1
        print(f"⚠️ [Outbox] Telegram fallback skipped for {eid[:8]}: no http_client")
        return
    try:
        journal.record_telegram_fallback_sent(eid)
        short_title = (title or "").strip()[:80]
        text = (
            f"⚠️ پوش آلارم «{short_title}» روی گوشی تأیید نشد. "
            f"سلامت اعلان‌های اپ را بررسی کن."
        )
        await send_telegram_alert(client, chat_id, text)
        METRICS["telegram_fallback_sent"] = METRICS.get("telegram_fallback_sent", 0) + 1
        print(f"📨 [Outbox] {eid[:8]} Telegram fallback sent")
    except Exception as e:
        # Make the flag retriable: a later retry (e.g. 2C-1) can try again.
        journal.clear_telegram_fallback_sent(eid)
        METRICS["telegram_fallback_failed"] = METRICS.get("telegram_fallback_failed", 0) + 1
        print(f"⚠️ [Outbox] Telegram fallback failed for {eid[:8]}: {e}")


async def outbox_worker_loop():
    """Picks up due entries (also the ones left over from before a restart)."""
    if OUTBOX:
        print(f"📬 [Outbox] Resuming {len(OUTBOX)} undelivered push(es) from disk.")
    while True:
        try:
            now = time.time()
            _update_outbox_metrics()
            for eid, entry in list(OUTBOX.items()):
                # When the alert's token changes, clear blocked_token and send immediately
                curr_tok = _outbox_current_token(entry)
                if entry.get("blocked_token") and curr_tok != entry["blocked_token"]:
                    entry["blocked_token"] = None
                    entry["next_attempt_at"] = now

                if eid in _OUTBOX_INFLIGHT:
                    continue
                if entry.get("phase") == "awaiting_ack" and now < entry.get("ack_due_at", 0):
                    continue
                if entry.get("next_attempt_at", 0) <= now:
                    _OUTBOX_INFLIGHT.add(eid)
                    _spawn(_deliver_outbox_entry(eid))
        except Exception as e:
            print(f"⚠️ [Outbox] worker error: {e}")
        await asyncio.sleep(2)
