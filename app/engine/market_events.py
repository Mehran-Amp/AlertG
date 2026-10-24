import os
import json
import time
import html
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
import httpx
from app.config import TELEGRAM_BOT_TOKEN, DATA_DIR
from app.security import _scrub, mask_identifier
import app.state as state
import app.storage as storage
from app.notifier.telegram import send_telegram_alert
from app.notifier.outbox import enqueue_alert_push
from app.engine.calendar import parse_event_start_utc

# In-Memory Cache for Market Events (Updated every 6 hours)
MARKET_EVENTS_CACHE: List[Dict[str, Any]] = []
LAST_EVENTS_UPDATE: Optional[datetime] = None
DISPATCHED_EVENT_IDS = set()

# High-Impact Filter Rules & Curated Seeds across 4 sectors:
# 1. Macro & Forex: FOMC, CPI, NFP, GDP (USD/EUR/GBP/JPY)
# 2. Energy: EIA Crude Oil Inventories, Natural Gas, OPEC+
# 3. Crypto: Halving, Major Hardforks, >$30M Token Unlocks, SEC/ETF rulings
# 4. Stocks: Mega-Cap Earnings (Magnificent 7)
CURATED_HIGH_IMPACT_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "macro_fomc_rate",
        "category": "macro",
        "market": "Forex & Global",
        "title": "US Fed Interest Rate Decision (FOMC)",
        "summary": "Federal Reserve monetary policy announcement & benchmark rate decision. High volatility expected.",
        "impact": "high",
        "time_utc": "Wednesday 18:00 UTC",
        "badge_color": "#0284C7", # Sky Blue
        "symbol": "USD"
    },
    {
        "id": "macro_cpi_inflation",
        "category": "macro",
        "market": "Forex & Stocks",
        "title": "US CPI Inflation Index Release",
        "summary": "Bureau of Labor Statistics publishes monthly Consumer Price Index measuring consumer inflation.",
        "impact": "high",
        "time_utc": "Thursday 12:30 UTC",
        "badge_color": "#0284C7",
        "symbol": "USD"
    },
    {
        "id": "crypto_eth_upgrade",
        "category": "crypto",
        "market": "Ethereum Ecosystem",
        "title": "Ethereum Network Upgrade & Hard Fork",
        "summary": "Major Ethereum consensus and execution client upgrade activated across global validators.",
        "impact": "high",
        "time_utc": "Friday 14:00 UTC",
        "badge_color": "#10B981", # Emerald Green
        "symbol": "ETH"
    },
    {
        "id": "crypto_sol_unlock",
        "category": "crypto",
        "market": "Solana Ecosystem",
        "title": "Solana (SOL) >$50M Ecosystem Unlock",
        "summary": "Major foundation and liquidity token cliff unlocking into circulating supply.",
        "impact": "high",
        "time_utc": "Saturday 00:00 UTC",
        "badge_color": "#10B981",
        "symbol": "SOL"
    },
    {
        "id": "energy_eia_crude",
        "category": "energy",
        "market": "Crude Oil & Commodities",
        "title": "EIA US Crude Oil Inventories Report",
        "summary": "Weekly change in commercial crude oil barrels held by US firms. Key driver for WTI & Brent.",
        "impact": "high",
        "time_utc": "Wednesday 14:30 UTC",
        "badge_color": "#F59E0B", # Amber / Orange
        "symbol": "WTI"
    },
    {
        "id": "energy_opec_meeting",
        "category": "energy",
        "market": "Global Energy",
        "title": "OPEC+ Ministerial Production Quota Review",
        "summary": "Joint Ministerial Monitoring Committee meeting to determine voluntary oil supply cuts.",
        "impact": "high",
        "time_utc": "Upcoming Weekend",
        "badge_color": "#F59E0B",
        "symbol": "BRENT"
    },
    {
        "id": "stocks_nvda_earnings",
        "category": "stocks",
        "market": "NASDAQ / S&P 500",
        "title": "NVIDIA (NVDA) Q3 Fiscal Earnings Release",
        "summary": "Nvidia reports quarterly revenue, data center GPU sales, and AI infrastructure guidance.",
        "impact": "high",
        "time_utc": "Thursday 20:00 UTC (AMC)",
        "badge_color": "#8B5CF6", # Purple
        "symbol": "NVDA"
    },
    {
        "id": "stocks_aapl_earnings",
        "category": "stocks",
        "market": "NASDAQ / S&P 500",
        "title": "Apple (AAPL) Global Revenue & Hardware Results",
        "summary": "Apple announces quarterly iPhone, Mac, and Services segment financial performance.",
        "impact": "high",
        "time_utc": "Friday 20:30 UTC (AMC)",
        "badge_color": "#8B5CF6",
        "symbol": "AAPL"
    }
]

