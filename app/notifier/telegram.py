import html
import asyncio
from typing import Optional, Any
import httpx
from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_METADATA
from app.security import _scrub
from app.state import METRICS
import app.state as state
import app.storage as storage

# Two-button persistent menu keyboard for Telegram Bot
TELEGRAM_BOT_KEYBOARD = {
    "keyboard": [
        [
            {"text": "START"},
            {"text": "Get Telegram ID"}
        ]
    ],
    "resize_keyboard": True,
    "is_persistent": True
}

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

async def send_telegram_alert(
    client: httpx.AsyncClient,
    chat_id: str,
    message: str,
    bot_token: Optional[str] = None,
    reply_markup: Optional[dict] = None
):
    token = bot_token or TELEGRAM_BOT_TOKEN
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": reply_markup if reply_markup is not None else TELEGRAM_BOT_KEYBOARD
        }
        await client.post(url, json=payload, timeout=6.0)
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
    c = client or getattr(state, 'http_client', None)
    if c is None:
        class _FallbackClient:
            async def post(self, *a, **kw): pass
        c = _FallbackClient()
    await send_telegram_alert(c, target_chat, message)

def format_alert_registered_telegram_msg(alert: Any) -> str:
    """Formats a sleek confirmation message when an alert is added to the server using quotes."""
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

    body = "\n".join(lines)
    return f"<blockquote>{body}</blockquote>"

