import os
import re
import json
from typing import Dict, Any

APP_VERSION = "3.9.2"

DATA_DIR = os.getenv("DATA_DIR", ".")
CATALOG_FILE = os.getenv("CATALOG_FILE") or (os.path.join(DATA_DIR, "catalog.json") if DATA_DIR != "." else "catalog.json")
CATALOG_SNAPSHOTS_DIR = os.getenv("CATALOG_SNAPSHOTS_DIR") or (os.path.join(DATA_DIR, "catalog_snapshots") if DATA_DIR != "." else "catalog_snapshots")
SYNC_RUNS_FILE = os.getenv("SYNC_RUNS_FILE") or (os.path.join(DATA_DIR, "sync_runs.json") if DATA_DIR != "." else "sync_runs.json")
ALERTS_DATA_FILE = os.getenv("ALERTS_DATA_FILE") or (os.path.join(DATA_DIR, "alerts_data.json") if DATA_DIR != "." else "alerts_data.json")
USER_PROFILES_FILE = os.getenv("USER_PROFILES_FILE") or (os.path.join(DATA_DIR, "user_profiles.json") if DATA_DIR != "." else "user_profiles.json")
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

# External Global Stocks & Macro Provider API Keys (with robust default fallback demo keys)
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "").strip() or "sandbox_key"
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip() or "demo"
FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip() or "demo_fred"

# Phase REGEX-1: widened to match catalog.json and sync.py, per manager decision.
# - SYMBOL_RE: 1-32 chars (11 single-letter tickers exist: A, T, C, D, P, F, J, L, Q, O, V).
# - EXCHANGE_RE: 2-40 chars (matches sync.py; no single-char exchange exists).
# - Space allowed only in the middle (no leading/trailing space).
# - '&' allowed; EXCHANGE_RE also allows öäüéèáà.
# - No \s (avoids tabs/newlines); only a literal space.
# - (?!.*\.\.) rejects ".." (manager requirement) while still allowing "BRK.B".
SYMBOL_RE = re.compile(
    r'^(?!.*\.\.)[A-Za-z0-9^.=_/\-&\(](?:[A-Za-z0-9^.=_/\-& \(\)]{0,30}[A-Za-z0-9^.=_/\-&\)])?$'
)
EXCHANGE_RE = re.compile(
    r'^(?!.*\.\.)[A-Za-z0-9_.\-&öäüéèáà][A-Za-z0-9_.\-&öäüéèáà ]{0,38}[A-Za-z0-9_.\-&öäüéèáà]$',
    re.IGNORECASE,
)
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
# Phase WS-OFF-1: WebSocket is OFF by default until cPanel proxies /ws.
# Set WS_ENABLED=true (and configure reverse proxy) to enable it.
WS_ENABLED = os.getenv("WS_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")

# Phase Sync-Toggle: Automated weekly catalog sync flag (disabled by default; manual CLI sync preferred)
WEEKLY_CATALOG_SYNC_ENABLED = os.getenv("WEEKLY_CATALOG_SYNC_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")

# Phase 3: Strict Crypto Price Core (Rule R1: exchange isolation, zero cross-exchange fallback)
CRYPTO_STRICT_V2 = os.getenv("CRYPTO_STRICT_V2", "false").strip().lower() in ("1", "true", "yes", "on")

# Phase 5: Dynamic Crypto Exchange Catalogs & Safety Settings
CRYPTO_CATALOG_DIR = os.getenv("CRYPTO_CATALOG_DIR") or (os.path.join(DATA_DIR, "crypto_catalogs") if DATA_DIR != "." else "crypto_catalogs")
CRYPTO_CATALOG_SYNC_ENABLED = os.getenv("CRYPTO_CATALOG_SYNC_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
CRYPTO_CATALOG_SYNC_INTERVAL_HOURS = int(os.getenv("CRYPTO_CATALOG_SYNC_INTERVAL_HOURS", "6"))
CRYPTO_CATALOG_MIN_PAIRS = int(os.getenv("CRYPTO_CATALOG_MIN_PAIRS", "20"))
CRYPTO_CATALOG_MAX_DROP_RATIO = float(os.getenv("CRYPTO_CATALOG_MAX_DROP_RATIO", "0.50"))