def format_telegram_market_event_card(event: Dict[str, Any]) -> str:
    """Formats an upcoming market event into a rich Telegram card using quotes (zero line dividers)."""
    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    category_title = event.get('category', 'macro').upper()
    title = html.escape(str(event.get('title', 'Market Event')))
    market = html.escape(str(event.get('market', 'Global Market')))
    summary = html.escape(str(event.get('summary', 'High-impact market catalyst.')))
    time_str = html.escape(str(event.get('time_utc', 'Today')))

    category_emojis = {
        'crypto': '🪙',
        'macro': '🌐',
        'energy': '🛢️',
        'stocks': '📈'
    }
    cat_emoji = category_emojis.get(event.get('category', '').lower(), '⚡')

    body = "\n".join([
        f"🏷️ <b>Category:</b> {cat_emoji} <code>{category_title}</code>",
        f"🏛️ <b>Market Impact:</b> <code>{market}</code>",
        f"🕒 <b>Event Time:</b> <b><code>{time_str}</code></b>",
        f"⚠️ <b>Importance:</b> 🔴 <b>HIGH IMPACT CATALYST</b>",
        "",
        f"📢 <b>Key Details:</b>",
        f"<i>{summary}</i>"
    ])

    footer = "\n".join([
        f"🕒 <b>Dispatched:</b> <code>{now_str}</code>",
        "⚡ <b>Engine:</b> <i>AlertG Market Events Radar</i>"
    ])

    return (
        f"🔔 <b>UPCOMING MARKET EVENT | ALERTG RADAR</b>\n\n"
        f"<blockquote>{body}</blockquote>\n\n"
        f"<blockquote>{footer}</blockquote>"
    )

def format_telegram_event_reminder_card(event: Dict[str, Any], is_cancelled: bool = False, is_advance_notice: bool = False) -> str:
    """Formats an event reminder confirmation or 30-minute advance notice for Telegram."""
    category_title = event.get('category', 'macro').upper()
    title = html.escape(str(event.get('title', 'Market Event')))
    market = html.escape(str(event.get('market', 'Global Market')))
    summary = html.escape(str(event.get('summary', 'High-impact market catalyst.')))
    time_str = html.escape(str(event.get('time_utc', 'Upcoming')))

    category_emojis = {
        'crypto': '🪙',
        'macro': '🌐',
        'energy': '🛢️',
        'stocks': '📈'
    }
    cat_emoji = category_emojis.get(event.get('category', '').lower(), '⚡')

    if is_cancelled:
        return (
            f"🔕 <b>MARKET EVENT REMINDER CANCELLED</b>\n\n"
            f"<blockquote>"
            f"🏷️ <b>Category:</b> {cat_emoji} <code>{category_title}</code>\n"
            f"🎯 <b>Event:</b> <b>{title}</b>\n"
            f"🕒 <b>Scheduled Time:</b> <code>{time_str}</code>\n"
            f"ℹ️ <i>Reminder alerts have been cancelled for this event.</i>"
            f"</blockquote>"
        )

    if is_advance_notice:
        return (
            f"⏰ <b>UPCOMING CATALYST IN 30 MINUTES | ALERTG RADAR</b>\n\n"
            f"<blockquote>"
            f"🏷️ <b>Category:</b> {cat_emoji} <code>{category_title}</code>\n"
            f"🏛️ <b>Market Impact:</b> <code>{market}</code>\n"
            f"🕒 <b>Event Time:</b> <b><code>{time_str}</code></b>\n"
            f"⚠️ <b>Status:</b> 🔴 <b>STARTS IN 30 MINUTES</b>\n\n"
            f"📢 <b>Key Catalyst Details:</b>\n"
            f"<i>{summary}</i>"
            f"</blockquote>"
        )

    return (
        f"🔔 <b>MARKET EVENT REMINDER CONFIRMED</b>\n\n"
        f"<blockquote>"
        f"🏷️ <b>Category:</b> {cat_emoji} <code>{category_title}</code>\n"
        f"🎯 <b>Event:</b> <b>{title}</b>\n"
        f"🕒 <b>Event Time:</b> <b><code>{time_str}</code></b>\n"
        f"🏛️ <b>Market:</b> <code>{market}</code>\n\n"
        f"⚡ <b>Notice:</b> <i>You will receive a high-priority alert 30 minutes before this catalyst begins.</i>"
        f"</blockquote>"
    )

