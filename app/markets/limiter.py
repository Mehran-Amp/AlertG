import time
import asyncio
from typing import Dict, Optional, Any
from app.state import METRICS

class TokenBucketRateLimiter:
    """
    Thread-safe and async-safe Token Bucket Rate Limiter per provider.
    Allows bursts up to capacity while enforcing steady rate per second.
    """
    def __init__(self, rate_per_second: float, capacity: float):
        self.rate = rate_per_second
        self.capacity = capacity
        self.tokens = capacity
        self.last_updated = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0, wait: bool = True) -> bool:
        async with self._lock:
            now = time.time()
            elapsed = max(0.0, now - self.last_updated)
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_updated = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True

            if not wait:
                return False

            # Calculate wait duration
            needed = tokens - self.tokens
            wait_time = needed / self.rate

        # Sleep outside the lock so other tasks aren't completely blocked
        await asyncio.sleep(wait_time)

        async with self._lock:
            now = time.time()
            elapsed = max(0.0, now - self.last_updated)
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_updated = now
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            self.tokens = 0.0
            return True

# Provider-specific Token Bucket limiters:
# - yahoo: 10 req/s, capacity 20 (strict protection against German IP rate limits / 429)
# - nobitex: 15 req/s, capacity 25
# - iran_bridge: 10 req/s, capacity 15
# - bonbast: 3 req/s, capacity 6
# - binance: 25 req/s, capacity 40
# - kucoin/mexc/gateio: 20 req/s, capacity 30
# - default: 20 req/s, capacity 30
PROVIDER_LIMITERS: Dict[str, TokenBucketRateLimiter] = {
    'yahoo': TokenBucketRateLimiter(rate_per_second=10.0, capacity=20.0),
    'finnhub': TokenBucketRateLimiter(rate_per_second=5.0, capacity=10.0),
    'twelvedata': TokenBucketRateLimiter(rate_per_second=2.0, capacity=5.0),
    'fred': TokenBucketRateLimiter(rate_per_second=5.0, capacity=10.0),
    'nobitex': TokenBucketRateLimiter(rate_per_second=15.0, capacity=25.0),
    'iran_bridge': TokenBucketRateLimiter(rate_per_second=10.0, capacity=15.0),
    'bonbast': TokenBucketRateLimiter(rate_per_second=3.0, capacity=6.0),
    'binance': TokenBucketRateLimiter(rate_per_second=25.0, capacity=40.0),
    'crypto_global': TokenBucketRateLimiter(rate_per_second=20.0, capacity=30.0),
    'default': TokenBucketRateLimiter(rate_per_second=20.0, capacity=30.0),
}

# Provider quota limits (requests per day or window, based on plan tiers):
# - twelvedata: 800 req/day (free tier)
# - finnhub: 60 req/min (3,600 req/hr, ~86,400/day)
# - fred: 120 req/min (7,200 req/hr)
# - yahoo: 2,000 req/hr soft limit
# - nobitex: 5,000 req/hr soft limit
# - bonbast: 500 req/hr soft limit
# - binance: 1,200 req/min weight limit
# - iran_bridge: 1,000 req/hr soft limit
PROVIDER_QUOTAS: Dict[str, Dict[str, Any]] = {
    'twelvedata': {'limit': 800, 'window': 'daily', 'name': 'Twelve Data'},
    'finnhub': {'limit': 86400, 'window': 'daily', 'name': 'Finnhub'},
    'fred': {'limit': 7200, 'window': 'daily', 'name': 'FRED Economic Data'},
    'yahoo': {'limit': 50000, 'window': 'daily', 'name': 'Yahoo Finance'},
    'nobitex': {'limit': 20000, 'window': 'daily', 'name': 'Nobitex'},
    'iran_bridge': {'limit': 15000, 'window': 'daily', 'name': 'Iran Bridge (Aegkala)'},
    'bonbast': {'limit': 2000, 'window': 'daily', 'name': 'Bonbast'},
    'binance': {'limit': 100000, 'window': 'daily', 'name': 'Binance Spot'},
    'crypto_global': {'limit': 50000, 'window': 'daily', 'name': 'Global Crypto & DEX'},
    'default': {'limit': 20000, 'window': 'daily', 'name': 'Default Gateway'},
}

# Track whether >80% quota alert was already dispatched to admin to avoid spam
_QUOTA_ALERTED_PROVIDERS = set()
_OUTAGE_ALERTED_PROVIDERS = set()

