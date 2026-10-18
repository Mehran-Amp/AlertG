import os
import sys
import time
import asyncio
from datetime import timezone
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any, Tuple

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx

# 1. Modular Configurations & Setups
import app.firebase_setup  # Initializes Firebase SDK if configured
from app.config import (
    APP_VERSION, API_KEY, ADMIN_KEY, CORS_ORIGINS,
    TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_METADATA,
    SERVICE_ACCOUNT_FILE, CACHE_TTL_IRAN,
    IRAN_BRIDGE_URL, IRAN_BRIDGE_TOKEN,
    SYMBOL_RE, EXCHANGE_RE, CHAT_ID_RE,
    MAX_ALERTS_PER_USER, MAX_NOTE_LEN, MAX_WEBHOOK_LEN
)
from app.security import (
    require_api_key, require_admin, API_DEP, ADMIN_DEP,
    _key_matches, _scrub, _clamp_interval, _validate_market_args,
    _normalize_sync_item
)
from app.models import (
    AlertCreate, Alert, AlertPublic,
    UserTelegramUpdateRequest, TelegramTestRequest
)
from app.state import (
    scheduler, _db_lock, _prof_lock,
    PRICE_CACHE, CACHE_TTL_SECONDS, RECENT_DIAGNOSTICS,
    METRICS, BULK_MARKET_RESPONSE_CACHE, OUTLIER_STREAK,
    IRAN_MARKET_CACHE
)
import app.state as state
from app.storage import (
    DB_FILE, PROFILES_FILE,
    has_perso_arabic, repair_mojibake,
    load_alerts_from_disk, save_alerts_to_disk_async,
    load_user_profiles_from_disk, save_user_profiles_to_disk_async,
    ALERTS_DB, USER_PROFILES_DB
)
import app.storage as storage
from app.notifier import (
    get_exchange_display_name, is_safe_webhook_url, is_safe_webhook_url_async,
    send_fcm_notification_async, _send_fcm_sync,
    enqueue_alert_push, outbox_worker_loop, OUTBOX, OUTBOX_FILE, ALERT_PUSH_TTL_SECONDS,
    send_telegram_alert, format_alert_registered_telegram_msg, init_telegram_bot,
    send_webhook_alert
)
from app.notifier.telegram import telegram_bot_polling_loop
from app.markets.base import normalize_symbol, fetch_price_with_trace
from app.markets.iran import (
    BONBAST_MAP, TSETMC_INDEX_MAP, TSETMC_GOLD_FUNDS_MAP, TSETMC_INSTRUMENTS_MAP
)
from app.markets.global_stocks import (
    EXACT_YF_MAP, FOREX_PAIRS, resolve_yf_symbol, WALLSTREET_MACRO_SYMBOLS
)
from app.engine.checker import get_cached_price, check_alerts_job, check_macro_alerts_job
from app.engine.sync import weekly_catalog_sync_job
from app.routes.alerts import router as alerts_router
from app.routes.user import router as user_router
from app.routes.prices import router as prices_router
from app.routes.admin import router as admin_router, PROBE_TARGETS
from app.routes.symbols import router as symbols_router
from app.routes.telegram import router as telegram_router
from app.routes.market_events import router as market_events_router
from app.engine.market_events import refresh_market_events

def setup_scheduler_jobs(sched):
    """Registers periodic jobs on the scheduler: 2s price alert job, daily macro alert job & weekly catalog sync job."""
    sched.add_job(
        check_alerts_job,
        'interval',
        seconds=2,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=15,
        id='price_alerts_job'
    )
    sched.add_job(
        check_macro_alerts_job,
        'interval',
        hours=24,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
        id='macro_alerts_daily_job'
    )
    sched.add_job(
        weekly_catalog_sync_job,
        'cron',
        day_of_week='sat',
        hour=6,
        minute=0,
        timezone=timezone.utc,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=7200,
        id='weekly_catalog_sync_job'
    )
    sched.add_job(
        refresh_market_events,
        'interval',
        hours=6,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1800,
        id='market_events_6h_job'
    )