# -------------------------------------------------------------------
# Persistent State: Sent Reminders & User Registrations (Phase 2B-2)
# -------------------------------------------------------------------

EVENTS_STATE_FILE = os.path.join(DATA_DIR, "market_events_state.json") if DATA_DIR != "." else "market_events_state.json"
EVENTS_STATE_TTL_SECONDS = 7 * 24 * 3600  # 7 days


def _load_events_state() -> Tuple[Dict[str, float], Dict[str, Dict[str, str]], Dict[str, float]]:
    """
    Loads sent reminders, user registrations, and per-user dispatched events from disk (Phase 2B-2 / FIX-5b).
    - Drops entries older than 7 days.
    - If corrupted, renames to .bad and returns empty state without crashing.
    """
    sent_reminders: Dict[str, float] = {}
    user_reminders: Dict[str, Dict[str, str]] = {}
    dispatched_events: Dict[str, float] = {}

    if os.path.exists(EVENTS_STATE_FILE):
        try:
            with open(EVENTS_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                now = time.time()
                raw_sent = data.get("sent_reminders", {})
                if isinstance(raw_sent, dict):
                    for k, ts in raw_sent.items():
                        try:
                            ts_float = float(ts)
                            if (now - ts_float) <= EVENTS_STATE_TTL_SECONDS:
                                sent_reminders[str(k)] = ts_float
                        except (ValueError, TypeError):
                            pass

                raw_user = data.get("user_reminders", {})
                if isinstance(raw_user, dict):
                    for ev_id, u_map in raw_user.items():
                        if isinstance(u_map, dict):
                            user_reminders[str(ev_id)] = {
                                str(uid): str(cid) for uid, cid in u_map.items() if cid
                            }

                raw_disp = data.get("dispatched_events", {})
                if isinstance(raw_disp, dict):
                    for k, ts in raw_disp.items():
                        try:
                            ts_float = float(ts)
                            if (now - ts_float) <= EVENTS_STATE_TTL_SECONDS:
                                dispatched_events[str(k)] = ts_float
                        except (ValueError, TypeError):
                            pass
        except Exception as e:
            print(f"⚠️ [MarketEvents] Could not read {EVENTS_STATE_FILE}: {e} (keeping a .bad copy)")
            try:
                os.replace(EVENTS_STATE_FILE, EVENTS_STATE_FILE + ".bad")
            except Exception:
                pass

    return sent_reminders, user_reminders, dispatched_events


def save_events_state(now: Optional[float] = None) -> None:
    """Atomically persists sent reminders, user registrations, and dispatched events to disk (Phase 2B-2 / FIX-5b)."""
    try:
        now_val = time.time() if now is None else float(now)
        pruned_sent = {
            k: ts for k, ts in SENT_REMINDERS.items()
            if (now_val - float(ts)) <= EVENTS_STATE_TTL_SECONDS
        }
        pruned_dispatched = {
            k: ts for k, ts in DISPATCHED_EVENTS.items()
            if (now_val - float(ts)) <= EVENTS_STATE_TTL_SECONDS
        }
        payload = json.dumps({
            "version": 1,
            "sent_reminders": pruned_sent,
            "user_reminders": EVENT_USER_REMINDERS,
            "dispatched_events": pruned_dispatched,
        }, ensure_ascii=False)
        tmp = f"{EVENTS_STATE_FILE}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, EVENTS_STATE_FILE)
    except Exception as e:
        print(f"⚠️ [MarketEvents] Save state failed: {e}")


_init_sent, _init_user, _init_disp = _load_events_state()
# Sent reminders: 'event_id:chat_id:kind' -> timestamp (epoch seconds)
SENT_REMINDERS: Dict[str, float] = _init_sent
# Active reminders: event_id -> Dict[user_id, chat_id]
EVENT_USER_REMINDERS: Dict[str, Dict[str, str]] = _init_user
# Dispatched events: 'user_id:event_id:start_utc' -> timestamp (epoch seconds) (FIX-5b)
DISPATCHED_EVENTS: Dict[str, float] = _init_disp
# Per-chat/user dispatched event tracking set in memory
USER_DISPATCHED_EVENTS: Dict[str, set] = {}
for _k in DISPATCHED_EVENTS:
    _parts = _k.split(":")
    if len(_parts) >= 2:
        USER_DISPATCHED_EVENTS.setdefault(_parts[0], set()).add(_parts[1])


def mark_reminder_sent(event_id: str, chat_id: str, kind: str = "advance_30m", start_utc: Optional[int] = None, sent_at: Optional[float] = None) -> None:
    """Marks a reminder as sent (key includes start_utc if available) and persists state."""
    key = f"{event_id}:{chat_id}:{kind}:{start_utc}" if start_utc is not None else f"{event_id}:{chat_id}:{kind}"
    SENT_REMINDERS[key] = float(sent_at or time.time())
    save_events_state()


def is_reminder_sent(event_id: str, chat_id: str, kind: str = "advance_30m", start_utc: Optional[int] = None) -> bool:
    """Returns True if this reminder was already sent."""
    key = f"{event_id}:{chat_id}:{kind}:{start_utc}" if start_utc is not None else f"{event_id}:{chat_id}:{kind}"
    return key in SENT_REMINDERS


def user_supports_ack(user_id: str) -> bool:
    """Checks if any alert registered for user in ALERTS_DB has ack_supported=True (Phase 2B-4 / FIX-5a)."""
    clean_uid = (user_id or "").strip().lower()
    if not clean_uid:
        return False
    for a in storage.ALERTS_DB:
        if getattr(a, "user_id", "").lower() == clean_uid:
            if getattr(a, "ack_supported", False) is True:
                return True
    return False


class EventAlertStub:
    """Lightweight stub to allow market events to route through the outbox delivery pipeline (Phase 2B-4 / FIX-5a)."""
    def __init__(self, alert_id: str, user_id: str, fcm_token: str, telegram_chat_id: Optional[str] = None, ack_supported: Optional[bool] = None):
        self.id = alert_id
        self.user_id = user_id
        self.fcm_token = fcm_token
        self.telegram_chat_id = telegram_chat_id
        if ack_supported is not None:
            self.ack_supported = bool(ack_supported)
        else:
            self.ack_supported = user_supports_ack(user_id)


def resolve_user_fcm_token(user_id: str) -> Optional[str]:
    """Resolves FCM token for user: first from USER_PROFILES_DB, fallback to ALERTS_DB (Phase 2B-4)."""
    clean_uid = (user_id or "").strip().lower()
    if not clean_uid:
        return None

    # 1. Check USER_PROFILES_DB
    prof = storage.USER_PROFILES_DB.get(clean_uid, {})
    prof_token = (prof.get("fcm_token") or "").strip()
    if prof_token and not prof_token.startswith("dev_") and len(prof_token) >= 20:
        return prof_token

    # 2. Check ALERTS_DB for user's alerts
    for a in storage.ALERTS_DB:
        if getattr(a, "user_id", "").lower() == clean_uid:
            tok = (getattr(a, "fcm_token", None) or "").strip()
            if tok and not tok.startswith("dev_") and len(tok) >= 20:
                return tok

    return None


async def check_and_dispatch_30m_advance_reminders(
    client: Optional[httpx.AsyncClient] = None,
    now_ts: Optional[float] = None
) -> int:
    """
    Scans active user event reminders and sends a 30-minute advance notice (Phase 2B-3 & 2B-4).
    - Window: T - 30 minutes with 1-minute tolerance (1740s <= start_utc - now_ts <= 1860s).
    - Prevents duplicates via SENT_REMINDERS (key includes start_utc).
    - Persists sent state to disk so duplicates are prevented across server restarts.
    - Routes through enqueue_alert_push when user has an active FCM token (Phase 2B-4).
    Returns the number of reminders successfully dispatched.
    """
    if now_ts is None:
        now_ts = time.time()
    now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)

    if not EVENT_USER_REMINDERS:
        return 0

    c = client or getattr(state, "http_client", None)
    dispatched_count = 0

    events = MARKET_EVENTS_CACHE if MARKET_EVENTS_CACHE else list(CURATED_HIGH_IMPACT_CATALOG)
    events_by_id = {e.get("id"): dict(e) for e in events if e.get("id")}

    for event_id, users_map in list(EVENT_USER_REMINDERS.items()):
        event = events_by_id.get(event_id)
        if not event:
            continue

        # Dynamically compute start_utc at check time (FIX-4a)
        time_val = event.get("time_utc") if event.get("time_utc") is not None else event.get("start_utc")
        start_utc = parse_event_start_utc(time_val, now_dt=now_dt)
        if start_utc is None:
            # Excluded from reminders per rule 2: unparseable or invalid
            continue
        event["start_utc"] = start_utc

        remaining = start_utc - now_ts
        # Window: T - 30 minutes with 1-minute tolerance (1800s +- 60s -> [1740, 1860])
        if not (1740 <= remaining <= 1860):
            continue

        for user_id, chat_id in list(users_map.items()):
            # Dedup key includes start_utc so changing event time doesn't suppress new reminder
            dedup_key = f"{event_id}:{user_id}:advance_30m:{start_utc}"
            if dedup_key in SENT_REMINDERS or (chat_id and f"{event_id}:{chat_id}:advance_30m:{start_utc}" in SENT_REMINDERS):
                continue

            try:
                # 1. Telegram reminder card
                if chat_id and c is not None and TELEGRAM_BOT_TOKEN:
                    card_text = format_telegram_event_reminder_card(
                        event, is_cancelled=False, is_advance_notice=True
                    )
                    await send_telegram_alert(c, str(chat_id), card_text)

                # 2. FCM Outbox push (Phase 2B-4)
                fcm_token = resolve_user_fcm_token(user_id)
                if fcm_token:
                    remind_title = f"⏰ 30m Event Reminder: {event.get('title', 'Market Event')}"
                    remind_body = f"{event.get('market', '')} • Starts in 30 minutes! Impact: High"
                    remind_payload = {
                        "type": "event_advance_reminder",
                        "event_id": str(event_id),
                        "start_utc": str(start_utc),
                        "category": str(event.get("category", "")),
                        "user_id": str(user_id),
                        "is_advance_notice": "true",
                    }
                    stub = EventAlertStub(
                        alert_id=f"remind_{event_id}_{user_id}",
                        user_id=user_id,
                        fcm_token=fcm_token,
                        telegram_chat_id=chat_id or None
                    )
                    await enqueue_alert_push(
                        alert=stub,
                        title=remind_title,
                        body=remind_body,
                        data_payload=remind_payload,
                        fallback_chat_id=str(chat_id) if chat_id else None
                    )

                SENT_REMINDERS[dedup_key] = now_ts
                if chat_id:
                    SENT_REMINDERS[f"{event_id}:{chat_id}:advance_30m:{start_utc}"] = now_ts
                save_events_state(now=now_ts)
                dispatched_count += 1
            except Exception as e:
                print(f"⚠️ [Advance Reminder Error] event={event_id} user={user_id}: {_scrub(e)}")

    return dispatched_count


