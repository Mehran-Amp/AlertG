import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.notifier import journal
from app.state import METRICS
from server import app


class TestDeliveryAckEndpoint(unittest.TestCase):
    def setUp(self):
        self._orig_journal = dict(journal.JOURNAL)
        self._orig_metrics = dict(METRICS)
        journal.JOURNAL.clear()
        self.client = TestClient(app)
        self._api_key_patch = patch("app.config.API_KEY", "testkey123")
        self._api_key_patch.start()

    def tearDown(self):
        self._api_key_patch.stop()
        journal.JOURNAL.clear()
        journal.JOURNAL.update(self._orig_journal)
        METRICS.clear()
        METRICS.update(self._orig_metrics)

    def _auth_headers(self):
        return {"X-API-Key": "testkey123"}

    def test_ack_known_delivery_marks_acked(self):
        journal.record_queued("d-123", "alert-1")
        with patch("app.notifier.journal._save_journal"):
            res = self.client.post("/api/deliveries/d-123/ack", headers=self._auth_headers())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "acked")
        self.assertEqual(journal.get_status("d-123"), "acked")

    def test_ack_unknown_delivery_returns_unknown(self):
        res = self.client.post("/api/deliveries/does-not-exist/ack", headers=self._auth_headers())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "unknown")

    def test_ack_requires_api_key(self):
        journal.record_queued("d-456", "alert-2")
        with patch("app.notifier.journal._save_journal"):
            res = self.client.post("/api/deliveries/d-456/ack")  # no header
        self.assertIn(res.status_code, (401, 403, 503))
        self.assertEqual(journal.get_status("d-456"), "queued")

    def test_repeated_ack_counts_once_in_metric(self):
        journal.record_queued("d-789", "alert-3")
        before = METRICS.get("fcm_acked", 0)
        with patch("app.notifier.journal._save_journal"):
            for _ in range(3):
                res = self.client.post("/api/deliveries/d-789/ack", headers=self._auth_headers())
                self.assertEqual(res.status_code, 200)
        self.assertEqual(METRICS.get("fcm_acked", 0), before + 1)


if __name__ == "__main__":
    unittest.main()