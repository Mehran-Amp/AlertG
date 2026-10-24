import unittest
from unittest.mock import AsyncMock, patch
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from server import setup_scheduler_jobs
from app.engine.market_events import (
    check_and_dispatch_30m_advance_reminders,
    check_and_dispatch_event_notifications,
)


class TestAdvanceReminderScheduler(unittest.IsolatedAsyncioTestCase):
    def test_advance_reminder_job_registered_with_interval_under_60s(self):
        """1. Verifies that the advance reminder job is registered with interval <= 60s (30s) and coalesce=True."""
        sched = AsyncIOScheduler()
        setup_scheduler_jobs(sched)

        jobs = sched.get_jobs()
        job = next((j for j in jobs if j.id == "advance_reminders_30s_job"), None)

        self.assertIsNotNone(job, "Job 'advance_reminders_30s_job' was not registered in setup_scheduler_jobs")
        self.assertEqual(job.func, check_and_dispatch_30m_advance_reminders)
        self.assertIsNotNone(job.trigger)

        # Interval must be <= 60 seconds (specifically 30 seconds)
        interval_seconds = job.trigger.interval.total_seconds()
        self.assertLessEqual(interval_seconds, 60.0)
        self.assertEqual(interval_seconds, 30.0)
        self.assertEqual(job.max_instances, 1)
        self.assertTrue(job.coalesce)

    async def test_advance_reminder_not_called_from_6h_path(self):
        """2. Verifies that check_and_dispatch_30m_advance_reminders is removed from the 6h notification path."""
        mock_client = AsyncMock()

        with patch("app.engine.market_events.check_and_dispatch_30m_advance_reminders", new_callable=AsyncMock) as mock_reminders:
            await check_and_dispatch_event_notifications(mock_client)
            mock_reminders.assert_not_called()


if __name__ == "__main__":
    unittest.main()
