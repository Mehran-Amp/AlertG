#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit and Integration Tests for Telegram User Privacy & Chat ID Isolation:
- Verifies that chat IDs are strictly scoped to their respective users (user_id).
- Confirms zero leakage of telegram_chat_id between different user accounts.
- Confirms that users without a Telegram chat ID receive telegram_chat_id=None and is_connected=False.
- Confirms removal of all fallbacks to other users' alerts, user_default, and @aegkalair_bot.
"""

import sys
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

# Offline mock setup for test execution in any environment
for mod in [
    'fastapi', 'fastapi.middleware.cors', 'fastapi.responses', 'pydantic', 'httpx',
    'apscheduler', 'apscheduler.schedulers', 'apscheduler.schedulers.asyncio',
    'firebase_admin', 'firebase_admin.credentials', 'firebase_admin.messaging', 'firebase_admin.exceptions'
]:
    if mod not in sys.modules:
        m = MagicMock()
        if mod == 'fastapi':
            class HTTPException(Exception):
                def __init__(self, status_code=400, detail=""):
                    super().__init__(detail)
                    self.status_code = status_code
                    self.detail = detail
            m.HTTPException = HTTPException
            class APIRouter:
                def get(self, *args, **kwargs):
                    def decorator(f): return f
                    return decorator
                def post(self, *args, **kwargs):
                    def decorator(f): return f
                    return decorator
                def delete(self, *args, **kwargs):
                    def decorator(f): return f
                    return decorator
                def include_router(self, *args, **kwargs): pass
            m.APIRouter = APIRouter
        elif mod == 'pydantic':
            class BaseModel:
                def __init__(self, **kwargs):
                    for k, v in kwargs.items():
                        setattr(self, k, v)
                def dict(self): return self.__dict__
                def model_dump(self): return self.__dict__
            m.BaseModel = BaseModel
            m.Field = lambda *args, **kwargs: kwargs.get('default', None)
        sys.modules[mod] = m

import app.storage as storage
from app.models import Alert, UserTelegramUpdateRequest, AlertCreate
from app.routes.user import get_user_telegram_status, update_user_telegram_status
from app.routes.alerts import create_alert, get_user_alerts
import app.state as state


class TestTelegramUserIsolation(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self._orig_alerts = list(storage.ALERTS_DB)
        self._orig_profiles = dict(storage.USER_PROFILES_DB)
        storage.ALERTS_DB.clear()
        storage.USER_PROFILES_DB.clear()

    async def asyncTearDown(self):
        storage.ALERTS_DB.clear()
        storage.ALERTS_DB.extend(self._orig_alerts)
        storage.USER_PROFILES_DB.clear()
        storage.USER_PROFILES_DB.update(self._orig_profiles)

    async def test_no_leakage_between_two_users_in_telegram_status(self):
        """User A has a connected chat ID; User B query must return disconnected and null chat_id."""
        # Setup User A with a valid chat_id
        await update_user_telegram_status(
            user_id="user_alpha",
            req=UserTelegramUpdateRequest(chat_id="111222333", is_connected=True)
        )

        # Populate a user_default profile as well
        storage.USER_PROFILES_DB["user_default"] = {
            "user_id": "user_default",
            "telegram_chat_id": "999888777",
            "is_connected": True
        }

        # Query User B status (User B has never set a chat id)
        status_b = await get_user_telegram_status("user_beta")

        self.assertEqual(status_b["user_id"], "user_beta")
        self.assertIsNone(status_b["telegram_chat_id"], "User B must NOT inherit User A's or default chat ID")
        self.assertFalse(status_b["is_connected"], "User B must have is_connected=False")
        self.assertNotEqual(status_b["telegram_chat_id"], "111222333")
        self.assertNotEqual(status_b["telegram_chat_id"], "999888777")
        self.assertNotEqual(status_b["telegram_chat_id"], "@aegkalair_bot")

    async def test_alert_registration_telegram_confirmation_does_not_leak_chat_id(self):
        """When User B creates an alert without a chat ID, User A's chat ID is NEVER messaged."""
        # User A has connected telegram
        storage.USER_PROFILES_DB["user_alpha"] = {
            "user_id": "user_alpha",
            "telegram_chat_id": "111222333",
            "is_connected": True
        }
        # User A also has an alert with chat_id in DB
        storage.ALERTS_DB.append(Alert(
            id="alert_a_1",
            user_id="user_alpha",
            symbol="BTCUSDT",
            exchange="binance",
            target_price=70000.0,
            condition="ABOVE",
            is_active=True,
            telegram_chat_id="111222333"
        ))

        state.http_client = AsyncMock()
        with patch("app.routes.alerts.send_telegram_alert", new_callable=AsyncMock) as mock_send_tg:
            # User B creates an alert without chat_id
            alert_b_input = AlertCreate(
                user_id="user_beta",
                symbol="ETHUSDT",
                exchange="binance",
                target_price=3500.0,
                condition="ABOVE",
                telegram_chat_id=None
            )
            created_alert = await create_alert(alert_b_input)

            # Assert telegram alert was NOT sent to User A's chat ID
            mock_send_tg.assert_not_called()
            self.assertIsNone(created_alert.telegram_chat_id)

    async def test_restore_alerts_does_not_adopt_other_user_or_bot_chat_id(self):
        """Restoring alerts for User B must never set User B profile to User A's chat_id or @aegkalair_bot."""
        # User A in DB
        storage.ALERTS_DB.append(Alert(
            id="alert_a_1",
            user_id="user_alpha",
            symbol="BTCUSDT",
            exchange="binance",
            target_price=70000.0,
            condition="ABOVE",
            is_active=True,
            telegram_chat_id="111222333"
        ))
        storage.USER_PROFILES_DB["user_default"] = {
            "user_id": "user_default",
            "telegram_chat_id": "999888777",
            "is_connected": True
        }

        # User B has an alert with NO chat_id
        storage.ALERTS_DB.append(Alert(
            id="alert_b_1",
            user_id="user_beta",
            symbol="EURUSD",
            exchange="forex",
            target_price=1.10,
            condition="ABOVE",
            is_active=True,
            telegram_chat_id=None
        ))

        # Query User B alerts
        b_alerts = await get_user_alerts("user_beta")
        self.assertEqual(len(b_alerts), 1)

        # Profile for User B should NOT have been created with User A's or bot's chat id
        prof_b = storage.USER_PROFILES_DB.get("user_beta")
        if prof_b:
            self.assertIsNone(prof_b.get("telegram_chat_id"))
            self.assertFalse(prof_b.get("is_connected", False))


if __name__ == "__main__":
    unittest.main()
