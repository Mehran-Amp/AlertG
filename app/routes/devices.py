import os
import json
import time
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.config import DATA_DIR
from app.security import API_DEP

router = APIRouter()

DEVICE_HEALTH_FILE = os.path.join(DATA_DIR, "device_health.json") if DATA_DIR != "." else "device_health.json"


def _load_device_health_from_disk() -> Dict[str, Dict[str, Any]]:
    if os.path.exists(DEVICE_HEALTH_FILE):
        try:
            with open(DEVICE_HEALTH_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {str(k).strip().lower(): v for k, v in data.items() if isinstance(v, dict)}
        except Exception as e:
            print(f"⚠️ [DeviceHealth] Could not read {DEVICE_HEALTH_FILE}: {e} (keeping a .bad copy)")
            try:
                os.replace(DEVICE_HEALTH_FILE, DEVICE_HEALTH_FILE + ".bad")
            except Exception:
                pass
    return {}


DEVICE_HEALTH: Dict[str, Dict[str, Any]] = _load_device_health_from_disk()


def save_device_health_to_disk() -> None:
    """Atomically persists the device health dictionary to disk via temp file."""
    try:
        payload = json.dumps(DEVICE_HEALTH, ensure_ascii=False, indent=2)
        tmp = f"{DEVICE_HEALTH_FILE}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, DEVICE_HEALTH_FILE)
    except Exception as e:
        print(f"⚠️ [DeviceHealth] Failed to save {DEVICE_HEALTH_FILE}: {e}")


def get_user_device_health(user_id: str) -> Optional[Dict[str, Any]]:
    """Helper to retrieve the latest device health record for a user."""
    if not user_id:
        return None
    return DEVICE_HEALTH.get(str(user_id).strip().lower())


class DeviceHeartbeatPayload(BaseModel):
    user_id: str
    fcm_token_tail: Optional[str] = None
    app_version: Optional[str] = None
    notifications_enabled: Optional[bool] = None
    battery_unrestricted: Optional[bool] = None
    fgs_running: Optional[bool] = None
    ts_ms: Optional[int] = None


@router.post("/api/device/heartbeat", dependencies=API_DEP)
@router.post("/device/heartbeat", dependencies=API_DEP)
def record_device_heartbeat(payload: DeviceHeartbeatPayload):
    """
    Records periodic heartbeat from device service isolate (Phase 3A-1).
    Stores latest health indicators atomically on disk.
    """
    clean_uid = payload.user_id.strip().lower()
    if not clean_uid:
        raise HTTPException(status_code=400, detail="user_id is required")

    tail = (payload.fcm_token_tail or "").strip()
    if len(tail) > 6:
        tail = tail[-6:]

    now_ts = int(time.time())
    now_iso = datetime.now(timezone.utc).isoformat()

    record = {
        "user_id": clean_uid,
        "fcm_token_tail": tail or None,
        "app_version": payload.app_version,
        "notifications_enabled": payload.notifications_enabled,
        "battery_unrestricted": payload.battery_unrestricted,
        "fgs_running": payload.fgs_running,
        "ts_ms": payload.ts_ms,
        "received_at": now_ts,
        "received_at_iso": now_iso,
    }

    DEVICE_HEALTH[clean_uid] = record
    save_device_health_to_disk()

    return {
        "status": "ok",
        "user_id": clean_uid,
        "received_at": now_ts
    }


@router.get("/api/device/health/{user_id}", dependencies=API_DEP)
@router.get("/device/health/{user_id}", dependencies=API_DEP)
def get_device_health(user_id: str):
    """
    Retrieves the latest device health record for a user (Phase 3A-1).
    """
    clean_uid = str(user_id).strip().lower()
    record = DEVICE_HEALTH.get(clean_uid)
    if not record:
        raise HTTPException(status_code=404, detail=f"No device health records found for user '{user_id}'")

    now = int(time.time())
    age_seconds = max(0, now - int(record.get("received_at", now)))

    return {
        "status": "ok",
        "data": record,
        "age_seconds": age_seconds
    }
