import time
import asyncio
from datetime import timedelta
from typing import Tuple
import firebase_admin
from firebase_admin import messaging
from firebase_admin import exceptions as fb_exceptions
from app.state import METRICS

def _send_fcm_sync(fcm_token: str, title: str, body: str, data_payload: dict = None, ttl_seconds: int = 300) -> Tuple[bool, str]:
    if not firebase_admin._apps:
        return False, "Firebase Admin SDK not initialized."
    if not fcm_token or fcm_token.startswith('dev_') or fcm_token.startswith('device_token_') or len(fcm_token) < 40:
        return False, "Not a valid Google FCM registration token."

    try:
        full_data = {"title": str(title), "body": str(body), **(data_payload or {})}
        full_data_str = {k: str(v) if v is not None else "" for k, v in full_data.items()}

        effective_ttl = timedelta(seconds=max(60, min(2419200, ttl_seconds)))

        message = messaging.Message(
            data=full_data_str,
            token=fcm_token,
            android=messaging.AndroidConfig(priority='high', ttl=effective_ttl, direct_boot_ok=True),
            apns=messaging.APNSConfig(payload=messaging.APNSPayload(aps=messaging.Aps(content_available=True, badge=1)))
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
