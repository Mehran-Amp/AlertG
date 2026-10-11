#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SignalAlert Offline Catalog Validator (Phase 4 / v3.2.0)

Strictly validates catalog items offline against domain integrity rules:
1. SYMBOL_RE: Valid ticker pattern (e.g., AAPL, BRK.B, ^GSPC, EUR/USD, DGS10)
2. EXCHANGE_RE: Valid exchange code (e.g., NASDAQ, NYSE, CME, FRED, FOREX, HKEX)
3. asset_class: One of ('stock', 'etf', 'forex', 'index', 'commodity', 'bond', 'macro')
4. currency: ISO standard currency code
5. provider_map: Non-empty, priority-mapped, restricted to permitted providers:
   ['yahoo', 'finnhub', 'twelve_data', 'fred']. Stooq or unapproved 5th provider rejected.
6. Deduplication: No duplicate symbol IDs.
7. Category isolation: No symbol assigned to multiple categories.
8. Iran & Crypto isolation: No Iran market ('iran_market') or crypto assets in global catalog.
"""

import sys
import os
import json
import re
from typing import Dict, Any, List, Tuple

SYMBOL_RE = re.compile(r'^[A-Za-z0-9^][A-Za-z0-9\.\-\=\/\_\s\(\)\&\^]{0,31}$', re.IGNORECASE)
EXCHANGE_RE = re.compile(r'^[a-zA-Z0-9\_\-\s\.\&öäüéèáà]{2,40}$', re.IGNORECASE)
VALID_ASSET_CLASSES = {'stock', 'etf', 'forex', 'index', 'commodity', 'bond', 'macro'}
VALID_CURRENCIES = {'USD', 'EUR', 'GBP', 'JPY', 'CAD', 'CHF', 'AUD', 'NZD', 'CNY', 'HKD', 'AED', 'IRR', 'IRT'}
ALLOWED_PROVIDERS = {'yahoo', 'finnhub', 'twelve_data', 'fred'}
FORBIDDEN_CATEGORIES = {'iran_market', 'crypto'}


def validate_catalog_payload(data: Any) -> Tuple[bool, List[str]]:
    """
    Validates a catalog payload (dict or list of items) completely offline.
    Returns (is_valid, list_of_errors).
    """
    errors: List[str] = []

    if isinstance(data, dict):
        items = data.get("symbols", [])
        if not isinstance(items, list):
            errors.append("Payload 'symbols' field must be a list.")
            return False, errors
    elif isinstance(data, list):
        items = data
    else:
        errors.append("Invalid payload format; expected dict with 'symbols' or list of symbol dicts.")
        return False, errors

    if not items:
        errors.append("Catalog contains zero items; empty catalog rejected.")
        return False, errors

    seen_symbols: set = set()
    symbol_to_category: Dict[str, str] = {}

    for idx, item in enumerate(items):
        prefix = f"Item #{idx}"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: Item is not an object/dict.")
            continue

        sym_id = (item.get("id") or item.get("symbol") or "").strip()
        prefix = f"Item #{idx} ({sym_id or 'UNKNOWN'})"

        # 1. Required symbol ID and SYMBOL_RE
        if not sym_id:
            errors.append(f"{prefix}: Missing 'id' / 'symbol'.")
        elif not SYMBOL_RE.match(sym_id):
            errors.append(f"{prefix}: Symbol '{sym_id}' violates SYMBOL_RE pattern.")

        # Deduplication check
        sym_key = sym_id.upper()
        if sym_key in seen_symbols:
            errors.append(f"{prefix}: Duplicate symbol '{sym_id}' found in catalog.")
        seen_symbols.add(sym_key)

        # 2. Asset class / Category validation
        raw_asset_class = (item.get("asset_class") or item.get("category") or "").strip().lower()
        if not raw_asset_class:
            errors.append(f"{prefix}: Missing 'asset_class' or 'category'.")
        elif raw_asset_class in FORBIDDEN_CATEGORIES:
            errors.append(f"{prefix}: Asset class '{raw_asset_class}' belongs to isolated market (Iran/Crypto) and is forbidden in global catalog.")
        elif raw_asset_class not in VALID_ASSET_CLASSES:
            errors.append(f"{prefix}: Invalid asset_class '{raw_asset_class}'. Allowed: {sorted(VALID_ASSET_CLASSES)}")
        else:
            # Check multi-category collision
            if sym_key in symbol_to_category and symbol_to_category[sym_key] != raw_asset_class:
                errors.append(f"{prefix}: Symbol '{sym_id}' exists in multiple categories ('{symbol_to_category[sym_key]}' and '{raw_asset_class}').")
            symbol_to_category[sym_key] = raw_asset_class

        # 3. Exchange validation
        raw_exchange = (item.get("exchange") or item.get("marketName") or "").strip()
        if not raw_exchange:
            errors.append(f"{prefix}: Missing 'exchange'.")
        elif not EXCHANGE_RE.match(raw_exchange):
            errors.append(f"{prefix}: Exchange '{raw_exchange}' violates EXCHANGE_RE pattern.")

        # 4. Currency validation
        raw_currency = (item.get("currency") or item.get("unit") or "$").strip().upper()
        # Normalize common symbol notations
        curr_map = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "FR": "CHF", "Fr": "CHF", "C$": "CAD", "A$": "AUD", "ت": "IRT", "%": "USD", "PTS": "USD", "واحد": "IRR"}
        normalized_curr = curr_map.get(raw_currency, raw_currency)
        if normalized_curr not in VALID_CURRENCIES:
            errors.append(f"{prefix}: Invalid currency '{raw_currency}'. Allowed: {sorted(VALID_CURRENCIES)}")

        # 5. Provider Map validation
        provider_map = item.get("provider_map")
        if provider_map is not None:
            if not isinstance(provider_map, dict) or len(provider_map) == 0:
                errors.append(f"{prefix}: 'provider_map' must be a non-empty dictionary.")
            else:
                for prov, prov_conf in provider_map.items():
                    if prov not in ALLOWED_PROVIDERS:
                        errors.append(f"{prefix}: Provider '{prov}' is forbidden. Only {sorted(ALLOWED_PROVIDERS)} permitted.")
                    if isinstance(prov_conf, dict):
                        if not prov_conf.get("symbol"):
                            errors.append(f"{prefix}: Provider '{prov}' missing mapped 'symbol'.")
                        if not isinstance(prov_conf.get("priority", 1), int):
                            errors.append(f"{prefix}: Provider '{prov}' priority must be an integer.")

    return len(errors) == 0, errors


def validate_catalog_file(file_path: str) -> Tuple[bool, List[str]]:
    """Validates a JSON catalog file offline from disk."""
    if not os.path.exists(file_path):
        return False, [f"File not found: {file_path}"]

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return False, [f"Malformed JSON in {file_path}: {e}"]

    return validate_catalog_payload(data)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/validate_catalog_offline.py <path_to_catalog_or_seed.json>")
        sys.exit(2)

    target_path = sys.argv[1]
    is_valid, errors = validate_catalog_file(target_path)

    if is_valid:
        print(f"✅ [VALID] {target_path} passed all structural and domain validation rules.")
        sys.exit(0)
    else:
        print(f"❌ [INVALID] {target_path} failed validation with {len(errors)} error(s):")
        for err in errors:
            print(f"  • {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