def record_provider_metric(provider_key: str, event_type: str, status_code: Optional[int] = None):
    """
    Records provider metrics: requests, errors, 429 rate limits, and checks 80% quota threshold.
    event_type: 'requests', 'errors', 'rate_limits_429', 'success'
    """
    prov_metrics = METRICS.setdefault("providers", {})
    p_data = prov_metrics.setdefault(provider_key, {
        "requests": 0,
        "success": 0,
        "errors": 0,
        "rate_limits_429": 0,
        "last_status_code": 200,
        "last_event_at": time.time(),
        "health": "HEALTHY"
    })

    p_data["last_event_at"] = time.time()
    if status_code is not None:
        p_data["last_status_code"] = status_code

    if event_type in p_data:
        p_data[event_type] += 1

    # Check health status
    total_reqs = p_data.get("requests", 0)
    errors = p_data.get("errors", 0)
    rate_limits = p_data.get("rate_limits_429", 0)

    quota_info = PROVIDER_QUOTAS.get(provider_key)
    prov_display_name = quota_info.get("name", provider_key) if quota_info else provider_key

    if rate_limits > 5 or (errors > 5 and errors / max(1, total_reqs) > 0.4):
        p_data["health"] = "OUTAGE_OR_BLOCKED"
        if provider_key not in _OUTAGE_ALERTED_PROVIDERS:
            _OUTAGE_ALERTED_PROVIDERS.add(provider_key)
            msg = (
                f"🚨 <b>[هشدار ادمین - قطعی سرویس‌دهنده]</b>\n"
                f"📡 سرویس‌دهنده: <b>{prov_display_name}</b>\n"
                f"⚠️ وضعیت: <b>OUTAGE_OR_BLOCKED (قطع / مسدود)</b>\n"
                f"📊 خطاها: {errors} خطا از {total_reqs} درخواست ({rate_limits} بار ۴۲۹)\n"
                f"⏱️ لطفاً اتصالات شبکه یا کلیدهای دسترسی این سرویس را بررسی فرمایید."
            )
            from app.notifier.telegram import notify_admin_telegram
            from app.notifier.outbox import _spawn
            _spawn(notify_admin_telegram(msg))
    elif errors > 2 or rate_limits > 0:
        p_data["health"] = "DEGRADED"
    else:
        p_data["health"] = "HEALTHY"
        _OUTAGE_ALERTED_PROVIDERS.discard(provider_key)

    # Check 80% quota ceiling
    if quota_info:
        limit = quota_info.get("limit", 1000)
        usage_ratio = total_reqs / max(1, limit)
        p_data["quota_limit"] = limit
        p_data["quota_used"] = total_reqs
        p_data["quota_percentage"] = round(usage_ratio * 100, 1)

        if usage_ratio >= 0.80 and provider_key not in _QUOTA_ALERTED_PROVIDERS:
            _QUOTA_ALERTED_PROVIDERS.add(provider_key)
            msg = (
                f"⚠️ <b>[هشدار ادمین - سهمیه بالای ۸۰٪]</b>\n"
                f"📡 سرویس‌دهنده: <b>{prov_display_name}</b>\n"
                f"📊 مصرف سهمیه: {total_reqs:,} / {limit:,} ({round(usage_ratio * 100, 1)}%)\n"
                f"⏱️ لطفاً سهمیه یا پلن API را بازبینی فرمایید."
            )
            from app.notifier.telegram import notify_admin_telegram
            from app.notifier.outbox import _spawn
            _spawn(notify_admin_telegram(msg))

def get_all_providers_status() -> Dict[str, Any]:
    """Returns aggregated health and quota usage for all configured providers."""
    from app.markets.kill_switch import is_provider_killed
    prov_metrics = METRICS.setdefault("providers", {})
    statuses = {}
    for p_key, q_info in PROVIDER_QUOTAS.items():
        curr = prov_metrics.get(p_key, {
            "requests": 0, "success": 0, "errors": 0, "rate_limits_429": 0, "health": "HEALTHY"
        })
        limit = q_info["limit"]
        reqs = curr.get("requests", 0)
        pct = round((reqs / max(1, limit)) * 100, 1)
        killed = is_provider_killed(p_key)
        health = "KILLED" if killed else curr.get("health", "HEALTHY")

        statuses[p_key] = {
            "name": q_info["name"],
            "health": health,
            "is_killed": killed,
            "requests": reqs,
            "success": curr.get("success", 0),
            "errors": curr.get("errors", 0),
            "rate_limits_429": curr.get("rate_limits_429", 0),
            "quota_limit": limit,
            "quota_used": reqs,
            "quota_percentage": pct,
            "quota_warning": pct >= 80.0
        }
    return statuses

async def acquire_provider_slot(provider_key: str, wait: bool = True) -> bool:
    from app.markets.kill_switch import is_provider_killed
    if is_provider_killed(provider_key):
        return False
    limiter = PROVIDER_LIMITERS.get(provider_key) or PROVIDER_LIMITERS['default']
    record_provider_metric(provider_key, "requests")
    return await limiter.acquire(1.0, wait=wait)
