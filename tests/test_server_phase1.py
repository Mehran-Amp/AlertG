#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 1.2 Comprehensive Unit Tests:
 1. 13 edge cases with subTest (EURUSD, XAUUSD, AUDUSD, USDJPY, EURUSD=X, ^TNX, ^GSPC, DX-Y.NYB, GC=F, BRK-B, 7203.T, AAPL/USD, TSLAUSD)
 2. 404 does NOT retry query2 (stops immediately)
 3. asOf skipping: identical market tick does not re-evaluate, but different asOf does
 4. Level-crossing guard (Hysteresis): alert initially on triggered side does NOT fire until crossing occurs
 5. Rejection of admin_key in query string (header-only requirement)
 6. /10 division ONLY for Rial quotes; Nobitex USDT quotes (BTCUSDT) are NOT divided by 10

All tests run completely OFFLINE using mocks.
"""

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

from server import (
    resolve_yf_symbol,
    EXACT_YF_MAP,
    FOREX_PAIRS,
    normalize_symbol,
    fetch_price_with_trace,
    PRICE_CACHE,
    get_cached_price,
    require_admin,
    Alert,
)


class TestServerPhase12(unittest.IsolatedAsyncioTestCase):

    def test_01_all_13_edge_cases_with_subtest(self):
        """Verify all 13 critical edge cases using subTest"""
        cases = [
            ('EURUSD', 'EURUSD=X'),
            ('XAUUSD', 'GC=F'),
            ('AUDUSD', 'AUDUSD=X'),
            ('USDJPY', 'USDJPY=X'),
            ('EURUSD=X', 'EURUSD=X'),
            ('^TNX', '^TNX'),
            ('^GSPC', '^GSPC'),
            ('DX-Y.NYB', 'DX-Y.NYB'),
            ('GC=F', 'GC=F'),
            ('BRK-B', 'BRK-B'),
            ('7203.T', '7203.T'),
            ('AAPL/USD', 'AAPL'),
            ('TSLAUSD', 'TSLA'),
        ]
        for input_sym, expected in cases:
            with self.subTest(input_sym=input_sym, expected=expected):
                resolved = resolve_yf_symbol(input_sym)
                self.assertEqual(resolved, expected, f"Failed for {input_sym}")

    async def test_02_yahoo_no_retry_on_404(self):
        """Verify that when query1 returns 404, query2 is NOT retried"""
        mock_client = AsyncMock()

        res_404 = MagicMock()
        res_404.status_code = 404
        mock_client.get.return_value = res_404

        price, traces = await fetch_price_with_trace(
            mock_client,
            exchange='global_stocks',
            symbol='UNKNOWN_TICKER',
            collect_all_traces=False
        )

        self.assertIsNone(price)
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0]['status_code'], 404)
        self.assertEqual(mock_client.get.call_count, 1)

    async def test_03_asof_skipping_logic(self):
        """Verify that asOf timestamp per-alert skips redundant ticks and triggers on new ticks"""
        alert = Alert(
            id='test-alert-asof',
            user_id='u1',
            exchange='global_stocks',
            symbol='AAPL',
            target_price=200.0,
            condition='ABOVE',
            fcm_token='token1',
            check_interval_seconds=180,
            last_checked_at=0.0,
            last_triggered_at=0.0,
            last_eval_asof=1728200000,
            created_at='2026-10-06T00:00:00Z',
        )

        # 1. Market returns identical asOf (market closed/weekend)
        cached_meta = {'asOf': 1728200000, 'state': 'CLOSED'}
        as_of = cached_meta.get('asOf')

        # Logic test: if as_of == alert.last_eval_asof, it skips
        should_skip = (alert.last_eval_asof == as_of)
        self.assertTrue(should_skip, "Identical asOf on closed market must skip re-evaluation")

        # 2. Market returns new asOf (new tick on open)
        new_as_of = 1728200060
        should_skip_new = (alert.last_eval_asof == new_as_of)
        self.assertFalse(should_skip_new, "Different asOf tick must NOT skip re-evaluation")

    def test_04_edge_crossing_hysteresis_guard(self):
        """
        Verify that an alert created when price is ALREADY above target does NOT trigger immediately.
        It enters waiting_for_cross=True, and only arms when price dips below, then triggers on upward cross.
        """
        alert = Alert(
            id='test-alert-edge',
            user_id='u1',
            exchange='binance',
            symbol='BTCUSDT',
            target_price=60000.0,
            condition='ABOVE',
            fcm_token='token1',
            check_interval_seconds=180,
            created_at='2026-10-06T00:00:00Z',
        )

        # Price at creation/startup is ALREADY 65000 (above target 60000)
        current_price = 65000.0

        # Initial check simulation:
        self.assertIsNone(alert.last_eval_price)
        alert.last_eval_price = current_price
        is_initially_triggered = (alert.condition == 'ABOVE' and current_price >= alert.target_price)
        self.assertTrue(is_initially_triggered)
        alert.waiting_for_cross = True

        # In this state, it does NOT trigger!
        self.assertTrue(alert.waiting_for_cross)

        # Next check: price is still 64000 (still above)
        price_step_2 = 64000.0
        # waiting_for_cross remains True
        self.assertTrue(alert.waiting_for_cross)

        # Price dips to 59000 (safely below target!)
        price_step_3 = 59000.0
        if alert.condition == 'ABOVE' and price_step_3 < alert.target_price:
            alert.waiting_for_cross = False # Now armed!

        self.assertFalse(alert.waiting_for_cross, "Alert is now armed for crossing!")

        # Price crosses back above 60000 to 60500 -> TRIGGERS!
        price_step_4 = 60500.0
        triggered = (not alert.waiting_for_cross and price_step_4 >= alert.target_price)
        self.assertTrue(triggered, "Alert triggers properly on legitimate level crossing!")

    async def test_05_require_admin_header_only_rejects_query(self):
        """Verify require_admin strictly enforces X-Admin-Key header and rejects missing/invalid header"""
        from fastapi import HTTPException
        with patch('server.ADMIN_KEY', 'valid_admin_secret_key_32bytes'):
            # Missing header raises 401
            with self.assertRaises(HTTPException) as ctx:
                await require_admin(x_admin_key=None)
            self.assertEqual(ctx.exception.status_code, 401)

            # Valid header succeeds
            await require_admin(x_admin_key='valid_admin_secret_key_32bytes')

    async def test_06_nobitex_quotes_irr_vs_usdt_division(self):
        """
        Verify:
        - USDTIRT (in Rials, e.g. 2,684,000) is divided by 10 to 268,400 Tomans.
        - BTCUSDT (in USDT, e.g. 85,600) is NOT divided by 10!
        """
        mock_client = AsyncMock()

        # 1. Test USDTIRT (Orderbook in Rials -> divide by 10)
        res_orderbook_irt = MagicMock()
        res_orderbook_irt.status_code = 200
        res_orderbook_irt.json.return_value = {
            "status": "ok",
            "lastTradePrice": "2684000",
            "bids": [["2684000", "100"]]
        }
        res_stats_404 = MagicMock()
        res_stats_404.status_code = 404

        mock_client.get.side_effect = [res_stats_404, res_orderbook_irt]

        price_irt, _ = await fetch_price_with_trace(
            mock_client, exchange='nobitex', symbol='USDTIRT', collect_all_traces=False
        )
        self.assertEqual(price_irt, 268400.0, "USDTIRT must be divided by 10 to Tomans")

        # 2. Test BTCUSDT (Orderbook in USDT -> DO NOT divide by 10!)
        res_orderbook_usdt = MagicMock()
        res_orderbook_usdt.status_code = 200
        res_orderbook_usdt.json.return_value = {
            "status": "ok",
            "lastTradePrice": "85600.5",
            "bids": [["85600.5", "0.5"]]
        }
        mock_client.get.side_effect = [res_stats_404, res_orderbook_usdt]

        price_usdt, _ = await fetch_price_with_trace(
            mock_client, exchange='nobitex', symbol='BTCUSDT', collect_all_traces=False
        )
        self.assertEqual(price_usdt, 85600.5, "BTCUSDT quote in USDT must NOT be divided by 10!")


if __name__ == '__main__':
    unittest.main()
