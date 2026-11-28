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
import gzip
import html
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = PROJECT_ROOT / "health_check_state.json"
HEALTH_URL = os.getenv("HEALTH_CHECK_URL", "http://127.0.0.1:8000/health/deep")
RUN_SERVER = PROJECT_ROOT / "run_server.sh"

ALERT_RATE_LIMIT_SECONDS = 30 * 60        # 30 min between Telegram alerts
RESTART_RATE_LIMIT_SECONDS = 5 * 60       # 5 min between auto-restarts

# Phase 26c: Disk space / user quota alert + copytruncate gzip log rotation
DISK_QUOTA_MB = float(os.getenv("DISK_QUOTA_MB", "3000"))            # 3000 MB (~2.93 GiB user quota on server360)
DISK_MIN_FREE_MB = float(os.getenv("DISK_MIN_FREE_MB", "512"))       # alert when < 512 MB free
DISK_ALERT_RATE_LIMIT_SECONDS = 6 * 3600                             # 6 hours between low-disk alerts
SERVER_LOG_MAX_BYTES = int(os.getenv("SERVER_LOG_MAX_BYTES", str(10 * 1024 * 1024)))
HEALTH_LOG_MAX_BYTES = int(os.getenv("HEALTH_LOG_MAX_BYTES", str(5 * 1024 * 1024)))
GATEWAY_LOG_MAX_BYTES = int(os.getenv("GATEWAY_LOG_MAX_BYTES", str(5 * 1024 * 1024)))


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


def rotate_log_copytruncate(path: Path, max_bytes: int, keep: int = 3) -> bool:
    """Safely rotate an actively written log file in-place (copy -> gzip -> truncate).

    Preserves the inode so long-running processes opened with `>>` keep logging at offset 0.
    Returns True if rotation occurred.
    """
    if max_bytes <= 0 or keep < 1 or not path.is_file():
        return False
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size < max_bytes:
        return False

    try:
        for idx in range(keep, 1, -1):
            src = Path(f"{path}.{idx - 1}.gz")
            dst = Path(f"{path}.{idx}.gz")
            if src.exists():
                os.replace(src, dst)

        first_gz = Path(f"{path}.1.gz")
        tmp_gz = Path(f"{path}.1.gz.tmp")
        with open(path, "rb") as fin, gzip.open(tmp_gz, "wb", compresslevel=6) as fout:
            shutil.copyfileobj(fin, fout, length=65536)
        os.replace(tmp_gz, first_gz)

        with open(path, "r+b") as f:
            f.truncate(0)
            f.flush()
        print(f"🧹 [health_check] rotated {path.name} ({size // 1024} KiB -> {first_gz.name})")
        return True
    except Exception as e:
        print(f"⚠️ [health_check] log rotation failed for {path}: {e}")
        return False


def rotate_managed_logs(
    project_root: Path = PROJECT_ROOT,
    home_dir: Optional[Path] = None,
) -> List[str]:
    """Rotate AlertG and gateway log files when they exceed configured byte caps."""
    home = home_dir if home_dir is not None else Path.home()
    targets: List[Tuple[Path, int, int]] = [
        (project_root / "server.log", SERVER_LOG_MAX_BYTES, 3),
        (project_root / "health_check.log", HEALTH_LOG_MAX_BYTES, 2),
        (home / "tsetmc-gateway" / "gateway.log", GATEWAY_LOG_MAX_BYTES, 2),
    ]
    rotated: List[str] = []
    for log_path, cap, keep in targets:
        if rotate_log_copytruncate(log_path, max_bytes=cap, keep=keep):
            rotated.append(str(log_path))
    return rotated


