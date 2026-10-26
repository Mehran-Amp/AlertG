"""SYNC-1b: sync_mode ('mirror' default, 'merge') controls delete vs upsert."""
import pytest


class TestSyncMode:
    @pytest.mark.asyncio
    async def test_merge_with_empty_list_does_not_delete(self, monkeypatch):
        import app.routes.alerts as alerts_mod
        import app.storage as storage
        from app.models import Alert

        monkeypatch.setattr(storage, "ALERTS_DB", [
            Alert(id="a1", user_id="merge_user", symbol="BTCUSDT", exchange="binance", condition="ABOVE", target_price=100.0, fcm_token="x" * 60),
        ])
        payload = {"user_id": "merge_user", "fcm_token": "x" * 60, "alerts": [], "sync_mode": "merge"}
        result = await alerts_mod.sync_user_alerts(payload)
        assert result["count"] == 0
        assert result["mode"] == "merge"
        # Alert must still be there
        assert len(storage.ALERTS_DB) == 1
        assert storage.ALERTS_DB[0].id == "a1"

    @pytest.mark.asyncio
    async def test_mirror_with_empty_list_deletes(self, monkeypatch):
        import app.routes.alerts as alerts_mod
        import app.storage as storage
        from app.models import Alert

        monkeypatch.setattr(storage, "ALERTS_DB", [
            Alert(id="a1", user_id="mirror_user", symbol="BTCUSDT", exchange="binance", condition="ABOVE", target_price=100.0, fcm_token="x" * 60),
        ])
        payload = {"user_id": "mirror_user", "fcm_token": "x" * 60, "alerts": [], "sync_mode": "mirror"}
        result = await alerts_mod.sync_user_alerts(payload)
        assert result["mode"] == "mirror"
        # Alert must be gone
        assert len(storage.ALERTS_DB) == 0

    @pytest.mark.asyncio
    async def test_merge_upserts_and_keeps_others(self, monkeypatch):
        import app.routes.alerts as alerts_mod
        import app.storage as storage
        from app.models import Alert

        monkeypatch.setattr(storage, "ALERTS_DB", [
            Alert(id="a1", user_id="merge_user2", symbol="BTCUSDT", exchange="binance", condition="ABOVE", target_price=100.0, fcm_token="x" * 60),
            Alert(id="a2", user_id="merge_user2", symbol="ETHUSDT", exchange="binance", condition="ABOVE", target_price=200.0, fcm_token="x" * 60),
        ])
        payload = {
            "user_id": "merge_user2",
            "fcm_token": "x" * 60,
            "alerts": [
                {"id": "a1", "exchange": "binance", "symbol": "BTCUSDT", "target_price": 150.0, "condition": "ABOVE", "fcm_token": "x" * 60},
                {"id": "a3", "exchange": "binance", "symbol": "SOLUSDT", "target_price": 50.0, "condition": "ABOVE", "fcm_token": "x" * 60},
            ],
            "sync_mode": "merge",
        }
        result = await alerts_mod.sync_user_alerts(payload)
        assert result["count"] == 2
        assert result["mode"] == "merge"
        # a1 updated to 150, a2 kept, a3 added
        ids = {a.id: a for a in storage.ALERTS_DB}
        assert len(ids) == 3
        assert ids["a1"].target_price == 150.0
        assert ids["a2"].target_price == 200.0
        assert ids["a3"].symbol == "SOLUSDT"