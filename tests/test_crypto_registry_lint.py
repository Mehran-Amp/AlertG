#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — Acceptance Lint Tests for Phase 2 (Crypto Registry & LBank).
Verifies:
1. All exchange IDs match config.EXCHANGE_RE regex.
2. All exchange IDs are strictly lowercase and unique.
3. All required metadata fields are non-empty and well-formed.
4. LBank is officially registered with category='asia' and status='active'.
5. CoinEx is maintained with status='closing'.
6. Every provider_key has an entry in PROVIDER_LIMITERS and PROVIDER_QUOTAS.
7. Notifier get_exchange_display_name returns clean names for all exchanges.
8. Regression Guard: Stock and Forex alert display names are 100% byte-for-byte identical.
"""

import unittest
import sys
from unittest.mock import MagicMock

# Mock optional dependencies for test runners
try:
    import httpx
except ImportError:
    httpx = MagicMock()
    sys.modules['httpx'] = httpx

try:
    import apscheduler
except ImportError:
    apscheduler = MagicMock()
    sys.modules['apscheduler'] = apscheduler
    sys.modules['apscheduler.schedulers'] = apscheduler
    sys.modules['apscheduler.schedulers.asyncio'] = apscheduler

try:
    import pydantic
except ImportError:
    pydantic = MagicMock()
    class BaseModel: pass
    pydantic.BaseModel = BaseModel
    sys.modules['pydantic'] = pydantic

try:
    import fastapi
except ImportError:
    import types
    fastapi = types.ModuleType('fastapi')
    fastapi.__path__ = []
    class APIRouter:
        def get(self, *a, **kw): return lambda fn: fn
        def post(self, *a, **kw): return lambda fn: fn
        def delete(self, *a, **kw): return lambda fn: fn
        def put(self, *a, **kw): return lambda fn: fn
        def patch(self, *a, **kw): return lambda fn: fn
        def include_router(self, *a, **kw): pass
    class Response:
        def __init__(self, content=b"", status_code=200, headers=None, media_type=None, **kwargs):
            self.content = content if isinstance(content, bytes) else str(content).encode("utf-8")
            self.status_code = status_code
            self.headers = headers or {}
    class Request: pass
    class HTTPException(Exception):
        def __init__(self, status_code=500, detail="", **kwargs):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail
    fastapi.APIRouter = APIRouter
    fastapi.HTTPException = HTTPException
    fastapi.Response = Response
    fastapi.Request = Request
    fastapi.Header = MagicMock()
    fastapi.Depends = MagicMock()
    fastapi.Query = lambda default=None, **kw: default
    sys.modules['fastapi'] = fastapi

    resp_mod = types.ModuleType('fastapi.responses')
    class JSONResponse(Response):
        def __init__(self, content=None, status_code=200, headers=None, **kwargs):
            b = json.dumps(content).encode("utf-8") if isinstance(content, (dict, list)) else (content or b"")
            super().__init__(content=b, status_code=status_code, headers=headers or {})
    class HTMLResponse(Response): pass
    resp_mod.Response = Response
    resp_mod.JSONResponse = JSONResponse
    resp_mod.HTMLResponse = HTMLResponse
    fastapi.responses = resp_mod
    sys.modules['fastapi.responses'] = resp_mod

import app.config as config
from app.markets.crypto_registry import (
    _CRYPTO_EXCHANGES,
    get_crypto_exchange,
    list_crypto_exchanges,
    is_supported_crypto_exchange,
    get_crypto_provider_key
)
from app.markets.limiter import PROVIDER_LIMITERS, PROVIDER_QUOTAS
from app.notifier.telegram import get_exchange_display_name


class TestCryptoRegistryLint(unittest.TestCase):

    def test_01_all_exchange_ids_match_exchange_re(self):
        """Every registered exchange ID must strictly match config.EXCHANGE_RE."""
        self.assertGreater(len(_CRYPTO_EXCHANGES), 0, "Registry must not be empty")
        for ex_id, meta in _CRYPTO_EXCHANGES.items():
            self.assertTrue(
                bool(config.EXCHANGE_RE.match(ex_id)),
                f"Exchange ID '{ex_id}' does not match config.EXCHANGE_RE regex!"
            )
            self.assertEqual(ex_id, meta.id, "Dictionary key must match metadata id")

    def test_02_all_exchange_ids_are_lowercase_and_unique(self):
        """All exchange IDs must be lowercase and unique."""
        seen = set()
        for ex_id in _CRYPTO_EXCHANGES.keys():
            self.assertEqual(ex_id, ex_id.lower(), f"ID '{ex_id}' must be lowercase")
            self.assertNotIn(ex_id, seen, f"Duplicate exchange ID '{ex_id}' found!")
            seen.add(ex_id)

    def test_03_all_fields_populated_and_valid(self):
        """All metadata fields must be non-empty and point to valid HTTPS endpoints."""
        for ex_id, meta in _CRYPTO_EXCHANGES.items():
            self.assertTrue(meta.name and len(meta.name.strip()) > 0, f"{ex_id}: name missing")
            self.assertTrue(meta.category and len(meta.category.strip()) > 0, f"{ex_id}: category missing")
            self.assertTrue(meta.provider_key and len(meta.provider_key.strip()) > 0, f"{ex_id}: provider_key missing")
            self.assertTrue(meta.markets_url.startswith("https://"), f"{ex_id}: markets_url must be HTTPS")
            self.assertTrue(meta.bulk_ticker_url.startswith("https://"), f"{ex_id}: bulk_ticker_url must be HTTPS")
            self.assertIn(meta.status, ('active', 'closing', 'inactive'), f"{ex_id}: invalid status {meta.status}")

    def test_04_lbank_registered_as_active_in_asia_category(self):
        """LBank must be registered with category='asia' and status='active'."""
        lbank = get_crypto_exchange('lbank')
        self.assertIsNotNone(lbank, "LBank must be registered in crypto_registry")
        self.assertEqual(lbank.id, 'lbank')
        self.assertEqual(lbank.name, 'LBank')
        self.assertEqual(lbank.category, 'asia')
        self.assertEqual(lbank.status, 'active')
        self.assertEqual(lbank.provider_key, 'crypto_lbank')
        self.assertIn('lbank.info', lbank.markets_url)

    def test_05_coinex_registered_as_closing(self):
        """CoinEx must be registered with status='closing' for migration handling."""
        coinex = get_crypto_exchange('coinex')
        self.assertIsNotNone(coinex, "CoinEx must be in registry with closing status")
        self.assertEqual(coinex.status, 'closing')
        self.assertEqual(coinex.provider_key, 'crypto_coinex')

    def test_06_provider_keys_registered_in_limiters_and_quotas(self):
        """Every provider_key must have an isolated TokenBucket limiter and quota entry."""
        for ex_id, meta in _CRYPTO_EXCHANGES.items():
            pkey = meta.provider_key
            self.assertIn(
                pkey,
                PROVIDER_LIMITERS,
                f"Missing TokenBucketRateLimiter for provider_key '{pkey}' (exchange '{ex_id}')"
            )
            self.assertIn(
                pkey,
                PROVIDER_QUOTAS,
                f"Missing quota entry for provider_key '{pkey}' (exchange '{ex_id}')"
            )
            quota = PROVIDER_QUOTAS[pkey]
            self.assertGreater(quota['limit'], 0, f"Quota limit for {pkey} must be > 0")

    def test_07_notifier_display_names_registered(self):
        """All crypto exchanges must resolve cleanly in get_exchange_display_name."""
        expected = {
            'binance': 'Binance',
            'mexc': 'MEXC',
            'kucoin': 'KuCoin',
            'gateio': 'Gate.io',
            'lbank': 'LBank',
            'okx': 'OKX',
            'bybit': 'Bybit',
            'bitget': 'Bitget',
            'kraken': 'Kraken',
            'coinex': 'CoinEx',
        }
        for ex_id, expected_name in expected.items():
            resolved = get_exchange_display_name(ex_id)
            self.assertEqual(
                resolved,
                expected_name,
                f"Display name mismatch for {ex_id}: expected '{expected_name}', got '{resolved}'"
            )

    def test_08_stocks_and_iran_display_names_unaffected(self):
        """Regression Guard: Non-crypto display names must be 100% byte-for-byte identical."""
        self.assertEqual(get_exchange_display_name('nobitex'), 'Nobitex')
        self.assertEqual(get_exchange_display_name('wallex'), 'Wallex')
        self.assertEqual(get_exchange_display_name('stocks'), 'Stocks')
        self.assertEqual(get_exchange_display_name('global_stocks'), 'Global Stocks')
        self.assertEqual(get_exchange_display_name('forex'), 'Forex')
        self.assertEqual(get_exchange_display_name('deutsche börse'), 'Deutsche Börse')
        self.assertEqual(get_exchange_display_name('tokyo stock exchange'), 'Tokyo Stock Exchange')


if __name__ == '__main__':
    unittest.main()
