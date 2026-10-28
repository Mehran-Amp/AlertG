# -*- coding: utf-8 -*-
"""
AlertG — Base Crypto Exchange Adapter Interface (Phase 1 Fix / Version 2).
Abstract interface, standard models, error classification, and leveraged token detection.
Enforces:
- Section E1.6: Single status vocabulary:
  'OK', 'UNKNOWN_EXCHANGE', 'EXCHANGE_NOT_ALERT_CAPABLE', 'SYMBOL_NOT_LISTED',
  'NO_PRICE', 'STALE_PRICE', 'RATE_LIMITED', 'PROVIDER_BLOCKED', 'TIMEOUT',
  'PROVIDER_ERROR', 'INVALID_RESPONSE'.
- Rule R1: Exchange isolation (zero cross-exchange fallback).
- Rule R9: Single bulk query per poll window.
- Rule R11: Source label contains exchange ID.
- Task 4: Leveraged detection: ^[A-Z0-9]+[0-9][LS]$ or exchange metadata.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
import re
import time

_LEVERAGED_RE = re.compile(r'^[A-Z0-9]+[0-9][LS]$')


def is_leveraged_token(base: str, metadata_flag: bool = False) -> bool:
    """
    Detects leveraged / inverse ETF tokens according to strict Rule Task 4:
    A base is leveraged only if it matches ^[A-Z0-9]+[0-9][LS]$ (digit followed by L or S,
    e.g. BTC3L, ETH5S, A3S) or the exchange's own metadata explicitly says so.
    Legitimate tokens like JUP, SYRUP, 1INCH are strictly NOT leveraged.
    """
    if metadata_flag:
        return True
    b = (base or "").upper().strip()
    return bool(_LEVERAGED_RE.match(b))


@dataclass
class SymbolInfo:
    """Standard representation of an active spot trading pair on an exchange."""
    base: str               # Canonical base currency (e.g. 'BTC', 'ETH', '1INCH', 'JUP')
    quote: str              # Strictly 'USDT'
    market_symbol: str      # Exchange-native symbol (e.g. 'BTCUSDT', 'BTC-USDT', 'BTC_USDT')
    is_active: bool = True  # True if spot trading is currently allowed
    is_etf: bool = False    # True if leveraged or ETF token (matches ^[A-Z0-9]+[0-9][LS]$)
    min_price: Optional[float] = None
    min_qty: Optional[float] = None
    raw: Optional[Dict[str, Any]] = None


@dataclass
class BatchPriceResult:
    """Standard result of a bulk/batch ticker query."""
    prices: Dict[str, float] = field(default_factory=dict)  # market_symbol -> live price
    as_of: int = field(default_factory=lambda: int(time.time()))
    source: str = ""
    error: Optional[str] = None
    error_code: Optional[str] = None  # 'OK' | 'RATE_LIMITED' | 'PROVIDER_BLOCKED' | 'TIMEOUT' | 'PROVIDER_ERROR' | 'INVALID_RESPONSE'


@dataclass
class SinglePriceResult:
    """Standard result of a single-pair price query."""
    price: Optional[float] = None
    as_of: Optional[int] = None
    source: Optional[str] = None
    status: str = "NO_PRICE"  # 'OK' | 'NO_PRICE' | 'RATE_LIMITED' | 'PROVIDER_BLOCKED' | 'TIMEOUT' | 'INVALID_RESPONSE'
    market_symbol: str = ""
    currency: str = "USDT"


def classify_http_error(
    status_code: Any,
    error_text: str = "",
    headers: Optional[Dict[str, str]] = None
) -> Tuple[str, str]:
    """
    Categorizes HTTP error status codes into canonical failure statuses (Section E1.6).
    Handles HTTP 418 (Binance IP ban/teapot) and captures Retry-After headers.
    Returns (status_code_name, explanation).
    """
    try:
        sc = int(status_code)
    except (TypeError, ValueError):
        sc = 0

    retry_after = None
    if headers:
        for k, v in headers.items():
            if str(k).lower() == "retry-after":
                retry_after = v
                break

    suffix = f" (Retry-After: {retry_after}s)" if retry_after else (f": {error_text}" if error_text else "")

    if sc == 429:
        return "RATE_LIMITED", f"Provider rate limited (HTTP 429){suffix}"
    elif sc in (403, 418, 451):
        return "PROVIDER_BLOCKED", f"Provider blocked / IP ban / geo-restricted (HTTP {sc}){suffix}"
    elif sc in (408, 504):
        return "TIMEOUT", f"Provider gateway/read timeout (HTTP {sc}){suffix}"
    elif sc == 404:
        return "SYMBOL_NOT_LISTED", f"Symbol not found (HTTP 404){suffix}"
    elif 500 <= sc < 600:
        return "PROVIDER_ERROR", f"Provider server error (HTTP {sc}){suffix}"
    else:
        return "INVALID_RESPONSE", f"HTTP {status_code}{suffix}"


class BaseExchangeAdapter(ABC):
    """
    Abstract Base Class for all cryptocurrency exchange adapters.
    Each exchange adapter must be self-contained and isolated.
    """
    exchange_id: str
    display_name: str
    market_list_url: str
    batch_price_url: str
    provider_key: str

    def is_leveraged_token(self, base: str, metadata_flag: bool = False) -> bool:
        """Standard leveraged token check across all adapters."""
        return is_leveraged_token(base, metadata_flag)

    @abstractmethod
    def to_native_symbol(self, base_or_symbol: str) -> str:
        """Converts base currency or symbol to exchange-native representation."""
        pass

    @abstractmethod
    def to_canonical_base(self, native_symbol: str) -> str:
        """Converts exchange-native representation back to canonical base currency."""
        pass

    @abstractmethod
    def parse_symbols_response(self, raw_data: Any) -> List[SymbolInfo]:
        """
        Parses exchange market list response.
        Must strictly:
        - Keep only spot trading pairs.
        - Keep only quote == 'USDT'.
        - Keep only active/trading pairs.
        - Detect ETF/leveraged tokens via is_leveraged_token.
        """
        pass

    @abstractmethod
    def parse_batch_prices_response(self, raw_data: Any) -> Dict[str, float]:
        """
        Parses exchange bulk ticker response.
        Returns mapping: market_symbol -> live price (float > 0).
        """
        pass
