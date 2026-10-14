import time
import asyncio
from datetime import timedelta
from typing import Tuple
try:
    import firebase_admin
    from firebase_admin import messaging
    from firebase_admin import exceptions as fb_exceptions
except ImportError:
    firebase_admin = None
    messaging = None
    fb_exceptions = None
from app.state import METRICS

def _send_fcm_sync(fcm_token: str, title: str, body: str, data_payload: dict = None, ttl_seconds: int = 300) -> Tuple[bool, str]:
    if not firebase_admin._apps:
        return False, "Firebase Admin SDK not initialized."
    if not fcm_token or fcm_token.startswith('dev_') or fcm_token.startswith('device_token_') or len(fcm_token) < 40:
        return False, "Not a valid Google FCM registration token."

    try:
        user_id = (data_payload or {}).get("user_id")
        user_prof = {}
        if user_id:
            try:
                from app.storage import USER_PROFILES_DB
                user_prof = USER_PROFILES_DB.get(str(user_id).lower(), {})
            except Exception:
                user_prof = {}

        # 1. Base payload (never unconditionally force 'true')
        full_data = {
            "title": str(title),
            "body": str(body),
            **(data_payload or {})
        }

        # 2. Read preferences from profile if not explicitly supplied in payload
        if "sound_enabled" not in full_data and "sound_enabled" in user_prof:
            full_data["sound_enabled"] = "true" if user_prof["sound_enabled"] else "false"
        if "vibration_enabled" not in full_data and "vibration_enabled" in user_prof:
            full_data["vibration_enabled"] = "true" if user_prof["vibration_enabled"] else "false"
        if "tts_enabled" not in full_data and "tts_enabled" in user_prof:
            full_data["tts_enabled"] = "true" if user_prof["tts_enabled"] else "false"

        # 3. Sound and channel resolution
        sound_setting = full_data.get("sound") or user_prof.get("sound") or "default"
        channel_setting = full_data.get("channel_id") or user_prof.get("channel_id") or "alarmer_critical_price_alerts"

        full_data["channel_id"] = channel_setting
        if sound_setting:
            full_data["sound"] = sound_setting

        full_data_str = {k: str(v) if v is not None else "" for k, v in full_data.items()}

        effective_ttl = timedelta(seconds=max(60, min(2419200, ttl_seconds)))

        is_sound_on = full_data.get("sound_enabled") != "false"
        is_vib_on = full_data.get("vibration_enabled") != "false"
        is_default_sound = sound_setting in ("default", "", None)
        android_sound = sound_setting if (is_sound_on and not is_default_sound) else None

        message = messaging.Message(
            data=full_data_str,
            token=fcm_token,
            android=messaging.AndroidConfig(
                priority='high',
                ttl=effective_ttl,
                direct_boot_ok=True,
                notification=messaging.AndroidNotification(
                    channel_id=channel_setting,
                    sound=android_sound,
                    priority='max',
                    visibility='public',
                    default_sound=is_default_sound and is_sound_on,
                    default_vibrate_timings=is_vib_on,
                    default_light_settings=True,
                )
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        sound=f"{sound_setting}.wav" if (is_sound_on and not is_default_sound) else ("default" if is_sound_on else None),
                        badge=1,
                        content_available=True,
                        custom_data={"interruption-level": "time-sensitive"}
                    )
                )
            )
        )
        # Retry transient failures (FCM 5xx / quota) so a blip never drops an alert.
        last_err = None
        for attempt, delay in enumerate((0, 0.5, 1.5), start=1):
            if delay:
                time.sleep(delay)
            try:
                response = messaging.send(message)
                METRICS["fcm_success"] += 1
                print(f"🚀 [FCM Push] Sent (TTL: {effective_ttl}, attempt {attempt}): {response}")
                return True, f"FCM Message ID: {response}"
            except (fb_exceptions.UnavailableError, fb_exceptions.InternalError, messaging.QuotaExceededError) as e:
                last_err = e
                print(f"⚠️ [FCM Push] transient error (attempt {attempt}): {e}")
        raise last_err
    except messaging.UnregisteredError:
        METRICS["fcm_failed"] += 1
        print(f"❌ [FCM Push] token no longer registered: ...{fcm_token[-6:]}")
        return False, "UNREGISTERED"
    except Exception as e:
        METRICS["fcm_failed"] += 1
        print(f"❌ [FCM Push Error] {e}")
        return False, str(e)

async def send_fcm_notification_async(fcm_token: str, title: str, body: str, data_payload: dict = None, ttl_seconds: int = 300) -> Tuple[bool, str]:
    return await asyncio.to_thread(_send_fcm_sync, fcm_token, title, body, data_payload, ttl_seconds)
