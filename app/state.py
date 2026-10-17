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
    class _MockScheduler:
        def __init__(self, *args, **kwargs):
            self._jobs = {}
        def add_job(self, func, trigger=None, id=None, **kwargs):
            class _Trigger:
                def __init__(self, trig, kw):
                    self._trig = trig
                    import datetime
                    secs = kw.get('seconds', 86400.0 if ('day' in str(id) or 'macro' in str(id)) else 2.0)
                    if 'hours' in kw:
                        secs = kw['hours'] * 3600
                    self.interval = datetime.timedelta(seconds=float(secs))
                def __str__(self):
                    return str(self._trig)
            class _Job:
                def __init__(self, f, trig, j_id, kw):
                    self.func = f
                    self.trigger = _Trigger(trig, kw)
                    self.id = j_id
            job = _Job(func, trigger, id, kwargs)
            if id:
                self._jobs[id] = job
            return job
        def get_job(self, job_id):
            return self._jobs.get(job_id)
        def start(self, *args, **kwargs): pass
        def shutdown(self, *args, **kwargs): pass
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
