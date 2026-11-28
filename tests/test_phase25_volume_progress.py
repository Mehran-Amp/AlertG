# -*- coding: utf-8 -*-
"""
Phase 25a — Server exposes current traded volume (`current_volume`) on Iran Bourse
alert responses (`GET /api/alerts/{user_id}` and `POST /api/alerts`) so the mobile
app can render an honest `currentVolume / targetVolume` progress bar for `volumeAbove`.
"""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.markets.iran_bourse.alert_rules import (
    current_volume_for_alert,
    evaluate_special_alert,
)
from app.markets.iran_bourse.snapshot import BourseSnapshotStore
from app.models import Alert
from app.routes.alerts import _to_alert_public, get_user_alerts


def _make_bourse_volume_alert(
    alert_id: str = "vol-alert-1",
    user_id: str = "user_p25@example.com",
    symbol: str = "35425587644337450",
    target_volume: float = 10_000_000.0,
    last_eval_volume=None,
) -> Alert:
    return Alert(
        id=alert_id,
        user_id=user_id,
        exchange="tsetmc",
        symbol=symbol,
        target_price=target_volume,
        condition="ABOVE",
        condition_type="volumeAbove",
        direction="above",
        fcm_token="secret-fcm-token-must-not-leak",
        created_at="2026-11-28T10:00:00+00:00",
        last_eval_volume=last_eval_volume,
    )


class TestPhase25aCurrentVolumeExposure(unittest.TestCase):
    def test_25a_current_volume_reads_live_poller_snapshot_first(self):
        store = BourseSnapshotStore(stale_seconds=60.0)
        store.set_watched(["35425587644337450"])
        store.apply(
            [{"id": "35425587644337450", "volume": 3_500_000}],
            {"seq": 10, "stale": False},
        )
        fake_poller = SimpleNamespace(store=store)
        alert = _make_bourse_volume_alert(last_eval_volume=1_200_000.0)

        with patch("app.markets.iran_bourse.poller.BOURSE_POLLER", fake_poller):
            self.assertEqual(current_volume_for_alert(alert), 3_500_000.0)
            pub = _to_alert_public(alert)
            self.assertEqual(pub.current_volume, 3_500_000.0)
            dumped = pub.model_dump() if hasattr(pub, "model_dump") else pub.dict()
            self.assertNotIn("fcm_token", dumped)

    def test_25a_falls_back_to_last_eval_volume_and_handles_zero(self):
        alert = _make_bourse_volume_alert()
        meta = {
            "alert_eligible": True,
            "is_stale": False,
            "carried_over": False,
            "state": "OPEN",
            "traded_today": True,
            "volume": 4_250_000,
        }
        triggered, _, _ = evaluate_special_alert(alert, 5_000.0, meta)
        self.assertFalse(triggered)
        self.assertEqual(alert.last_eval_volume, 4_250_000.0)

        # When poller is absent, current_volume falls back to alert.last_eval_volume
        with patch("app.markets.iran_bourse.poller.BOURSE_POLLER", None):
            self.assertEqual(current_volume_for_alert(alert), 4_250_000.0)

        # Zero volume (untraded session) is preserved honestly as 0.0, not None
        store = BourseSnapshotStore(stale_seconds=60.0)
        store.set_watched(["35425587644337450"])
        store.apply([{"id": "35425587644337450", "volume": 0}], {"seq": 11, "stale": False})
        with patch("app.markets.iran_bourse.poller.BOURSE_POLLER", SimpleNamespace(store=store)):
            self.assertEqual(current_volume_for_alert(alert), 0.0)

    def test_25a_non_bourse_alerts_do_not_get_bourse_current_volume(self):
        crypto = Alert(
            id="btc-1",
            user_id="user_p25@example.com",
            exchange="binance",
            symbol="BTCUSDT",
            target_price=100_000.0,
            condition="ABOVE",
            condition_type="priceThreshold",
            fcm_token="secret-tok",
            created_at="2026-11-28T10:00:00+00:00",
        )
        self.assertIsNone(current_volume_for_alert(crypto))
        pub = _to_alert_public(crypto)
        self.assertIsNone(pub.current_volume)

    def test_25a_get_user_alerts_route_includes_live_current_volume(self):
        alert = _make_bourse_volume_alert(
            alert_id="vol-route-1",
            user_id="p25_route@example.com",
            target_volume=10_000_000.0,
        )
        store = BourseSnapshotStore(stale_seconds=60.0)
        store.set_watched([alert.symbol])
        store.apply(
            [{"id": alert.symbol, "volume": 6_400_000}],
            {"seq": 22, "stale": False},
        )
        fake_poller = SimpleNamespace(store=store)

        with patch("app.storage.ALERTS_DB", [alert]), \
             patch("app.markets.iran_bourse.poller.BOURSE_POLLER", fake_poller):
            res = asyncio.run(get_user_alerts("p25_route@example.com"))

        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].id, "vol-route-1")
        self.assertEqual(res[0].target_price, 10_000_000.0)
        self.assertEqual(res[0].current_volume, 6_400_000.0)


if __name__ == "__main__":
    unittest.main()
