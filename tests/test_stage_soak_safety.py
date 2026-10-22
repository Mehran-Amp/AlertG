"""
Safety tests for scripts/soak_test_48h.py and scripts/load_test_worst_case.py.

- live mode never silently uses the mock client
- the scripts never read/write the real alerts_data.json / user_profiles.json / fcm_outbox.json,
  even when an alert really triggers and is persisted (price crosses the target)
- unreachable default target price: alerts never trigger/deactivate, so every cycle evaluates all of them
- memory leak verdict uses a growth slope (MB/hour) and refuses to judge runs that are too short
"""
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import _soak_common as common  # noqa: E402


def _load_script(name):
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", os.path.join(SCRIPTS, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


soak = _load_script("soak_test_48h")
load = _load_script("load_test_worst_case")


class TestClientSelection(unittest.TestCase):
    def test_live_mode_gets_real_httpx_client_never_mock(self):
        try:
            import httpx
            if getattr(httpx, '_mock_name', None) is not None or not hasattr(httpx, '__file__'):
                self.skipTest("httpx is not installed (mocked)")
        except ImportError:
            self.skipTest("httpx is not installed in the environment")
        for module in (soak, load):
            client = module.make_client(False)
            try:
                self.assertIsInstance(client, httpx.AsyncClient, module.__name__)
            finally:
                asyncio.run(client.aclose())

    def test_mock_only_when_requested(self):
        self.assertEqual(type(soak.make_client(True)).__name__, "SoakMockClient")
        self.assertEqual(type(load.make_client(True)).__name__, "MockHttpxClient")

    def test_default_target_price_is_unreachable(self):
        self.assertGreaterEqual(common.UNREACHABLE_TARGET_PRICE, 1e9)


class TestMemorySlope(unittest.TestCase):
    def test_slope_of_linear_growth(self):
        samples = [{"time_s": t, "mem_mb": 100.0 + t / 3600.0 * 2.0} for t in range(0, 7201, 600)]
        self.assertAlmostEqual(common.compute_memory_slope_mb_per_hour(samples, 0), 2.0, places=3)

    def test_warmup_is_ignored(self):
        samples = [{"time_s": 0, "mem_mb": 50.0}] + [{"time_s": t, "mem_mb": 80.0} for t in range(600, 3601, 600)]
        self.assertAlmostEqual(common.compute_memory_slope_mb_per_hour(samples, warmup_seconds=300), 0.0, places=6)

    def test_too_few_samples_returns_none(self):
        self.assertIsNone(common.compute_memory_slope_mb_per_hour([{"time_s": 0, "mem_mb": 1}, {"time_s": 5, "mem_mb": 2}]))

    def test_verdicts(self):
        self.assertIn("INCONCLUSIVE", common.memory_verdict(0.0, 60.0))
        self.assertIn("INCONCLUSIVE", common.memory_verdict(None, 99999.0))
        self.assertTrue(common.memory_verdict(0.1, 7200.0, 0.5).startswith("PASS"))
        self.assertTrue(common.memory_verdict(3.0, 7200.0, 0.5).startswith("WARNING"))