def _dir_usage_bytes(path: Path) -> Optional[int]:
    """Return total bytes under `path` via fast `du -sk`, falling back to os.walk."""
    try:
        res = subprocess.run(
            ["du", "-sk", str(path)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if res.returncode == 0 and res.stdout.strip():
            kb = int(res.stdout.strip().split()[0])
            return kb * 1024
    except Exception:
        pass
    try:
        total = 0
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += os.lstat(os.path.join(root, name)).st_size
                except OSError:
                    pass
        return total
    except Exception:
        return None


def _top_home_consumers(home_dir: Path, limit: int = 3) -> List[Tuple[str, float]]:
    """Return top-level directory/file sizes in MB under `home_dir` for actionable low-disk alerts."""
    rows: List[Tuple[str, float]] = []
    try:
        entries = list(home_dir.iterdir())
    except OSError:
        return []
    for entry in entries:
        try:
            if entry.is_symlink():
                continue
            if entry.is_file():
                b = entry.stat().st_size
            elif entry.is_dir():
                b = _dir_usage_bytes(entry) or 0
            else:
                continue
            rows.append((entry.name, round(b / (1024 * 1024), 1)))
        except OSError:
            continue
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows[:limit]


def measure_disk_status(
    project_root: Path = PROJECT_ROOT,
    home_dir: Optional[Path] = None,
    quota_mb: Optional[float] = None,
    min_free_mb: Optional[float] = None,
) -> Dict[str, object]:
    """Measure both filesystem free space and user home quota headroom (for shared/CageFS hosts)."""
    home = home_dir if home_dir is not None else Path.home()
    q_mb = DISK_QUOTA_MB if quota_mb is None else float(quota_mb)
    threshold_mb = DISK_MIN_FREE_MB if min_free_mb is None else float(min_free_mb)

    part_usage = shutil.disk_usage(str(project_root))
    partition_free_mb = round(part_usage.free / (1024 * 1024), 1)
    partition_total_mb = round(part_usage.total / (1024 * 1024), 1)

    home_used_bytes = _dir_usage_bytes(home) if q_mb > 0 else None
    home_used_mb = round(home_used_bytes / (1024 * 1024), 1) if home_used_bytes is not None else None
    quota_free_mb = round(max(0.0, q_mb - home_used_mb), 1) if home_used_mb is not None else None

    effective_free_mb = (
        min(partition_free_mb, quota_free_mb) if quota_free_mb is not None else partition_free_mb
    )
    low = effective_free_mb < threshold_mb
    top_consumers = _top_home_consumers(home, limit=3) if low else []

    return {
        "partition_free_mb": partition_free_mb,
        "partition_total_mb": partition_total_mb,
        "quota_mb": q_mb if q_mb > 0 else None,
        "home_used_mb": home_used_mb,
        "quota_free_mb": quota_free_mb,
        "effective_free_mb": effective_free_mb,
        "min_free_mb": threshold_mb,
        "low": low,
        "top_consumers": top_consumers,
    }


def check_disk_space(
    *,
    project_root: Path = PROJECT_ROOT,
    home_dir: Optional[Path] = None,
    quota_mb: Optional[float] = None,
    min_free_mb: Optional[float] = None,
    now: Optional[float] = None,
) -> Dict[str, object]:
    """Check disk & user quota headroom and send a rate-limited Telegram admin alert when low."""
    ts = time.time() if now is None else float(now)
    state = _load_state()
    info = measure_disk_status(
        project_root=project_root,
        home_dir=home_dir,
        quota_mb=quota_mb,
        min_free_mb=min_free_mb,
    )
    threshold_mb = float(info["min_free_mb"])
    free_mb = float(info["effective_free_mb"])

    if info["low"]:
        last_disk_alert = float(state.get("disk_last_alert_ts", 0.0))
        if (ts - last_disk_alert) >= DISK_ALERT_RATE_LIMIT_SECONDS:
            consumers = info["top_consumers"] or []
            top_lines = "\n".join(
                f"• <code>{html.escape(str(name))}</code>: {mb:.0f} MB" for name, mb in consumers
            )
            quota_line = (
                f"سهمیه کاربر: <code>{info['home_used_mb']:.0f} / {info['quota_mb']:.0f} MB</code> "
                f"(آزاد: <code>{info['quota_free_mb']:.0f} MB</code>)\n"
                if info["quota_free_mb"] is not None
                else ""
            )
            top_block = f"بیشترین مصرف:\n{top_lines}" if top_lines else ""
            msg = (
                f"💾 <b>هشدار کمبود فضای دیسک AlertG</b>\n"
                f"<blockquote>"
                f"{quota_line}"
                f"فضای آزاد مؤثر: <code>{free_mb:.0f} MB</code> (آستانه هشدار: <code>{threshold_mb:.0f} MB</code>)\n"
                f"{top_block}"
                f"</blockquote>"
            )
            if _send_admin_alert(msg):
                state["disk_last_alert_ts"] = ts
                _save_state(state)
                info["alert_sent"] = True
            else:
                info["alert_sent"] = False
        else:
            info["alert_sent"] = False
        print(f"⚠️ [health_check] low disk space: free={free_mb:.0f}MB < {threshold_mb:.0f}MB")
    else:
        info["alert_sent"] = False
        if "disk_last_alert_ts" in state and free_mb >= (threshold_mb + 100.0):
            state.pop("disk_last_alert_ts", None)
            _save_state(state)

    return info


def main() -> int:
    rotate_managed_logs()
    check_disk_space()
    return check_once()


if __name__ == "__main__":
    sys.exit(main())