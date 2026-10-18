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