class TestDataIsolation(unittest.TestCase):
    def _run(self, script, args, cwd, extra_env=None):
        env = {k: v for k, v in os.environ.items() if k not in ("DATA_DIR", common.ISOLATION_ENV_FLAG)}
        env["PYTHONIOENCODING"] = "utf-8"
        env.update(extra_env or {})
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run([sys.executable, os.path.join(SCRIPTS, script)] + args, cwd=cwd, env=env,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)

    def _sentinels(self, folder):
        files = {"alerts_data.json": "[]", "user_profiles.json": "{}", "fcm_outbox.json": "[]"}
        for name, content in files.items():
            with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
                f.write(content)
        return files

    def _assert_untouched(self, folder, files):
        for name, content in files.items():
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                self.assertEqual(f.read(), content, f"{name} was modified")

    def test_all_storage_paths_point_to_the_isolated_dir(self):
        """The real alerts/profile/outbox/catalog files can never be targeted after isolate_data_dir()."""
        with tempfile.TemporaryDirectory() as folder:
            self._sentinels(folder)
            code = (
                "import sys, os, json; sys.path.insert(0, %r); sys.path.insert(0, %r);"
                "import _soak_common as c; tmp = c.isolate_data_dir(%r);"
                "import app.storage as st, app.config as cfg; from app.notifier import outbox;"
                "print(json.dumps({'tmp': tmp, 'db': os.path.abspath(st.DB_FILE), 'profiles': os.path.abspath(st.PROFILES_FILE),"
                " 'outbox': os.path.abspath(outbox.OUTBOX_FILE), 'catalog': os.path.abspath(cfg.CATALOG_FILE)}))"
            ) % (SCRIPTS, ROOT, ROOT)
            env = {k: v for k, v in os.environ.items() if k not in ("DATA_DIR", common.ISOLATION_ENV_FLAG)}
            env["PYTHONIOENCODING"] = "utf-8"
            res = subprocess.run([sys.executable, "-c", code], cwd=folder, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
            self.assertEqual(res.returncode, 0, res.stderr)
            paths = json.loads(res.stdout.strip().splitlines()[-1])
            tmp = os.path.realpath(paths.pop("tmp"))
            for name, path in paths.items():
                self.assertTrue(os.path.realpath(path).startswith(tmp + os.sep), f"{name} -> {path} is outside {tmp}")

    def test_triggered_alert_is_persisted_only_inside_the_isolated_dir(self):
        """A real price crossing triggers + persists; the write must land in the temp dir, never in the real files."""
        with tempfile.TemporaryDirectory() as folder:
            files = self._sentinels(folder)
            code = (
                "import sys, os, asyncio, json, time; sys.path.insert(0, %r); sys.path.insert(0, %r)\n"
                "import _soak_common as c; tmp = c.isolate_data_dir(%r)\n"
                "import app.state as state\n"
                "from app.models import Alert\n"
                "from app.storage import ALERTS_DB, DB_FILE\n"
                "import app.engine.checker as chk\n"
                "import app.markets.base as mb\n"
                "import app.markets.global_stocks as gs\n"
                "chk.is_market_open = lambda *a, **k: True\n"
                "mock_prices = [1.1900, 1.2100]\n"
                "call_index = 0\n"
                "base_ts = int(time.time())\n"
                "def next_sample():\n"
                "    global call_index\n"
                "    p = mock_prices[0] if len(mock_prices) == 1 else mock_prices.pop(0)\n"
                "    ts = base_ts + call_index\n"
                "    call_index += 1\n"
                "    return p, ts\n"
                "async def mock_fetch(*a, **k):\n"
                "    p, ts = next_sample()\n"
                "    return p, [{'success': True, 'parsed_price': p, 'state': 'REGULAR', 'currency': 'USD', 'asOf': ts, 'source': 'mock_provider'}]\n"
                "chk.fetch_price_with_trace = mock_fetch\n"
                "mb.fetch_price_with_trace = mock_fetch\n"
                "async def mock_quote(sym, client=None):\n"
                "    p, ts = next_sample()\n"
                "    return {'price': p, 'currency': 'USD', 'market_state': 'REGULAR', 'timestamp': ts, 'asOf': ts, 'source': 'mock_provider'}\n"
                "gs.yahoo_adapter.fetch_quote = mock_quote\n"
                "class DummyClient:\n"
                "    async def get(self, *a, **k):\n"
                "        class Resp:\n"
                "            status_code = 200\n"
                "            def json(self): return {'chart': {'result': [{'meta': {'regularMarketPrice': 1.25, 'currency': 'USD'}}]}}\n"
                "            @property\n"
                "            def text(self): return json.dumps(self.json())\n"
                "        return Resp()\n"
                "    async def post(self, *a, **k):\n"
                "        class Resp:\n"
                "            status_code = 200\n"
                "            def json(self): return {'ok': True}\n"
                "            @property\n"
                "            def text(self): return json.dumps(self.json())\n"
                "        return Resp()\n"
                "async def run():\n"
                "    state.http_client = DummyClient()\n"
                "    ALERTS_DB.clear()\n"
                "    ALERTS_DB.append(Alert(id='x1', user_id='soak_test_runner', exchange='global_stocks', symbol='EUR/USD',"
                " target_price=1.2, condition='ABOVE', is_active=True, check_interval_seconds=1, last_checked_at=0.0,"
                " created_at='2026-01-01T00:00:00Z'))\n"
                "    for _ in range(2):\n"
                "        state.PRICE_CACHE.clear(); state.BULK_MARKET_RESPONSE_CACHE.clear()\n"
                "        ALERTS_DB[0].last_checked_at = 0.0\n"
                "        await asyncio.sleep(0.05)\n"
                "        await chk.check_alerts_job()\n"
                "    await asyncio.sleep(0.5)\n"
                "asyncio.run(run())\n"
                "print('DB_EXISTS', os.path.exists(DB_FILE), os.path.realpath(DB_FILE).startswith(os.path.realpath(tmp)))\n"
            ) % (SCRIPTS, ROOT, ROOT)
            env = {k: v for k, v in os.environ.items() if k not in ("DATA_DIR", common.ISOLATION_ENV_FLAG)}
            env["PYTHONIOENCODING"] = "utf-8"
            res = subprocess.run([sys.executable, "-c", code], cwd=folder, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
            if res.returncode != 0 or "[TRIGGER]" not in res.stdout:
                print("--- SUBPROCESS STDOUT ---\n", res.stdout)
                print("--- SUBPROCESS STDERR ---\n", res.stderr)
            self.assertEqual(res.returncode, 0, f"Subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}")
            self.assertIn("[TRIGGER]", res.stdout, f"price must cross the target so the persistence path is exercised.\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}")
            self.assertIn("DB_EXISTS True True", res.stdout)
            self._assert_untouched(folder, files)

    def test_default_target_never_triggers_and_all_cycles_evaluate_alerts(self):
        with tempfile.TemporaryDirectory() as folder:
            files = self._sentinels(folder)
            res = self._run("load_test_worst_case.py", ["--cycles", "3", "--export", os.path.join(folder, "r.json")], folder)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertNotIn("[TRIGGER]", res.stdout)
            with open(os.path.join(folder, "r.json"), encoding="utf-8") as f:
                report = json.load(f)
            self.assertEqual(report["test_mode"], "mock")
            self.assertEqual(report["http_client"], "MockHttpxClient")
            self._assert_untouched(folder, files)

    def test_run_without_isolation_is_refused(self):
        code = ("import sys; sys.path.insert(0, %r); import asyncio, soak_test_48h as s; "
                "asyncio.run(s.run_soak_test(duration_hours=0.0001, use_mock=True, total_target_seconds=1))") % SCRIPTS
        env = {k: v for k, v in os.environ.items() if k != common.ISOLATION_ENV_FLAG}
        res = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("not isolated", res.stderr)

    def test_isolated_dir_is_removed_on_exit(self):
        code = ("import sys, json; sys.path.insert(0, %r); import _soak_common as c; "
                "print(c.isolate_data_dir(%r))") % (SCRIPTS, ROOT)
        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse(os.path.exists(res.stdout.strip()))

    def test_soak_report_declares_network_mode_and_server_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            report_path = os.path.join(folder, "r.json")
            res = self._run("soak_test_48h.py", ["--cycles", "2", "--interval-seconds", "0.05", "--mock",
                                                 "--export", report_path], folder)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            with open(report_path, encoding="utf-8") as f:
                report = json.load(f)
            self.assertEqual(report["network_mode"], "mock")
            self.assertEqual(report["http_client"], "SoakMockClient")
            self.assertIn("NOT the server", report["memory_profile_mb"]["scope"])
            self.assertIsNone(report["server_memory_mb"])

    def test_server_pid_memory_is_sampled(self):
        with tempfile.TemporaryDirectory() as folder:
            report_path = os.path.join(folder, "r.json")
            res = self._run("soak_test_48h.py", ["--cycles", "2", "--interval-seconds", "0.05", "--mock",
                                                 "--server-pid", str(os.getpid()), "--export", report_path], folder)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            with open(report_path, encoding="utf-8") as f:
                server = json.load(f)["server_memory_mb"]
            self.assertEqual(server["pid"], os.getpid())
            self.assertGreater(server["final"], 0)


if __name__ == "__main__":
    unittest.main()