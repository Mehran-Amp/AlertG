import time
import asyncio
from typing import Optional, Dict, Tuple, List, Any
try:
    import httpx
except ImportError:
    httpx = None

http_client = None

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler()
except ImportError:
    from datetime import timedelta
    class _MockTrigger:
        def __init__(self, seconds=0, desc=""):
            self.interval = timedelta(seconds=seconds)
            self.desc = desc
        def __str__(self):
            return self.desc or f"interval[{self.interval}]"
    class _MockJob:
        def __init__(self, id, func=None, seconds=0, desc=""):
            self.id = id
            self.func = func
            self.trigger = _MockTrigger(seconds, desc=desc)
    class _MockScheduler:
        def __init__(self):
            self.jobs = {}
        def add_job(self, func, trigger='interval', id=None, seconds=None, hours=None, day_of_week=None, hour=None, **kwargs):
            sec = seconds if seconds is not None else ((hours * 3600) if hours is not None else 0)
            desc = f"cron[day_of_week={day_of_week}, hour={hour}]" if trigger == 'cron' else f"interval[{sec}s]"
            job = _MockJob(id, func=func, seconds=sec, desc=desc)
            self.jobs[id] = job
            return job
        def get_job(self, job_id):
            return self.jobs.get(job_id)
        def start(self): pass
        def shutdown(self): pass
    AsyncIOScheduler = _MockScheduler
    scheduler = _MockScheduler()
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
