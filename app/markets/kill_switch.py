import os
import re
from typing import Set, Dict, Any, List

def _parse_list_from_env(var_name: str) -> Set[str]:
    val = os.getenv(var_name, "").strip().lower()
    if not val:
        return set()
    # Split by comma or whitespace or semicolon
    items = [x.strip() for x in re.split(r'[,;\s]+', val) if x.strip()]
    return set(items)

def is_provider_killed(provider_id: str) -> bool:
    """
    Checks if a provider is disabled via environment variable kill switch.
    Supports:
      - KILL_SWITCH_PROVIDERS="yahoo,twelvedata"
      - KILL_SWITCH_PROVIDER_<NAME>=1 / true / yes
    """
    if not provider_id:
        return False
    norm_id = provider_id.strip().lower()
    
    # 1. Global list
    killed_list = _parse_list_from_env("KILL_SWITCH_PROVIDERS")
    if norm_id in killed_list:
        return True
    
    # Also check if provider aliases match (e.g. 'gate' vs 'gateio')
    if norm_id == 'gate' and 'gateio' in killed_list:
        return True
    if norm_id == 'gateio' and 'gate' in killed_list:
        return True

    # 2. Specific per-provider env variable
    clean_env_key = re.sub(r'[^a-zA-Z0-9_]', '_', norm_id).upper()
    val = os.getenv(f"KILL_SWITCH_PROVIDER_{clean_env_key}", "").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True

    return False

def is_category_killed(category: str) -> bool:
    """
    Checks if a market category is disabled via environment variable kill switch.
    Supports:
      - KILL_SWITCH_CATEGORIES="iran,crypto,macro"
      - KILL_SWITCH_CATEGORY_<CAT>=1 / true / yes
      - KILL_SWITCH_<CAT>=1 / true / yes (e.g. KILL_SWITCH_IRAN=1)
    """
    if not category:
        return False
    norm_cat = category.strip().lower()

    # 1. Global list
    killed_list = _parse_list_from_env("KILL_SWITCH_CATEGORIES")
    if norm_cat in killed_list:
        return True

    # Also check category aliases (e.g., 'global_stocks' vs 'stocks', 'iran_market' vs 'iran')
    if norm_cat in ('stocks', 'global_stocks') and ('stocks' in killed_list or 'global_stocks' in killed_list):
        return True
    if norm_cat in ('iran', 'iran_market') and ('iran' in killed_list or 'iran_market' in killed_list):
        return True

    # 2. Specific env variables
    clean_env_key = re.sub(r'[^a-zA-Z0-9_]', '_', norm_cat).upper()
    val1 = os.getenv(f"KILL_SWITCH_CATEGORY_{clean_env_key}", "").strip().lower()
    if val1 in ("1", "true", "yes", "on"):
        return True

    val2 = os.getenv(f"KILL_SWITCH_{clean_env_key}", "").strip().lower()
    if val2 in ("1", "true", "yes", "on"):
        return True

    return False

def get_active_kill_switches() -> Dict[str, Any]:
    """Returns overview of all currently active kill switches."""
    providers_killed: Set[str] = set()
    categories_killed: Set[str] = set()

    # From list envs
    providers_killed.update(_parse_list_from_env("KILL_SWITCH_PROVIDERS"))
    categories_killed.update(_parse_list_from_env("KILL_SWITCH_CATEGORIES"))

    # From per-item envs
    for k, v in os.environ.items():
        v_low = v.strip().lower()
        if v_low in ("1", "true", "yes", "on"):
            if k.startswith("KILL_SWITCH_PROVIDER_"):
                prov = k[len("KILL_SWITCH_PROVIDER_"):].lower()
                providers_killed.add(prov)
            elif k.startswith("KILL_SWITCH_CATEGORY_"):
                cat = k[len("KILL_SWITCH_CATEGORY_"):].lower()
                categories_killed.add(cat)
            elif k.startswith("KILL_SWITCH_") and k not in ("KILL_SWITCH_PROVIDERS", "KILL_SWITCH_CATEGORIES"):
                cat_or_prov = k[len("KILL_SWITCH_"):].lower()
                categories_killed.add(cat_or_prov)

    prov_sorted = sorted(list(providers_killed))
    cat_sorted = sorted(list(categories_killed))

    return {
        "providers_killed": prov_sorted,
        "categories_killed": cat_sorted,
        "any_active": bool(prov_sorted or cat_sorted)
    }
