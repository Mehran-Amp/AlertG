import html
import asyncio
from typing import Optional, Any
import httpx
from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_METADATA
from app.security import _scrub
from app.state import METRICS
import app.state as state
import app.storage as storage

def get_exchange_display_name(exchange_id: str) -> str:
    mapping = {
        'nobitex': 'Nobitex', 'wallex': 'Wallex', 'binance': 'Binance',
        'tabdeal': 'Tabdeal', 'ramzinex': 'Ramzinex', 'kucoin': 'KuCoin',
        'mexc': 'MEXC', 'gateio': 'Gate.io', 'gate': 'Gate.io',
        'coinex': 'CoinEx', 'okx': 'OKX', 'bybit': 'Bybit',
        'bitbarg': 'BitBarg', 'tetherland': 'Tetherland', 'abantether': 'AbanTether',
        'global_stocks': 'Global Stocks', 'stocks': 'Stocks', 'forex': 'Forex',
        'macro': 'Macro', 'bonds': 'Bonds', 'wallstreet': 'Wall Street', 'iran_market': 'IR_M'
    }
    return mapping.get((exchange_id or '').lower(), (exchange_id or 'Market').capitalize())

async def send_telegram_alert(client: httpx.AsyncClient, chat_id: str, message: str, bot_token: Optional[str] = None):
    token = bot_token or TELEGRAM_BOT_TOKEN
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        await client.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=6.0)
        METRICS["telegram_sent"] += 1
    except Exception as e:
        print(f"⚠️ [Telegram Dispatch Error] {_scrub(e)}")

async def notify_admin_telegram(message: str, client: Optional[httpx.AsyncClient] = None):
    """
    Sends critical operational notification to admin Telegram chat:
    - Provider outages / errors
    - Provider quota usage > 80%
    - Failed or halted catalog syncs
    """
    from app.config import TELEGRAM_ADMIN_CHAT_ID
    target_chat = TELEGRAM_ADMIN_CHAT_ID
    if not target_chat:
        print(f"ℹ️ [Admin Telegram Alert] (No TELEGRAM_ADMIN_CHAT_ID set): {message}")
        return
    c = client or state.http_client
    if c is None:
        return
    await send_telegram_alert(c, target_chat, message)

def format_alert_registered_telegram_msg(alert: Any) -> str:
    """Formats a sleek, clean confirmation message when an alert is added to the server"""
    display_symbol = getattr(alert, 'symbol', '') or ''
    if '/' not in display_symbol and len(display_symbol) > 3:
        for q in ['USDT', 'USDC', 'BUSD', 'FDUSD', 'EUR', 'USD', 'TMN', 'IRT', 'BTC', 'ETH']:
            if display_symbol.endswith(q) and len(display_symbol) > len(q):
                display_symbol = f"{display_symbol[:-len(q)]}/{q}"
                break
    exchange_name = get_exchange_display_name(getattr(alert, 'exchange', ''))

    condition = (getattr(alert, 'condition', 'ABOVE') or 'ABOVE').upper()
    cond_arrow = "▲" if condition == "ABOVE" else "▼"
    if condition == "BOTHSIDES":
        cond_arrow = "⇅"

    cond_type = getattr(alert, 'condition_type', 'priceThreshold')
    percent_val = getattr(alert, 'percent', None)
    target_price = getattr(alert, 'target_price', 0.0) or 0.0

    if cond_type == "percentChange" and percent_val:
        target_repr = f"{percent_val:g}%"
    else:
        is_tmn = getattr(alert, 'exchange', '').lower() == 'nobitex' or getattr(alert, 'symbol', '').endswith(('TMN', 'IRT'))
        if is_tmn:
            target_repr = f"{int(target_price):,} تومان"
        elif target_price < 1:
            target_repr = f"${target_price:,.4f}".rstrip('0').rstrip('.')
        else:
            target_repr = f"${target_price:,.2f}"

    features = []
    interval_sec = getattr(alert, 'check_interval_seconds', 180)
    int_mins = interval_sec // 60
    if interval_sec % 60 == 0:
        features.append(f"⏱️ {int_mins}m")
    else:
        features.append(f"⏱️ {interval_sec}s")

    if getattr(alert, 'sound_enabled', True):
        features.append("🔊")
    if getattr(alert, 'vibration_enabled', True):
        features.append("📳")
    if getattr(alert, 'tts_enabled', False):
        features.append("🗣️")
    if getattr(alert, 'trigger_mode', 'oneShot') == "recurring":
        features.append("🔄")

    feat_str = " ".join(features)

    lines = [
        f"✅ <b>{html.escape(display_symbol)}</b> <code>{target_repr}</code> {cond_arrow}",
        f"🏛️ {html.escape(exchange_name)} | {feat_str}"
    ]
    custom_n = getattr(alert, 'note', None) or getattr(alert, 'upper_note', None) or getattr(alert, 'lower_note', None)
    if custom_n and str(custom_n).strip():
        n = str(custom_n).strip()
        if n.startswith('📝'):
            n = n[1:].strip()
        if n:
            lines.append(f"📝 {html.escape(n)}")
    return "\n".join(lines)

