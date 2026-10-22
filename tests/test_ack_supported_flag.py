import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.config import API_KEY
from app.models import Alert
from app import storage
from server import app


class TestAckSupportedFlag(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        storage.ALERTS_DB[:] = [
            a for a in storage.ALERTS_DB
            if a.id not in ("ack-1", "ack-2", "ack-3")
        ]

    def _auth_headers(self):
        return {"X-API-Key": API_KEY} if API_KEY else {}

    async def test_sync_with_flag_true_sets_ack_supported(self):
        payload = {
            "user_id": "user_ack_test",
            "fcm_token": "valid_fcm_token_1234567890123456789012345678901234567890",
            "ack_supported": True,
            "alerts": [{
                "id": "ack-1",
                "user_id": "user_ack_test",
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "target_price": 100.0,
                "condition": "ABOVE",
            }],
        }
        with patch("app.routes.alerts.save_alerts_to_disk_async", new_callable=AsyncMock):
            res = self.client.post("/api/alerts/sync", json=payload, headers=self._auth_headers())
        self.assertEqual(res.status_code, 200)
        found = [a for a in storage.ALERTS_DB if a.id == "ack-1"]
        self.assertTrue(found)
        self.assertTrue(found[0].ack_supported)

    async def test_sync_without_flag_defaults_false(self):
        payload = {
            "user_id": "user_ack_test2",
            "fcm_token": "valid_fcm_token_1234567890123456789012345678901234567890",
            "alerts": [{
                "id": "ack-2",
                "user_id": "user_ack_test2",
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "target_price": 100.0,
                "condition": "ABOVE",
            }],
        }
        with patch("app.routes.alerts.save_alerts_to_disk_async", new_callable=AsyncMock):
            res = self.client.post("/api/alerts/sync", json=payload, headers=self._auth_headers())
        self.assertEqual(res.status_code, 200)
        found = [a for a in storage.ALERTS_DB if a.id == "ack-2"]
        self.assertTrue(found)
        self.assertFalse(found[0].ack_supported)

    async def test_alert_round_trips_ack_supported_through_json(self):
        alert = Alert(
            id="ack-3",
            user_id="u",
            exchange="binance",
            symbol="BTCUSDT",
            target_price=1.0,
            condition="ABOVE",
            ack_supported=True,
            created_at="2026-01-01T00:00:00Z",
        )
        data = alert.model_dump()
        self.assertTrue(data["ack_supported"])
        back = Alert(**data)
        self.assertTrue(back.ack_supported)


if __name__ == "__main__":
    unittest.main()