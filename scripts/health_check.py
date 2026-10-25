#!/usr/bin/env python3
"""
Phase 3E-2: Deep health check + auto-restart + admin alert.

Runs from cron every 5 minutes:
  */5 * * * * /home/aisocial/AlertG1/AlertG/scripts/run_health_check.sh >> /home/aisocial/AlertG1/AlertG/health_check.log 2>&1

Behaviour:
  - 200 OK        -> log "ok", reset failure counter, clear alert state
  - 503 degraded  -> Telegram alert (rate-limited to 1 per 30 min), log warnings
  - connection refused -> run `./run_server.sh start` (rate-limited to 1 per 5 min),
                          Telegram alert "server was down, restarted", log
  - other error   -> Telegram alert (rate-limited to 1 per 30 min), log

State is kept in health_check_state.json next to this script.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = PROJECT_ROOT / "health_check_state.json"
HEALTH_URL = os.getenv("HEALTH_CHECK_URL", "http://127.0.0.1:8000/health/deep")
RUN_SERVER = PROJECT_ROOT / "run_server.sh"

ALERT_RATE_LIMIT_SECONDS = 30 * 60        # 30 min between Telegram alerts
RESTART_RATE_LIMIT_SECONDS = 5 * 60       # 5 min between auto-restarts


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception as e:
            print(f"⚠️ [health_check] state read failed: {e}")
    return {}


def _save_state(state: dict) -> None:
    try:
        tmp = STATE_FILE.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        print(f"⚠️ [health_check] state save failed: {e}")


def _api_key() -> str:
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from app.config import API_KEY
        return (API_KEY or "").strip()
    except Exception as e:
        print(f"⚠️ [health_check] API_KEY load failed: {e}")
        return ""


def _send_admin_alert(text: str) -> bool:
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_ID
    except Exception as e:
        print(f"⚠️ [health_check] config load failed: {e}")
        return False

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID:
        print("ℹ️ [health_check] TELEGRAM_ADMIN_CHAT_ID or TELEGRAM_BOT_TOKEN not set; alert skipped")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_ADMIN_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        print(f"⚠️ [health_check] Telegram alert failed: {e}")
        return False


def _can_alert(state: dict, now: float) -> bool:
    last = float(state.get("last_alert_ts", 0.0))
    return (now - last) >= ALERT_RATE_LIMIT_SECONDS


def _can_restart(state: dict, now: float) -> bool:
    last = float(state.get("last_restart_ts", 0.0))
    return (now - last) >= RESTART_RATE_LIMIT_SECONDS


def _try_restart() -> bool:
    pid_file = PROJECT_ROOT / "server.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            print(f"ℹ️ [health_check] server.pid exists and pid {pid} is alive; skip restart")
            return False
        except (ValueError, OSError):
            try:
                pid_file.unlink()
            except Exception:
                pass

    if not RUN_SERVER.exists():
        print(f"❌ [health_check] {RUN_SERVER} not found; cannot restart")
        return False

    try:
        result = subprocess.run(
            [str(RUN_SERVER), "start"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        print(f"🔁 [health_check] run_server.sh start exit={result.returncode}")
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f"❌ [health_check] restart failed: {e}")
        return False


def check_once() -> int:
    now = time.time()
    state = _load_state()
    api_key = _api_key()

    req = urllib.request.Request(HEALTH_URL, method="GET")
    if api_key:
        req.add_header("X-API-Key", api_key)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
        print(f"❌ [health_check] server unreachable: {e}")
        state["consecutive_failures"] = int(state.get("consecutive_failures", 0)) + 1
        restarted = False
        if _can_restart(state, now):
            restarted = _try_restart()
            state["last_restart_ts"] = now
        if _can_alert(state, now):
            _send_admin_alert(
                f"🚨 <b>AlertG: server was down</b>\n"
                f"<blockquote>Health check could not reach {HEALTH_URL}.\n"
                f"Auto-restart via run_server.sh {'succeeded' if restarted else 'failed'}.</blockquote>"
            )
            state["last_alert_ts"] = now
        _save_state(state)
        return 1

    try:
        payload = json.loads(body) if body else {}
    except Exception:
        payload = {}

    if status == 200:
        state["consecutive_failures"] = 0
        state.pop("last_alert_ts", None)
        _save_state(state)
        print(f"✅ [health_check] ok (uptime={payload.get('checks', {}).get('uptime_seconds')}s)")
        return 0

    if status == 503:
        warnings = payload.get("warnings", [])
        state["consecutive_failures"] = int(state.get("consecutive_failures", 0)) + 1
        print(f"⚠️ [health_check] degraded: {warnings}")
        if _can_alert(state, now):
            _send_admin_alert(
                f"⚠️ <b>AlertG: /health/deep is degraded</b>\n"
                f"<blockquote>" + "\n".join(f"• {w}" for w in warnings) + "</blockquote>"
            )
            state["last_alert_ts"] = now
        _save_state(state)
        return 1

    state["consecutive_failures"] = int(state.get("consecutive_failures", 0)) + 1
    print(f"⚠️ [health_check] unexpected status {status}: {body[:200]}")
    if _can_alert(state, now):
        _send_admin_alert(
            f"⚠️ <b>AlertG: /health/deep returned HTTP {status}</b>\n"
            f"<blockquote>{body[:400]}</blockquote>"
        )
        state["last_alert_ts"] = now
    _save_state(state)
    return 1


if __name__ == "__main__":
    sys.exit(check_once())