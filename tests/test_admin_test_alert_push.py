"""TEST-1: /api/admin/test/alert-push must enqueue a synthetic alert through
the real outbox pipeline and return a delivery_id that can be acked."""
import pytest
from fastapi.testclient import TestClient


class TestAdminTestAlertPush:
    def test_queues_alert_with_delivery_id(self, monkeypatch):
        # Mock FCM to succeed
        async def fake_send(**kwargs):
            return True, "MOCK_OK"
        import app.notifier.outbox as outbox_mod
        monkeypatch.setattr(outbox_mod, "send_fcm_notification_async", fake_send)

        # Add a fake alert with FCM token to ALERTS_DB
        import app.storage as storage
        from app.models import Alert
        fake_alert = Alert(
            id="test_alert_1",
            user_id="test_user",
            symbol="BTCUSDT",
            exchange="binance",
            condition="ABOVE",
            target_price=100.0,
            fcm_token="x" * 60,
            is_active=True,
        )
        storage.ALERTS_DB.append(fake_alert)

        import server
        client = TestClient(server.app)
        # Bypass ADMIN_DEP
        from app.security import require_admin
        server.app.dependency_overrides[require_admin] = lambda: None
        try:
            r = client.post("/api/admin/test/alert-push?user_id=test_user")
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "queued"
            assert data["delivery_id"] is not None
            assert data["token_tail"].endswith("xxxxxx")
        finally:
            server.app.dependency_overrides.clear()
            storage.ALERTS_DB.remove(fake_alert)

    def test_returns_400_without_token(self):
        import server
        from app.security import require_admin
        server.app.dependency_overrides[require_admin] = lambda: None
        client = TestClient(server.app)
        try:
            r = client.post("/api/admin/test/alert-push?user_id=no_such_user_xyz")
            assert r.status_code == 400
        finally:
            server.app.dependency_overrides.clear()


        def test_chat_id_propagated_to_outbox(self, monkeypatch):
            """TEST-1c: the provided chat_id must be stored on the outbox entry
            as fallback_chat_id."""
            async def fake_send(**kwargs):
                return True, "MOCK_OK"
            import app.notifier.outbox as outbox_mod
            monkeypatch.setattr(outbox_mod, "send_fcm_notification_async", fake_send)

            import app.storage as storage
            from app.models import Alert
            fake_alert = Alert(
                id="test_alert_chat_id",
                user_id="test_user_chat",
                symbol="BTCUSDT",
                exchange="binance",
                condition="ABOVE",
                target_price=100.0,
                fcm_token="x" * 60,
                is_active=True,
            )
            storage.ALERTS_DB.append(fake_alert)

            import server
            from app.security import require_admin
            server.app.dependency_overrides[require_admin] = lambda: None
            client = TestClient(server.app)
            try:
                r = client.post(
                    "/api/admin/test/alert-push?user_id=test_user_chat&chat_id=123456789"
                )
                assert r.status_code == 200
                data = r.json()
                delivery_id = data["delivery_id"]
                # Check the outbox entry
                entry = outbox_mod.OUTBOX.get(delivery_id)
                assert entry is not None
                assert entry.get("fallback_chat_id") == "123456789"
            finally:
                server.app.dependency_overrides.clear()
                storage.ALERTS_DB.remove(fake_alert)