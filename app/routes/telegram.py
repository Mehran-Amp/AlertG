from datetime import datetime
from fastapi import APIRouter, HTTPException

from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_METADATA, CHAT_ID_RE
from app.security import API_DEP, _scrub
from app.models import TelegramTestRequest
from app.state import METRICS
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

    test_msg = (
        "🚨 <b>هشدار فعال شد:</b>\n"
        "📊🟢 <b>^TNX/USD $5.31 ▲3.12%</b>\n"
        "🎯 <b>قیمت تارگت:</b> $5.90\n"
        "🏛️ Global Stocks\n"
        f"🕒 <b>زمان:</b> <code>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</code>\n"
        "⚡ <i>ارسال شده توسط ربات هوشمند SignalAlert Enterprise</i>"
    )

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        res = await state.http_client.post(url, json={
            "chat_id": chat_id,
            "text": test_msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }, timeout=8.0)
        if res.status_code == 200:
            METRICS["telegram_sent"] += 1
            return {"status": "ok", "message": "پیام تست با موفقیت به تلگرام شما ارسال شد!", "chat_id": chat_id}
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
