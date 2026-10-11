import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import json
import time
import sys

# Mock server dependencies for offline test execution
for mod_name in [
    'fastapi', 'fastapi.middleware.cors', 'fastapi.responses',
    'httpx', 'pydantic',
    'apscheduler', 'apscheduler.schedulers', 'apscheduler.schedulers.asyncio',
    'firebase_admin', 'firebase_admin.credentials', 'firebase_admin.messaging', 'firebase_admin.exceptions'
]:
    if mod_name not in sys.modules:
        try:
            __import__(mod_name)
        except ImportError:
            m = MagicMock()
            if mod_name == 'fastapi':
                class HTTPException(Exception):
                    def __init__(self, status_code=400, detail=""):
                        super().__init__(detail)
                        self.status_code = status_code
                        self.detail = detail
                m.HTTPException = HTTPException
            elif mod_name == 'pydantic':
                class BaseModel:
                    def __init__(self, **kwargs):
                        for k, v in kwargs.items():
                            setattr(self, k, v)
                    def dict(self):
                        return self.__dict__
                    def model_dump(self):
                        return self.__dict__
                m.BaseModel = BaseModel
                m.Field = lambda *args, **kwargs: kwargs.get('default', None)
            sys.modules[mod_name] = m

import asyncio
from app.engine.limiter import TokenBucketRateLimiter, acquire_provider_slot, record_provider_metric
from app.engine.categories import (
    resolve_symbol_category, get_category_cache_ttl,
    get_category_outlier_threshold
)
from app.engine.checker import (
    PRICE_FETCH_CONCURRENCY, PRICE_FETCH_SEMAPHORE,
    get_cached_price, check_alerts_job
)
from app.state import METRICS, PRICE_CACHE, OUTLIER_STREAK

class TestPhase3StabilityEngine(unittest.IsolatedAsyncioTestCase):

    def test_01_category_cache_ttl_and_outliers(self):
        """Verify Category-based TTL and Outlier Threshold assignments"""
        # 1. Forex
        self.assertEqual(resolve_symbol_category('forex', 'EURUSD'), 'forex')
        self.assertEqual(resolve_symbol_category('global_stocks', 'EURUSD=X'), 'forex')
        self.assertEqual(get_category_cache_ttl('forex'), 20.0)
        self.assertEqual(get_category_outlier_threshold('forex'), 0.05)

        # 2. Stock / Index / Commodity
        self.assertEqual(resolve_symbol_category('global_stocks', 'AAPL'), 'stock')
        self.assertEqual(get_category_cache_ttl('stock'), 30.0)
        self.assertEqual(get_category_outlier_threshold('stock'), 0.25)

        self.assertEqual(resolve_symbol_category('global_stocks', '^GSPC'), 'index')
        self.assertEqual(get_category_cache_ttl('index'), 30.0)
        self.assertEqual(get_category_outlier_threshold('index'), 0.10)

        self.assertEqual(resolve_symbol_category('global_stocks', 'GC=F'), 'commodity')
        self.assertEqual(get_category_cache_ttl('commodity'), 30.0)
        self.assertEqual(get_category_outlier_threshold('commodity'), 0.15)

        # 3. Macro / Bonds
        self.assertEqual(resolve_symbol_category('global_stocks', 'DX-Y.NYB'), 'macro')
        self.assertEqual(get_category_cache_ttl('macro'), 60.0)
        self.assertEqual(get_category_outlier_threshold('macro'), 0.20)

        # 4. Crypto
        self.assertEqual(resolve_symbol_category('binance', 'BTCUSDT'), 'crypto')
        self.assertEqual(get_category_cache_ttl('crypto'), 2.0)
        self.assertEqual(get_category_outlier_threshold('crypto'), 0.50)

        # 5. Iran Market
        self.assertEqual(resolve_symbol_category('nobitex', 'USDTIRT'), 'iran_market')
        self.assertEqual(get_category_cache_ttl('iran_market'), 60.0)
        self.assertEqual(get_category_outlier_threshold('iran_market'), 0.50)

    async def test_02_token_bucket_rate_limiter(self):
        """Verify token bucket enforces rate and capacity smoothly"""
        limiter = TokenBucketRateLimiter(rate_per_second=10.0, capacity=2.0)
        # First 2 tokens should be available immediately
        self.assertTrue(await limiter.acquire(1.0, wait=False))
        self.assertTrue(await limiter.acquire(1.0, wait=False))
        # 3rd token immediately without wait returns False
        self.assertFalse(await limiter.acquire(1.0, wait=False))

    async def test_03_provider_metrics_counters(self):
        """Verify metrics counter increments for requests, errors, and 429s"""
        record_provider_metric('yahoo', 'requests')
        record_provider_metric('yahoo', 'rate_limits_429')
        record_provider_metric('yahoo', 'errors')

        prov = METRICS.get('providers', {}).get('yahoo', {})
        self.assertGreaterEqual(prov.get('requests', 0), 1)
        self.assertGreaterEqual(prov.get('rate_limits_429', 0), 1)
        self.assertGreaterEqual(prov.get('errors', 0), 1)

    async def test_04_concurrency_ceiling_load_test_500_pairs(self):
        """
        Load test with 500 mock pairs:
        Verifies semaphore strictly constrains concurrency so it never exceeds ceiling.
        """
        current_active = 0
        max_concurrent_seen = 0
        lock = asyncio.Lock()

        async def mock_fetch_price(*args, **kwargs):
            nonlocal current_active, max_concurrent_seen
            async with lock:
                current_active += 1
                if current_active > max_concurrent_seen:
                    max_concurrent_seen = current_active
            await asyncio.sleep(0.005)
            async with lock:
                current_active -= 1
            return (100.0, [{'success': True, 'parsed_price': 100.0}])

        with patch('app.engine.checker.fetch_price_with_trace', side_effect=mock_fetch_price):
            mock_client = AsyncMock()
            # Launch 500 concurrent price fetches
            tasks = [
                get_cached_price(mock_client, 'binance', f'PAIR_{i}USDT')
                for i in range(500)
            ]
            results = await asyncio.gather(*tasks)

        self.assertEqual(len(results), 500)
        # Crucial acceptance check: Concurrency must NEVER exceed PRICE_FETCH_CONCURRENCY ceiling
        self.assertLessEqual(max_concurrent_seen, PRICE_FETCH_CONCURRENCY)
        self.assertEqual(current_active, 0)

if __name__ == '__main__':
    unittest.main()
