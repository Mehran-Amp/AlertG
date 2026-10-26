#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for FRED stale data guard thresholds in app/engine/checker.py:
- Quarterly: 120 days (10,368,000s)
- Annual: 400 days (34,560,000s)
- Monthly: 60 days (unchanged)
- Weekly: 21 days (unchanged)
- Daily: 7 days (unchanged)
- Live / Default: 3600s (unchanged)
"""

import pytest
import time
from app.engine.checker import is_data_stale


class TestFredStaleThresholds:
    """Verifies that is_data_stale honors quarterly (120d) and annual (400d) thresholds while preserving existing ones."""

    NOW = 1715000000.0  # Stable reference timestamp
    DAY = 86400.0

    def test_quarterly_threshold_120_days(self):
        """Quarterly data is fresh within 120 days and stale after 120 days."""
        now = self.NOW
        day = self.DAY

        # 90 days (1 quarter) old: fresh
        assert is_data_stale(now - (90 * day), 'quarterly', current_time=now) is False

        # 119 days old: fresh
        assert is_data_stale(now - (119 * day), 'quarterly', current_time=now) is False

        # Exactly 120 days: not stale (threshold boundary)
        assert is_data_stale(now - (120 * day), 'quarterly', current_time=now) is False

        # 121 days old: stale
        assert is_data_stale(now - (121 * day), 'quarterly', current_time=now) is True

        # 150 days old: stale
        assert is_data_stale(now - (150 * day), 'quarterly', current_time=now) is True

        # Case-insensitivity and whitespace tolerance
        assert is_data_stale(now - (110 * day), '  QUARTERLY  ', current_time=now) is False
        assert is_data_stale(now - (125 * day), 'Quarterly', current_time=now) is True

    def test_annual_threshold_400_days(self):
        """Annual data is fresh within 400 days and stale after 400 days."""
        now = self.NOW
        day = self.DAY

        # 365 days (1 year) old: fresh (annual observations update with lag)
        assert is_data_stale(now - (365 * day), 'annual', current_time=now) is False

        # 399 days old: fresh
        assert is_data_stale(now - (399 * day), 'annual', current_time=now) is False

        # Exactly 400 days: not stale (threshold boundary)
        assert is_data_stale(now - (400 * day), 'annual', current_time=now) is False

        # 401 days old: stale
        assert is_data_stale(now - (401 * day), 'annual', current_time=now) is True

        # 450 days old: stale
        assert is_data_stale(now - (450 * day), 'annual', current_time=now) is True

        # Case-insensitivity and whitespace tolerance
        assert is_data_stale(now - (380 * day), '  ANNUAL  ', current_time=now) is False
        assert is_data_stale(now - (410 * day), 'Annual', current_time=now) is True

    def test_existing_frequencies_unchanged(self):
        """Ensures monthly (60d), weekly (21d), daily (7d), and live (3600s) remain unchanged."""
        now = self.NOW
        day = self.DAY

        # Monthly (60 days)
        assert is_data_stale(now - (50 * day), 'monthly', current_time=now) is False
        assert is_data_stale(now - (65 * day), 'monthly', current_time=now) is True

        # Weekly (21 days)
        assert is_data_stale(now - (15 * day), 'weekly', current_time=now) is False
        assert is_data_stale(now - (25 * day), 'weekly', current_time=now) is True

        # Daily (7 days)
        assert is_data_stale(now - (4 * day), 'daily', current_time=now) is False
        assert is_data_stale(now - (8 * day), 'daily', current_time=now) is True

        # Live / Default (3600s = 1 hour)
        assert is_data_stale(now - 1800, 'live', current_time=now) is False
        assert is_data_stale(now - 1800, None, current_time=now) is False
        assert is_data_stale(now - 7200, 'live', current_time=now) is True
        assert is_data_stale(now - 7200, None, current_time=now) is True

    def test_invalid_or_missing_as_of(self):
        """Invalid, zero, negative, or None as_of timestamps should return False."""
        now = self.NOW
        assert is_data_stale(None, 'quarterly', current_time=now) is False
        assert is_data_stale(0, 'annual', current_time=now) is False
        assert is_data_stale(-100, 'monthly', current_time=now) is False
        assert is_data_stale("invalid", 'daily', current_time=now) is False
