# -*- coding: utf-8 -*-
"""
AlertG — Crypto Alert Validation Engine (Phase 4 / Version 2).
Enforces Rule R1, R5, and Phase 4 constraints:
1. Rejects discontinued exchange 'coinex' with code 'EXCHANGE_NOT_SUPPORTED'.
2. Rejects unknown crypto exchanges with code 'EXCHANGE_NOT_SUPPORTED'.
3. Rejects non-USDT quote currencies for crypto alerts with code 'INVALID_QUOTE_CURRENCY'.
4. Verifies coin listing in the exchange's catalog with code 'SYMBOL_NOT_LISTED'.
5. Preserves 100% backward compatibility for stock, forex, and Iranian alerts.
"""

from typing import Tuple, Optional, Dict, Any
import logging

import app.config as config
from app.markets.crypto_registry import (
    get_crypto_exchange,
    is_supported_crypto_exchange,
    list_crypto_exchanges,
)
from app.markets.crypto_catalog import resolve_pair

logger = logging.getLogger("signalalert.crypto_validation")

# Non-crypto exchanges that are handled by other market subsystems
NON_CRYPTO_EXCHANGES = frozenset({
    "nobitex", "wallex", "tabdeal", "bitpin", "tetherland", "abantether",
    "ramzinex", "bitbarg", "sarmayex", "exir", "iran_market", "bonbast",
    "bridge", "tse", "stocks", "global_stocks", "macro", "forex", "bonds",
    "wallstreet", "commodities", "timer", "local", "clock", "none"
})


def is_crypto_exchange_candidate(exchange_id: str) -> bool:
    """Returns True if the exchange ID targets the global cryptocurrency subsystem."""
    ex = (exchange_id or "").lower().strip()
    if ex in NON_CRYPTO_EXCHANGES:
        return False
    return True


def validate_crypto_alert(
    exchange: str,
    symbol: str,
    base_currency: Optional[str] = None,
    counter_currency: Optional[str] = None,
    market_symbol: Optional[str] = None,
    override_dir: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates a crypto alert candidate.

    Returns:
        (is_valid, error_code, error_message)
    """
    ex = (exchange or "").lower().strip()
    sym = (symbol or "").strip()

    # 1. Non-crypto markets pass validation untouched
    if not is_crypto_exchange_candidate(ex):
        return True, None, None

    # 2. CoinEx is completely discontinued (Owner Decision E1.2)
    if ex == "coinex":
        return False, "EXCHANGE_NOT_SUPPORTED", "CoinEx has been discontinued and is not supported."

    # 3. Must be a registered, active crypto exchange
    if not is_supported_crypto_exchange(ex, allow_pending=False):
        return False, "EXCHANGE_NOT_SUPPORTED", f"Exchange '{exchange}' is not a supported crypto exchange."

    # 4. Quote currency must be USDT for spot crypto alerts (Rule R1 / Mission)
    quote = str(counter_currency or "").strip().upper()
    if quote and quote != "USDT":
        return False, "INVALID_QUOTE_CURRENCY", f"Only USDT quote currency is supported for crypto alerts, got '{counter_currency}'."

    # 5. Coin existence check in the exchange's catalog
    lookup_sym = (market_symbol or base_currency or sym).strip()
    resolve_status, pair_data = resolve_pair(
        exchange_id=ex,
        symbol_or_base=lookup_sym,
        override_dir=override_dir,
        base_currency=base_currency,
        counter_currency=counter_currency,
        market_symbol=market_symbol,
    )

    if resolve_status == "SYMBOL_NOT_LISTED":
        return False, "SYMBOL_NOT_LISTED", f"Symbol '{sym}' is not listed on {ex.upper()} spot market."

    if resolve_status == "UNKNOWN_EXCHANGE":
        return False, "EXCHANGE_NOT_SUPPORTED", f"Exchange '{exchange}' is not recognized."

    return True, None, None
