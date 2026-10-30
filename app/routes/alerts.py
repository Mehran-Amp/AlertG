import os
import json
import time
import app.config as config
from app.config import DATA_DIR
import uuid
import math
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Response
from app.markets.common import normalize_symbol
from app.config import (
    SYMBOL_RE, EXCHANGE_RE, CHAT_ID_RE,
    MAX_ALERTS_PER_USER, MAX_NOTE_LEN
)
from app.security import (
    API_DEP, _clamp_interval, _normalize_sync_item, mask_identifier
)
from app.models import AlertCreate, Alert, AlertPublic
from app.state import _db_lock
from app.storage import ALERTS_DB, USER_PROFILES_DB, save_alerts_to_disk_async, save_user_profiles_to_disk_async
from app.notifier.safety import is_safe_webhook_url_async
from app.notifier.telegram import format_alert_registered_telegram_msg, send_telegram_alert
from app.notifier.outbox import _spawn
import app.state as state
import app.storage as storage

router = APIRouter()

def _trigger_signature(x) -> tuple:
    def _to_float(v):
        if v is None:
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    if isinstance(x, dict):
        exchange = (x.get('exchange') or '').strip().lower()
        symbol = normalize_symbol(x.get('symbol') or '')
        condition = (x.get('condition') or '').strip().upper()
        condition_type = x.get('condition_type') or 'priceThreshold'
        try:
            target_price = float(x.get('target_price', 0.0) or 0.0)
        except (ValueError, TypeError):
            target_price = 0.0
        upper_target_price = _to_float(x.get('upper_target_price'))
        lower_target_price = _to_float(x.get('lower_target_price'))
        percent = _to_float(x.get('percent'))
        base_price = _to_float(x.get('base_price'))
        direction = x.get('direction') or 'above'
        alert_nature = x.get('alert_nature') or 'price'
    else:
        exchange = (getattr(x, 'exchange', None) or '').strip().lower()
        symbol = normalize_symbol(getattr(x, 'symbol', None) or '')
        condition = (getattr(x, 'condition', None) or '').strip().upper()
        condition_type = getattr(x, 'condition_type', None) or 'priceThreshold'
        try:
            target_price = float(getattr(x, 'target_price', 0.0) or 0.0)
        except (ValueError, TypeError):
            target_price = 0.0
        upper_target_price = _to_float(getattr(x, 'upper_target_price', None))
        lower_target_price = _to_float(getattr(x, 'lower_target_price', None))
        percent = _to_float(getattr(x, 'percent', None))
        base_price = _to_float(getattr(x, 'base_price', None))
        direction = getattr(x, 'direction', None) or 'above'
        alert_nature = getattr(x, 'alert_nature', None) or 'price'

    return (
        exchange,
        symbol,
        condition,
        condition_type,
        target_price,
        upper_target_price,
        lower_target_price,
        percent,
        base_price,
        direction,
        alert_nature,
    )

trigger_signature = _trigger_signature