def format_telegram_history_card(
    alert: Any,
    current_price: float,
    triggered_target: Optional[float] = None,
    previous_price: Optional[float] = None,
    cached_meta: Optional[dict] = None,
    custom_note: Optional[str] = None
) -> str:
    """
    Formats a rich Telegram notification matching the exact structure and visual fields
    of the app's History card in English, using native Telegram <blockquote> quotes instead of line dividers.
    """
    from datetime import datetime, timezone

    # 1. Symbol & Market
    display_symbol = getattr(alert, 'symbol', '') or ''
    if '/' not in display_symbol and len(display_symbol) > 3:
        for q in ['USDT', 'USDC', 'BUSD', 'FDUSD', 'EUR', 'USD', 'TMN', 'IRT', 'BTC', 'ETH']:
            if display_symbol.endswith(q) and len(display_symbol) > len(q):
                display_symbol = f"{display_symbol[:-len(q)]}/{q}"
                break

    raw_exchange = str(getattr(alert, 'exchange', '') or '')
    exchange_name = get_exchange_display_name(raw_exchange)
    exchange_badge = exchange_name.upper()

    # 2. Condition Type & Direction
    cond_type_raw = str(getattr(alert, 'condition_type', '') or 'priceThreshold')
    type_map = {
        'priceThreshold': 'Price Threshold',
        'percentChange': 'Percent Move',
        'absolutePriceChange': 'Absolute Change',
        'volumeChange': 'Volume Spike',
        'macro': 'Macro Metric'
    }
    cond_type_en = type_map.get(cond_type_raw, cond_type_raw)

    direction_raw = str(getattr(alert, 'direction', '') or getattr(alert, 'condition', '') or 'above').lower()
    if direction_raw in ('above', 'up'):
        dir_label = "Bullish / Cross Above ▲"
    elif direction_raw in ('below', 'down'):
        dir_label = "Bearish / Cross Below ▼"
    else:
        dir_label = "Dual Range (OCO) ⇅"

    # Price Formatter
    is_tmn = raw_exchange.lower() in ('nobitex', 'tse', 'iran_market') or display_symbol.endswith(('TMN', 'IRT'))
    def _fmt(val: Optional[float]) -> str:
        if val is None:
            return "-"
        if is_tmn:
            return f"{int(val):,} Tomans"
        if val < 1:
            return f"${val:,.4f}".rstrip('0').rstrip('.')
        return f"${val:,.2f}"

    curr_fmt = _fmt(current_price)

    # Reference Price for Movement Calculation
    ref_price = triggered_target or previous_price or getattr(alert, 'base_price', None) or getattr(alert, 'target_price', None)
    pct_str = ""
    arrow_icon = "🟢 ▲"

    if ref_price and ref_price > 0:
        diff = current_price - ref_price
        is_upward = diff >= 0
        move_pct = (diff / ref_price) * 100.0
        sign = "+" if is_upward else ""
        pct_str = f"{sign}{move_pct:.2f}%"
        arrow_icon = "🟢 ▲" if is_upward else "🔴 ▼"
    else:
        arrow_icon = "🟢" if direction_raw in ('above', 'up') else "🔴"

    # 3. Price Movement Box
    price_lines = []
    if ref_price and ref_price > 0 and abs(current_price - ref_price) > 1e-6:
        ref_fmt = _fmt(ref_price)
        price_lines.append(f"🎯 <b>Target / Reference:</b> <code>{ref_fmt}</code>")
        price_lines.append(f"⚡ <b>Triggered At:</b> <b><code>{curr_fmt}</code></b>")
        if pct_str:
            price_lines.append(f"📈 <b>Price Movement:</b> <code>{pct_str}</code> {arrow_icon}")
    else:
        price_lines.append(f"⚡ <b>Triggered At:</b> <b><code>{curr_fmt}</code></b> {arrow_icon}")

    # 4. Detail description
    if cond_type_raw == 'percentChange' and pct_str:
        detail_msg = f"{display_symbol} moved {pct_str} to reach {curr_fmt}, fulfilling the percentage trigger."
    elif ref_price and ref_price > 0:
        detail_msg = f"{display_symbol} crossed {curr_fmt}, satisfying the target of {_fmt(ref_price)}."
    else:
        detail_msg = f"Alert condition for {display_symbol} was triggered at {curr_fmt}."

    # 5. Note block
    note_val = custom_note or getattr(alert, 'note', None) or getattr(alert, 'upper_note', None) or getattr(alert, 'lower_note', None)
    note_line = ""
    if note_val and str(note_val).strip():
        clean_n = str(note_val).strip()
        if clean_n.startswith('📝'):
            clean_n = clean_n[1:].strip()
        if clean_n:
            note_line = f"\n📝 <b>Strategy Note:</b>\n<i>{html.escape(clean_n)}</i>"

    # 6. Mode & Features
    mode_raw = getattr(alert, 'trigger_mode', 'oneShot')
    mode_str = "One-Shot" if mode_raw == "oneShot" else "Recurring"

    features = []
    if getattr(alert, 'sound_enabled', True):
        features.append("🔊 Sound")
    if getattr(alert, 'vibration_enabled', True):
        features.append("📳 Vibrate")
    if getattr(alert, 'tts_enabled', False):
        features.append("🗣️ Voice")
    feat_str = " | ".join(features)
    if feat_str:
        feat_str = f"({feat_str})"

    # 7. Timestamp
    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

    details_content = "\n".join([
        f"🏷️ <b>Asset:</b> <code>{html.escape(display_symbol)}</code>",
        f"🏛️ <b>Exchange:</b> <code>{html.escape(exchange_badge)}</code>",
        f"🎯 <b>Condition:</b> <code>{html.escape(cond_type_en)}</code>",
        f"🧭 <b>Direction:</b> {html.escape(dir_label)}",
        "",
        "📊 <b>Price Movement:</b>",
        *price_lines,
        "",
        "📢 <b>Summary:</b>",
        f"<i>{html.escape(detail_msg)}</i>" + note_line,
    ])

    footer_content = "\n".join([
        f"🕒 <b>Time:</b> <code>{now_str}</code>",
        f"⚡ <b>Status:</b> ✅ Triggered | {html.escape(mode_str)} {feat_str}".strip(),
        "🚀 <b>Engine:</b> <i>AlertG Real-Time Radar</i>"
    ])

    # Formatted with native Telegram quotes instead of line dividers
    return (
        f"🔔 <b>ALERT TRIGGERED | HISTORY CARD</b>\n\n"
        f"<blockquote>{details_content}</blockquote>\n\n"
        f"<blockquote>{footer_content}</blockquote>"
    )

def format_telegram_macro_history_card(
    symbol: str,
    price: float,
    source: str,
    trigger_reason: str,
    release_date: Optional[str] = None,
    note: Optional[str] = None
) -> str:
    """Formats macro economic alerts matching the History card layout in English using quotes."""
    from datetime import datetime, timezone
    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    note_line = ""
    if note and str(note).strip():
        n = str(note).strip()
        if n.startswith('📝'):
            n = n[1:].strip()
        if n:
            note_line = f"\n📝 <b>Strategy Note:</b>\n<i>{html.escape(n)}</i>"

    macro_body = "\n".join([
        f"📊 <b>Indicator:</b> <code>{html.escape(symbol)}</code>",
        f"🏛️ <b>Data Source:</b> <code>{html.escape(source.upper())}</code>",
        f"🎯 <b>Category:</b> <code>Macroeconomic Metric</code>",
        "",
        f"⚡ <b>Reported Value:</b> <b><code>{price:g}</code></b>",
        f"📢 <b>Event:</b> <i>{html.escape(trigger_reason)}</i>" + note_line,
    ])

    macro_footer = "\n".join([
        f"🕒 <b>Release Time:</b> <code>{html.escape(release_date or now_str)}</code>",
        "⚡ <b>Status:</b> ✅ Data Published (Triggered)",
        "🚀 <b>Engine:</b> <i>AlertG Real-Time Radar</i>"
    ])

    return (
        f"🔔 <b>MACRO ALERT | HISTORY CARD</b>\n\n"
        f"<blockquote>{macro_body}</blockquote>\n\n"
        f"<blockquote>{macro_footer}</blockquote>"
    )

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

            # Register Bot Command Menu (START & Get Telegram ID)
            try:
                await client.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setMyCommands",
                    json={
                        "commands": [
                            {"command": "start", "description": "Start & Main Menu"},
                            {"command": "id", "description": "Get Telegram Chat ID"}
                        ]
                    },
                    timeout=6.0
                )
            except Exception as cmd_err:
                print(f"⚠️ [Telegram Bot setMyCommands Note] {_scrub(cmd_err)}")
    except Exception as e:
        print(f"⚠️ [Telegram Bot Init Note] {_scrub(e)}")

