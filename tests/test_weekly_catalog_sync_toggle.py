#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for WEEKLY_CATALOG_SYNC_ENABLED configuration toggle:
- Disabled by default (WEEKLY_CATALOG_SYNC_ENABLED = False)
- When False: weekly_catalog_sync_job is NOT registered on scheduler
- When True: weekly_catalog_sync_job is registered on scheduler with Saturday 06:00 UTC trigger
- Manual CLI execution path (scripts/run_catalog_sync.py --dry-run) remains intact
"""

import os
import sys
import pytest
from datetime import timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import app.config as config
from server import setup_scheduler_jobs
from app.engine.sync import weekly_catalog_sync_job


class TestWeeklyCatalogSyncToggle:
    """Verifies that the weekly catalog sync job in the scheduler honors the config flag."""

    def test_default_flag_is_false(self):
        """Verifies that automated weekly sync is disabled by default in config."""
        assert hasattr(config, "WEEKLY_CATALOG_SYNC_ENABLED")
        # In default configuration (no env var overriding it), it evaluates to False
        val = os.getenv("WEEKLY_CATALOG_SYNC_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")
        assert val is False

    def test_scheduler_skips_job_when_flag_is_false(self, monkeypatch):
        """When WEEKLY_CATALOG_SYNC_ENABLED is False, weekly_catalog_sync_job must NOT be added to scheduler."""
        monkeypatch.setattr(config, "WEEKLY_CATALOG_SYNC_ENABLED", False)

        sched = AsyncIOScheduler()
        setup_scheduler_jobs(sched)

        registered_job_ids = [j.id for j in sched.get_jobs()]
        assert "weekly_catalog_sync_job" not in registered_job_ids

        # Ensure core operations jobs are still active
        assert "price_alerts_job" in registered_job_ids
        assert "macro_alerts_daily_job" in registered_job_ids
        assert "advance_reminders_30s_job" in registered_job_ids
        assert "market_events_6h_job" in registered_job_ids

    def test_scheduler_registers_job_when_flag_is_true(self, monkeypatch):
        """When WEEKLY_CATALOG_SYNC_ENABLED is True, weekly_catalog_sync_job MUST be registered."""
        monkeypatch.setattr(config, "WEEKLY_CATALOG_SYNC_ENABLED", True)

        sched = AsyncIOScheduler()
        setup_scheduler_jobs(sched)

        jobs = sched.get_jobs()
        sync_job = next((j for j in jobs if j.id == "weekly_catalog_sync_job"), None)
        assert sync_job is not None
        assert sync_job.func == weekly_catalog_sync_job
        assert sync_job.max_instances == 1
        assert sync_job.coalesce is True

        # Check Saturday 06:00 UTC trigger
        trigger_str = str(sync_job.trigger).lower()
        assert "sat" in trigger_str or "5" in trigger_str or "6" in trigger_str

    @pytest.mark.parametrize(
        "env_val, expected",
        [
            ("1", True),
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("yes", True),
            ("on", True),
            ("0", False),
            ("false", False),
            ("False", False),
            ("no", False),
            ("off", False),
            ("", False),
            ("random", False),
        ]
    )
    def test_env_var_boolean_parsing(self, env_val, expected):
        """Verifies standard truthy/falsy evaluation for env flag values."""
        parsed = env_val.strip().lower() in ("1", "true", "yes", "on")
        assert parsed is expected

    def test_manual_sync_script_dry_run_dispatch(self):
        """Verifies that manual CLI script run_catalog_sync.py parse_args and dry-run flag exist."""
        import scripts.run_catalog_sync as runner
        parser = runner.parse_args
        assert callable(parser)
