# -*- coding: utf-8 -*-
"""
Tests for scripts/bourse/run_gateway.sh (Phase 18c-3).

Runs the real POSIX sh supervisor script against a lightweight fake
`tsetmc_gateway` Python package inside a temporary GATEWAY_DIR:
- start & status (running, pid, port, uptime, exit 0)
- double start refused (exit non-zero, original process preserved)
- start refused when port is already occupied by another listener
- stop & status (stopped, exit 3)
- ensure is quiet/idempotent when running, and revives a killed process
- restart replaces the running process with a new pid
- log rotation when gateway.log reaches LOG_MAX_BYTES
- no secret values (TSETMC_API_KEY, bridge token in TSETMC_BASE_URL) ever appear in output
"""

import os
import signal
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "bourse", "run_gateway.sh")

FAKE_API_KEY = "SUPER_SECRET_GATEWAY_KEY_9876543210"
FAKE_BRIDGE_TOKEN = "SECRET_BRIDGE_TOKEN_ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _create_fake_gateway_dir(base_dir: str, port: int) -> str:
    pkg_dir = os.path.join(base_dir, "tsetmc_gateway")
    os.makedirs(pkg_dir, exist_ok=True)
    with open(os.path.join(pkg_dir, "__init__.py"), "w", encoding="utf-8") as f:
        f.write('__version__ = "0.2.2-test"\n')

    main_code = textwrap.dedent("""\
        import os
        import signal
        import socket
        import sys
        import time

        host = os.environ.get("TSETMC_HOST", "127.0.0.1")
        port = int(os.environ.get("TSETMC_PORT", "8080"))

        # Verify required env vars arrived without printing their secret values
        assert os.environ.get("TSETMC_API_KEY"), "missing TSETMC_API_KEY"
        assert os.environ.get("TSETMC_BASE_URL"), "missing TSETMC_BASE_URL"

        stop_flag = False

        def _handle(signum, frame):
            global stop_flag
            stop_flag = True

        signal.signal(signal.SIGTERM, _handle)
        signal.signal(signal.SIGINT, _handle)

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port))
        srv.listen(5)
        srv.settimeout(0.2)
        print(f"fake_gateway listening on {host}:{port}", flush=True)

        try:
            while not stop_flag:
                try:
                    conn, _ = srv.accept()
                    conn.close()
                except socket.timeout:
                    pass
                except OSError:
                    break
        finally:
            srv.close()
            print("fake_gateway exiting cleanly", flush=True)
    """)
    with open(os.path.join(pkg_dir, "__main__.py"), "w", encoding="utf-8") as f:
        f.write(main_code)

    env_path = os.path.join(base_dir, "gateway.env")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(
            f"TSETMC_HOST=127.0.0.1\n"
            f"TSETMC_PORT={port}\n"
            f"TSETMC_HTTP_TIMEOUT=30\n"
            f"TSETMC_API_KEY={FAKE_API_KEY}\n"
            f"TSETMC_BASE_URL=https://aegkala.com/tse-forward.php/{FAKE_BRIDGE_TOKEN}\n"
        )
    os.chmod(env_path, 0o600)
    return base_dir


