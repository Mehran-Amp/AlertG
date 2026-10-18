from datetime import datetime
from fastapi import APIRouter, HTTPException

from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_METADATA, CHAT_ID_RE
from app.security import API_DEP, _scrub
from app.models import TelegramTestRequest, Alert
from app.state import METRICS
from app.notifier.telegram import format_telegram_history_card, TELEGRAM_BOT_KEYBOARD
import app.state as state

router = APIRouter()

@router.get("/api/telegram/bot-info", dependencies=API_DEP)
@router.get("/telegram/bot-info", dependencies=API_DEP)
def get_telegram_bot_info():
    uname = TELEGRAM_BOT_METADATA.get("username", "aisocialfeedbot")
    return {
        "bot_token_configured": bool(TELEGRAM_BOT_TOKEN),
        "username": uname,
        "first_name": TELEGRAM_BOT_METADATA.get("first_name", "AiSFeed"),
        "is_connected": TELEGRAM_BOT_METADATA.get("is_connected", False),
        "bot_url": f"https://t.me/{uname}",
        "bot_handle": f"@{uname}"
    }

@router.post("/api/telegram/test-message", dependencies=API_DEP)
@router.post("/telegram/test-message", dependencies=API_DEP)
async def send_telegram_test_message(req: TelegramTestRequest):
    if not state.http_client:
        raise HTTPException(status_code=503, detail="Server client not initialized.")
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=400, detail="Telegram Bot Token is not configured.")

    chat_id = (req.chat_id or "").strip()
    if not chat_id or not CHAT_ID_RE.match(chat_id):
        raise HTTPException(status_code=400, detail="Valid chat_id is required.")

    sample_alert = Alert(
        id="test_sample_alert",
        user_id="test_user",
        symbol="BTCUSDT",
        exchange="binance",
        condition_type="priceThreshold",
        direction="above",
        condition="ABOVE",
        target_price=68000.0,
        base_price=67200.0,
        trigger_mode="oneShot",
        sound_enabled=True,
        vibration_enabled=True,
        tts_enabled=True,
        note="Breakout above resistance confirmed! Looking for 70k."
    )

    test_msg = format_telegram_history_card(
        alert=sample_alert,
        current_price=68450.0,
        triggered_target=68000.0,
        previous_price=67200.0,
        custom_note="Breakout above resistance confirmed! Looking for 70k."
    )

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        res = await state.http_client.post(url, json={
            "chat_id": chat_id,
            "text": test_msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": TELEGRAM_BOT_KEYBOARD
        }, timeout=8.0)
        if res.status_code == 200:
            METRICS["telegram_sent"] += 1
            return {"status": "ok", "message": "Test alert card sent successfully to your Telegram!", "chat_id": chat_id}
        else:
            err_msg = res.text[:200]
            if res.status_code == 401:
                raise HTTPException(status_code=502, detail="توکن ربات تلگرام روی سرور نامعتبر یا منقضی شده است (Telegram Bot Unauthorized 401).")
            elif res.status_code == 400:
                raise HTTPException(status_code=400, detail="شناسه چت نامعتبر است یا کاربر ربات را استارت نکرده است (/start در ربات تلگرام لازم است).")
            raise HTTPException(status_code=res.status_code, detail=f"خطای تلگرام: {err_msg}")
    except HTTPException:
        raise
    except Exception as e:
        print(f"⚠️ [Telegram Test Error] {_scrub(e)}")
        raise HTTPException(status_code=502, detail=f"ارتباط با تلگرام برقرار نشد: {_scrub(e)}")
