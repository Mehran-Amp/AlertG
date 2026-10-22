import os
import json
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from server import app
from app.routes import devices
import app.config as config
import server


class TestDeviceHeartbeat(unittest.TestCase):
    def setUp(self):
        self._orig_file = devices.DEVICE_HEALTH_FILE
        self._orig_health = dict(devices.DEVICE_HEALTH)
        self._tmp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp_file.close()

        devices.DEVICE_HEALTH_FILE = self._tmp_file.name
        devices.DEVICE_HEALTH.clear()

        self.api_key = "test_device_api_key_123"
        self.headers = {"X-API-Key": self.api_key}

    def tearDown(self):
        devices.DEVICE_HEALTH_FILE = self._orig_file
        devices.DEVICE_HEALTH.clear()
        devices.DEVICE_HEALTH.update(self._orig_health)

        for p in (self._tmp_file.name, self._tmp_file.name + ".tmp", self._tmp_file.name + ".bad"):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass

    def test_post_device_heartbeat_stores_and_persists(self):
        """1. POST /api/device/heartbeat records indicators and persists atomically to disk (Phase 3A-1)."""
        with patch.object(config, "API_KEY", self.api_key), \
             patch.object(server, "API_KEY", self.api_key):
            client = TestClient(app)
            payload = {
                "user_id": "trader_device_1",
                "fcm_token_tail": "abcdef123456",  # tail > 6 should truncate to last 6
                "app_version": "2.4.0",
                "notifications_enabled": True,
                "battery_unrestricted": True,
                "fgs_running": True,
                "ts_ms": 1729000000000
            }
            res = client.post("/api/device/heartbeat", json=payload, headers=self.headers)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(data.get("user_id"), "trader_device_1")
            self.assertIn("received_at", data)

            # In-memory record check
            record = devices.DEVICE_HEALTH.get("trader_device_1")
            self.assertIsNotNone(record)
            self.assertEqual(record["fcm_token_tail"], "123456")
            self.assertEqual(record["app_version"], "2.4.0")
            self.assertTrue(record["battery_unrestricted"])

            # Verify persisted to disk
            with open(devices.DEVICE_HEALTH_FILE, "r", encoding="utf-8") as f:
                disk_data = json.load(f)
            self.assertIn("trader_device_1", disk_data)
            self.assertEqual(disk_data["trader_device_1"]["fcm_token_tail"], "123456")

    def test_get_device_health_returns_latest_state(self):
        """2. GET /api/device/health/{user_id} returns latest record and age_seconds (Phase 3A-1)."""
        with patch.object(config, "API_KEY", self.api_key), \
             patch.object(server, "API_KEY", self.api_key):
            client = TestClient(app)

            # Seed heartbeat
            payload = {
                "user_id": "trader_active",
                "fcm_token_tail": "999888",
                "app_version": "2.4.1",
                "notifications_enabled": True,
                "battery_unrestricted": False,
                "fgs_running": True,
                "ts_ms": 1729500000000
            }
            post_res = client.post("/api/device/heartbeat", json=payload, headers=self.headers)
            self.assertEqual(post_res.status_code, 200)

            # Query health
            get_res = client.get("/api/device/health/trader_active", headers=self.headers)
            self.assertEqual(get_res.status_code, 200)
            data = get_res.json()
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(data["data"]["user_id"], "trader_active")
            self.assertEqual(data["data"]["fcm_token_tail"], "999888")
            self.assertIn("age_seconds", data)
            self.assertGreaterEqual(data["age_seconds"], 0)

    def test_unknown_user_returns_404_and_auth_enforced(self):
        """3. GET unknown user returns 404 and missing API key is rejected (Phase 3A-1)."""
        with patch.object(config, "API_KEY", self.api_key), \
             patch.object(server, "API_KEY", self.api_key):
            client = TestClient(app)

            # 1. Unknown user -> 404
            res_404 = client.get("/api/device/health/non_existent_trader", headers=self.headers)
            self.assertEqual(res_404.status_code, 404)

            # 2. Unauthorized request -> rejection
            res_unauth = client.post("/api/device/heartbeat", json={"user_id": "u1"})
            self.assertIn(res_unauth.status_code, (401, 503))


if __name__ == "__main__":
    unittest.main()
