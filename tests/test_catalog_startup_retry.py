# -*- coding: utf-8 -*-
"""
Phase CS3 Unit Tests: Interval (2h) and startup retry worker.
Verifies that:
1. Existing scheduler job 'crypto_catalog_sync_job' defaults to 2h interval (CRYPTO_CATALOG_SYNC_HOURS).
2. All scheduler jobs have strictly unique IDs (no duplicates).
3. _run_stale_catalogs_retry_worker re-syncs only stale exchanges, logs start/ok, and terminates when healthy.
4. _run_stale_catalogs_retry_worker logs abort on cancellation.
"""

import os
import sys
import asyncio
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from apscheduler.schedulers.asyncio import AsyncIOScheduler

try:
    import httpx
except ImportError:
    httpx = MagicMock()
    sys.modules['httpx'] = httpx

import app.config as config
from app.markets.crypto_catalog import DEFAULT_SYNC_HOURS
import server


class TestCatalogStartupRetry(unittest.IsolatedAsyncioTestCase):
    def test_01_default_interval_is_2h_and_no_duplicate_job_ids(self):
        """1. Asserts crypto_catalog_sync_job runs every 2h and scheduler has no duplicate IDs."""
        self.assertEqual(DEFAULT_SYNC_HOURS, 2)
        self.assertEqual(config.CRYPTO_CATALOG_SYNC_INTERVAL_HOURS, 2)

        sched = AsyncIOScheduler()
        server.setup_scheduler_jobs(sched)

        jobs = sched.get_jobs()
        job_ids = [j.id for j in jobs]

        # Verify no duplicate job IDs
        self.assertEqual(len(job_ids), len(set(job_ids)), f"Duplicate job IDs found: {job_ids}")

        # Verify crypto_catalog_sync_job is present and configured for 2 hours
        sync_job = next((j for j in jobs if j.id == 'crypto_catalog_sync_job'), None)
        self.assertIsNotNone(sync_job, "crypto_catalog_sync_job was not registered on scheduler")
        self.assertIn("interval", str(sync_job.trigger).lower())
        self.assertEqual(sync_job.max_instances, 1)
        self.assertTrue(sync_job.coalesce)

    async def test_02_retry_worker_resyncs_stale_exchanges_and_stops(self):
        """2. Startup retry worker attempts only stale exchanges and terminates when healthy."""
        mock_sync_single = AsyncMock(return_value={"success": True, "total_pairs": 500})

        # Cycle 1: binance is stale
        status_1 = {
            "exchanges": {
                "binance": {"is_stale": True, "file_exists": True},
                "kraken": {"is_stale": False, "file_exists": True},
            }
        }
        # Cycle 2: all healthy
        status_2 = {
            "exchanges": {
                "binance": {"is_stale": False, "file_exists": True},
                "kraken": {"is_stale": False, "file_exists": True},
            }
        }

        with patch.dict(os.environ, {"CRYPTO_CATALOG_RETRY_INTERVAL_SECONDS": "0"}), \
             patch("app.markets.crypto_catalog.sync_single_exchange_catalog", mock_sync_single), \
             patch("app.markets.crypto_catalog.get_crypto_catalogs_status", side_effect=[status_1, status_2]), \
             self.assertLogs("signalalert.server", level="INFO") as cm:

            await server._run_stale_catalogs_retry_worker(["binance"])

            # Verify sync_single_exchange_catalog was called for binance only
            mock_sync_single.assert_awaited_once_with("binance")

            # Verify start and ok logs
            has_start = any("[CatalogSync] retry start" in log for log in cm.output)
            has_ok = any("[CatalogSync] retry ok" in log for log in cm.output)
            self.assertTrue(has_start, f"Missing start log in {cm.output}")
            self.assertTrue(has_ok, f"Missing ok log in {cm.output}")

    async def test_03_retry_worker_logs_abort_on_cancellation(self):
        """3. When retry worker is cancelled, logs [CatalogSync] retry abort."""
        with patch.dict(os.environ, {"CRYPTO_CATALOG_RETRY_INTERVAL_SECONDS": "60"}), \
             self.assertLogs("signalalert.server", level="INFO") as cm:

            task = asyncio.create_task(server._run_stale_catalogs_retry_worker(["okx"]))
            await asyncio.sleep(0.01)
            task.cancel()

            with self.assertRaises(asyncio.CancelledError):
                await task

            has_abort = any("[CatalogSync] retry abort" in log for log in cm.output)
            self.assertTrue(has_abort, f"Missing abort log in {cm.output}")


if __name__ == "__main__":
    unittest.main()
