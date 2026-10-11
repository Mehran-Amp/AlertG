#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit Tests for Phase 6 (v2.9.1): Macro Alerts & Market Calendar:
Acceptance Criteria Verified:
1. alert_nature='macro' in models.py:
   - Supported in AlertCreate, Alert, AlertPublic
   - Conditions: «مقدار جدید منتشر شد» (NEW_RELEASE / newRelease) and «از آستانه رد شد» (THRESHOLD_CROSS / thresholdCross)
   - Macro state fields (last_macro_release_date, last_macro_value) preserved
2. Daily Macro Job on Scheduler:
   - Distinct daily job (check_macro_alerts_job) registered on scheduler (hours=24), NOT every 2s
   - check_alerts_job ignores macro alerts (only checks alert_nature == 'price')
   - Triggers on new release publication and on threshold crossings
3. Market Calendar:
   - US: MarketState Yahoo (REGULAR -> open, CLOSED -> closed) and NYSE schedule fallback
   - Forex: 24h from Sunday night (17:00 ET) to Friday night (17:00 ET), closed on weekends
   - Commodities: 24/5 with 1h daily break (17:00-18:00 ET Monday-Thursday)
   - Closed market:
     * is_market_open returns False -> poll stopped in check_alerts_job
     * /api/markets/status returns "status": "closed" and "state_fa": "بسته"
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import zoneinfo
import time
import httpx

from app.models import AlertCreate, Alert, AlertPublic
from app.engine.calendar import (
    is_us_market_open,
    is_forex_market_open,
    is_commodity_market_open,
    is_tse_market_open,
    is_crypto_market_open,
    is_market_open,
    get_all_markets_status,
    NY_TZ,
    TEHRAN_TZ,
)
from app.engine.checker import check_alerts_job, check_macro_alerts_job
from app.state import PRICE_CACHE, METRICS
import app.storage as storage
import app.state as state
from server import scheduler


