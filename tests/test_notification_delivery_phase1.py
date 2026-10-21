#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Phase 1 - Step 1A:
1A-1: Preserve evaluation state on sync/create (trigger_signature)
  a) ABOVE 100 alert; evaluate at 99; sync identical payload; evaluate at 101 -> enqueue_alert_push called exactly once.
  b) sync payload with target 100->105 resets last_eval_*/waiting_for_cross.
  c) one-shot already triggered stays inactive after sync.
  d) payload identical except condition letter case / numeric string -> signature equal.
1A-2: Dead/invalid FCM token blocking without entry drop or token wiping; resume on token update; INVALID_PAYLOAD retries.
1A-3: Lifespan server startup completes in <1s without waiting on notifications/refresh_market_events, and price job is registered.
"""

import sys
import unittest
import time
import asyncio
from unittest.mock import AsyncMock, patch

import app.storage as storage
import app.state as state
from app.models import Alert
from app.routes.alerts import _trigger_signature, trigger_signature, sync_user_alerts
from app.notifier import outbox
from app.engine.checker import check_alerts_job
from server import app, lifespan, scheduler


class TestNotificationDeliveryPhase1(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self._orig_alerts = list(storage.ALERTS_DB)
        self._orig_profiles = dict(storage.USER_PROFILES_DB)
        self._orig_http_client = state.http_client
        state.http_client = AsyncMock()
        storage.ALERTS_DB.clear()
        outbox.OUTBOX.clear()
        outbox.DEAD_TOKENS.clear()
        state.METRICS["fcm_invalid_token"] = 0
        state.METRICS["outbox_blocked"] = 0
        self._disk_patch = patch("app.storage.save_alerts_to_disk_async", new_callable=AsyncMock)
        self._disk_patch.start()

    def tearDown(self):
        try:
            self._disk_patch.stop()
        except Exception:
            pass
        storage.ALERTS_DB.clear()
        storage.ALERTS_DB.extend(self._orig_alerts)
        storage.USER_PROFILES_DB.clear()
        storage.USER_PROFILES_DB.update(self._orig_profiles)
        state.http_client = self._orig_http_client
        outbox.OUTBOX.clear()
        outbox.DEAD_TOKENS.clear()

    # -------------------------------------------------------------
    # 1A-1 Tests
    # -------------------------------------------------------------

    async def test_1a1_a_above_100_eval_99_sync_identical_eval_101_triggers_once(self):
        """a) ABOVE 100 alert; evaluate at 99; sync identical payload; evaluate at 101 -> enqueue_alert_push called exactly once."""
        rule_id = "test_rule_1a1_a"
        user_id = "user_test_1a1"
        test_token = "valid_fcm_token_1234567890123456789012345678901234567890"

        alert = Alert(
            id=rule_id,
            user_id=user_id,
            exchange="binance",
            symbol="BTCUSDT",
            target_price=100.0,
            condition="ABOVE",
            condition_type="priceThreshold",
            is_active=True,
            check_interval_seconds=0,
            fcm_token=test_token,
            last_checked_at=0.0
        )
        storage.ALERTS_DB.append(alert)

        # 1. Evaluate at 99 -> last_eval_price becomes 99, not triggered yet
        with patch("app.engine.checker.get_cached_price", new_callable=AsyncMock) as mock_price, \
             patch("app.engine.checker.enqueue_alert_push", new_callable=AsyncMock) as mock_push:
            mock_price.return_value = 99.0
            await check_alerts_job()

            self.assertEqual(alert.last_eval_price, 99.0)
            self.assertFalse(alert.waiting_for_cross)
            self.assertEqual(mock_push.call_count, 0)

        # 2. Sync identical payload for this alert
        sync_payload = {
            "user_id": user_id,
            "fcm_token": test_token,
            "alerts": [{
                "id": rule_id,
                "user_id": user_id,
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "target_price": 100.0,
                "condition": "ABOVE",
                "condition_type": "priceThreshold",
                "is_active": True,
                "check_interval_seconds": 0,
                "fcm_token": test_token
            }]
        }
        with patch("app.routes.alerts.save_alerts_to_disk_async", new_callable=AsyncMock):
            await sync_user_alerts(sync_payload)

        synced_alert = next((a for a in storage.ALERTS_DB if a.id == rule_id), None)
        self.assertIsNotNone(synced_alert)
        # Evaluation state must be preserved across identical sync!
        self.assertEqual(synced_alert.last_eval_price, 99.0)
        self.assertFalse(synced_alert.waiting_for_cross)

        # 3. Evaluate at 101 -> crossing occurs and enqueue_alert_push is called!
        with patch("app.engine.checker.get_cached_price", new_callable=AsyncMock) as mock_price, \
             patch("app.engine.checker.enqueue_alert_push", new_callable=AsyncMock) as mock_push:
            mock_price.return_value = 101.0
            # reset last_checked_at so it's ready to evaluate
            synced_alert.last_checked_at = 0.0
            await check_alerts_job()

            self.assertEqual(mock_push.call_count, 1)

    async def test_1a1_b_sync_payload_with_different_target_resets_eval_state(self):
        """b) sync payload with target 100->105 resets last_eval_*/waiting_for_cross."""
        rule_id = "test_rule_1a1_b"
        user_id = "user_test_1a1_b"
        test_token = "valid_fcm_token_1234567890123456789012345678901234567890"

        alert = Alert(
            id=rule_id,
            user_id=user_id,
            exchange="binance",
            symbol="BTCUSDT",
            target_price=100.0,
            condition="ABOVE",
            last_eval_price=99.0,
            last_eval_asof=int(time.time()),
            waiting_for_cross=True,
            fcm_token=test_token,
            is_active=True
        )
        storage.ALERTS_DB.append(alert)

        # Sync changes target 100 -> 105
        sync_payload = {
            "user_id": user_id,
            "fcm_token": test_token,
            "alerts": [{
                "id": rule_id,
                "user_id": user_id,
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "target_price": 105.0,
                "condition": "ABOVE",
                "fcm_token": test_token
            }]
        }
        with patch("app.routes.alerts.save_alerts_to_disk_async", new_callable=AsyncMock):
            await sync_user_alerts(sync_payload)

        synced_alert = next((a for a in storage.ALERTS_DB if a.id == rule_id), None)
        self.assertIsNotNone(synced_alert)
        self.assertIsNone(synced_alert.last_eval_price)
        self.assertIsNone(synced_alert.last_eval_asof)
        self.assertFalse(synced_alert.waiting_for_cross)

    async def test_1a1_c_one_shot_already_triggered_stays_inactive_after_sync(self):
        """c) one-shot already triggered stays inactive after sync."""
        rule_id = "test_rule_1a1_c"
        user_id = "user_test_1a1_c"
        test_token = "valid_fcm_token_1234567890123456789012345678901234567890"

        # Already triggered one-shot alert is inactive
        alert = Alert(
            id=rule_id,
            user_id=user_id,
            exchange="nobitex",
            symbol="USDTIRT",
            target_price=70000.0,
            condition="ABOVE",
            trigger_mode="oneShot",
            is_active=False,
            last_triggered_at=time.time() - 100,
            fcm_token=test_token
        )
        storage.ALERTS_DB.append(alert)

        # Incoming sync payload attempts to pass is_active=True
        sync_payload = {
            "user_id": user_id,
            "fcm_token": test_token,
            "alerts": [{
                "id": rule_id,
                "user_id": user_id,
                "exchange": "nobitex",
                "symbol": "USDTIRT",
                "target_price": 70000.0,
                "condition": "ABOVE",
                "trigger_mode": "oneShot",
                "is_active": True,
                "fcm_token": test_token
            }]
        }
        with patch("app.routes.alerts.save_alerts_to_disk_async", new_callable=AsyncMock):
            await sync_user_alerts(sync_payload)

        synced_alert = next((a for a in storage.ALERTS_DB if a.id == rule_id), None)
        self.assertIsNotNone(synced_alert)
        self.assertFalse(synced_alert.is_active, "One-shot already triggered must stay inactive after sync")

    def test_1a1_d_trigger_signature_normalization(self):
        """d) payload identical except condition letter case / numeric string -> signature equal."""
        item1 = {
            "exchange": "Binance ",
            "symbol": "btcusdt",
            "condition": "above",
            "condition_type": "priceThreshold",
            "target_price": "100.5",
            "percent": "5.0",
            "base_price": "95.0",
            "direction": "above",
            "alert_nature": "price"
        }
        item2 = {
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "condition": "ABOVE",
            "condition_type": "priceThreshold",
            "target_price": 100.5,
            "percent": 5.0,
            "base_price": 95.0,
            "direction": "above",
            "alert_nature": "price"
        }
        sig1 = _trigger_signature(item1)
        sig2 = _trigger_signature(item2)
        self.assertEqual(sig1, sig2)
        self.assertEqual(trigger_signature(item1), trigger_signature(item2))

    # -------------------------------------------------------------
    # 1A-2 Tests
    # -------------------------------------------------------------

    async def test_1a2_unregistered_and_invalid_token_blocking_and_resume(self):
        """UNREGISTERED: FCM called once, second worker tick does not call it, entry kept, token not wiped; new token calls again."""
        rule_id = "test_rule_1a2"
        dead_token = "dead_token_1234567890123456789012345678901234567890"
        alert = Alert(
            id=rule_id,
            user_id="user_1a2",
            exchange="binance",
            symbol="ETHUSDT",
            target_price=3500.0,
            fcm_token=dead_token
        )
        storage.ALERTS_DB.append(alert)

        eid = "eid_unregistered_phase1"
        now = time.time()
        outbox.OUTBOX[eid] = {
            "id": eid,
            "alert_id": alert.id,
            "token": dead_token,
            "title": "Alert Triggered",
            "body": "ETH reached target",
            "data": {},
            "created_at": now,
            "expires_at": now + 3600,
            "next_attempt_at": now,
            "attempts": 0,
            "last_error": "",
            "blocked_token": None,
        }

        with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_send, \
             patch("app.notifier.outbox._save_outbox", new_callable=AsyncMock):
            mock_send.return_value = (False, "UNREGISTERED")

            # 1. First deliver call
            await outbox._deliver_outbox_entry(eid)
            self.assertEqual(mock_send.call_count, 1)
            self.assertIn(eid, outbox.OUTBOX, "Entry must NOT be dropped")
            self.assertEqual(alert.fcm_token, dead_token, "Token must NOT be blanked in alert")
            self.assertEqual(outbox.OUTBOX[eid]["blocked_token"], dead_token)
            self.assertGreater(state.METRICS["fcm_invalid_token"], 0)
            self.assertEqual(state.METRICS["outbox_blocked"], 1)

            # 2. Second worker tick (entry due, but token is still blocked)
            outbox.OUTBOX[eid]["next_attempt_at"] = time.time() - 1
            await outbox._deliver_outbox_entry(eid)
            # FCM must NOT be called again
            self.assertEqual(mock_send.call_count, 1)

            # 3. New token syncs for this alert
            new_token = "fresh_new_token_1234567890123456789012345678901234567890"
            alert.fcm_token = new_token
            mock_send.return_value = (True, "FCM Message ID: delivered_ok")

            await outbox._deliver_outbox_entry(eid)
            self.assertEqual(mock_send.call_count, 2)
            self.assertNotIn(eid, outbox.OUTBOX, "Delivered entry should be removed")

    async def test_1a2_invalid_payload_keeps_token_and_retries(self):
        """INVALID_PAYLOAD: token kept, retried with backoff, fcm_failed incremented."""
        rule_id = "test_rule_1a2_payload"
        token = "valid_token_1234567890123456789012345678901234567890"
        alert = Alert(
            id=rule_id,
            user_id="user_1a2_payload",
            exchange="binance",
            symbol="ETHUSDT",
            target_price=3500.0,
            fcm_token=token
        )
        storage.ALERTS_DB.append(alert)

        eid = "eid_invalid_payload_phase1"
        now = time.time()
        outbox.OUTBOX[eid] = {
            "id": eid,
            "alert_id": alert.id,
            "token": token,
            "title": "Alert Triggered",
            "body": "ETH reached target",
            "data": {},
            "created_at": now,
            "expires_at": now + 3600,
            "next_attempt_at": now,
            "attempts": 0,
            "last_error": "",
            "blocked_token": None,
        }

        with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_send, \
             patch("app.notifier.outbox._save_outbox", new_callable=AsyncMock):
            mock_send.return_value = (False, "INVALID_PAYLOAD")

            await outbox._deliver_outbox_entry(eid)

            self.assertIn(eid, outbox.OUTBOX)
            self.assertEqual(alert.fcm_token, token)
            self.assertEqual(outbox.OUTBOX[eid]["attempts"], 1)
            self.assertEqual(outbox.OUTBOX[eid]["last_error"], "INVALID_PAYLOAD")
            self.assertIsNone(outbox.OUTBOX[eid].get("blocked_token"))

    # -------------------------------------------------------------
    # 1A-3 Test
    # -------------------------------------------------------------

    async def test_1a3_lifespan_startup_completes_in_under_1s_without_blocking_on_notifications(self):
        """Test: with send_telegram_alert patched to sleep 30s, lifespan startup completes in <1s and price job is registered."""
        async def slow_send_telegram(client, chat_id, msg):
            await asyncio.sleep(30)

        with patch("server.send_telegram_alert", side_effect=slow_send_telegram), \
             patch("app.engine.market_events.send_telegram_alert", side_effect=slow_send_telegram), \
             patch("server.init_telegram_bot", new_callable=AsyncMock), \
             patch("server.telegram_bot_polling_loop", new_callable=AsyncMock), \
             patch("server.outbox_worker_loop", new_callable=AsyncMock):

            t0 = time.time()
            async with lifespan(app):
                elapsed = time.time() - t0

                # Must complete startup in < 1s
                self.assertLess(elapsed, 1.0, f"Startup took {elapsed:.2f}s, must be <1.0s")

                # The price alerts job must be registered on scheduler
                job = scheduler.get_job('price_alerts_job')
                self.assertIsNotNone(job, "price_alerts_job must be registered on scheduler")

    # -------------------------------------------------------------
    # 7. Additional Verification Tests
    # -------------------------------------------------------------

    def test_7a_fcm_exception_classification(self):
        """7a: call fcm._send_fcm_sync with firebase_admin._apps patched non-empty and messaging.send patched to raise
        the REAL classes messaging.UnregisteredError, messaging.SenderIdMismatchError,
        firebase_admin.exceptions.InvalidArgumentError, messaging.QuotaExceededError (patch time.sleep).
        Assert returns 'UNREGISTERED', 'UNREGISTERED', 'INVALID_PAYLOAD', and a non-code error string.
        """
        import firebase_admin
        from firebase_admin import messaging, exceptions as fb_exceptions
        from app.notifier.fcm import _send_fcm_sync

        test_token = "valid_fcm_token_1234567890123456789012345678901234567890"

        with patch.object(firebase_admin, "_apps", {"[DEFAULT]": True}), patch("time.sleep"):
            # 1. UnregisteredError -> UNREGISTERED
            with patch.object(messaging, "send", side_effect=messaging.UnregisteredError("App instance unregistered")):
                ok, msg = _send_fcm_sync(test_token, "Title", "Body")
                self.assertFalse(ok)
                self.assertEqual(msg, "UNREGISTERED")

            # 2. SenderIdMismatchError -> UNREGISTERED
            with patch.object(messaging, "send", side_effect=messaging.SenderIdMismatchError("Sender ID mismatch")):
                ok, msg = _send_fcm_sync(test_token, "Title", "Body")
                self.assertFalse(ok)
                self.assertEqual(msg, "UNREGISTERED")

            # 3. InvalidArgumentError -> INVALID_PAYLOAD
            with patch.object(messaging, "send", side_effect=fb_exceptions.InvalidArgumentError("Invalid argument in payload")):
                ok, msg = _send_fcm_sync(test_token, "Title", "Body")
                self.assertFalse(ok)
                self.assertEqual(msg, "INVALID_PAYLOAD")

            # 4. QuotaExceededError -> non-code error string
            with patch.object(messaging, "send", side_effect=messaging.QuotaExceededError("FCM quota exceeded")):
                ok, msg = _send_fcm_sync(test_token, "Title", "Body")
                self.assertFalse(ok)
                self.assertNotIn(msg, ("UNREGISTERED", "INVALID_PAYLOAD", "INVALID_TOKEN_FORMAT"))
                self.assertIn("quota", msg.lower())

    def test_7b_metrics_removed_and_status_unauthorized(self):
        """7b: GET /metrics must return 404 (route removed) and /api/status without admin key must NOT return 200."""
        from fastapi.testclient import TestClient
        client = TestClient(app)

        res_metrics = client.get("/metrics")
        self.assertEqual(res_metrics.status_code, 404)

        res_api_metrics = client.get("/api/metrics")
        self.assertEqual(res_api_metrics.status_code, 404)

        res_status = client.get("/api/status")
        self.assertNotEqual(res_status.status_code, 200)

    async def test_7c_second_trigger_on_dead_tokens_does_not_call_fcm(self):
        """7c: a second trigger for an alert whose token is in DEAD_TOKENS must not call send_fcm_notification_async."""
        dead_token = "dead_token_1234567890123456789012345678901234567890"
        alert = Alert(
            id="alert_dead_token_test",
            user_id="user_test_dead",
            exchange="binance",
            symbol="BTCUSDT",
            target_price=50000.0,
            fcm_token=dead_token
        )
        storage.ALERTS_DB.append(alert)

        with patch("app.notifier.outbox.send_fcm_notification_async", new_callable=AsyncMock) as mock_send, \
             patch("app.notifier.outbox._save_outbox", new_callable=AsyncMock):
            mock_send.return_value = (False, "UNREGISTERED")

            # 1. First trigger: calls FCM and gets UNREGISTERED -> adds dead_token to DEAD_TOKENS
            await outbox.enqueue_alert_push(alert, "Title 1", "Body 1", {})
            # Wait for spawned task
            await asyncio.sleep(0.01)
            self.assertEqual(mock_send.call_count, 1)
            self.assertIn(dead_token, outbox.DEAD_TOKENS)

            # 2. Second trigger for the same alert (whose token is in DEAD_TOKENS)
            await outbox.enqueue_alert_push(alert, "Title 2", "Body 2", {})
            await asyncio.sleep(0.01)

            # Must NOT call send_fcm_notification_async again
            self.assertEqual(mock_send.call_count, 1)


if __name__ == "__main__":
    unittest.main()
