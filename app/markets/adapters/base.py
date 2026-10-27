# -*- coding: utf-8 -*-
"""
AlertG — Base Crypto Exchange Adapter Interface (Phase 4).
Abstract interface, standard models, and error classification for exchange adapters.
Enforces:
- Rule R1: Exchange isolation (zero fallback, single exchange target).
- Rule R7: Single batch/bulk query for multi-symbol requests.
- Strict USDT-only, spot-only filtering.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
import time


@dataclass
class SymbolInfo:
    """Standard representation of an active spot trading pair on an exchange."""
    base: str               # Canonical base currency (e.g. 'BTC', 'ETH', '1INCH')
    quote: str              # Strictly 'USDT'
    market_symbol: str      # Exchange-native symbol (e.g. 'BTCUSDT', 'BTC-USDT')
    is_active: bool = True  # True if spot trading is currently allowed
    is_etf: bool = False    # True if leveraged or ETF token (e.g. BTC3L, BTCUP)
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
    error_code: Optional[str] = None  # 'SUCCESS' | 'RATE_LIMITED' | 'GEO_BLOCKED' | 'TIMEOUT' | 'INVALID_RESPONSE'


@dataclass
class SinglePriceResult:
    """Standard result of a single-pair price query."""
    price: Optional[float] = None
    as_of: Optional[int] = None
    source: Optional[str] = None
    status: str = "NO_PRICE"  # 'SUCCESS' | 'NO_PRICE' | 'RATE_LIMITED' | 'GEO_BLOCKED' | 'TIMEOUT' | 'INVALID_RESPONSE'
    market_symbol: str = ""
    currency: str = "USDT"


def classify_http_error(status_code: Any, error_text: str = "") -> Tuple[str, str]:
    """
    Categorizes HTTP error status codes into canonical failure statuses.
    Returns (status_code_name, explanation).
    """
    try:
        sc = int(status_code)
    except (TypeError, ValueError):
        sc = 0

    if sc == 429:
        return "RATE_LIMITED", f"Provider rate limited (HTTP 429): {error_text}"
    elif sc in (403, 451):
        return "GEO_BLOCKED", f"Provider blocked or geo-restricted (HTTP {sc}): {error_text}"
    elif sc in (408, 504):
        return "TIMEOUT", f"Provider gateway/read timeout (HTTP {sc}): {error_text}"
    elif sc == 404:
        return "SYMBOL_NOT_LISTED", f"Symbol not found (HTTP 404): {error_text}"
    elif 500 <= sc < 600:
        return "PROVIDER_ERROR", f"Provider server error (HTTP {sc}): {error_text}"
    else:
        return "INVALID_RESPONSE", f"HTTP {status_code}: {error_text}"


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
        - Detect ETF/leveraged tokens.
        """
        pass

    @abstractmethod
    def parse_batch_prices_response(self, raw_data: Any) -> Dict[str, float]:
        """
        Parses exchange bulk ticker response.
        Returns mapping: market_symbol -> live price (float > 0).
        """
        pass