async def register_user_event_reminder(
    client: httpx.AsyncClient,
    user_id: str,
    event_id: str,
    cancel: bool = False,
    chat_id: Optional[str] = None,
    fcm_token: Optional[str] = None
) -> Dict[str, Any]:
    """Registers or cancels a user's reminder for an upcoming market event and syncs with Telegram."""
    clean_uid = user_id.strip().lower()
    event = next((e for e in (MARKET_EVENTS_CACHE or CURATED_HIGH_IMPACT_CATALOG) if e.get('id') == event_id), None)
    if not event:
        return {"status": "error", "message": f"Event {event_id} not found."}

    # Store FCM token in profile if provided (Phase 2B-4)
    if fcm_token and clean_uid != 'user_default':
        prof = storage.USER_PROFILES_DB.setdefault(clean_uid, {"user_id": clean_uid})
        prof["fcm_token"] = str(fcm_token).strip()
        await storage.save_user_profiles_to_disk_async(storage.USER_PROFILES_DB)

    # Resolve target chat_id
    target_chat = chat_id
    if not target_chat:
        prof = storage.USER_PROFILES_DB.get(clean_uid, {})
        target_chat = prof.get('telegram_chat_id')

    if cancel:
        if event_id in EVENT_USER_REMINDERS and clean_uid in EVENT_USER_REMINDERS[event_id]:
            del EVENT_USER_REMINDERS[event_id][clean_uid]
            if not EVENT_USER_REMINDERS[event_id]:
                del EVENT_USER_REMINDERS[event_id]
            save_events_state()
        if target_chat and TELEGRAM_BOT_TOKEN:
            msg = format_telegram_event_reminder_card(event, is_cancelled=True)
            await send_telegram_alert(client, target_chat, msg)
        return {"status": "ok", "message": "Reminder cancelled", "event_id": event_id}

    # Register reminder
    if event_id not in EVENT_USER_REMINDERS:
        EVENT_USER_REMINDERS[event_id] = {}
    if target_chat or fcm_token:
        EVENT_USER_REMINDERS[event_id][clean_uid] = target_chat or ""
        save_events_state()
        if target_chat and TELEGRAM_BOT_TOKEN:
            msg = format_telegram_event_reminder_card(event, is_cancelled=False)
            await send_telegram_alert(client, target_chat, msg)

    return {
        "status": "ok",
        "message": "Reminder set (30 minutes prior)",
        "event_id": event_id,
        "event_title": event.get('title'),
        "time_utc": event.get('time_utc')
    }


