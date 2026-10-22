from typing import List, Optional
from fastapi import APIRouter, Query
from app.security import API_DEP
from app.engine.market_events import get_market_events, LAST_EVENTS_UPDATE

router = APIRouter()

@router.get("/api/market-events", dependencies=API_DEP)
@router.get("/market-events", dependencies=API_DEP)
def fetch_market_events(
    category: Optional[List[str]] = Query(None, description="Optional category filters (crypto, macro, energy, stocks)")
):
    """
    Returns curated high-impact market events (Crypto, Forex/Macro, Energy, Mega-Cap Stocks)
    refreshed every 6 hours with noise filtering.
    """
    events = get_market_events(categories=category)
    return {
        "status": "ok",
        "last_updated": LAST_EVENTS_UPDATE.isoformat() if LAST_EVENTS_UPDATE else None,
        "total": len(events),
        "events": events
    }

@router.post("/api/market-events/remind", dependencies=API_DEP)
@router.post("/market-events/remind", dependencies=API_DEP)
async def set_event_reminder(payload: dict):
    """
    Registers a 30-minute advance notification reminder for a specific market event.
    Dispatches a real Telegram confirmation if user has connected their Telegram account.
    """
    from app.engine.market_events import register_user_event_reminder
    import app.state as state
    import httpx

    user_id = str(payload.get('user_id') or 'user_default').strip()
    event_id = str(payload.get('event_id') or '').strip()
    cancel = bool(payload.get('cancel', False))
    chat_id = payload.get('chat_id')
    fcm_token = payload.get('fcm_token')

    if not event_id:
        return {"status": "error", "message": "event_id is required"}

    client = state.http_client
    if client is None:
        client = httpx.AsyncClient(timeout=10.0)

    res = await register_user_event_reminder(
        client=client,
        user_id=user_id,
        event_id=event_id,
        cancel=cancel,
        chat_id=chat_id,
        fcm_token=fcm_token
    )
    return res

