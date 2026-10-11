import time
import asyncio
from typing import Optional, Dict, Tuple, List, Any
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

http_client: Optional[httpx.AsyncClient] = None
scheduler = AsyncIOScheduler()
_db_lock = asyncio.Lock()
_prof_lock = asyncio.Lock()

# Price In-Memory Cache: key -> (price, timestamp)
PRICE_CACHE: Dict[str, Tuple[float, float]] = {}
CACHE_TTL_SECONDS = 2.0

# Diagnostic Log Ring Buffer (Max 100 entries)
RECENT_DIAGNOSTICS: List[Dict[str, Any]] = []

# Failing Symbols Tracker: key -> {symbol, exchange, error, failed_at, attempts}
FAILED_SYMBOLS: Dict[str, Dict[str, Any]] = {}

# Global Engine Metrics
METRICS: Dict[str, Any] = {
    "start_time": time.time(),
    "total_checks": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "total_triggers": 0,
    "fcm_success": 0,
    "fcm_failed": 0,
    "telegram_sent": 0,
    "webhook_sent": 0,
    "providers": {}
}

BULK_MARKET_RESPONSE_CACHE: Dict[str, Tuple[Any, float]] = {}
OUTLIER_STREAK: Dict[str, int] = {}
IRAN_MARKET_CACHE: Dict[str, Tuple[float, float, Dict[str, Any]]] = {}
