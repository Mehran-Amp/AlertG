# -*- coding: utf-8 -*-
"""
Iranian Bourse — periodic health logging (IB-12c / Phase 26a) and
market-hours outage alerting to Telegram admin (IB-12d / Phase 26b).

* Emits ONE structured single-line log every `interval_seconds` summarizing
  gateway, bridge (upstream feed status), and poller state. Never logs secrets.
* During Tehran Bourse market hours only (Sat-Wed 08:30-19:00), if the gateway
  or bridge remains in error for >= `outage_threshold_seconds` (default 600s = 10m),
  sends a rate-limited Telegram admin alert and a recovery notice once healthy again.
* Off unless IRAN_BOURSE_ENABLED is true; touches no other market.
"""
import asyncio
import html
import logging
import time
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

import app.config as config
from app.engine.calendar import is_iran_bourse_open
from app.markets.iran_bourse.client import BourseError

logger = logging.getLogger("signalalert.iran_bourse")

DEFAULT_HEALTH_LOG_SECONDS = 180.0
DEFAULT_OUTAGE_ALERT_SECONDS = 600.0
DEFAULT_OUTAGE_REPEAT_SECONDS = 1800.0
DEFAULT_BRIDGE_ERROR_FRESH_SECONDS = 180.0


def _sanitize_detail(raw: Any, limit: int = 120) -> str:
    text = str(raw or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text


def _parse_timestamp(raw: Any) -> Optional[float]:
    """Parse Unix epoch seconds (or milliseconds / ISO-8601 string) to float seconds."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        val = float(raw)
        if val <= 0:
            return None
        return val / 1000.0 if val > 1e12 else val
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            val = float(s)
            if val <= 0:
                return None
            return val / 1000.0 if val > 1e12 else val
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _parse_last_error(container: Dict[str, Any]) -> Tuple[str, Optional[float]]:
    """Extract `(message, error_epoch_seconds)` from `stats` or `bridge` dict."""
    raw_err = container.get("last_error")
    if raw_err is None:
        raw_err = container.get("error")
    err_at: Optional[float] = None
    if isinstance(raw_err, dict):
        msg = _sanitize_detail(
            raw_err.get("message")
            or raw_err.get("error")
            or raw_err.get("detail")
            or raw_err.get("msg")
            or raw_err
        )
        err_at = _parse_timestamp(raw_err.get("at") or raw_err.get("ts") or raw_err.get("timestamp"))
    elif raw_err:
        msg = _sanitize_detail(raw_err)
    else:
        msg = ""

    if msg and err_at is None:
        err_at = _parse_timestamp(
            container.get("last_error_at")
            or container.get("error_at")
            or container.get("at")
        )
    return msg, err_at


def _int_or_none(raw: Any) -> Optional[int]:
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _extract_bridge_state(
    health_body: Dict[str, Any],
    *,
    now: Optional[float] = None,
    prev_errors: Optional[int] = None,
    fresh_window_seconds: float = DEFAULT_BRIDGE_ERROR_FRESH_SECONDS,
) -> Tuple[str, str]:
    """Classify Iranian bridge / upstream TSETMC health from gateway /health JSON.

    Returns `(status, detail)` where status is `'ok'` or `'error'`.
    Phase 26e rule: when the gateway itself is healthy (`status == "ok"`, `ready == True`,
    `stale == False`), an old retained `stats.last_error` is NOT treated as an active outage.
    Bridge is reported as `'error'` only if:
      1. gateway is not ready, `status != "ok"`, or `stale == True`; OR
      2. `last_error.at` (or `last_error_at`) is fresher than `fresh_window_seconds` (180s); OR
      3. `stats.errors` increased compared to `prev_errors` from the previous probe.
    """
    cur_now = time.time() if now is None else float(now)

    bridge_obj = health_body.get("bridge")
    if isinstance(bridge_obj, dict):
        b_ok = bridge_obj.get("ok")
        b_status = str(bridge_obj.get("status") or "").strip().lower()
        b_err, b_at = _parse_last_error(bridge_obj)
        b_fresh = b_at is not None and (cur_now - b_at) < fresh_window_seconds
        if b_ok is False or b_status in ("error", "down", "degraded", "fail", "failed"):
            return "error", b_err or b_status or "bridge_error"
        if b_err and b_fresh:
            return "error", b_err

    stats = health_body.get("stats") if isinstance(health_body.get("stats"), dict) else {}
    err_msg, err_at = _parse_last_error(stats)
    if err_msg and err_at is None:
        err_at = _parse_timestamp(health_body.get("last_error_at") or health_body.get("error_at"))
    gw_status = str(health_body.get("status") or "ok").strip().lower()
    stale = bool(health_body.get("stale", False))
    ready = bool(health_body.get("ready", True))
    err_count_int = _int_or_none(stats.get("errors", 0))
    err_count_disp = err_count_int if err_count_int is not None else 0

    if not ready or gw_status != "ok" or stale:
        if err_msg:
            return "error", err_msg
        reason = "not_ready" if not ready else ("stale" if stale else gw_status)
        return "error", f"{reason},errors={err_count_disp}"

    error_is_fresh = err_at is not None and (cur_now - err_at) < fresh_window_seconds
    errors_increased = (
        prev_errors is not None
        and err_count_int is not None
        and err_count_int > prev_errors
    )

    if error_is_fresh:
        return "error", err_msg or f"errors={err_count_disp}"
    if errors_increased:
        return "error", err_msg or f"errors={prev_errors}->{err_count_int}"
    return "ok", f"errors={err_count_disp}"


class BourseHealthMonitor:
    """Periodic single-line health logger (IB-12c) + market-hours outage alerter (IB-12d)."""

    def __init__(
        self,
        *,
        poller_fn: Optional[Callable[[], Any]] = None,
        health_fn: Optional[Callable[[], Awaitable[Dict[str, Any]]]] = None,
        notify_fn: Optional[Callable[[str], Awaitable[Any]]] = None,
        market_open_fn: Optional[Callable[[datetime], Tuple[bool, str]]] = None,
        interval_seconds: Optional[float] = None,
        outage_threshold_seconds: Optional[float] = None,
        repeat_alert_seconds: Optional[float] = None,
        clock: Callable[[], float] = time.time,
        now_dt_fn: Optional[Callable[[], datetime]] = None,
    ):
        self._poller_fn = poller_fn or self._default_poller
        self._health_fn = health_fn
        self._notify_fn = notify_fn
        self._market_open_fn = market_open_fn or (lambda dt: is_iran_bourse_open(dt))
        self._interval = max(
            1.0,
            float(
                interval_seconds
                if interval_seconds is not None
                else getattr(config, "IRAN_BOURSE_HEALTH_LOG_SECONDS", DEFAULT_HEALTH_LOG_SECONDS)
            ),
        )
        self._outage_threshold = max(
            1.0,
            float(
                outage_threshold_seconds
                if outage_threshold_seconds is not None
                else getattr(config, "IRAN_BOURSE_OUTAGE_ALERT_SECONDS", DEFAULT_OUTAGE_ALERT_SECONDS)
            ),
        )
        self._repeat_alert = max(
            1.0,
            float(
                repeat_alert_seconds
                if repeat_alert_seconds is not None
                else getattr(config, "IRAN_BOURSE_OUTAGE_REPEAT_SECONDS", DEFAULT_OUTAGE_REPEAT_SECONDS)
            ),
        )
        self._clock = clock
        self._now_dt_fn = now_dt_fn or (lambda: datetime.now().astimezone())

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._fault_since: Optional[float] = None
        self._fault_kind: Optional[str] = None
        self._alert_sent = False
        self._last_alert_at: Optional[float] = None
        self._last_line: Optional[str] = None
        self._last_check_at: Optional[float] = None
        self._prev_bridge_errors: Optional[int] = None

    @staticmethod
    def _default_poller() -> Any:
        from app.markets.iran_bourse import poller as pmod
        return pmod.BOURSE_POLLER

    async def _probe_gateway(self, poller: Any) -> Dict[str, Any]:
        if self._health_fn is not None:
            return await self._health_fn()
        if poller is None:
            from app.markets.iran_bourse.poller import get_poller
            poller = get_poller()
        return await poller._get_client().health()

    async def _send_alert(self, message: str) -> None:
        if self._notify_fn is not None:
            await self._notify_fn(message)
            return
        from app.notifier.telegram import notify_admin_telegram
        await notify_admin_telegram(message)

    def _poller_summary(self, poller: Any) -> Tuple[str, int]:
        if poller is None:
            return "none", 0
        st = poller.store.stats()
        running = "running" if getattr(poller, "_running", False) else "stopped"
        leader = "true" if getattr(poller, "is_leader", False) else "false"
        fails = int(getattr(poller, "_failures", 0) or 0)
        stale = "true" if st.get("stale", False) else "false"
        summary = (
            f"{running}(leader={leader},seq={st.get('seq', 0)},"
            f"watched={st.get('watched', 0)},fails={fails},stale={stale})"
        )
        return summary, fails

    async def check_once(self) -> Dict[str, Any]:
        """Run one health probe, emit one structured log line, and alert if outage >= threshold during market hours."""
        now = self._clock()
        now_dt = self._now_dt_fn()
        market_open, market_state = self._market_open_fn(now_dt)
        poller = self._poller_fn()
        poller_text, poller_fails = self._poller_summary(poller)

        gateway_status = "ok"
        gateway_detail = ""
        bridge_status = "ok"
        bridge_detail = ""
        fault_kind: Optional[str] = None
        fault_detail = ""

        try:
            health = await self._probe_gateway(poller)
            ver = _sanitize_detail(health.get("version", "?"), 24)
            ready = "true" if health.get("ready") else "false"
            stale = "true" if health.get("stale") else "false"
            age = health.get("age_seconds")
            age_str = f"{int(round(float(age)))}s" if isinstance(age, (int, float)) else "?"
            gateway_status = "ok" if (health.get("ready") and health.get("status") == "ok" and not health.get("stale")) else "degraded"
            gateway_detail = f"v{ver},ready={ready},stale={stale},age={age_str}"

            bridge_status, bridge_detail = _extract_bridge_state(
                health,
                now=now,
                prev_errors=self._prev_bridge_errors,
            )
            stats = health.get("stats") if isinstance(health.get("stats"), dict) else {}
            cur_err_count = _int_or_none(stats.get("errors"))
            if cur_err_count is not None:
                self._prev_bridge_errors = cur_err_count
            if bridge_status != "ok":
                fault_kind = "bridge"
                fault_detail = bridge_detail
            elif poller_fails > 0:
                fault_kind = "gateway"
                fault_detail = f"poller_failures={poller_fails}"
        except asyncio.CancelledError:
            raise
        except (BourseError, Exception) as exc:
            gateway_status = "down"
            gateway_detail = _sanitize_detail(type(exc).__name__, 48)
            bridge_status = "unknown"
            bridge_detail = "gateway_down"
            fault_kind = "gateway"
            fault_detail = _sanitize_detail(f"{type(exc).__name__}: {exc}", 140)

        outage_seconds = 0.0
        alert_triggered = False
        recovery_sent = False

        if not market_open:
            # Outside Tehran Bourse hours: do not page admin and reset outage timer.
            self._fault_since = None
            self._fault_kind = None
            self._alert_sent = False
            self._last_alert_at = None
        elif fault_kind is not None:
            if self._fault_since is None:
                self._fault_since = now
            self._fault_kind = fault_kind
            outage_seconds = max(0.0, now - self._fault_since)

            should_notify = (
                outage_seconds >= self._outage_threshold
                and (
                    not self._alert_sent
                    or self._last_alert_at is None
                    or (now - self._last_alert_at) >= self._repeat_alert
                )
            )
            if should_notify:
                mins = int(outage_seconds // 60)
                source_fa = "گیت‌وی بورس (tsetmc-gateway)" if fault_kind == "gateway" else "پل ایرانی / فید TSETMC"
                msg = (
                    f"🚨 <b>هشدار اختلال بورس ایران</b>\n"
                    f"<blockquote>"
                    f"منبع خطا: <b>{html.escape(source_fa)}</b>\n"
                    f"مدت اختلال وسط بازار: <code>{mins} دقیقه</code>\n"
                    f"جزئیات: <code>{html.escape(fault_detail or gateway_detail)}</code>\n"
                    f"بررسی سریع: <code>~/AlertG1/AlertG/scripts/bourse/run_gateway.sh status</code>"
                    f"</blockquote>"
                )
                try:
                    await self._send_alert(msg)
                    self._alert_sent = True
                    self._last_alert_at = now
                    alert_triggered = True
                except Exception as exc:
                    logger.warning("[IranBourse][health] admin alert send failed: %s", type(exc).__name__)
        else:
            if self._alert_sent:
                prev_kind = self._fault_kind or "gateway"
                mins = int(max(0.0, now - (self._fault_since or now)) // 60)
                msg = (
                    f"✅ <b>بازیابی سرویس بورس ایران</b>\n"
                    f"<blockquote>"
                    f"اختلال <code>{html.escape(prev_kind)}</code> پس از حدود <code>{mins} دقیقه</code> برطرف شد و فید دوباره سالم است."
                    f"</blockquote>"
                )
                try:
                    await self._send_alert(msg)
                    recovery_sent = True
                except Exception as exc:
                    logger.warning("[IranBourse][health] recovery alert send failed: %s", type(exc).__name__)
            self._fault_since = None
            self._fault_kind = None
            self._alert_sent = False
            self._last_alert_at = None

        err_suffix = f" err_sec={int(outage_seconds)}" if outage_seconds > 0 else ""
        line = (
            f"[IranBourse][health] market={market_state} "
            f"gateway={gateway_status}({gateway_detail}) "
            f"bridge={bridge_status}({bridge_detail}) "
            f"poller={poller_text}{err_suffix}"
        )
        self._last_line = line
        self._last_check_at = now
        logger.info("%s", line)

        return {
            "market_open": market_open,
            "market_state": market_state,
            "gateway": gateway_status,
            "bridge": bridge_status,
            "poller": poller_text,
            "fault_kind": fault_kind,
            "outage_seconds": outage_seconds,
            "alert_triggered": alert_triggered,
            "recovery_sent": recovery_sent,
            "line": line,
        }

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "interval_seconds": self._interval,
            "outage_threshold_seconds": self._outage_threshold,
            "fault_kind": self._fault_kind,
            "fault_since": self._fault_since,
            "alert_sent": self._alert_sent,
            "last_check_at": self._last_check_at,
            "last_line": self._last_line,
        }

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.check_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("[IranBourse][health] monitor loop error: %s", exc)
            await asyncio.sleep(self._interval)

    def start(self) -> bool:
        if self._running:
            return True
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "[IranBourse][health] monitor started (interval=%.0fs, outage_alert=%.0fs)",
            self._interval,
            self._outage_threshold,
        )
        return True

    async def stop(self) -> None:
        self._running = False
        task, self._task = self._task, None
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


BOURSE_MONITOR: Optional[BourseHealthMonitor] = None


def get_monitor() -> BourseHealthMonitor:
    global BOURSE_MONITOR
    if BOURSE_MONITOR is None:
        BOURSE_MONITOR = BourseHealthMonitor()
    return BOURSE_MONITOR


def start_bourse_monitor() -> bool:
    if not getattr(config, "IRAN_BOURSE_ENABLED", False):
        return False
    return get_monitor().start()


async def stop_bourse_monitor() -> None:
    if BOURSE_MONITOR is not None:
        await BOURSE_MONITOR.stop()