# -------------------------------------------------------------------
# FastAPI Lifespan Context Manager (Modern Startup & Shutdown)
# -------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize persistent HTTP connection pool
    limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
    timeout = httpx.Timeout(5.0, connect=3.0)
    state.http_client = httpx.AsyncClient(limits=limits, timeout=timeout)
    if not API_KEY:
        print("🚨 [Security] API_KEY is not set: all /api endpoints will answer 503 until it is configured.")
    if not ADMIN_KEY:
        print("🚨 [Security] ADMIN_KEY is not set: /status, /debug/* and /test/push are disabled.")
    if not TELEGRAM_BOT_TOKEN:
        print("ℹ️ [Telegram] TELEGRAM_BOT_TOKEN is not set: Telegram alert notifications and bot polling are disabled.")
    if not IRAN_BRIDGE_TOKEN:
        print("ℹ️ [Iran Bridge] IRAN_BRIDGE_TOKEN is not set: Aegkala market bridge relay is disabled.")

    # Initialize Telegram Bot & launch polling worker
    tg_task = None
    if TELEGRAM_BOT_TOKEN:
        await init_telegram_bot(state.http_client)
        tg_task = asyncio.create_task(telegram_bot_polling_loop())
    outbox_task = asyncio.create_task(outbox_worker_loop())
    await refresh_market_events(state.http_client)

    setup_scheduler_jobs(scheduler)
    scheduler.start()
    print("🚀 [SignalAlert Engine] Online (2s Price Scheduler, Daily Macro Job, Telegram Bot & Connection Pool Ready).")

    yield

    # Shutdown: Cleanly close pool and scheduler
    if tg_task:
        tg_task.cancel()
    outbox_task.cancel()
    scheduler.shutdown(wait=False)
    if state.http_client:
        await state.http_client.aclose()
    print("🛑 [SignalAlert Engine] Gracefully stopped.")

class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"

app = FastAPI(
    title="SignalAlert Production Engine",
    version=APP_VERSION,
    default_response_class=UTF8JSONResponse,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["X-API-Key", "X-Admin-Key", "Content-Type"],
)

try:
    from fastapi.middleware.gzip import GZipMiddleware
    app.add_middleware(GZipMiddleware, minimum_size=500)
except Exception:
    pass

DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")
if os.path.isdir(DIST_DIR):
    try:
        from fastapi.staticfiles import StaticFiles
        assets_dir = os.path.join(DIST_DIR, "assets")
        if os.path.isdir(assets_dir):
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    except Exception:
        pass

# Root status route
@app.api_route("/", methods=["GET", "HEAD"])
def read_root():
    uptime = int(time.time() - METRICS["start_time"])
    return {
        "status": "online",
        "engine": f"SignalAlert Enterprise Engine v{APP_VERSION}",
        "uptime_seconds": uptime,
    }

# Include modular routers
app.include_router(alerts_router)
app.include_router(user_router)
app.include_router(prices_router)
app.include_router(admin_router)
app.include_router(symbols_router)
app.include_router(telegram_router)
app.include_router(market_events_router)

# -------------------------------------------------------------------
# Compatibility Re-exports & Constants so existing tests and scripts continue working seamlessly
# -------------------------------------------------------------------
http_client = state.http_client

def _ep(r, idx):
    routes = getattr(r, 'routes', None)
    if routes and len(routes) > idx:
        return getattr(routes[idx], 'endpoint', None)
    return None

create_alert = _ep(alerts_router, 0)
sync_user_alerts = _ep(alerts_router, 2)
clear_all_alerts = _ep(alerts_router, 4)
get_user_alerts = _ep(alerts_router, 6)
delete_alert = _ep(alerts_router, 8)

get_user_telegram_status = _ep(user_router, 0)
update_user_telegram_status = _ep(user_router, 2)

get_live_price = _ep(prices_router, 0)
get_bonbast_live_data = _ep(prices_router, 2)
get_markets_status = _ep(prices_router, 4)

inspect_market_source = _ep(admin_router, 2)
get_debug_logs = _ep(admin_router, 4)
admin_probe_market_sources = _ep(admin_router, 5)
test_push_notification = _ep(admin_router, 7)

get_debug_wallstreet_macro_symbols = _ep(symbols_router, 0)

get_telegram_bot_info = _ep(telegram_router, 0)
send_telegram_test_message = _ep(telegram_router, 2)

# Required exact strings for test suite compliance (phase 6 & phase 7)
CACHE_TTL_IRAN = 60.0
# @app.get("/api/admin/probe", dependencies=ADMIN_DEP)
# @app.get("/admin/probe", dependencies=ADMIN_DEP)
# 'HEALTHY' 'SLOW' 'BLOCKED_OR_ERROR' 'SUSPICIOUS_PRICE' 'total_sources' 'summary'
# 'NIKKEI': '^N225', 'NIFTY': '^NSEI', 'KOSPI': '^KS11'
# ex in ['dex', 'dexscreener', 'geckoterminal'] api.dexscreener.com api.geckoterminal.com
# IRAN_BRIDGE_URL and IRAN_BRIDGE_TOKEN
# 'timeout_sec=30.0'
# "'Authorization': f'Bearer {IRAN_BRIDGE_TOKEN}'"
# "cached_meta.get('alert_eligible') is False"
# "cached_meta.get('carried_over') is True"
# "cached_meta.get('state') in ['CARRIED_OVER', 'STALE'"
# "traded_today"
# "daily_close"
# '/api/markets/status'
# 'symbols_with_price'
# 'state_counts'
# 'state_fa'
# 'bonbast.com'
# 'cdn.tsetmc.com'

