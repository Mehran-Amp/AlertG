"""
Shared safety helpers for scripts/soak_test_48h.py and scripts/load_test_worst_case.py.

Standard library only (never import `app.*` here): isolate_data_dir() must run BEFORE app.config is imported,
otherwise the soak/load scripts would read and WRITE the real alerts_data.json / user_profiles.json /
fcm_outbox.json of the server they run on.
"""
import atexit
import os
import shutil
import sys
import tempfile
from typing import Any, Dict, List, Optional

ISOLATION_ENV_FLAG = "SOAK_DATA_ISOLATED"
# A price target no market can reach: alerts never trigger, so they are never deactivated or persisted and
# every cycle really evaluates every alert.
UNREACHABLE_TARGET_PRICE = 1e12


def isolate_data_dir(root_dir: str) -> str:
    """Point DATA_DIR to a throw-away directory (seeded with a copy of catalog.json) and return its path."""
    if "app.config" in sys.modules:
        raise RuntimeError("isolate_data_dir() must be called before app.config is imported.")
    real = os.getenv("DATA_DIR", ".")
    base = os.getcwd() if real == "." else real
    tmp = tempfile.mkdtemp(prefix="soak_data_")
    for candidate in (os.path.join(base, "catalog.json"), os.path.join(root_dir, "catalog.json")):
        if os.path.isfile(candidate):
            shutil.copy2(candidate, os.path.join(tmp, "catalog.json"))
            break
    os.environ["DATA_DIR"] = tmp
    os.environ[ISOLATION_ENV_FLAG] = "1"
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    return tmp


def require_isolated_data_dir() -> None:
    if os.environ.get(ISOLATION_ENV_FLAG) != "1":
        raise RuntimeError(
            "Refusing to run: data directory is not isolated. Start the script through its main() "
            "(it calls isolate_data_dir() first) so real alerts/profiles are never touched."
        )


def build_live_http_client():
    """Real httpx client with the same limits/timeouts as server.py lifespan. Never falls back to a mock."""
    import httpx
    limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
    timeout = httpx.Timeout(5.0, connect=3.0)
    return httpx.AsyncClient(limits=limits, timeout=timeout)


def sample_pid_memory_mb(pid: int) -> float:
    """RSS (MB) of another process, e.g. the running server (cat server.pid)."""
    try:
        import psutil
        return psutil.Process(pid).memory_info().rss / (1024 * 1024)
    except ImportError:
        try:
            with open(f"/proc/{pid}/statm", "r") as f:
                rss_pages = int(f.read().split()[1])
                import resource
                page_size = resource.getpagesize()
                return (rss_pages * page_size) / (1024 * 1024)
        except Exception as e:
            raise RuntimeError(f"psutil or readable /proc/{pid}/statm is required for --server-pid") from e
    except Exception as e:
        if "NoSuchProcess" in type(e).__name__:
            raise RuntimeError(f"Server process {pid} not found.") from e
        elif "AccessDenied" in type(e).__name__:
            raise RuntimeError(f"No permission to read memory of process {pid}.") from e
        raise


def compute_memory_slope_mb_per_hour(samples: List[Dict[str, Any]], warmup_seconds: float = 0.0) -> Optional[float]:
    """Least-squares slope of mem_mb over time_s, ignoring the warm-up period. None if < 3 usable samples."""
    pts = [(float(s["time_s"]), float(s["mem_mb"])) for s in samples if float(s["time_s"]) >= warmup_seconds]
    if len(pts) < 3:
        return None
    n = len(pts)
    mean_t = sum(t for t, _ in pts) / n
    mean_m = sum(m for _, m in pts) / n
    den = sum((t - mean_t) ** 2 for t, _ in pts)
    if den == 0:
        return None
    num = sum((t - mean_t) * (m - mean_m) for t, m in pts)
    return num / den * 3600.0


def memory_verdict(slope_mb_per_hour: Optional[float], duration_seconds: float,
                   threshold_mb_per_hour: float = 0.5, min_duration_seconds: float = 600.0) -> str:
    if slope_mb_per_hour is None or duration_seconds < min_duration_seconds:
        return "INCONCLUSIVE (run too short for a leak verdict)"
    if slope_mb_per_hour <= threshold_mb_per_hour:
        return f"PASS (growth {slope_mb_per_hour:+.2f} MB/h <= {threshold_mb_per_hour:.2f} MB/h)"
    return f"WARNING (growth {slope_mb_per_hour:+.2f} MB/h > {threshold_mb_per_hour:.2f} MB/h)"
