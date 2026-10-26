"""SYNC-1a: sync_user_alerts must back up user alerts before a destructive
sync (fewer alerts than current) and not otherwise."""
import json
import pytest


class TestSyncBackup:
    @pytest.mark.asyncio
    async def test_backup_created_on_shrink(self, monkeypatch, tmp_path):
        import app.routes.alerts as alerts_mod
        import app.storage as storage
        from app.models import Alert

        monkeypatch.setattr(alerts_mod, "DATA_DIR", str(tmp_path))
        monkeypatch.setattr(storage, "ALERTS_DB", [
            Alert(id="a1", user_id="test_backup_user", symbol="BTCUSDT", exchange="binance", condition="ABOVE", target_price=100.0, fcm_token="x" * 60),
            Alert(id="a2", user_id="test_backup_user", symbol="ETHUSDT", exchange="binance", condition="ABOVE", target_price=200.0, fcm_token="x" * 60),
        ])

        payload = {"user_id": "test_backup_user", "fcm_token": "x" * 60, "alerts": []}
        await alerts_mod.sync_user_alerts(payload)

        backup_dir = tmp_path / "alerts_backup"
        files = list(backup_dir.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_no_backup_without_shrink(self, monkeypatch, tmp_path):
        import app.routes.alerts as alerts_mod
        import app.storage as storage
        from app.models import Alert

        monkeypatch.setattr(alerts_mod, "DATA_DIR", str(tmp_path))
        monkeypatch.setattr(storage, "ALERTS_DB", [
            Alert(id="a1", user_id="test_backup_user2", symbol="BTCUSDT", exchange="binance", condition="ABOVE", target_price=100.0, fcm_token="x" * 60),
        ])

        payload = {
            "user_id": "test_backup_user2",
            "fcm_token": "x" * 60,
            "alerts": [
                {"id": "a1", "exchange": "binance", "symbol": "BTCUSDT", "target_price": 100.0, "condition": "ABOVE", "fcm_token": "x" * 60},
                {"id": "a2", "exchange": "binance", "symbol": "ETHUSDT", "target_price": 200.0, "condition": "ABOVE", "fcm_token": "x" * 60},
            ],
        }
        await alerts_mod.sync_user_alerts(payload)

        backup_dir = tmp_path / "alerts_backup"
        files = list(backup_dir.glob("*.json")) if backup_dir.exists() else []
        assert len(files) == 0