@router.post("/api/alerts", response_model=AlertPublic, dependencies=API_DEP)
@router.post("/alerts", response_model=AlertPublic, dependencies=API_DEP)
async def create_alert(alert_in: AlertCreate, response: Response = None):
    alert_in.condition = (alert_in.condition or 'ABOVE').strip().upper()
    alert_in.exchange = (alert_in.exchange or '').strip().lower()
    alert_in.symbol = normalize_symbol(alert_in.symbol or '')
    if not EXCHANGE_RE.match(alert_in.exchange) or not SYMBOL_RE.match(alert_in.symbol):
        raise HTTPException(status_code=400, detail="Invalid exchange or symbol.")
    if not math.isfinite(alert_in.target_price):
        raise HTTPException(status_code=400, detail="Invalid target_price.")
    if not alert_in.user_id.strip() or len(alert_in.user_id) > 128 or len(alert_in.fcm_token or "") > 512:
        raise HTTPException(status_code=400, detail="Invalid user_id or fcm_token.")
    if alert_in.telegram_chat_id:
        alert_in.telegram_chat_id = alert_in.telegram_chat_id.strip()
        if not CHAT_ID_RE.match(alert_in.telegram_chat_id):
            raise HTTPException(status_code=400, detail="Invalid telegram_chat_id.")
    if alert_in.webhook_url and not await is_safe_webhook_url_async(alert_in.webhook_url):
        raise HTTPException(status_code=400, detail="Unsafe or unresolvable webhook_url (https + public host required).")

    # Phase 4: Crypto Alert Validation ('enforce' / 'warn')
    val_mode = str(getattr(config, "CRYPTO_VALIDATE_ALERTS", "false")).strip().lower()
    validation_warning = None
    if val_mode in ("true", "1", "yes", "on", "enforce", "warn"):
        from app.markets.crypto_validation import validate_crypto_alert
        is_val, err_code, err_msg = validate_crypto_alert(
            exchange=alert_in.exchange,
            symbol=alert_in.symbol,
            base_currency=alert_in.base_currency,
            counter_currency=alert_in.counter_currency,
            market_symbol=alert_in.market_symbol,
        )
        if not is_val:
            if val_mode in ("true", "1", "yes", "on", "enforce"):
                raise HTTPException(status_code=400, detail=f"{err_code}: {err_msg}")
            else:
                validation_warning = f"{err_code}: {err_msg}"
                if response:
                    response.headers["X-Alert-Warning"] = validation_warning
                alert_in.warning = validation_warning
                print(f"⚠️ [Alert Create Warn] {alert_in.exchange}:{alert_in.symbol} - {validation_warning}")

    alert_in.check_interval_seconds = _clamp_interval(alert_in.check_interval_seconds, exchange=alert_in.exchange)
    if alert_in.note:
        alert_in.note = alert_in.note[:MAX_NOTE_LEN]
    rule_id = (alert_in.id or str(uuid.uuid4()))[:128]
    async with _db_lock:
        existing = next((a for a in storage.ALERTS_DB if a.id == rule_id), None)
        if existing:
            sig_before = _trigger_signature(existing)
            sig_new = _trigger_signature(alert_in)
            if sig_before != sig_new:
                existing.last_eval_asof = None
                existing.last_eval_price = None
                existing.waiting_for_cross = False
            existing.user_id = alert_in.user_id
            existing.exchange = alert_in.exchange
            existing.symbol = alert_in.symbol
            existing.target_price = alert_in.target_price
            existing.condition = alert_in.condition
            existing.condition_type = alert_in.condition_type or "priceThreshold"
            existing.direction = alert_in.direction or "above"
            existing.both_way_behavior = alert_in.both_way_behavior or "oco"
            existing.percent = alert_in.percent
            existing.upper_target_price = alert_in.upper_target_price
            existing.upper_note = alert_in.upper_note
            existing.lower_target_price = alert_in.lower_target_price
            existing.lower_note = alert_in.lower_note
            existing.delta_absolute = alert_in.delta_absolute
            existing.volume_percent = alert_in.volume_percent
            existing.base_price = alert_in.base_price
            existing.base_volume = alert_in.base_volume
            existing.base_currency = alert_in.base_currency
            existing.counter_currency = alert_in.counter_currency
            existing.market_symbol = alert_in.market_symbol
            existing.language = alert_in.language or "fa"
            existing.prefer_server_proxy = alert_in.prefer_server_proxy
            existing.raw_rule = alert_in.raw_rule
            existing.fcm_token = alert_in.fcm_token
            existing.check_interval_seconds = alert_in.check_interval_seconds
            existing.note = alert_in.note
            existing.trigger_mode = alert_in.trigger_mode or "oneShot"
            existing.alert_nature = alert_in.alert_nature or "price"
            existing.sound_enabled = alert_in.sound_enabled
            existing.vibration_enabled = alert_in.vibration_enabled
            existing.flash_enabled = alert_in.flash_enabled
            existing.tts_enabled = alert_in.tts_enabled
            existing.sound = alert_in.sound or "alarm_siren"
            existing.telegram_chat_id = alert_in.telegram_chat_id
            existing.webhook_url = alert_in.webhook_url
            existing.is_active = True
            existing.last_triggered_at = 0.0
            existing.last_checked_at = 0.0
            new_alert = existing
        else:
            if sum(1 for a in storage.ALERTS_DB if a.user_id == alert_in.user_id) >= MAX_ALERTS_PER_USER:
                raise HTTPException(status_code=400, detail="Alert limit reached for this user.")
            new_alert = Alert(
                id=rule_id,
                user_id=alert_in.user_id,
                exchange=alert_in.exchange,
                symbol=alert_in.symbol,
                target_price=alert_in.target_price,
                condition=alert_in.condition,
                condition_type=alert_in.condition_type or "priceThreshold",
                direction=alert_in.direction or "above",
                both_way_behavior=alert_in.both_way_behavior or "oco",
                percent=alert_in.percent,
                upper_target_price=alert_in.upper_target_price,
                upper_note=alert_in.upper_note,
                lower_target_price=alert_in.lower_target_price,
                lower_note=alert_in.lower_note,
                delta_absolute=alert_in.delta_absolute,
                volume_percent=alert_in.volume_percent,
                base_price=alert_in.base_price,
                base_volume=alert_in.base_volume,
                base_currency=alert_in.base_currency,
                counter_currency=alert_in.counter_currency,
                market_symbol=alert_in.market_symbol,
                language=alert_in.language or "fa",
                prefer_server_proxy=alert_in.prefer_server_proxy,
                raw_rule=alert_in.raw_rule,
                fcm_token=alert_in.fcm_token,
                check_interval_seconds=alert_in.check_interval_seconds,
                note=alert_in.note,
                trigger_mode=alert_in.trigger_mode or "oneShot",
                alert_nature=alert_in.alert_nature or "price",
                sound_enabled=alert_in.sound_enabled,
                vibration_enabled=alert_in.vibration_enabled,
                flash_enabled=alert_in.flash_enabled,
                tts_enabled=alert_in.tts_enabled,
                sound=alert_in.sound or "alarm_siren",
                telegram_chat_id=alert_in.telegram_chat_id,
                webhook_url=alert_in.webhook_url,
                is_active=True,
                created_at=datetime.now(timezone.utc).isoformat(),
                last_checked_at=0.0,
                last_triggered_at=0.0,
                last_eval_asof=None,
                last_eval_price=None,
                waiting_for_cross=False,
                warning=validation_warning
            )
            storage.ALERTS_DB.append(new_alert)

        if alert_in.telegram_chat_id and alert_in.user_id.lower() != 'user_default':
            storage.USER_PROFILES_DB[alert_in.user_id.lower()] = {
                "user_id": alert_in.user_id.lower(),
                "telegram_chat_id": alert_in.telegram_chat_id,
                "is_connected": True,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            await save_user_profiles_to_disk_async(storage.USER_PROFILES_DB)
    await save_alerts_to_disk_async(storage.ALERTS_DB)
    print(f"📩 [API] New Alert Created/Updated: {new_alert.symbol} ({new_alert.exchange}) | ID: {new_alert.id} | Target: {new_alert.target_price} | Interval: {new_alert.check_interval_seconds}s")

    # Dispatch Telegram confirmation message with alert features upon registration
    try:
        effective_chat_id = (new_alert.telegram_chat_id or "").strip()
        if not effective_chat_id:
            user_prof = storage.USER_PROFILES_DB.get(new_alert.user_id.lower(), {})
            effective_chat_id = (user_prof.get('telegram_chat_id') or "").strip()

        if effective_chat_id and state.http_client is not None:
            tg_conf_msg = format_alert_registered_telegram_msg(new_alert)
            _spawn(send_telegram_alert(state.http_client, effective_chat_id, tg_conf_msg))
            print(f"🤖 [Telegram Confirmation] Sent for {new_alert.symbol} to chat {mask_identifier(effective_chat_id)}")
    except Exception as e:
        print(f"⚠️ [Telegram Confirmation Note] {e}")

    if alert_in.fcm_token:
        try:
            from app.notifier.outbox import on_alert_token_updated
            on_alert_token_updated(new_alert.id, alert_in.fcm_token)
        except Exception:
            pass

    return new_alert

@router.post("/api/alerts/sync", dependencies=API_DEP)
@router.post("/alerts/sync", dependencies=API_DEP)
async def sync_user_alerts(payload: dict):
    user_id = str(payload.get('user_id') or 'user_default').strip()
    fcm_token = str(payload.get('fcm_token') or '').strip()
    alerts_data = payload.get('alerts', [])
    ack_supported_flag = bool(payload.get('ack_supported', False))
    sync_mode = str(payload.get('sync_mode') or 'mirror').strip().lower()
    if sync_mode not in ('mirror', 'merge'):
        raise HTTPException(status_code=400, detail="sync_mode must be 'mirror' or 'merge'.")
    if user_id == 'user_default' and len(fcm_token) <= 10:
        raise HTTPException(status_code=400, detail="user_id or a valid fcm_token is required.")
    if len(user_id) > 128 or len(fcm_token) > 512:
        raise HTTPException(status_code=400, detail="user_id or fcm_token too long.")
    if not isinstance(alerts_data, list) or len(alerts_data) > MAX_ALERTS_PER_USER:
        raise HTTPException(status_code=400, detail=f"'alerts' must be a list of at most {MAX_ALERTS_PER_USER} items.")
    try:
        alerts_data = [_normalize_sync_item(i) for i in alerts_data]
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid alert payload: {e}")
    for item in alerts_data:
        hook = item.get('webhook_url')
        if hook:
            if await is_safe_webhook_url_async(str(hook)):
                item['webhook_url'] = str(hook)
            else:
                print(f"⚠️ [API] Dropped unsafe webhook_url from synced alert {item.get('id')}")
                item['webhook_url'] = None

    val_mode = str(getattr(config, "CRYPTO_VALIDATE_ALERTS", "false")).strip().lower()
    backup_snapshot = None
    should_backup = sync_mode == 'mirror'  # SYNC-1b: only mirror can shrink

    async with _db_lock:
        existing_map = {a.id: a for a in storage.ALERTS_DB if (a.user_id == user_id or a.fcm_token == fcm_token)}
        new_alerts = []
        added_count = 0
        sync_warnings = []
        for item in alerts_data:
            rule_id = item.get('id') or str(uuid.uuid4())
            existing = existing_map.get(rule_id)

            sig_matches = existing is not None and (_trigger_signature(existing) == _trigger_signature(item))

            # Phase 4: Per-item Crypto Alert Validation (applies ONLY to new or changed items)
            # Alerts already on the server pass through untouched
            item_warning = None
            if not sig_matches and val_mode in ("true", "1", "yes", "on", "enforce", "warn"):
                from app.markets.crypto_validation import validate_crypto_alert
                ex = str(item.get('exchange') or 'nobitex').strip().lower()
                sym = str(item.get('symbol') or 'USDTIRT').strip()
                is_val, err_code, err_msg = validate_crypto_alert(
                    exchange=ex,
                    symbol=sym,
                    base_currency=item.get('base_currency'),
                    counter_currency=item.get('counter_currency'),
                    market_symbol=item.get('market_symbol'),
                )
                if not is_val:
                    warning_detail = f"{err_code}: {err_msg}"
                    sync_warnings.append({
                        "id": rule_id,
                        "exchange": ex,
                        "symbol": sym,
                        "error_code": err_code,
                        "error": err_msg,
                    })
                    if val_mode in ("true", "1", "yes", "on", "enforce"):
                        print(f"⚠️ [Sync Validation] Rejected invalid crypto alert {rule_id} ({ex}:{sym}): {warning_detail}")
                        continue  # Skip this single invalid item; all other alerts sync cleanly
                    else:
                        item_warning = warning_detail
                        print(f"⚠️ [Sync Validation Warn] Allowed with warning {rule_id} ({ex}:{sym}): {warning_detail}")
            if sig_matches:
                last_eval_asof = existing.last_eval_asof
                last_eval_price = existing.last_eval_price
                waiting_for_cross = existing.waiting_for_cross
                last_trig = existing.last_triggered_at
                last_chk = existing.last_checked_at
            else:
                last_eval_asof = None
                last_eval_price = None
                waiting_for_cross = False
                last_trig = 0.0
                last_chk = 0.0

            is_act = bool(item.get('is_active', True))
            if existing and not existing.is_active and getattr(existing, 'trigger_mode', 'oneShot') == 'oneShot':
                is_act = False

            eff_chat = item.get('telegram_chat_id')
            if not eff_chat:
                user_prof = storage.USER_PROFILES_DB.get(user_id.lower(), {})
                if user_prof.get('is_connected'):
                    eff_chat = user_prof.get('telegram_chat_id')
            if not eff_chat and existing and existing.telegram_chat_id:
                eff_chat = existing.telegram_chat_id

            alert_obj = Alert(
                id=rule_id,
                ack_supported=ack_supported_flag,
                user_id=user_id,
                exchange=item.get('exchange', 'nobitex').lower(),
                symbol=item.get('symbol', 'USDTIRT').upper(),
                target_price=float(item.get('target_price', 0.0)),
                condition=item.get('condition', 'ABOVE').upper(),
                condition_type=item.get('condition_type') or 'priceThreshold',
                direction=item.get('direction') or 'above',
                both_way_behavior=item.get('both_way_behavior') or 'oco',
                percent=item.get('percent'),
                upper_target_price=item.get('upper_target_price'),
                upper_note=item.get('upper_note'),
                lower_target_price=item.get('lower_target_price'),
                lower_note=item.get('lower_note'),
                delta_absolute=item.get('delta_absolute'),
                volume_percent=item.get('volume_percent'),
                base_price=item.get('base_price'),
                base_volume=item.get('base_volume'),
                base_currency=item.get('base_currency'),
                counter_currency=item.get('counter_currency'),
                market_symbol=item.get('market_symbol'),
                language=item.get('language') or 'fa',
                prefer_server_proxy=bool(item.get('prefer_server_proxy', False)),
                raw_rule=item.get('raw_rule'),
                fcm_token=item.get('fcm_token') or fcm_token,
                check_interval_seconds=_clamp_interval(item.get('check_interval_seconds', 180), exchange=item.get('exchange', 'nobitex').lower()),
                note=item.get('note'),
                trigger_mode=item.get('trigger_mode', 'oneShot'),
                alert_nature=item.get('alert_nature') or 'price',
                sound_enabled=bool(item.get('sound_enabled', True)),
                vibration_enabled=bool(item.get('vibration_enabled', True)),
                flash_enabled=bool(item.get('flash_enabled', False)),
                tts_enabled=bool(item.get('tts_enabled', True)),
                sound=item.get('sound', 'alarm_siren'),
                telegram_chat_id=eff_chat,
                webhook_url=item.get('webhook_url'),
                is_active=is_act,
                created_at=item.get('created_at') or datetime.now(timezone.utc).isoformat(),
                last_checked_at=last_chk,
                last_triggered_at=last_trig,
                last_eval_asof=last_eval_asof,
                last_eval_price=last_eval_price,
                waiting_for_cross=waiting_for_cross,
                warning=item_warning
            )
            new_alerts.append(alert_obj)
            added_count += 1

        # SYNC-1a-fix: snapshot only inside the lock, write outside.
        current_user_alerts = [a for a in storage.ALERTS_DB if (a.user_id or "").lower() == user_id.lower()]
        if should_backup and len(current_user_alerts) > 0 and len(new_alerts) < len(current_user_alerts):
            backup_snapshot = [a.model_dump() if hasattr(a, 'model_dump') else a.dict() for a in current_user_alerts]

        # SYNC-1b: mirror = replace (current behavior); merge = upsert (no delete)
        if sync_mode == 'mirror':
            if user_id == 'user_default':
                storage.ALERTS_DB[:] = [a for a in storage.ALERTS_DB if a.fcm_token != fcm_token]
            elif len(fcm_token) > 10:
                storage.ALERTS_DB[:] = [a for a in storage.ALERTS_DB if (a.user_id != user_id and a.fcm_token != fcm_token)]
            else:
                storage.ALERTS_DB[:] = [a for a in storage.ALERTS_DB if a.user_id != user_id]

        # For merge: replace only alerts with matching id (same user), keep others, add new
        if sync_mode == 'merge':
            existing_ids = {a.id for a in new_alerts}
            storage.ALERTS_DB[:] = [
                a for a in storage.ALERTS_DB
                if not (
                    (a.user_id or "").lower() == user_id.lower()
                    and a.id in existing_ids
                )
            ]
        storage.ALERTS_DB.extend(new_alerts)

        if user_id.lower() != 'user_default':
            first_chat = next((i.get('telegram_chat_id') for i in alerts_data if i.get('telegram_chat_id')), None)
            if first_chat:
                storage.USER_PROFILES_DB[user_id.lower()] = {
                    "user_id": user_id.lower(),
                    "telegram_chat_id": str(first_chat).strip(),
                    "is_connected": True,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
                await save_user_profiles_to_disk_async(storage.USER_PROFILES_DB)

    # SYNC-1a-fix: write backup OUTSIDE the lock.
    if backup_snapshot:
        try:
            import hashlib
            uid_hash = hashlib.sha256(user_id.lower().encode()).hexdigest()[:8]
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            backup_dir = os.path.join(DATA_DIR, "alerts_backup")
            os.makedirs(backup_dir, exist_ok=True)
            backup_path = os.path.join(backup_dir, f"{uid_hash}_{ts}.json")
            tmp_path = f"{backup_path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(backup_snapshot, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, backup_path)
            print(f"📦 [API] Backed up {len(backup_snapshot)} alert(s) for user {mask_identifier(user_id)} -> {backup_path}")
            user_prefix = f"{uid_hash}_"
            user_backups = sorted(
                [os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.startswith(user_prefix) and f.endswith(".json")],
                key=os.path.getmtime, reverse=True
            )
            for old in user_backups[10:]:
                try: os.remove(old)
                except Exception: pass
            cutoff = time.time() - 7 * 86400
            for old in user_backups:
                try:
                    if os.path.getmtime(old) < cutoff:
                        os.remove(old)
                except Exception: pass
        except Exception as e:
            print(f"⚠️ [API] Backup failed for user {mask_identifier(user_id)}: {e}")

    await save_alerts_to_disk_async(storage.ALERTS_DB)
    active_remaining = len([a for a in storage.ALERTS_DB if a.is_active])
    print(f"🔄 [API] Bulk Synced {added_count} alert(s) for user {mask_identifier(user_id)} (mode: {sync_mode}, Active remaining: {active_remaining})")

    for item in alerts_data:
        r_id = item.get('id')
        t = item.get('fcm_token') or fcm_token
        if r_id and t:
            try:
                from app.notifier.outbox import on_alert_token_updated
                on_alert_token_updated(r_id, t)
            except Exception:
                pass

    res = {"status": "synced", "count": added_count, "total_active": active_remaining, "mode": sync_mode}
    if sync_warnings:
        res["warnings"] = sync_warnings
    return res


@router.delete("/api/alerts", dependencies=API_DEP)
@router.delete("/alerts", dependencies=API_DEP)
async def clear_all_alerts(user_id: Optional[str] = None, fcm_token: Optional[str] = None):
    async with _db_lock:
        if fcm_token:
            storage.ALERTS_DB[:] = [a for a in storage.ALERTS_DB if a.fcm_token != fcm_token]
        elif user_id:
            storage.ALERTS_DB[:] = [a for a in storage.ALERTS_DB if a.user_id != user_id]
        else:
            raise HTTPException(status_code=400, detail="user_id or fcm_token is required.")
    await save_alerts_to_disk_async(storage.ALERTS_DB)
    print("🧹 [API] Alerts purged from server.")
    return {"status": "cleared", "total_alerts": len(storage.ALERTS_DB)}

@router.get("/api/alerts/{user_id}", response_model=List[AlertPublic], dependencies=API_DEP)
@router.get("/alerts/{user_id}", response_model=List[AlertPublic], dependencies=API_DEP)
async def get_user_alerts(user_id: str, fcm_token: Optional[str] = None):
    clean_uid = (user_id or "").strip().lower()
    clean_fcm = (fcm_token or "").strip()

    async with _db_lock:
        results = []
        seen_ids = set()
        for a in storage.ALERTS_DB:
            a_uid = (a.user_id or "").strip().lower()
            a_fcm = (a.fcm_token or "").strip()

            is_match = False
            if clean_uid and a_uid == clean_uid:
                if clean_uid == 'user_default':
                    if clean_fcm and a_fcm and a_fcm == clean_fcm:
                        is_match = True
                else:
                    is_match = True
            elif clean_uid == 'user_default' and clean_fcm and a_fcm and a_fcm == clean_fcm:
                is_match = True

            if is_match and a.id not in seen_ids:
                seen_ids.add(a.id)
                results.append(a)

        # Prepare profile update (only data, no I/O inside the lock)
        profile_update = None
        if clean_uid and clean_uid != 'user_default':
            first_chat = next((a.telegram_chat_id for a in results if a.telegram_chat_id and a.user_id.lower() == clean_uid), None)
            if first_chat:
                profile_update = {
                    "user_id": clean_uid,
                    "telegram_chat_id": str(first_chat).strip(),
                    "is_connected": True,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }

    # I/O OUTSIDE the lock to avoid deadlock with save_alerts_to_disk_async
    if profile_update:
        storage.USER_PROFILES_DB[clean_uid] = profile_update
        await save_user_profiles_to_disk_async(storage.USER_PROFILES_DB)

    return results
 
@router.post("/api/alerts/claim", dependencies=API_DEP)
@router.post("/alerts/claim", dependencies=API_DEP)
async def claim_guest_alerts(payload: dict):
    """
    Explicitly claims guest alerts belonging to 'user_default' for the caller's user_id,
    requiring strict, exact match of the device FCM token.
    Alerts without an FCM token or with mismatched tokens are NEVER transferred.
    """
    target_uid = str(payload.get("user_id") or "").strip().lower()
    clean_fcm = str(payload.get("fcm_token") or "").strip()

    if not target_uid or target_uid == "user_default" or not clean_fcm or len(clean_fcm) < 5:
        raise HTTPException(status_code=400, detail="Valid target user_id and exact fcm_token required.")

    claimed_count = 0
    async with _db_lock:
        for a in storage.ALERTS_DB:
            a_uid = (a.user_id or "").strip().lower()
            a_fcm = (a.fcm_token or "").strip()
            if a_uid == "user_default" and a_fcm and a_fcm == clean_fcm:
                a.user_id = target_uid
                claimed_count += 1

    # SYNC-3: save OUTSIDE the lock (DEADLOCK-1 lesson).
    if claimed_count > 0:
        await save_alerts_to_disk_async(storage.ALERTS_DB)

    return {"status": "success", "claimed_count": claimed_count}

@router.delete("/api/alerts/{alert_id}", dependencies=API_DEP)
@router.delete("/alerts/{alert_id}", dependencies=API_DEP)
async def delete_alert(alert_id: str):
    clean_id = (alert_id or "").strip()
    async with _db_lock:
        storage.ALERTS_DB[:] = [a for a in storage.ALERTS_DB if a.id != clean_id]
    await save_alerts_to_disk_async(storage.ALERTS_DB)
    return {"status": "deleted", "id": clean_id}
