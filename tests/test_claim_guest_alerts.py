"""SYNC-3: claim_guest_alerts must not deadlock when saving under _db_lock."""
import asyncio
import pytest


class TestClaimGuestAlerts:
    @pytest.mark.asyncio
    async def test_claim_completes_within_timeout(self, monkeypatch):
        import app.routes.alerts as alerts_mod
        import app.storage as storage
        from app.models import Alert

        fake_alert = Alert(
            id="guest_claim_test",
            user_id="user_default",
            symbol="BTCUSDT",
            exchange="binance",
            condition="ABOVE",
            target_price=100.0,
            fcm_token="x" * 60,
            is_active=True,
        )
        monkeypatch.setattr(storage, "ALERTS_DB", [fake_alert])

        payload = {"user_id": "real_user_claim", "fcm_token": "x" * 60}
        result = await asyncio.wait_for(
            alerts_mod.claim_guest_alerts(payload), timeout=1.0
        )
        assert result["claimed_count"] == 1
        assert fake_alert.user_id == "real_user_claim"