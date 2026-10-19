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

        # 1. If profile has an active connection with a chat_id, return it immediately
        if profile and profile.get("is_connected") and profile.get("telegram_chat_id"):
            return profile

        # 2. Check if any alert for this user has telegram_chat_id
        saved_chat = None
        user_alert = next((a for a in storage.ALERTS_DB if a.user_id.lower() == clean_uid and a.telegram_chat_id), None)
        if user_alert and user_alert.telegram_chat_id:
            saved_chat = user_alert.telegram_chat_id

        # 3. No fallbacks to other users, user_default, or bots
        if saved_chat:
            profile = {
                "user_id": clean_uid,
                "telegram_chat_id": saved_chat,
                "is_connected": True,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            storage.USER_PROFILES_DB[clean_uid] = profile
            await save_user_profiles_to_disk_async(storage.USER_PROFILES_DB)
            return profile

        if profile:
            return {
                "user_id": clean_uid,
                "telegram_chat_id": profile.get("telegram_chat_id") if profile.get("is_connected") else None,
                "is_connected": bool(profile.get("is_connected") and profile.get("telegram_chat_id")),
                "updated_at": profile.get("updated_at") or datetime.now(timezone.utc).isoformat()
            }

    return {
        "user_id": clean_uid,
        "telegram_chat_id": None,
        "is_connected": False,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

@router.post("/api/user/{user_id}/telegram", dependencies=API_DEP)
@router.post("/user/{user_id}/telegram", dependencies=API_DEP)
async def update_user_telegram_status(user_id: str, req: UserTelegramUpdateRequest):
    clean_uid = (user_id or "").strip().lower()
    if not clean_uid:
        raise HTTPException(status_code=400, detail="Invalid user_id.")

    clean_chat = req.chat_id.strip() if req.chat_id is not None and req.chat_id != "" else None
    if clean_chat and not CHAT_ID_RE.match(clean_chat):
        raise HTTPException(status_code=400, detail="Invalid telegram_chat_id.")

    async with _db_lock:
        existing_prof = storage.USER_PROFILES_DB.get(clean_uid, {})
        # If chat_id wasn't provided in payload, preserve existing saved chat ID
        if clean_chat is None and req.chat_id is None:
            clean_chat = existing_prof.get("telegram_chat_id")

        # Determine connection state
        # Only explicitly disconnect if req.is_connected is False AND req.chat_id == "" (explicit user unlink)
        is_explicit_unlink = (req.is_connected is False and (req.chat_id == "" or req.chat_id is None))
        effective_connected = False if is_explicit_unlink else (bool(clean_chat) and req.is_connected)

        profile = {
            **existing_prof,
            "user_id": clean_uid,
            "telegram_chat_id": clean_chat if effective_connected else (None if is_explicit_unlink else existing_prof.get("telegram_chat_id")),
            "is_connected": effective_connected,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        if req.events_notification_enabled is not None:
            profile["events_notification_enabled"] = req.events_notification_enabled
        if req.events_telegram_enabled is not None:
            profile["events_telegram_enabled"] = req.events_telegram_enabled
        if req.events_crypto_enabled is not None:
            profile["events_crypto_enabled"] = req.events_crypto_enabled
        if req.events_macro_enabled is not None:
            profile["events_macro_enabled"] = req.events_macro_enabled
        if req.events_energy_enabled is not None:
            profile["events_energy_enabled"] = req.events_energy_enabled
        if req.events_stocks_enabled is not None:
            profile["events_stocks_enabled"] = req.events_stocks_enabled

        storage.USER_PROFILES_DB[clean_uid] = profile

        # Synchronize active user alerts with their latest Telegram state
        if clean_chat and effective_connected:
            for a in storage.ALERTS_DB:
                if a.user_id.lower() == clean_uid:
                    a.telegram_chat_id = clean_chat
        elif is_explicit_unlink:
            for a in storage.ALERTS_DB:
                if a.user_id.lower() == clean_uid:
                    a.telegram_chat_id = None

    await save_user_profiles_to_disk_async(storage.USER_PROFILES_DB)
    await save_alerts_to_disk_async(storage.ALERTS_DB)
    print(f"📱 [User Profile] Telegram updated for {clean_uid}: chat_id={profile.get('telegram_chat_id')}, connected={profile['is_connected']}")
    return profile

