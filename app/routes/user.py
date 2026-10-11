from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException

from app.config import CHAT_ID_RE
from app.security import API_DEP
from app.models import UserTelegramUpdateRequest
from app.state import _db_lock
from app.storage import ALERTS_DB, USER_PROFILES_DB, save_alerts_to_disk_async, save_user_profiles_to_disk_async
import app.storage as storage

router = APIRouter()

@router.get("/api/user/{user_id}/telegram", dependencies=API_DEP)
@router.get("/user/{user_id}/telegram", dependencies=API_DEP)
async def get_user_telegram_status(user_id: str):
    clean_uid = (user_id or "").strip().lower()
    async with _db_lock:
        profile = storage.USER_PROFILES_DB.get(clean_uid)
        if not profile:
            # Fallback: check if any existing alert has telegram_chat_id for this user
            user_alert = next((a for a in storage.ALERTS_DB if a.user_id.lower() == clean_uid and a.telegram_chat_id), None)
            if user_alert and user_alert.telegram_chat_id:
                profile = {
                    "user_id": clean_uid,
                    "telegram_chat_id": user_alert.telegram_chat_id,
                    "is_connected": True,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
                storage.USER_PROFILES_DB[clean_uid] = profile
        if profile:
            return profile
    return {
        "user_id": clean_uid,
        "telegram_chat_id": None,
        "is_connected": False,
        "updated_at": None
    }

@router.post("/api/user/{user_id}/telegram", dependencies=API_DEP)
@router.post("/user/{user_id}/telegram", dependencies=API_DEP)
async def update_user_telegram_status(user_id: str, req: UserTelegramUpdateRequest):
    clean_uid = (user_id or "").strip().lower()
    if not clean_uid:
        raise HTTPException(status_code=400, detail="Invalid user_id.")

    clean_chat = req.chat_id.strip() if req.chat_id else None
    if clean_chat and not CHAT_ID_RE.match(clean_chat):
        raise HTTPException(status_code=400, detail="Invalid telegram_chat_id.")

    async with _db_lock:
        profile = {
            "user_id": clean_uid,
            "telegram_chat_id": clean_chat if req.is_connected else None,
            "is_connected": req.is_connected and bool(clean_chat),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        storage.USER_PROFILES_DB[clean_uid] = profile

        # Synchronize active user alerts with their latest Telegram state
        if clean_chat and req.is_connected:
            for a in storage.ALERTS_DB:
                if a.user_id.lower() == clean_uid:
                    a.telegram_chat_id = clean_chat
        elif not req.is_connected:
            for a in storage.ALERTS_DB:
                if a.user_id.lower() == clean_uid:
                    a.telegram_chat_id = None

    await save_user_profiles_to_disk_async(storage.USER_PROFILES_DB)
    await save_alerts_to_disk_async(storage.ALERTS_DB)
    print(f"📱 [User Profile] Telegram updated for {clean_uid}: chat_id={clean_chat}, connected={profile['is_connected']}")
    return profile