class TestRunGatewayScript(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="gw_test_")
        self.gw_dir = self._tmp.name
        self.port = _pick_free_port()
        _create_fake_gateway_dir(self.gw_dir, self.port)

    def tearDown(self):
        # Always guarantee no orphan fake gateway process survives the test
        try:
            self._run("stop")
        except Exception:
            pass
        pid_file = os.path.join(self.gw_dir, "gateway.pid")
        if os.path.isfile(pid_file):
            try:
                pid = int(open(pid_file, encoding="utf-8").read().strip())
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
        self._tmp.cleanup()

    def _run(self, *args, extra_env=None) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["GATEWAY_DIR"] = self.gw_dir
        env["PYTHON"] = sys.executable
        if extra_env:
            env.update(extra_env)
        res = subprocess.run(
            ["/bin/sh", SCRIPT, *args],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Hard security invariant: secrets must NEVER appear in stdout or stderr
        combined = (res.stdout or "") + (res.stderr or "")
        self.assertNotIn(FAKE_API_KEY, combined, "TSETMC_API_KEY leaked in script output!")
        self.assertNotIn(FAKE_BRIDGE_TOKEN, combined, "TSETMC_BASE_URL token leaked in script output!")
        return res

    def _read_pid(self) -> int:
        with open(os.path.join(self.gw_dir, "gateway.pid"), encoding="utf-8") as f:
            return int(f.read().strip())

    def test_01_status_when_stopped_returns_exit_3(self):
        res = self._run("status")
        self.assertEqual(res.returncode, 3)
        self.assertIn("stopped", res.stdout)
        self.assertIn(f"port={self.port}", res.stdout)

    def test_02_start_status_double_start_refused_and_stop(self):
        # 1. Start
        start_res = self._run("start")
        self.assertEqual(start_res.returncode, 0, start_res.stderr)
        self.assertIn("started", start_res.stdout)
        pid1 = self._read_pid()

        # 2. Status while running -> exit 0, pid, port, uptime
        st_res = self._run("status")
        self.assertEqual(st_res.returncode, 0, st_res.stderr)
        self.assertIn("running", st_res.stdout)
        self.assertIn(f"pid={pid1}", st_res.stdout)
        self.assertIn(f"port={self.port}", st_res.stdout)
        self.assertIn("uptime=", st_res.stdout)

        # 3. Double start must be refused and keep original pid
        dup_res = self._run("start")
        self.assertNotEqual(dup_res.returncode, 0)
        self.assertIn("already running", dup_res.stderr)
        self.assertEqual(self._read_pid(), pid1)

        # 4. Stop -> exit 0, subsequent status -> stopped (exit 3)
        stop_res = self._run("stop")
        self.assertEqual(stop_res.returncode, 0, stop_res.stderr)
        self.assertIn("stopped", stop_res.stdout)

        st_after = self._run("status")
        self.assertEqual(st_after.returncode, 3)
        self.assertIn("stopped", st_after.stdout)

    def test_03_start_refused_when_port_is_busy(self):
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        blocker.bind(("127.0.0.1", self.port))
        blocker.listen(1)
        try:
            res = self._run("start")
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("already in use", res.stderr)
            self.assertFalse(os.path.exists(os.path.join(self.gw_dir, "gateway.pid")))
        finally:
            blocker.close()

    def test_04_ensure_is_quiet_when_running_and_revives_killed_process(self):
        # Start via ensure
        e1 = self._run("ensure")
        self.assertEqual(e1.returncode, 0, e1.stderr)
        pid1 = self._read_pid()

        # Second ensure while running must be completely quiet and keep same pid
        e2 = self._run("ensure")
        self.assertEqual(e2.returncode, 0, e2.stderr)
        self.assertEqual(e2.stdout.strip(), "")
        self.assertEqual(e2.stderr.strip(), "")
        self.assertEqual(self._read_pid(), pid1)

        # Kill the process abruptly (SIGKILL), then ensure must revive it with a new pid
        os.kill(pid1, signal.SIGKILL)
        for _ in range(20):
            try:
                os.waitpid(pid1, os.WNOHANG)
            except ChildProcessError:
                pass
            try:
                os.kill(pid1, 0)
                time.sleep(0.1)
            except ProcessLookupError:
                break

        e3 = self._run("ensure")
        self.assertEqual(e3.returncode, 0, e3.stderr)
        pid2 = self._read_pid()
        self.assertNotEqual(pid2, pid1)

        st = self._run("status")
        self.assertEqual(st.returncode, 0)
        self.assertIn("running", st.stdout)
        self.assertIn(f"pid={pid2}", st.stdout)

    def test_05_restart_gives_new_pid(self):
        self.assertEqual(self._run("start").returncode, 0)
        pid1 = self._read_pid()

        r = self._run("restart")
        self.assertEqual(r.returncode, 0, r.stderr)
        pid2 = self._read_pid()
        self.assertNotEqual(pid2, pid1)
        self.assertEqual(self._run("status").returncode, 0)

    def test_06_log_rotation_at_threshold(self):
        log_path = os.path.join(self.gw_dir, "gateway.log")
        with open(log_path, "wb") as f:
            f.write(b"x" * 2048)

        res = self._run("start", extra_env={"LOG_MAX_BYTES": "1024"})
        self.assertEqual(res.returncode, 0, res.stderr)
        rotated = log_path + ".1"
        self.assertTrue(os.path.isfile(rotated), "gateway.log should rotate to gateway.log.1")
        self.assertEqual(os.path.getsize(rotated), 2048)

    def test_07_invalid_command_returns_exit_2(self):
        res = self._run("bogus_cmd")
        self.assertEqual(res.returncode, 2)
        self.assertIn("Usage:", res.stderr)


if __name__ == "__main__":
    unittest.main()
