# -*- coding: utf-8 -*-
"""
Phase H3 Unit Tests: Graceful shutdown of _SERVER_BG_TASKS in lifespan.
Verifies that:
1. Fake slow task added to _SERVER_BG_TASKS is cancelled during shutdown.
2. The fake slow task is awaited to full completion before state.http_client.aclose() is called.
3. Cleanup during CancelledError in background tasks completes before http_client is closed.
4. Multiple tasks (and tasks that raise exceptions during cancellation) are cleanly awaited without failing shutdown.
5. Lifespan shutdown completes cleanly when _SERVER_BG_TASKS is empty.
"""

import asyncio
import time
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

import server
from server import app, lifespan, state, _SERVER_BG_TASKS


class TestLifespanBgTasksShutdown(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Save snapshot of background tasks set
        self.orig_bg_tasks = set(_SERVER_BG_TASKS)
        _SERVER_BG_TASKS.clear()

    async def asyncTearDown(self):
        # Cancel any leftover tasks if any
        for t in list(_SERVER_BG_TASKS):
            if not t.done():
                t.cancel()
        _SERVER_BG_TASKS.clear()
        _SERVER_BG_TASKS.update(self.orig_bg_tasks)

    async def test_01_fake_slow_task_cancelled_and_awaited_before_http_client_aclose(self):
        """1. Asserts a fake slow task in _SERVER_BG_TASKS is cancelled and awaited before state.http_client.aclose()."""
        event_log = []

        async def fake_slow_task():
            try:
                event_log.append("slow_task_started")
                await asyncio.sleep(60.0)  # Long running task
            except asyncio.CancelledError:
                event_log.append("slow_task_cancelling")
                # Ensure client is still open and not closed during cancellation cleanup
                if state.http_client is not None:
                    event_log.append(f"client_is_closed_during_cleanup:{state.http_client.is_closed}")
                await asyncio.sleep(0.02)  # Simulate asynchronous cleanup
                event_log.append("slow_task_cleanup_done")
                raise

        with patch("server._run_background_crypto_catalog_sync", new_callable=AsyncMock), \
             patch("server._run_background_market_refresh", new_callable=AsyncMock), \
             patch("server.outbox_worker_loop", new_callable=AsyncMock):

            async with lifespan(app):
                # Spying on state.http_client.aclose
                orig_aclose = state.http_client.aclose

                async def spy_aclose():
                    event_log.append("http_client_aclose_called")
                    return await orig_aclose()

                state.http_client.aclose = spy_aclose

                # Launch fake slow task and add to _SERVER_BG_TASKS
                task = asyncio.create_task(fake_slow_task())
                _SERVER_BG_TASKS.add(task)
                task.add_done_callback(_SERVER_BG_TASKS.discard)

                # Let task start
                await asyncio.sleep(0.01)
                self.assertIn("slow_task_started", event_log)
                self.assertFalse(task.done())

            # Lifespan has now exited. Verify execution ordering and task completion.
            self.assertTrue(task.done(), "Fake slow task must be completed after lifespan exits")
            self.assertIn("slow_task_cancelling", event_log)
            self.assertIn("slow_task_cleanup_done", event_log)
            self.assertIn("http_client_aclose_called", event_log)
            self.assertIn("client_is_closed_during_cleanup:False", event_log)

            idx_cleanup = event_log.index("slow_task_cleanup_done")
            idx_aclose = event_log.index("http_client_aclose_called")
            self.assertLess(
                idx_cleanup,
                idx_aclose,
                f"Task cleanup must finish BEFORE http_client.aclose()! Events: {event_log}"
            )

    async def test_02_multiple_tasks_with_exception_absorbed_gracefully(self):
        """2. Asserts multiple tasks (including one raising an exception on cancel) are handled safely."""
        event_log = []

        async def clean_task():
            try:
                await asyncio.sleep(60.0)
            except asyncio.CancelledError:
                event_log.append("clean_task_cancelled")
                raise

        async def faulty_task():
            try:
                await asyncio.sleep(60.0)
            except asyncio.CancelledError:
                event_log.append("faulty_task_raising_error")
                raise RuntimeError("Unexpected failure during background task cancel")

        with patch("server._run_background_crypto_catalog_sync", new_callable=AsyncMock), \
             patch("server._run_background_market_refresh", new_callable=AsyncMock), \
             patch("server.outbox_worker_loop", new_callable=AsyncMock):

            async with lifespan(app):
                t1 = asyncio.create_task(clean_task())
                t2 = asyncio.create_task(faulty_task())
                _SERVER_BG_TASKS.add(t1)
                _SERVER_BG_TASKS.add(t2)
                t1.add_done_callback(_SERVER_BG_TASKS.discard)
                t2.add_done_callback(_SERVER_BG_TASKS.discard)
                await asyncio.sleep(0.01)

            # Both tasks must be finished despite faulty_task raising RuntimeError
            self.assertTrue(t1.done())
            self.assertTrue(t2.done())
            self.assertIn("clean_task_cancelled", event_log)
            self.assertIn("faulty_task_raising_error", event_log)

    async def test_03_empty_server_bg_tasks_shutdown_cleanly(self):
        """3. Asserts lifespan shutdown completes cleanly with zero errors when _SERVER_BG_TASKS is empty."""
        with patch("server._run_background_crypto_catalog_sync", new_callable=AsyncMock), \
             patch("server._run_background_market_refresh", new_callable=AsyncMock), \
             patch("server.outbox_worker_loop", new_callable=AsyncMock):

            async with lifespan(app):
                _SERVER_BG_TASKS.clear()

            # Successfully reached here without exception
            self.assertEqual(len(_SERVER_BG_TASKS), 0)

    async def test_04_tg_task_and_outbox_task_cancelled_and_awaited_before_http_client_aclose(self):
        """4. Asserts tg_task and outbox_task are both cancelled and awaited before state.http_client.aclose() (Phase H3b)."""
        event_log = []

        async def fake_tg_loop():
            try:
                event_log.append("tg_loop_started")
                await asyncio.sleep(60.0)
            except asyncio.CancelledError:
                event_log.append("tg_loop_cancelling")
                if state.http_client is not None:
                    event_log.append(f"tg_client_is_closed:{state.http_client.is_closed}")
                await asyncio.sleep(0.02)
                event_log.append("tg_loop_cleanup_done")
                raise

        async def fake_outbox_loop():
            try:
                event_log.append("outbox_loop_started")
                await asyncio.sleep(60.0)
            except asyncio.CancelledError:
                event_log.append("outbox_loop_cancelling")
                if state.http_client is not None:
                    event_log.append(f"outbox_client_is_closed:{state.http_client.is_closed}")
                await asyncio.sleep(0.02)
                event_log.append("outbox_loop_cleanup_done")
                raise

        with patch("server.TELEGRAM_BOT_TOKEN", "fake_bot_token_for_test"), \
             patch("server.init_telegram_bot", new_callable=AsyncMock), \
             patch("server.telegram_bot_polling_loop", side_effect=fake_tg_loop), \
             patch("server.outbox_worker_loop", side_effect=fake_outbox_loop), \
             patch("server._run_background_crypto_catalog_sync", new_callable=AsyncMock), \
             patch("server._run_background_market_refresh", new_callable=AsyncMock):

            async with lifespan(app):
                orig_aclose = state.http_client.aclose

                async def spy_aclose():
                    event_log.append("http_client_aclose_called")
                    return await orig_aclose()

                state.http_client.aclose = spy_aclose
                await asyncio.sleep(0.01)

            # Both tasks must be awaited to completion before http_client.aclose()
            self.assertIn("tg_loop_started", event_log)
            self.assertIn("outbox_loop_started", event_log)
            self.assertIn("tg_loop_cleanup_done", event_log)
            self.assertIn("outbox_loop_cleanup_done", event_log)
            self.assertIn("http_client_aclose_called", event_log)
            self.assertIn("tg_client_is_closed:False", event_log)
            self.assertIn("outbox_client_is_closed:False", event_log)

            idx_tg = event_log.index("tg_loop_cleanup_done")
            idx_outbox = event_log.index("outbox_loop_cleanup_done")
            idx_aclose = event_log.index("http_client_aclose_called")
            self.assertLess(idx_tg, idx_aclose, f"tg_task cleanup must finish before aclose! {event_log}")
            self.assertLess(idx_outbox, idx_aclose, f"outbox_task cleanup must finish before aclose! {event_log}")


if __name__ == "__main__":
    unittest.main()
