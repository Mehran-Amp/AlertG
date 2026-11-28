# -*- coding: utf-8 -*-
"""
Phase 26 — Operations & Safety Monitoring Tests:
  - 26a (IB-12c): single-line periodic health log (gateway, bridge, poller)
  - 26b (IB-12d): Telegram admin alert after >10 min gateway/bridge error during market hours
                  + silence outside market hours + recovery notice
  - 26c: low-disk / user-quota Telegram alert + in-place copytruncate gzip log rotation
"""
import asyncio
import gzip
import importlib.util
import logging
import shutil
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.markets.iran_bourse.client import BourseConnectionError
from app.markets.iran_bourse.monitor import BourseHealthMonitor, _extract_bridge_state
from app.markets.iran_bourse.snapshot import BourseSnapshotStore

SAT_OPEN = datetime(2026, 11, 14, 6, 30, tzinfo=timezone.utc)    # Saturday 10:00 Tehran (OPEN)
THU_CLOSED = datetime(2026, 11, 12, 6, 30, tzinfo=timezone.utc)  # Thursday 10:00 Tehran (CLOSED)


class _Clock:
    def __init__(self, t: float = 1_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


class _FakePoller:
    def __init__(self, clock):
        self.store = BourseSnapshotStore(60.0, clock=clock)
        self.store.apply([{"id": "123456789012345"}], {"seq": 42, "stale": False})
        self._running = True
        self.is_leader = True
        self._failures = 0


def _healthy_gateway():
    return {
        "status": "ok",
        "version": "0.2.2",
        "ready": True,
        "stale": False,
        "age_seconds": 12.4,
        "instruments": 3241,
        "seq": 42,
        "stats": {"init_ok": 1, "plus_ok": 10, "errors": 0, "last_error": None},
    }


class TestPhase26aAnd26bMonitor(unittest.TestCase):
    def _run(self, coro):
        return asyncio.run(coro)

    def test_26a_emits_single_line_health_log_with_gateway_bridge_poller(self):
        clk = _Clock()
        poller = _FakePoller(clk)
        alerts = []

        async def health_ok():
            return _healthy_gateway()

        async def notify(msg: str):
            alerts.append(msg)

        mon = BourseHealthMonitor(
            poller_fn=lambda: poller,
            health_fn=health_ok,
            notify_fn=notify,
            clock=clk,
            now_dt_fn=lambda: SAT_OPEN,
            outage_threshold_seconds=600.0,
        )

        with self.assertLogs("signalalert.iran_bourse", level=logging.INFO) as cm:
            res = self._run(mon.check_once())

        self.assertEqual(len(cm.output), 1)
        line = res["line"]
        self.assertNotIn("\n", line)
        self.assertIn("market=OPEN", line)
        self.assertIn("gateway=ok(v0.2.2,ready=true,stale=false,age=12s)", line)
        self.assertIn("bridge=ok(errors=0)", line)
        self.assertIn("poller=running(leader=true,seq=42", line)
        self.assertEqual(alerts, [])

    def test_26b_gateway_down_over_10_min_during_market_alerts_then_recovers(self):
        clk = _Clock(10_000.0)
        poller = _FakePoller(clk)
        alerts = []
        gateway_up = {"ok": False}

        async def probe():
            if not gateway_up["ok"]:
                raise BourseConnectionError("gateway unreachable: ConnectError")
            return _healthy_gateway()

        async def notify(msg: str):
            alerts.append(msg)

        mon = BourseHealthMonitor(
            poller_fn=lambda: poller,
            health_fn=probe,
            notify_fn=notify,
            clock=clk,
            now_dt_fn=lambda: SAT_OPEN,
            outage_threshold_seconds=600.0,
            repeat_alert_seconds=1800.0,
        )

        # t=0m: gateway turned off -> starts outage timer, no alert yet
        r0 = self._run(mon.check_once())
        self.assertEqual(r0["gateway"], "down")
        self.assertEqual(r0["fault_kind"], "gateway")
        self.assertFalse(r0["alert_triggered"])
        self.assertEqual(alerts, [])

        # t=9m (540s < 600s): still below 10 min -> no alert yet
        clk.t += 540.0
        r1 = self._run(mon.check_once())
        self.assertFalse(r1["alert_triggered"])
        self.assertEqual(alerts, [])

        # t=10m 5s (605s >= 600s): crosses 10 min -> Telegram admin alert sent!
        clk.t += 65.0
        r2 = self._run(mon.check_once())
        self.assertTrue(r2["alert_triggered"])
        self.assertEqual(len(alerts), 1)
        self.assertIn("گیت‌وی بورس", alerts[0])
        self.assertIn("10 دقیقه", alerts[0])
        self.assertIn("err_sec=605", r2["line"])

        # t=15m: inside repeat suppression window (<1800s) -> no duplicate spam
        clk.t += 300.0
        r3 = self._run(mon.check_once())
        self.assertFalse(r3["alert_triggered"])
        self.assertEqual(len(alerts), 1)

        # t=18m: gateway comes back -> sends recovery notice & resets outage state
        gateway_up["ok"] = True
        clk.t += 180.0
        r4 = self._run(mon.check_once())
        self.assertTrue(r4["recovery_sent"])
        self.assertEqual(len(alerts), 2)
        self.assertIn("بازیابی", alerts[1])
        self.assertIsNone(mon.status()["fault_since"])
        self.assertFalse(mon.status()["alert_sent"])

    def test_26b_bridge_error_during_market_alerts_after_10_min(self):
        clk = _Clock(20_000.0)
        poller = _FakePoller(clk)
        alerts = []

        async def bridge_failing():
            body = _healthy_gateway()
            body["status"] = "degraded"
            body["stale"] = True
            body["stats"]["errors"] = 7
            body["stats"]["last_error"] = "bridge HTTP 502"
            return body

        async def notify(msg: str):
            alerts.append(msg)

        mon = BourseHealthMonitor(
            poller_fn=lambda: poller,
            health_fn=bridge_failing,
            notify_fn=notify,
            clock=clk,
            now_dt_fn=lambda: SAT_OPEN,
            outage_threshold_seconds=600.0,
        )

        self._run(mon.check_once())
        clk.t += 610.0
        r = self._run(mon.check_once())
        self.assertEqual(r["bridge"], "error")
        self.assertEqual(r["fault_kind"], "bridge")
        self.assertTrue(r["alert_triggered"])
        self.assertEqual(len(alerts), 1)
        self.assertIn("پل ایرانی", alerts[0])
        self.assertIn("bridge HTTP 502", alerts[0])

    def test_26b_no_alert_outside_market_hours(self):
        clk = _Clock(30_000.0)
        poller = _FakePoller(clk)
        alerts = []

        async def probe_down():
            raise BourseConnectionError("down during weekend")

        async def notify(msg: str):
            alerts.append(msg)

        mon = BourseHealthMonitor(
            poller_fn=lambda: poller,
            health_fn=probe_down,
            notify_fn=notify,
            clock=clk,
            now_dt_fn=lambda: THU_CLOSED,
            outage_threshold_seconds=600.0,
        )

        self._run(mon.check_once())
        clk.t += 1200.0
        r = self._run(mon.check_once())
        self.assertFalse(r["market_open"])
        self.assertFalse(r["alert_triggered"])
        self.assertEqual(alerts, [])

    def test_26e_stale_error_from_5_hours_ago_with_healthy_gateway_is_ok(self):
        """Old retained last_error (5h ago) with healthy gateway must NOT trigger error/alert."""
        now = 1_795_875_784.0
        five_hours_ago = now - 5 * 3600.0

        # Shape 1: stats.last_error is a dict with `at` and `message`
        body_dict = _healthy_gateway()
        body_dict["stats"]["errors"] = 1
        body_dict["stats"]["last_error"] = {"at": five_hours_ago, "message": "502 Bad Gateway"}
        status, detail = _extract_bridge_state(body_dict, now=now)
        self.assertEqual(status, "ok")
        self.assertEqual(detail, "errors=1")

        # Shape 2: stats.last_error is a string paired with stats.last_error_at
        body_str = _healthy_gateway()
        body_str["stats"]["errors"] = 1
        body_str["stats"]["last_error"] = "502 Bad Gateway"
        body_str["stats"]["last_error_at"] = five_hours_ago
        status2, detail2 = _extract_bridge_state(body_str, now=now)
        self.assertEqual(status2, "ok")
        self.assertEqual(detail2, "errors=1")

        # Full monitor run over >10 min during market hours -> zero fault & zero Telegram alerts
        clk = _Clock(now)
        poller = _FakePoller(clk)
        alerts = []

        async def healthy_with_old_err():
            b = _healthy_gateway()
            b["stats"]["errors"] = 1
            b["stats"]["last_error"] = {"at": five_hours_ago, "message": "502 Bad Gateway"}
            return b

        async def notify(msg: str):
            alerts.append(msg)

        mon = BourseHealthMonitor(
            poller_fn=lambda: poller,
            health_fn=healthy_with_old_err,
            notify_fn=notify,
            clock=clk,
            now_dt_fn=lambda: SAT_OPEN,
            outage_threshold_seconds=600.0,
        )
        r0 = self._run(mon.check_once())
        self.assertEqual(r0["bridge"], "ok")
        self.assertIsNone(r0["fault_kind"])
        self.assertEqual(r0["outage_seconds"], 0.0)

        clk.t += 720.0
        r1 = self._run(mon.check_once())
        self.assertEqual(r1["bridge"], "ok")
        self.assertIsNone(r1["fault_kind"])
        self.assertFalse(r1["alert_triggered"])
        self.assertEqual(alerts, [])

    def test_26e_fresh_error_from_30_seconds_ago_is_error(self):
        """A recent last_error (<180s ago) must still be classified as bridge=error."""
        now = 1_795_875_784.0
        thirty_sec_ago = now - 30.0

        # Dict form
        body_dict = _healthy_gateway()
        body_dict["stats"]["errors"] = 1
        body_dict["stats"]["last_error"] = {"at": thirty_sec_ago, "message": "502 Bad Gateway"}
        status, detail = _extract_bridge_state(body_dict, now=now)
        self.assertEqual(status, "error")
        self.assertIn("502 Bad Gateway", detail)

        # String + last_error_at form
        body_str = _healthy_gateway()
        body_str["stats"]["errors"] = 1
        body_str["stats"]["last_error"] = "502 Bad Gateway"
        body_str["stats"]["last_error_at"] = thirty_sec_ago
        status2, detail2 = _extract_bridge_state(body_str, now=now)
        self.assertEqual(status2, "error")
        self.assertIn("502 Bad Gateway", detail2)

        # Monitor records active bridge fault on fresh error
        clk = _Clock(now)
        poller = _FakePoller(clk)

        async def fresh_err():
            b = _healthy_gateway()
            b["stats"]["errors"] = 1
            b["stats"]["last_error"] = {"at": thirty_sec_ago, "message": "502 Bad Gateway"}
            return b

        mon = BourseHealthMonitor(
            poller_fn=lambda: poller,
            health_fn=fresh_err,
            notify_fn=lambda _m: asyncio.sleep(0),
            clock=clk,
            now_dt_fn=lambda: SAT_OPEN,
            outage_threshold_seconds=600.0,
        )
        r = self._run(mon.check_once())
        self.assertEqual(r["bridge"], "error")
        self.assertEqual(r["fault_kind"], "bridge")
        self.assertIn("bridge=error(502 Bad Gateway)", r["line"])

    def test_26e_increasing_error_counter_across_consecutive_probes_is_error(self):
        """When stats.errors increases between probes, bridge must report error even without fresh timestamp."""
        now = 1_795_875_784.0
        five_hours_ago = now - 5 * 3600.0

        # Direct helper check
        body = _healthy_gateway()
        body["stats"]["errors"] = 3
        body["stats"]["last_error"] = "upstream timeout"
        status_same, _ = _extract_bridge_state(body, now=now, prev_errors=3)
        self.assertEqual(status_same, "ok")
        status_inc, detail_inc = _extract_bridge_state(body, now=now, prev_errors=2)
        self.assertEqual(status_inc, "error")
        self.assertIn("upstream timeout", detail_inc)

        # Consecutive probes in BourseHealthMonitor
        clk = _Clock(now)
        poller = _FakePoller(clk)
        state = {"errors": 2, "msg": "502 Bad Gateway", "at": five_hours_ago}

        async def probe():
            b = _healthy_gateway()
            b["stats"]["errors"] = state["errors"]
            b["stats"]["last_error"] = {"at": state["at"], "message": state["msg"]}
            return b

        mon = BourseHealthMonitor(
            poller_fn=lambda: poller,
            health_fn=probe,
            notify_fn=lambda _m: asyncio.sleep(0),
            clock=clk,
            now_dt_fn=lambda: SAT_OPEN,
            outage_threshold_seconds=600.0,
        )

        # Probe 1: baseline errors=2 with 5h old timestamp -> ok
        r1 = self._run(mon.check_once())
        self.assertEqual(r1["bridge"], "ok")
        self.assertIsNone(r1["fault_kind"])

        # Probe 2: errors jumps 2 -> 3 (even without updated timestamp) -> error
        clk.t += 180.0
        state["errors"] = 3
        r2 = self._run(mon.check_once())
        self.assertEqual(r2["bridge"], "error")
        self.assertEqual(r2["fault_kind"], "bridge")

        # Probe 3: errors keeps climbing 3 -> 4 -> stays error
        clk.t += 180.0
        state["errors"] = 4
        r3 = self._run(mon.check_once())
        self.assertEqual(r3["bridge"], "error")
        self.assertEqual(r3["fault_kind"], "bridge")

        # Probe 4: errors stops climbing (stays 4) & no fresh error -> recovers to ok
        clk.t += 180.0
        r4 = self._run(mon.check_once())
        self.assertEqual(r4["bridge"], "ok")
        self.assertIsNone(r4["fault_kind"])



def _load_health_check_module():
    spec = importlib.util.spec_from_file_location(
        "health_check_p26",
        Path(__file__).resolve().parent.parent / "scripts" / "health_check.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestPhase26cDiskAndLogRotation(unittest.TestCase):
    def test_26c_copytruncate_log_rotation_compresses_truncates_and_caps_backups(self):
        mod = _load_health_check_module()
        with TemporaryDirectory() as td:
            log = Path(td) / "server.log"
            log.write_bytes(b"A" * 500)

            # Under limit -> no rotation
            self.assertFalse(mod.rotate_log_copytruncate(log, max_bytes=1024, keep=2))
            self.assertEqual(log.stat().st_size, 500)

            # Exceeds limit -> compressed to .1.gz and truncated in place
            log.write_bytes(b"FIRST-LOG-PAYLOAD\n" * 100)
            orig_inode = log.stat().st_ino
            self.assertTrue(mod.rotate_log_copytruncate(log, max_bytes=1024, keep=2))
            self.assertEqual(log.stat().st_ino, orig_inode)
            self.assertEqual(log.stat().st_size, 0)
            gz1 = Path(f"{log}.1.gz")
            self.assertTrue(gz1.exists())
            self.assertIn(b"FIRST-LOG-PAYLOAD", gzip.decompress(gz1.read_bytes()))

            # Second rotation shifts .1.gz -> .2.gz and writes new .1.gz
            log.write_bytes(b"SECOND-LOG-PAYLOAD\n" * 100)
            self.assertTrue(mod.rotate_log_copytruncate(log, max_bytes=1024, keep=2))
            gz2 = Path(f"{log}.2.gz")
            self.assertTrue(gz2.exists())
            self.assertIn(b"SECOND-LOG-PAYLOAD", gzip.decompress(gz1.read_bytes()))
            self.assertIn(b"FIRST-LOG-PAYLOAD", gzip.decompress(gz2.read_bytes()))

            # Third rotation keeps only 2 backups (no .3.gz)
            log.write_bytes(b"THIRD-LOG-PAYLOAD\n" * 100)
            self.assertTrue(mod.rotate_log_copytruncate(log, max_bytes=1024, keep=2))
            self.assertFalse(Path(f"{log}.3.gz").exists())
            self.assertIn(b"THIRD-LOG-PAYLOAD", gzip.decompress(gz1.read_bytes()))
            self.assertIn(b"SECOND-LOG-PAYLOAD", gzip.decompress(gz2.read_bytes()))

    def test_26c_disk_quota_low_alert_rate_limited_and_clears_on_recovery(self):
        mod = _load_health_check_module()
        with TemporaryDirectory() as td:
            root = Path(td)
            fake_home = root / "home"
            fake_home.mkdir()
            (fake_home / "tmp").mkdir()
            (fake_home / "tmp" / "big.bin").write_bytes(b"x" * (2 * 1024 * 1024))

            mod.STATE_FILE = root / "state.json"
            alerts = []
            # Simulate plenty of partition space (50 GB) but user home quota nearly full (2650/3000 MB -> 350 MB free < 512 MB)
            fake_part = shutil._ntuple_diskusage(50 * 1024**3, 10 * 1024**3, 40 * 1024**3)
            used_bytes = {"v": int(2650 * 1024 * 1024)}

            with patch.object(shutil, "disk_usage", return_value=fake_part), \
                 patch.object(mod, "_dir_usage_bytes", side_effect=lambda p: used_bytes["v"] if p == fake_home else 2 * 1024 * 1024), \
                 patch.object(mod, "_send_admin_alert", side_effect=lambda txt: alerts.append(txt) or True):
                info1 = mod.check_disk_space(
                    project_root=root,
                    home_dir=fake_home,
                    quota_mb=3000.0,
                    min_free_mb=512.0,
                    now=100_000.0,
                )
                self.assertTrue(info1["low"])
                self.assertTrue(info1["alert_sent"])
                self.assertEqual(len(alerts), 1)
                self.assertIn("کمبود فضای دیسک", alerts[0])
                self.assertIn("350 MB", alerts[0])

                # Within 6h rate limit -> suppressed
                info2 = mod.check_disk_space(
                    project_root=root,
                    home_dir=fake_home,
                    quota_mb=3000.0,
                    min_free_mb=512.0,
                    now=100_000.0 + 3600.0,
                )
                self.assertTrue(info2["low"])
                self.assertFalse(info2["alert_sent"])
                self.assertEqual(len(alerts), 1)

                # Space freed (1500/3000 MB -> 1500 MB free >= 612 MB) -> clears alert throttle
                used_bytes["v"] = int(1500 * 1024 * 1024)
                info3 = mod.check_disk_space(
                    project_root=root,
                    home_dir=fake_home,
                    quota_mb=3000.0,
                    min_free_mb=512.0,
                    now=100_000.0 + 4000.0,
                )
                self.assertFalse(info3["low"])
                self.assertFalse(info3["alert_sent"])

                # Drops low again -> alerts immediately because state was cleared on recovery
                used_bytes["v"] = int(2800 * 1024 * 1024)
                info4 = mod.check_disk_space(
                    project_root=root,
                    home_dir=fake_home,
                    quota_mb=3000.0,
                    min_free_mb=512.0,
                    now=100_000.0 + 4200.0,
                )
                self.assertTrue(info4["alert_sent"])
                self.assertEqual(len(alerts), 2)


if __name__ == "__main__":
    unittest.main()
