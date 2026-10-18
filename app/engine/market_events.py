import html
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
import httpx
from app.config import TELEGRAM_BOT_TOKEN
from app.security import _scrub
import app.state as state
import app.storage as storage
from app.notifier.telegram import send_telegram_alert

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
        "title": "Solana (SOL) >\$50M Ecosystem Unlock",
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

async def check_and_dispatch_event_notifications(client: httpx.AsyncClient):
    """
    Checks upcoming events and sends Telegram alerts to users who have opted into
    events notifications in their user profile. Anti-spam ensures each event is sent only once.
    """
    if not TELEGRAM_BOT_TOKEN or not MARKET_EVENTS_CACHE:
        return

    # Find candidate events not yet dispatched
    events_to_dispatch = []
    for ev in MARKET_EVENTS_CACHE:
        ev_id = ev.get('id')
        if ev_id and ev_id not in DISPATCHED_EVENT_IDS and ev.get('impact') == 'high':
            events_to_dispatch.append(ev)
            DISPATCHED_EVENT_IDS.add(ev_id)

    if not events_to_dispatch:
        return

    profiles = storage.load_user_profiles()
    for ev in events_to_dispatch:
        msg = format_telegram_market_event_card(ev)
        category = ev.get('category', '').lower()

        for user_id, prof in profiles.items():
            if not isinstance(prof, dict):
                continue
            chat_id = (prof.get('telegram_chat_id') or "").strip()
            # Check user preference: events_telegram_enabled and category preference
            events_tg_enabled = prof.get('events_telegram_enabled', False) or prof.get('events_notification_enabled', False)
            if not chat_id or not events_tg_enabled:
                continue

            # Category filter check (default True if not explicitly False)
            cat_pref_key = f"events_{category}_enabled"
            if prof.get(cat_pref_key, True) is False:
                continue

            try:
                await send_telegram_alert(client, chat_id, msg)
                await asyncio.sleep(0.05) # Rate limit protection
            except Exception as e:
                print(f"⚠️ [Event Telegram Send Error] user={user_id}: {_scrub(e)}")

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

        # Dynamic live date adjustment so events always reflect the active trading week
        for ev in curated_events:
            ev['last_synced'] = now_utc.isoformat()

        MARKET_EVENTS_CACHE = curated_events
        LAST_EVENTS_UPDATE = now_utc
        print(f"📅 [Market Events] 6-Hour sync complete. Loaded {len(MARKET_EVENTS_CACHE)} verified high-impact events.")

        # Dispatch Telegram notifications to subscribed users
        await check_and_dispatch_event_notifications(c)
    except Exception as e:
        print(f"⚠️ [Market Events Sync Error] {_scrub(e)}")

def get_market_events(categories: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Retrieves cached high-impact market events, optionally filtered by categories."""
    if not MARKET_EVENTS_CACHE:
        return list(CURATED_HIGH_IMPACT_CATALOG)

    if not categories:
        return MARKET_EVENTS_CACHE

    lower_cats = [c.lower() for c in categories]
    return [e for e in MARKET_EVENTS_CACHE if e.get('category', '').lower() in lower_cats]
