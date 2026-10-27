#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for canonical market state in /api/price:
- Allowed states for stocks, ETFs, indices, and forex: strictly REGULAR, PRE, POST, CLOSED.
- Yahoo marketState takes precedence if provided.
- Calendar fallback:
  * US Market (America/New_York): Mon-Fri 09:30-16:00 ET (PRE 04:00-09:30, POST 16:00-20:00).
  * Forex: Sunday 22:00 UTC to Friday 22:00 UTC.
- FRED macro data remains 'delayed' without modification.
- Fixed time validations:
  * Saturday = CLOSED
  * Monday 10:00 ET = REGULAR
  * Monday 07:00 ET = PRE
  * Monday 17:00 ET = POST
  * Forex Saturday = CLOSED
"""

import time
import pytest
from datetime import datetime, timezone
import zoneinfo
from app.engine.calendar import get_canonical_market_state, NY_TZ
from fastapi.testclient import TestClient

from app.engine.calendar import (
    get_canonical_market_state,
    is_us_market_open,
    is_forex_market_open,
    NY_TZ
)
from app.state import PRICE_CACHE
import app.state as state
import server

client = TestClient(server.app)
VALID_CANONICAL_STATES = {'REGULAR', 'PRE', 'POST', 'CLOSED'}


class TestCanonicalMarketState:
    """Verifies market state resolution and adherence to canonical set."""

    def test_saturday_fixed_time_is_closed(self):
        """Saturday for US equities, ETFs, and indices must be CLOSED."""
        # 2026-10-24 is a Saturday
        sat_ny = datetime(2026, 10, 24, 12, 0, 0, tzinfo=NY_TZ)
        assert get_canonical_market_state('stock', now_dt=sat_ny) == 'CLOSED'
        assert get_canonical_market_state('etf', now_dt=sat_ny) == 'CLOSED'
        assert get_canonical_market_state('index', now_dt=sat_ny) == 'CLOSED'

    def test_monday_10am_et_fixed_time_is_regular(self):
        """Monday 10:00 ET during core trading hours (09:30-16:00 ET) must be REGULAR."""
        # 2026-10-26 is a Monday
        mon_10am = datetime(2026, 10, 26, 10, 0, 0, tzinfo=NY_TZ)
        assert get_canonical_market_state('stock', now_dt=mon_10am) == 'REGULAR'
        assert get_canonical_market_state('etf', now_dt=mon_10am) == 'REGULAR'
        assert get_canonical_market_state('index', now_dt=mon_10am) == 'REGULAR'

    def test_monday_7am_et_fixed_time_is_pre(self):
        """Monday 07:00 ET during pre-market window (04:00-09:30 ET) must be PRE."""
        mon_7am = datetime(2026, 10, 26, 7, 0, 0, tzinfo=NY_TZ)
        assert get_canonical_market_state('stock', now_dt=mon_7am) == 'PRE'
        assert get_canonical_market_state('etf', now_dt=mon_7am) == 'PRE'
        assert get_canonical_market_state('index', now_dt=mon_7am) == 'PRE'

    def test_monday_5pm_et_fixed_time_is_post(self):
        """Monday 17:00 ET during after-hours window (16:00-20:00 ET) must be POST."""
        mon_5pm = datetime(2026, 10, 26, 17, 0, 0, tzinfo=NY_TZ)
        assert get_canonical_market_state('stock', now_dt=mon_5pm) == 'POST'
        assert get_canonical_market_state('etf', now_dt=mon_5pm) == 'POST'
        assert get_canonical_market_state('index', now_dt=mon_5pm) == 'POST'

    def test_forex_saturday_fixed_time_is_closed(self):
        """Forex on Saturday is always CLOSED."""
        sat_utc = datetime(2026, 10, 24, 15, 0, 0, tzinfo=timezone.utc)
        assert get_canonical_market_state('forex', now_dt=sat_utc) == 'CLOSED'

    def test_forex_schedule_windows_et(self):
        """Forex schedule: Sunday 17:00 ET to Friday 17:00 ET is REGULAR; weekends CLOSED.

        Uses America/New_York so EDT/EST transitions are handled correctly
        (in EDT, 17:00 ET = 21:00 UTC; in EST, 17:00 ET = 22:00 UTC).
        """
        # Sunday before 17:00 ET -> CLOSED
        sun_before_17 = datetime(2026, 10, 25, 16, 0, 0, tzinfo=NY_TZ)
        assert get_canonical_market_state('forex', now_dt=sun_before_17) == 'CLOSED'

        # Sunday after 17:00 ET -> REGULAR
        sun_after_17 = datetime(2026, 10, 25, 17, 30, 0, tzinfo=NY_TZ)
        assert get_canonical_market_state('forex', now_dt=sun_after_17) == 'REGULAR'

        # Midweek Wednesday -> REGULAR
        wed_midday = datetime(2026, 10, 28, 14, 0, 0, tzinfo=NY_TZ)
        assert get_canonical_market_state('forex', now_dt=wed_midday) == 'REGULAR'

        # Friday before 17:00 ET -> REGULAR
        fri_before_17 = datetime(2026, 10, 30, 16, 0, 0, tzinfo=NY_TZ)
        assert get_canonical_market_state('forex', now_dt=fri_before_17) == 'REGULAR'

        # Friday after 17:00 ET -> CLOSED
        fri_after_17 = datetime(2026, 10, 30, 18, 0, 0, tzinfo=NY_TZ)
        assert get_canonical_market_state('forex', now_dt=fri_after_17) == 'CLOSED'

        # Saturday -> CLOSED
        sat_midday = datetime(2026, 10, 31, 12, 0, 0, tzinfo=NY_TZ)
        assert get_canonical_market_state('forex', now_dt=sat_midday) == 'CLOSED'

    def test_yahoo_market_state_precedence(self):
        """When Yahoo returns valid marketState, it takes precedence over local calendar."""
        # Force a Saturday datetime when calendar would say CLOSED
        sat_ny = datetime(2026, 10, 24, 12, 0, 0, tzinfo=NY_TZ)

        assert get_canonical_market_state('stock', raw_market_state='REGULAR', now_dt=sat_ny) == 'REGULAR'
        assert get_canonical_market_state('stock', raw_market_state='PRE', now_dt=sat_ny) == 'PRE'
        assert get_canonical_market_state('stock', raw_market_state='POST', now_dt=sat_ny) == 'POST'
        assert get_canonical_market_state('stock', raw_market_state='CLOSED', now_dt=sat_ny) == 'CLOSED'

    def test_api_price_stocks_canonical_state_and_fred_delayed(self, monkeypatch):
        """Checks /api/price response: stocks/etfs/forex state in valid set, FRED stays delayed."""
        from unittest.mock import AsyncMock
        import app.config as cfg
        monkeypatch.setattr(cfg, "API_KEY", "test_key")
        monkeypatch.setattr(state, "http_client", AsyncMock())
        headers = {"X-API-Key": "test_key"}

        from app.markets.common import normalize_symbol

        # 1. Mock cache entry for US Stock AAPL
        PRICE_CACHE[f"global_stocks:{normalize_symbol('AAPL')}"] = (
            225.50,
            time.time(),
            {'source': 'Yahoo Finance', 'marketState': 'REGULAR', 'currency': 'USD', 'category': 'stock'}
        )
        res = client.get("/api/price/global_stocks/AAPL", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["state"] in VALID_CANONICAL_STATES
        assert data["state"] == "REGULAR"

        # 2. Mock cache entry for US Stock in POST
        PRICE_CACHE[f"global_stocks:{normalize_symbol('TSLA')}"] = (
            250.00,
            time.time(),
            {'source': 'Yahoo Finance', 'marketState': 'POST', 'currency': 'USD', 'category': 'stock'}
        )
        res = client.get("/api/price/global_stocks/TSLA", headers=headers)
        assert res.status_code == 200
        assert res.json()["state"] == "POST"

        # 3. Mock cache entry for Forex EURUSD
        PRICE_CACHE[f"forex:{normalize_symbol('EURUSD')}"] = (
            1.0850,
            time.time(),
            {'source': 'Forex Interbank', 'currency': 'USD', 'category': 'forex'}
        )
        res = client.get("/api/price/forex/EURUSD", headers=headers)
        assert res.status_code == 200
        assert res.json()["state"] in VALID_CANONICAL_STATES

        # 4. FRED Macro series FEDFUNDS -> Must remain 'delayed'
        PRICE_CACHE[f"global_stocks:{normalize_symbol('FEDFUNDS')}"] = (
            5.33,
            time.time(),
            {'source': 'FRED', 'currency': '%', 'category': 'macro', 'data_frequency': 'monthly'}
        )
        res = client.get("/api/price/global_stocks/FEDFUNDS", headers=headers)
        assert res.status_code == 200
        assert res.json()["state"] == "delayed"