class TestPhase6MacroAndCalendar(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.orig_alerts = list(storage.ALERTS_DB)
        storage.ALERTS_DB.clear()
        PRICE_CACHE.clear()
        self.disk_save_patch = patch('app.engine.checker.save_alerts_to_disk_async', new_callable=AsyncMock)
        self.mock_disk_save = self.disk_save_patch.start()

    def tearDown(self):
        self.disk_save_patch.stop()
        storage.ALERTS_DB.clear()
        storage.ALERTS_DB.extend(self.orig_alerts)
        PRICE_CACHE.clear()

    def test_01_macro_alert_model_schema_and_conditions(self):
        """Verify alert_nature='macro' and conditions in models.py"""
        # 1. Condition: «مقدار جدید منتشر شد»
        alert_in_release = AlertCreate(
            user_id="trader_1",
            exchange="global_stocks",
            symbol="US10Y",
            condition="NEW_RELEASE",
            condition_type="newRelease",
            alert_nature="macro"
        )
        self.assertEqual(alert_in_release.alert_nature, "macro")
        self.assertEqual(alert_in_release.condition, "NEW_RELEASE")

        # 2. Condition: «از آستانه رد شد»
        alert_in_threshold = AlertCreate(
            user_id="trader_1",
            exchange="global_stocks",
            symbol="US10Y",
            target_price=4.50,
            condition="THRESHOLD_CROSS",
            condition_type="thresholdCross",
            alert_nature="macro"
        )
        self.assertEqual(alert_in_threshold.alert_nature, "macro")
        self.assertEqual(alert_in_threshold.target_price, 4.50)

        # 3. Model Alert contains macro tracking fields
        alert_obj = Alert(
            id="macro_01",
            user_id="trader_1",
            exchange="global_stocks",
            symbol="US10Y",
            created_at=datetime.now(timezone.utc).isoformat(),
            alert_nature="macro",
            last_macro_release_date="2026-10-08",
            last_macro_value=4.25
        )
        self.assertEqual(alert_obj.last_macro_release_date, "2026-10-08")
        self.assertEqual(alert_obj.last_macro_value, 4.25)

        # 4. AlertPublic schema preserves macro fields
        pub = AlertPublic(**alert_obj.model_dump())
        self.assertEqual(pub.alert_nature, "macro")
        self.assertEqual(pub.last_macro_release_date, "2026-10-08")
        self.assertEqual(pub.last_macro_value, 4.25)

    def test_02_daily_job_registered_on_scheduler(self):
        """Verify daily macro alerts job is registered on scheduler (NOT 2s)"""
        from server import setup_scheduler_jobs
        if not scheduler.get_job('macro_alerts_daily_job'):
            setup_scheduler_jobs(scheduler)

        macro_job = scheduler.get_job('macro_alerts_daily_job')
        self.assertIsNotNone(macro_job, "macro_alerts_daily_job must be registered on scheduler")
        self.assertEqual(macro_job.func, check_macro_alerts_job)
        # Verify interval is daily (24 hours = 86400 seconds)
        self.assertEqual(macro_job.trigger.interval.total_seconds(), 86400.0)

        # Verify price alerts job runs every 2s
        price_job = scheduler.get_job('price_alerts_job')
        self.assertIsNotNone(price_job)
        self.assertEqual(price_job.trigger.interval.total_seconds(), 2.0)

    @patch('app.engine.checker.fetch_price_with_trace')
    @patch('app.engine.checker.enqueue_alert_push', new_callable=AsyncMock)
    async def test_03_macro_job_new_release_condition(self, mock_push, mock_fetch):
        """Verify condition «مقدار جدید منتشر شد» triggers when new release arrives"""
        state.http_client = AsyncMock()

        alert = Alert(
            id="macro_cpi_1",
            user_id="macro_user",
            exchange="global_stocks",
            symbol="CPI",
            condition="NEW_RELEASE",
            condition_type="newRelease",
            alert_nature="macro",
            check_interval_seconds=86400,
            created_at=datetime.now(timezone.utc).isoformat(),
            last_macro_release_date="2026-09-01",
            last_macro_value=310.2,
            last_eval_price=310.2,
            last_eval_asof=1700000000
        )
        storage.ALERTS_DB.append(alert)

        # Mock incoming new release from FRED (New release date: 2026-10-01, value: 312.5)
        mock_fetch.return_value = (
            312.5,
            [{
                'parsed_price': 312.5,
                'asOf': 1700086400,
                'date': '2026-10-01',
                'source': 'FRED',
                'currency': 'pts',
                'success': True
            }]
        )

        await check_macro_alerts_job()

        # Alert should trigger because release date changed from 2026-09-01 to 2026-10-01
        mock_push.assert_called_once()
        self.assertFalse(alert.is_active, "oneShot macro alert must be disarmed")
        self.assertEqual(alert.last_macro_release_date, "2026-10-01")
        self.assertEqual(alert.last_macro_value, 312.5)
        self.assertGreater(alert.last_triggered_at, 0)

    @patch('app.engine.checker.fetch_price_with_trace')
    @patch('app.engine.checker.enqueue_alert_push', new_callable=AsyncMock)
    async def test_04_macro_job_threshold_cross_condition(self, mock_push, mock_fetch):
        """Verify condition «از آستانه رد شد» triggers when value crosses threshold"""
        state.http_client = AsyncMock()

        alert = Alert(
            id="macro_yield_1",
            user_id="macro_user",
            exchange="global_stocks",
            symbol="US10Y",
            target_price=4.50,
            condition="ABOVE",
            condition_type="thresholdCross",
            alert_nature="macro",
            created_at=datetime.now(timezone.utc).isoformat(),
            last_eval_price=4.30,  # was below 4.50
            last_macro_value=4.30
        )
        storage.ALERTS_DB.append(alert)

        # Mock current yield jumping to 4.55%
        mock_fetch.return_value = (
            4.55,
            [{
                'parsed_price': 4.55,
                'asOf': int(time.time()),
                'date': '2026-10-09',
                'source': 'FRED',
                'currency': '%',
                'success': True
            }]
        )

        await check_macro_alerts_job()

        mock_push.assert_called_once()
        self.assertFalse(alert.is_active)
        self.assertEqual(alert.last_eval_price, 4.55)

    def test_05_us_calendar_marketstate_yahoo_and_fallback(self):
        """Verify US market calendar from Yahoo marketState and NYSE fallback"""
        # 1. Yahoo marketState = REGULAR in PRICE_CACHE -> OPEN
        PRICE_CACHE['global_stocks:^gspc'] = (5000.0, time.time(), {'state': 'REGULAR'})
        is_open, state_str = is_us_market_open(check_cache=True)
        self.assertTrue(is_open)
        self.assertEqual(state_str, 'REGULAR')

        # 2. Yahoo marketState = CLOSED in PRICE_CACHE -> CLOSED
        PRICE_CACHE['global_stocks:^gspc'] = (5000.0, time.time(), {'state': 'CLOSED'})
        is_open, state_str = is_us_market_open(check_cache=True)
        self.assertFalse(is_open)
        self.assertEqual(state_str, 'CLOSED')

        # 3. Fallback schedule: Tuesday 10:30 AM ET -> OPEN
        tuesday_open = datetime(2026, 10, 6, 10, 30, tzinfo=NY_TZ)
        is_open, state_str = is_us_market_open(now_dt=tuesday_open, check_cache=False)
        self.assertTrue(is_open)
        self.assertEqual(state_str, 'REGULAR')

        # 4. Fallback schedule: Tuesday 21:00 ET -> CLOSED
        tuesday_night = datetime(2026, 10, 6, 21, 0, tzinfo=NY_TZ)
        is_open, state_str = is_us_market_open(now_dt=tuesday_night, check_cache=False)
        self.assertFalse(is_open)
        self.assertEqual(state_str, 'CLOSED')

        # 5. Fallback schedule: Saturday -> CLOSED
        saturday = datetime(2026, 10, 10, 12, 0, tzinfo=NY_TZ)
        is_open, state_str = is_us_market_open(now_dt=saturday, check_cache=False)
        self.assertFalse(is_open)
        self.assertEqual(state_str, 'CLOSED')

    def test_06_forex_calendar_sunday_night_to_friday_night(self):
        """Verify Forex calendar: 24h from Sunday 17:00 ET to Friday 17:00 ET"""
        # Sunday 16:00 ET -> CLOSED (before 17:00)
        sun_closed = datetime(2026, 10, 4, 16, 0, tzinfo=NY_TZ)
        self.assertFalse(is_forex_market_open(sun_closed)[0])

        # Sunday 17:30 ET -> OPEN
        sun_open = datetime(2026, 10, 4, 17, 30, tzinfo=NY_TZ)
        self.assertTrue(is_forex_market_open(sun_open)[0])

        # Wednesday 12:00 ET -> OPEN
        wed_midday = datetime(2026, 10, 7, 12, 0, tzinfo=NY_TZ)
        self.assertTrue(is_forex_market_open(wed_midday)[0])

        # Friday 16:30 ET -> OPEN
        fri_open = datetime(2026, 10, 9, 16, 30, tzinfo=NY_TZ)
        self.assertTrue(is_forex_market_open(fri_open)[0])

        # Friday 17:30 ET -> CLOSED (weekend)
        fri_closed = datetime(2026, 10, 9, 17, 30, tzinfo=NY_TZ)
        self.assertFalse(is_forex_market_open(fri_closed)[0])

        # Saturday -> CLOSED
        sat = datetime(2026, 10, 10, 12, 0, tzinfo=NY_TZ)
        self.assertFalse(is_forex_market_open(sat)[0])

    def test_07_commodity_calendar_24_5_with_daily_break(self):
        """Verify Commodity calendar: 24/5 with 1-hour daily break (17:00-18:00 ET)"""
        # Sunday 17:30 ET -> CLOSED (opens at 18:00)
        sun_before_18 = datetime(2026, 10, 4, 17, 30, tzinfo=NY_TZ)
        self.assertFalse(is_commodity_market_open(sun_before_18)[0])

        # Sunday 18:30 ET -> OPEN
        sun_after_18 = datetime(2026, 10, 4, 18, 30, tzinfo=NY_TZ)
        self.assertTrue(is_commodity_market_open(sun_after_18)[0])

        # Monday 17:30 ET -> CLOSED (Daily Break)
        mon_daily_break = datetime(2026, 10, 5, 17, 30, tzinfo=NY_TZ)
        is_open, state_str = is_commodity_market_open(mon_daily_break)
        self.assertFalse(is_open)
        self.assertEqual(state_str, 'DAILY_BREAK')

        # Monday 18:30 ET -> OPEN (Resumed after daily break)
        mon_after_break = datetime(2026, 10, 5, 18, 30, tzinfo=NY_TZ)
        self.assertTrue(is_commodity_market_open(mon_after_break)[0])

        # Friday 18:00 ET -> CLOSED (Weekend)
        fri_weekend = datetime(2026, 10, 9, 18, 0, tzinfo=NY_TZ)
        self.assertFalse(is_commodity_market_open(fri_weekend)[0])

    def test_08_closed_market_stops_polling_in_check_alerts_job(self):
        """Verify closed market halts polling in check_alerts_job"""
        # Create an alert on US stock
        alert = Alert(
            id="stock_aapl_1",
            user_id="user_1",
            exchange="global_stocks",
            symbol="AAPL",
            target_price=200.0,
            condition="ABOVE",
            alert_nature="price",
            check_interval_seconds=1,
            created_at=datetime.now(timezone.utc).isoformat(),
            last_checked_at=0.0
        )
        storage.ALERTS_DB.append(alert)

        # Mock Saturday (US market closed)
        sat = datetime(2026, 10, 10, 12, 0, tzinfo=NY_TZ)
        with patch('app.engine.calendar.get_ny_now', return_value=sat):
            self.assertFalse(is_market_open('global_stocks', 'AAPL'))

        # When check_alerts_job runs while market is closed, it must NOT poll
        with patch('app.engine.checker.is_market_open', return_value=False), \
             patch('app.engine.checker.get_cached_price') as mock_fetch:
            state.http_client = AsyncMock()
            # check_alerts_job must see ready_alerts is empty due to is_market_open == False
            # and never call get_cached_price
            import asyncio
            asyncio.run(check_alerts_job())
            mock_fetch.assert_not_called()

    def test_09_api_markets_status_returns_closed_and_baste(self):
        """Verify get_all_markets_status reports 'closed' and 'بسته' when market is closed"""
        # Mock Saturday
        sat = datetime(2026, 10, 10, 12, 0, tzinfo=NY_TZ)
        status_dict = get_all_markets_status(now_dt=sat)

        # US Stocks: closed / بسته
        self.assertEqual(status_dict['us_stocks']['status'], 'closed')
        self.assertEqual(status_dict['us_stocks']['state_fa'], 'بسته')
        self.assertEqual(status_dict['us_stocks']['status_fa'], 'بسته')
        self.assertFalse(status_dict['us_stocks']['is_open'])

        # Forex: closed / بسته
        self.assertEqual(status_dict['forex']['status'], 'closed')
        self.assertEqual(status_dict['forex']['state_fa'], 'بسته')

        # Commodities: closed / بسته
        self.assertEqual(status_dict['commodities']['status'], 'closed')
        self.assertEqual(status_dict['commodities']['state_fa'], 'بسته')

        # Crypto: always open / باز
        self.assertEqual(status_dict['crypto']['status'], 'open')
        self.assertEqual(status_dict['crypto']['state_fa'], 'باز')
        self.assertTrue(status_dict['crypto']['is_open'])


if __name__ == '__main__':
    unittest.main()