async def init_telegram_bot(client: httpx.AsyncClient):
    global TELEGRAM_BOT_METADATA
    if not TELEGRAM_BOT_TOKEN:
        return
    try:
        res = await client.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe", timeout=6.0)
        if res.status_code == 200:
            data = res.json().get("result", {})
            TELEGRAM_BOT_METADATA["username"] = data.get("username", "aisocialfeedbot")
            TELEGRAM_BOT_METADATA["first_name"] = data.get("first_name", "AiSFeed")
            TELEGRAM_BOT_METADATA["id"] = data.get("id", 8597547058)
            TELEGRAM_BOT_METADATA["is_connected"] = True
            print(f"🤖 [Telegram Bot] Connected to @{TELEGRAM_BOT_METADATA['username']} ({TELEGRAM_BOT_METADATA['first_name']})")
    except Exception as e:
        print(f"⚠️ [Telegram Bot Init Note] {_scrub(e)}")

async def telegram_bot_polling_loop():
    """Background listener for user interactions: /start, /myalerts, /clear, /stop, /help"""
    if not TELEGRAM_BOT_TOKEN:
        return
    offset = 0
    print("📡 [Telegram Bot] Polling listener active for instant Chat ID onboarding & alert management.")
    while True:
        try:
            if state.http_client is None:
                await asyncio.sleep(2)
                continue

            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            params = {"offset": offset, "timeout": 20, "allowed_updates": ["message"]}
            res = await state.http_client.get(url, params=params, timeout=25.0)
            if res.status_code == 200:
                data = res.json()
                for update in data.get("result", []):
                    offset = update.get("update_id", offset) + 1
                    msg = update.get("message") or {}
                    chat = msg.get("chat") or {}
                    chat_id = chat.get("id")
                    text = (msg.get("text") or "").strip()
                    user_name = html.escape(str(chat.get("first_name") or chat.get("username") or "کاربر گرامی"))

                    if not chat_id:
                        continue

                    reply_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                    chat_id_str = str(chat_id)
                    text_lower = text.lower()

                    # /start or any message - returns Chat ID cleanly
                    welcome_msg = (
                        f"🆔 <code>{chat_id}</code>\n\n"
                        f"این شناسه را در بخش تلگرام برنامه وارد کنید."
                    )
                    await state.http_client.post(reply_url, json={
                        "chat_id": chat_id,
                        "text": welcome_msg,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True
                    }, timeout=5.0)
            else:
                print(f"⚠️ [Telegram Polling] HTTP {res.status_code}: {res.text[:120]}")
                await asyncio.sleep(15 if res.status_code in (401, 409, 429) else 5)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"⚠️ [Telegram Polling Error] {_scrub(e)}")
            await asyncio.sleep(4)