async def telegram_bot_polling_loop():
    """Background listener for user interactions with two-button menu and quote layout."""
    if not TELEGRAM_BOT_TOKEN:
        return
    offset = 0
    print("📡 [Telegram Bot] Polling listener active with persistent menu [START, Get Telegram ID].")
    while True:
        try:
            if state.http_client is None:
                await asyncio.sleep(2)
                continue

            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            params = {"offset": offset, "timeout": 20, "allowed_updates": ["message", "callback_query"]}
            res = await state.http_client.get(url, params=params, timeout=25.0)
            if res.status_code == 200:
                data = res.json()
                for update in data.get("result", []):
                    offset = update.get("update_id", offset) + 1
                    msg = update.get("message") or {}
                    callback_query = update.get("callback_query") or {}

                    if callback_query:
                        cb_id = callback_query.get("id")
                        if cb_id:
                            try:
                                await state.http_client.post(
                                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                                    json={"callback_query_id": cb_id},
                                    timeout=3.0
                                )
                            except Exception:
                                pass
                        msg = callback_query.get("message") or {}
                        chat = msg.get("chat") or {}
                        chat_id = chat.get("id") or callback_query.get("from", {}).get("id")
                        text = callback_query.get("data") or ""
                        user_name = html.escape(str(callback_query.get("from", {}).get("first_name") or "User"))
                    else:
                        chat = msg.get("chat") or {}
                        chat_id = chat.get("id")
                        text = (msg.get("text") or "").strip()
                        user_name = html.escape(str(chat.get("first_name") or chat.get("username") or "User"))

                    if not chat_id:
                        continue

                    reply_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                    text_clean = text.strip()
                    text_lower = text_clean.lower()

                    is_id_request = (
                        "get telegram id" in text_lower or
                        text_lower in ("/id", "id", "chat_id", "myid", "my_id", "get_id", "cmd_id")
                    )

                    if is_id_request:
                        reply_text = (
                            f"<blockquote>"
                            f"🆔 <b>Your Telegram Chat ID:</b>\n"
                            f"<code>{chat_id}</code>"
                            f"</blockquote>\n\n"
                            f"<blockquote>"
                            f"📋 <i>Tap the number above to copy it instantly, then paste it in <b>AlertG App ➔ Settings ➔ Telegram Chat ID</b> to link your alerts.</i>"
                            f"</blockquote>"
                        )
                    else:
                        reply_text = (
                            f"👋 Hello <b>{user_name}</b>!\n\n"
                            f"<blockquote>"
                            f"⚡ <b>AlertG Real-Time Market Radar</b>\n"
                            f"Live high-frequency price & volatility alerts for Crypto, Stocks, Gold & Forex."
                            f"</blockquote>\n\n"
                            f"<blockquote>"
                            f"🆔 <b>Your Telegram Chat ID:</b> <code>{chat_id}</code>\n"
                            f"Tap the number above to copy and paste it into the <b>AlertG</b> app settings to receive real-time alert cards directly here."
                            f"</blockquote>\n\n"
                            f"<blockquote>"
                            f"👇 Use the menu buttons below to interact with the bot anytime."
                            f"</blockquote>"
                        )

                    await state.http_client.post(reply_url, json={
                        "chat_id": chat_id,
                        "text": reply_text,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                        "reply_markup": TELEGRAM_BOT_KEYBOARD
                    }, timeout=5.0)
            else:
                print(f"⚠️ [Telegram Polling] HTTP {res.status_code}: {res.text[:120]}")
                await asyncio.sleep(15 if res.status_code in (401, 409, 429) else 5)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"⚠️ [Telegram Polling Error] {_scrub(e)}")
            await asyncio.sleep(4)
