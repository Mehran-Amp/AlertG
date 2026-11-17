# -*- coding: utf-8 -*-
"""IB-9b: the crypto validator must not run on Bourse (tsetmc) alerts; other markets keep it."""
from unittest.mock import patch

import app.config as config
from test_iran_bourse_api import Base, body, AYAR, H


class TestCryptoValidatorSkipsBourse(Base):
    def post(self, **kw):
        return self.http.post("/api/alerts", headers=H, json=body(**kw))

    def sync(self, items):
        return self.http.post("/api/alerts/sync", headers=H,
                              json={"user_id": "u1", "fcm_token": "x" * 20, "sync_mode": "merge", "alerts": items})

    def test_create_has_no_crypto_warning_in_warn_and_enforce_modes(self):
        for i, mode in enumerate(("warn", "enforce", "true")):
            with patch.object(config, "CRYPTO_VALIDATE_ALERTS", mode):
                r = self.post(id=f"b{i}")
                self.assertEqual(r.status_code, 200, f"{mode}: {r.text}")
                self.assertIsNone(r.json()["warning"], mode)
                self.assertNotIn("x-alert-warning", {k.lower() for k in r.headers}, mode)
        self.assertEqual(len(self.alerts_db), 3)

    def test_crypto_alerts_are_still_validated(self):
        with patch.object(config, "CRYPTO_VALIDATE_ALERTS", "enforce"):
            r = self.http.post("/api/alerts", headers=H,
                               json=body(exchange="notanexchange", symbol="BTCUSDT", target_price=1.0))
            self.assertEqual(r.status_code, 400, r.text)
            self.assertIn("EXCHANGE_NOT_SUPPORTED", r.json()["detail"])
        with patch.object(config, "CRYPTO_VALIDATE_ALERTS", "warn"):
            r = self.http.post("/api/alerts", headers=H,
                               json=body(id="w1", exchange="notanexchange", symbol="BTCUSDT", target_price=1.0))
            self.assertEqual(r.status_code, 200, r.text)
            self.assertIn("EXCHANGE_NOT_SUPPORTED", r.json()["warning"])

    def test_sync_keeps_bourse_items_in_enforce_mode_and_still_drops_bad_crypto(self):
        with patch.object(config, "CRYPTO_VALIDATE_ALERTS", "enforce"):
            r = self.sync([body(id="ok1"),
                           body(id="bad1", exchange="notanexchange", symbol="BTCUSDT", target_price=1.0)])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([a.id for a in self.alerts_db], ["ok1"])
        warned = {w["id"] for w in r.json().get("warnings", [])}
        self.assertEqual(warned, {"bad1"})                 # only the crypto item is reported

    def test_sync_in_warn_mode_adds_no_warning_to_bourse_item(self):
        with patch.object(config, "CRYPTO_VALIDATE_ALERTS", "warn"):
            r = self.sync([body(id="ok1")])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("warnings", r.json())
        self.assertIsNone(self.alerts_db[0].warning)