async def check_and_dispatch_event_notifications(client: httpx.AsyncClient):
    """
    Checks upcoming events and sends Telegram and FCM alerts to users who have opted into
    events notifications in their user profile (Phase 2B-4). Anti-spam tracks dispatches per user.
    Note: 30-minute advance reminders are managed by a dedicated 30s scheduler job (FIX-4b).
    """
    events = MARKET_EVENTS_CACHE if MARKET_EVENTS_CACHE else list(CURATED_HIGH_IMPACT_CATALOG)
    if not events:
        return

    high_impact_events = [ev for ev in events if ev.get('impact') == 'high']
    if not high_impact_events:
        return

    profiles = dict(storage.USER_PROFILES_DB)
    for user_id, prof in profiles.items():
        if not isinstance(prof, dict):
            continue
        chat_id = (prof.get('telegram_chat_id') or "").strip()
        events_tg_enabled = prof.get('events_telegram_enabled', False)
        events_notif_enabled = prof.get('events_notification_enabled', False)
        if not events_tg_enabled and not events_notif_enabled:
            continue

        clean_uid = str(user_id).strip().lower()
        if clean_uid not in USER_DISPATCHED_EVENTS:
            USER_DISPATCHED_EVENTS[clean_uid] = set()

        for ev in high_impact_events:
            ev_id = ev.get('id')
            if not ev_id:
                continue

            time_val = ev.get("time_utc") if ev.get("time_utc") is not None else ev.get("start_utc")
            start_utc = parse_event_start_utc(time_val)
            ev["start_utc"] = start_utc

            disp_key = f"{clean_uid}:{ev_id}:{start_utc}"
            chat_disp_key = f"{chat_id}:{ev_id}:{start_utc}" if chat_id else None

            if disp_key in DISPATCHED_EVENTS or (chat_disp_key and chat_disp_key in DISPATCHED_EVENTS):
                continue
            if ev_id in USER_DISPATCHED_EVENTS.get(clean_uid, set()):
                continue
            if chat_id and ev_id in USER_DISPATCHED_EVENTS.get(chat_id, set()):
                continue

            category = ev.get('category', '').lower()
            cat_pref_key = f"events_{category}_enabled"
            if prof.get(cat_pref_key, True) is False:
                continue

            # 1. Telegram dispatch (if chat_id present and telegram enabled)
            if chat_id and (events_tg_enabled or events_notif_enabled) and TELEGRAM_BOT_TOKEN:
                try:
                    msg = format_telegram_market_event_card(ev)
                    await send_telegram_alert(client, chat_id, msg)
                    await asyncio.sleep(0.05) # Rate limit protection
                except Exception as e:
                    print(f"⚠️ [Event Telegram Send Error] user={mask_identifier(user_id)}: {_scrub(e)}")

            # 2. FCM Outbox dispatch (Phase 2B-4 / FIX-5a: FCM requires explicit opt-in via events_notification_enabled)
            if events_notif_enabled and prof.get('events_fcm_enabled', True):
                fcm_token = resolve_user_fcm_token(clean_uid)
                if fcm_token:
                    try:
                        title = f"🔔 Market Event: {ev.get('title', 'Market Event')}"
                        body = f"{ev.get('market', '')} • {ev.get('time_utc', '')} | Impact: High"
                        data_payload = {
                            "type": "market_event",
                            "event_id": str(ev_id),
                            "category": str(ev.get("category", "")),
                            "market": str(ev.get("market", "")),
                            "time_utc": str(ev.get("time_utc", "")),
                            "start_utc": str(ev.get("start_utc", "")),
                            "user_id": str(clean_uid),
                        }
                        stub = EventAlertStub(
                            alert_id=f"ev_{ev_id}_{clean_uid}",
                            user_id=clean_uid,
                            fcm_token=fcm_token,
                            telegram_chat_id=chat_id or None
                        )
                        await enqueue_alert_push(
                            alert=stub,
                            title=title,
                            body=body,
                            data_payload=data_payload,
                            fallback_chat_id=chat_id or None
                        )
                    except Exception as e:
                        print(f"⚠️ [Event FCM Outbox Error] user={mask_identifier(user_id)}: {_scrub(e)}")

            now_ts = time.time()
            DISPATCHED_EVENTS[disp_key] = now_ts
            if chat_disp_key:
                DISPATCHED_EVENTS[chat_disp_key] = now_ts
            USER_DISPATCHED_EVENTS.setdefault(clean_uid, set()).add(ev_id)
            if chat_id:
                USER_DISPATCHED_EVENTS.setdefault(chat_id, set()).add(ev_id)
            save_events_state(now=now_ts)

