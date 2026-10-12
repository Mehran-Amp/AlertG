import os
import re
import json
from typing import Dict, Any

APP_VERSION = "3.7.0"

DATA_DIR = os.getenv("DATA_DIR", ".")
CATALOG_FILE = os.path.join(DATA_DIR, "catalog.json") if DATA_DIR != "." else "catalog.json"
CATALOG_SNAPSHOTS_DIR = os.path.join(DATA_DIR, "catalog_snapshots") if DATA_DIR != "." else "catalog_snapshots"
SYNC_RUNS_FILE = os.path.join(DATA_DIR, "sync_runs.json") if DATA_DIR != "." else "sync_runs.json"
# Bump when the catalog.json layout changes; load_catalog() refuses files written by a newer schema.
CATALOG_SCHEMA_VERSION = 1

# Automatic .env loading for CLI tools/scripts if not already in os.environ
def _load_env_file():
    candidates = [
        os.getenv("ENV_FILE", ".env"),
        os.path.join(DATA_DIR, ".env") if DATA_DIR != "." else ".env",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
    ]
    for env_path in candidates:
        if os.path.exists(env_path) and os.path.isfile(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
                break
            except Exception:
                pass

_load_env_file()

# 0. Security Configuration, Auth Dependencies & Validation Helpers
API_KEY = os.getenv("API_KEY", "").strip()          # shared key the mobile app sends as X-API-Key
ADMIN_KEY = os.getenv("ADMIN_KEY", "").strip()      # operator key: /status, /debug/*, /test/push
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

# External Global Stocks & Macro Provider API Keys
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "").strip()
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()

SYMBOL_RE = re.compile(r'^[A-Za-z0-9^.=_/\-]{1,32}$')
EXCHANGE_RE = re.compile(r'^[a-z0-9_.\-]{1,32}$')
CHAT_ID_RE = re.compile(r'^(-?\d{1,20}|@[A-Za-z0-9_]{3,64})$')
MAX_ALERTS_PER_USER = 200
MAX_NOTE_LEN = 500
MAX_WEBHOOK_LEN = 500

# 1. Firebase Configuration & Telegram Bot Metadata
SERVICE_ACCOUNT_FILE = os.path.join(DATA_DIR, "serviceAccountKey.json") if DATA_DIR != "." else "serviceAccountKey.json"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_BOT_METADATA: Dict[str, Any] = {
    "username": "aisocialfeedbot",
    "first_name": "AiSFeed",
    "id": 8597547058,
    "is_connected": False
}

CACHE_TTL_IRAN = 60.0 # Strict 60-second cache as requested for Iran markets

# Iran High-Speed Bridge / Relay Endpoint (aegkala.com Host in Iran)
IRAN_BRIDGE_URL = os.environ.get("IRAN_BRIDGE_URL", "https://aegkala.com/market-bridge.php")
IRAN_BRIDGE_TOKEN = os.environ.get("SIGNALALERT_BRIDGE_TOKEN", os.environ.get("IRAN_BRIDGE_TOKEN", "")).strip()

# Admin Telegram Alerts & Notifications
TELEGRAM_ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").strip()

# Provider & Category Kill Switches
# Example: KILL_SWITCH_PROVIDERS="yahoo,nobitex" or KILL_SWITCH_CATEGORIES="crypto,forex"
# Or single env: KILL_SWITCHES="yahoo,iran,macro"
KILL_SWITCH_PROVIDERS = [p.strip().lower() for p in os.getenv("KILL_SWITCH_PROVIDERS", os.getenv("DISABLED_PROVIDERS", "")).split(",") if p.strip()]
KILL_SWITCH_CATEGORIES = [c.strip().lower() for c in os.getenv("KILL_SWITCH_CATEGORIES", os.getenv("DISABLED_CATEGORIES", "")).split(",") if c.strip()]
KILL_SWITCHES = [k.strip().lower() for k in os.getenv("KILL_SWITCHES", os.getenv("KILL_SWITCH", "")).split(",") if k.strip()]
