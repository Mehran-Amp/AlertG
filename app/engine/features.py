import os
import re
from typing import Set, Dict, Any, Optional

def get_beta_users() -> Set[str]:
    """Returns set of registered beta testers from environment variable BETA_USER_IDS."""
    raw = os.getenv("BETA_USER_IDS", "").strip()
    if not raw:
        return set()
    return {u.strip().lower() for u in re.split(r'[,;\s]+', raw) if u.strip()}

def is_beta_user(user_id: Optional[str]) -> bool:
    """Checks if a user or device ID is part of the beta cohort."""
    if not user_id:
        return False
    return user_id.strip().lower() in get_beta_users()

# Default feature flags configuration
DEFAULT_FEATURE_FLAGS: Dict[str, Dict[str, Any]] = {
    "v3_mobile_delta_sync": {
        "description": "Delta sync catalog for Flutter v3.0.0 app",
        "enabled": True,
        "beta_only": False,
    },
    "macro_alerts_engine": {
        "description": "US10Y, CPI, and economic calendar macro triggers",
        "enabled": True,
        "beta_only": False,
    },
    "deep_debug_observability": {
        "description": "Phase 9 Admin Observability and Quota Monitoring",
        "enabled": True,
        "beta_only": False,
    },
    "resilient_dex_pricing": {
        "description": "DexScreener and GeckoTerminal on-chain routing",
        "enabled": True,
        "beta_only": False,
    },
    "beta_experiments": {
        "description": "Experimental features restricted to beta cohort",
        "enabled": True,
        "beta_only": True,
    }
}

# Runtime overrides
_DYNAMIC_FLAGS: Dict[str, bool] = {}

def is_feature_enabled(flag_name: str, user_id: Optional[str] = None) -> bool:
    """
    Checks if a feature flag is enabled for the general population or a specific beta user.
    Precedence:
      1. Dynamic runtime override (set via admin API or tests)
      2. Environment variable: FEATURE_FLAG_<NAME>="true" / "1" / "beta"
      3. Default flag configuration
    """
    flag_key = flag_name.strip().lower()

    # 1. Dynamic override
    if flag_key in _DYNAMIC_FLAGS:
        val = _DYNAMIC_FLAGS[flag_key]
        if not val:
            return False

    # 2. Environment variable
    clean_env_key = re.sub(r'[^a-zA-Z0-9_]', '_', flag_key).upper()
    env_val = os.getenv(f"FEATURE_FLAG_{clean_env_key}", "").strip().lower()

    if env_val in ("0", "false", "off", "no"):
        return False

    flag_def = DEFAULT_FEATURE_FLAGS.get(flag_key, {
        "description": flag_name,
        "enabled": True,
        "beta_only": False,
    })

    is_beta_restricted = (env_val == "beta") or flag_def.get("beta_only", False)

    if is_beta_restricted:
        return is_beta_user(user_id)

    if env_val in ("1", "true", "on", "yes"):
        return True

    return bool(flag_def.get("enabled", True))

def set_feature_override(flag_name: str, enabled: Optional[bool]) -> None:
    """Sets or clears a dynamic runtime feature flag override."""
    flag_key = flag_name.strip().lower()
    if enabled is None:
        _DYNAMIC_FLAGS.pop(flag_key, None)
    else:
        _DYNAMIC_FLAGS[flag_key] = enabled

def get_all_feature_flags(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Returns overview of all configured feature flags and beta status."""
    flags = {}
    for name, conf in DEFAULT_FEATURE_FLAGS.items():
        enabled = is_feature_enabled(name, user_id=user_id)
        flags[name] = {
            "description": conf.get("description", ""),
            "enabled": enabled,
            "beta_only": conf.get("beta_only", False),
            "effective_for_user": enabled if user_id else None
        }
    return {
        "flags": flags,
        "beta_users_count": len(get_beta_users()),
        "user_is_beta": is_beta_user(user_id) if user_id else False
    }