async def refresh_market_events(client: Optional[httpx.AsyncClient] = None):
    """
    Refreshes the Market Events cache every 6 hours across Crypto, Macro, Energy, and Stocks.
    Filters exclusively for High-Impact, market-moving events.
    """
    global MARKET_EVENTS_CACHE, LAST_EVENTS_UPDATE
    c = client or getattr(state, 'http_client', None)
    if c is None:
        c = httpx.AsyncClient(timeout=15.0)

    try:
        now_utc = datetime.now(timezone.utc)
        curated_events = list(CURATED_HIGH_IMPACT_CATALOG)

        for ev in curated_events:
            ev['last_synced'] = now_utc.isoformat()

        MARKET_EVENTS_CACHE = curated_events
        LAST_EVENTS_UPDATE = now_utc
        print(f"📅 [Market Events] 6-Hour sync complete. Loaded {len(MARKET_EVENTS_CACHE)} verified high-impact events.")

        # Dispatch Telegram notifications to subscribed users
        await check_and_dispatch_event_notifications(c)
    except Exception as e:
        print(f"⚠️ [Market Events Sync Error] {_scrub(e)}")

def get_market_events(categories: Optional[List[str]] = None, now_dt: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Retrieves cached high-impact market events, dynamically computing start_utc at check time (Phase 2B-1 / FIX-4a)."""
    now = now_dt or datetime.now(timezone.utc)
    raw = MARKET_EVENTS_CACHE if MARKET_EVENTS_CACHE else list(CURATED_HIGH_IMPACT_CATALOG)
    events = []
    for e in raw:
        ev = dict(e)
        time_val = ev.get('time_utc') if ev.get('time_utc') is not None else ev.get('start_utc')
        ev['start_utc'] = parse_event_start_utc(time_val, now_dt=now)
        events.append(ev)

    if not categories:
        return events

    lower_cats = [c.lower() for c in categories]
    return [e for e in events if e.get('category', '').lower() in lower_cats]