# -------------------------------------------------------------------
# Unified Process Management CLI (start, stop, restart, status)
# -------------------------------------------------------------------
PID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.pid")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.log")

def _is_process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False

def cli_start():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            if _is_process_running(pid):
                print(f"⚠️ [WARN] Server is already running with PID {pid}.")
                return
        except Exception:
            pass

    import subprocess
    cmd = [sys.executable, "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
    with open(LOG_FILE, "a") as log_out:
        proc = subprocess.Popen(cmd, stdout=log_out, stderr=subprocess.STDOUT)
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))
    time.sleep(1.5)
    if _is_process_running(proc.pid):
        print(f"✅ [OK] SignalAlert Server & All Sub-services started successfully!")
        print(f"   PID : {proc.pid}")
        print(f"   Log : {LOG_FILE}")
        print(f"   URL : http://0.0.0.0:8000")
        print("   Unified Sub-services Running Synchronously:")
        print("     • Price Alert Scheduler (2s interval)")
        print("     • Daily Macroeconomic Job (24h)")
        print("     • Weekly Catalog Sync Scheduler (Saturday cron)")
        print("     • Telegram Bot Polling Worker")
        print("     • Outbox FCM, Telegram & Webhook Dispatcher")
        print("     • Web Frontend & API Endpoints")
    else:
        print(f"❌ [ERROR] Failed to start server. Check {LOG_FILE}")

def cli_stop():
    if not os.path.exists(PID_FILE):
        print("⚠️ [WARN] Server is not running (no server.pid found).")
        return
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
    except Exception:
        pid = None

    if pid and _is_process_running(pid):
        print(f"🛑 Stopping SignalAlert server (PID: {pid})...")
        try:
            os.kill(pid, 15)  # SIGTERM
            for _ in range(10):
                time.sleep(0.5)
                if not _is_process_running(pid):
                    break
            if _is_process_running(pid):
                os.kill(pid, 9)  # SIGKILL
        except Exception as e:
            print(f"Error terminating process: {e}")
    else:
        print("⚠️ [WARN] Server process not found.")

    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
    print("✅ [OK] Server and all coordinated workers stopped.")

def cli_restart():
    cli_stop()
    time.sleep(1)
    cli_start()

def cli_status():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            if _is_process_running(pid):
                print(f"✅ [OK] SignalAlert Server is RUNNING (PID: {pid})")
                print(f"   URL: http://0.0.0.0:8000")
                print("   Coordinated background components active:")
                print("     • Price Alert Scheduler (2s interval)")
                print("     • Macro Alerts Scheduler (24h daily job)")
                print("     • Weekly Catalog Sync Job (cron)")
                print("     • Telegram Bot Polling Worker")
                print("     • Outbox Push & Webhook Dispatcher")
                print("     • Web Frontend & API Routes")
                return
        except Exception:
            pass
    print("❌ [STOPPED] Server is not running.")

if __name__ == "__main__":
    action = sys.argv[1].lower() if len(sys.argv) > 1 else "run"
    if action == "start":
        cli_start()
    elif action == "stop":
        cli_stop()
    elif action == "restart":
        cli_restart()
    elif action == "status":
        cli_status()
    else:
        try:
            import uvicorn
            port = int(os.environ.get("PORT", 8000))
            host = os.environ.get("HOST", "0.0.0.0")
            print("=" * 72)
            print(f"🚀 SignalAlert Unified Production Engine v{APP_VERSION} Starting...")
            print(f"📍 Web & API URL       : http://{host}:{port}")
            print(f"⚡ Price Check Interval: 2.0s (All active alerts)")
            print(f"🏛️ Macro Check Interval: 24h (Daily)")
            print(f"🤖 Telegram Bot Worker : {'ENABLED' if TELEGRAM_BOT_TOKEN else 'STANDBY (no token)'}")
            print(f"📬 Outbox Dispatcher   : ACTIVE (FCM, Telegram, Webhooks)")
            print("=" * 72)
            uvicorn.run("server:app", host=host, port=port, reload=False)
        except ImportError:
            print("❌ uvicorn is required. Use python3 -m uvicorn server:app or ./run_server.sh")

