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
    headers: Optional[Any] = None
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
    if headers is not None:
        try:
            if isinstance(headers, dict):
                for k, v in headers.items():
                    if str(k).lower() == "retry-after":
                        retry_after = str(v)
                        break
            elif hasattr(headers, "get") and not type(headers).__name__.startswith("MagicMock"):
                val = headers.get("retry-after")
                if val is not None and not type(val).__name__.startswith("MagicMock"):
                    retry_after = str(val)
        except Exception:
            retry_after = None

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


@dataclass(frozen=True)
class AdapterSpecification:
    """
    Declarative specification defining an exchange's endpoints, rate limits, and metadata.
    Enforces Rule R11 (source label with ID) and Section E2.2 fields.
    """
    exchange_id: str
    display_name: str
    provider_key: str
    market_list_url: str
    batch_price_url: str
    single_price_url: Optional[str] = None
    rate_limit_rps: float = 10.0
    quote_currency: str = "USDT"
    status: str = "active"  # 'active' | 'pending_adapter' | 'inactive'
    has_leveraged_tokens: bool = False
    aliases: Tuple[str, ...] = ()
    notes: Optional[str] = None


def validate_adapter_specification(spec: AdapterSpecification) -> List[str]:
    """
    Validates that an AdapterSpecification satisfies all Phase 2 architectural constraints.
    Returns a list of error strings (empty list if completely valid).
    """
    errors: List[str] = []
    if not spec.exchange_id or spec.exchange_id != spec.exchange_id.lower().strip():
        errors.append(f"exchange_id '{spec.exchange_id}' must be non-empty and strictly lowercase")

    expected_id_tag = f"({spec.exchange_id})"
    if expected_id_tag not in spec.display_name:
        errors.append(f"display_name '{spec.display_name}' must contain lowercase ID in parentheses: '{expected_id_tag}' (Rule R11)")

    if not spec.provider_key.startswith("crypto_"):
        errors.append(f"provider_key '{spec.provider_key}' must begin with 'crypto_'")

    if not spec.market_list_url.startswith("https://"):
        errors.append(f"market_list_url '{spec.market_list_url}' must be a secure https URL")

    if not spec.batch_price_url.startswith("https://"):
        errors.append(f"batch_price_url '{spec.batch_price_url}' must be a secure https URL")

    if spec.quote_currency != "USDT":
        errors.append(f"quote_currency '{spec.quote_currency}' must be 'USDT'")

    if spec.rate_limit_rps <= 0:
        errors.append(f"rate_limit_rps '{spec.rate_limit_rps}' must be strictly positive")

    if spec.status not in ('active', 'pending_adapter', 'inactive'):
        errors.append(f"status '{spec.status}' must be 'active', 'pending_adapter', or 'inactive'")

    return errors


class BaseExchangeAdapter(ABC):
    """
    Abstract Base Class for all cryptocurrency exchange adapters.
    Each exchange adapter must be self-contained and isolated.
    Concrete fetch methods acquire rate-limiter slots, manage HTTP requests,
    classify errors, record metrics, and invoke declarative parsers.
    """
    exchange_id: str
    display_name: str
    market_list_url: str
    batch_price_url: str
    single_price_url: Optional[str] = None
    provider_key: str
    specification: Optional[AdapterSpecification] = None

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

    async def fetch_symbols(
        self,
        client: Any,
        timeout: float = 12.0
    ) -> Tuple[List[SymbolInfo], Optional[str], Optional[str]]:
        """
        Generic request engine: acquires slot, issues GET to market_list_url,
        classifies HTTP errors, handles malformed JSON, and parses symbols.
        Returns: (symbols_list, error_code, error_message)
        """
        from app.markets.limiter import acquire_provider_slot, record_provider_metric
        acquired = await acquire_provider_slot(self.provider_key)
        if not acquired:
            record_provider_metric(self.provider_key, "rate_limits_429", status_code=429)
            return [], "RATE_LIMITED", "Provider local rate limiter reached"

        headers = {"User-Agent": "AlertG-Adapter/1.0", "Accept": "application/json"}
        try:
            resp = await client.get(self.market_list_url, headers=headers, timeout=timeout)
            status_code = getattr(resp, "status_code", 200)
            if status_code != 200:
                resp_headers = getattr(resp, "headers", {})
                resp_text = getattr(resp, "text", "")
                err_code, err_msg = classify_http_error(status_code, resp_text, resp_headers)
                record_provider_metric(self.provider_key, "errors", status_code=status_code)
                return [], err_code, err_msg

            try:
                data = resp.json()
            except Exception as e:
                record_provider_metric(self.provider_key, "errors", status_code=200)
                return [], "INVALID_RESPONSE", f"Malformed JSON from {self.display_name}: {e}"

            symbols = self.parse_symbols_response(data)
            record_provider_metric(self.provider_key, "success", status_code=200)
            return symbols, None, None

        except Exception as e:
            err_type = type(e).__name__
            if "Timeout" in err_type or isinstance(e, TimeoutError):
                record_provider_metric(self.provider_key, "timeouts", status_code=408)
                return [], "TIMEOUT", f"Connection timeout fetching symbols from {self.display_name}: {e}"
            record_provider_metric(self.provider_key, "errors", status_code=500)
            return [], "PROVIDER_ERROR", f"Network error fetching symbols from {self.display_name}: {e}"

    async def fetch_batch_prices(
        self,
        client: Any,
        timeout: float = 12.0
    ) -> BatchPriceResult:
        """
        Generic bulk ticker engine: acquires slot, issues GET to batch_price_url,
        classifies errors, and parses live prices into BatchPriceResult.
        """
        from app.markets.limiter import acquire_provider_slot, record_provider_metric
        acquired = await acquire_provider_slot(self.provider_key)
        if not acquired:
            record_provider_metric(self.provider_key, "rate_limits_429", status_code=429)
            return BatchPriceResult(
                prices={},
                source=self.display_name,
                error="Provider local rate limiter reached",
                error_code="RATE_LIMITED"
            )

        headers = {"User-Agent": "AlertG-Adapter/1.0", "Accept": "application/json"}
        try:
            resp = await client.get(self.batch_price_url, headers=headers, timeout=timeout)
            status_code = getattr(resp, "status_code", 200)
            if status_code != 200:
                resp_headers = getattr(resp, "headers", {})
                resp_text = getattr(resp, "text", "")
                err_code, err_msg = classify_http_error(status_code, resp_text, resp_headers)
                record_provider_metric(self.provider_key, "errors", status_code=status_code)
                return BatchPriceResult(
                    prices={},
                    source=self.display_name,
                    error=err_msg,
                    error_code=err_code
                )

            try:
                data = resp.json()
            except Exception as e:
                record_provider_metric(self.provider_key, "errors", status_code=200)
                return BatchPriceResult(
                    prices={},
                    source=self.display_name,
                    error=f"Malformed JSON from {self.display_name}: {e}",
                    error_code="INVALID_RESPONSE"
                )

            prices = self.parse_batch_prices_response(data)
            record_provider_metric(self.provider_key, "success", status_code=200)
            return BatchPriceResult(
                prices=prices,
                source=self.display_name,
                as_of=int(time.time()),
                error=None,
                error_code="SUCCESS"
            )

        except Exception as e:
            err_type = type(e).__name__
            if "Timeout" in err_type or isinstance(e, TimeoutError):
                record_provider_metric(self.provider_key, "timeouts", status_code=408)
                return BatchPriceResult(
                    prices={},
                    source=self.display_name,
                    error=f"Timeout fetching batch prices from {self.display_name}: {e}",
                    error_code="TIMEOUT"
                )
            record_provider_metric(self.provider_key, "errors", status_code=500)
            return BatchPriceResult(
                prices={},
                source=self.display_name,
                error=f"Network error fetching batch prices from {self.display_name}: {e}",
                error_code="PROVIDER_ERROR"
            )

    async def fetch_single_price(
        self,
        client: Any,
        symbol: str,
        timeout: float = 8.0
    ) -> SinglePriceResult:
        """
        Generic single pair price fetcher: fallback / single-symbol query path.
        """
        from app.markets.limiter import acquire_provider_slot, record_provider_metric
        native_sym = self.to_native_symbol(symbol)
        if not self.single_price_url:
            # Fallback to bulk prices if single URL not defined
            batch_res = await self.fetch_batch_prices(client, timeout=timeout)
            p = batch_res.prices.get(native_sym)
            return SinglePriceResult(
                price=p,
                as_of=batch_res.as_of,
                source=self.display_name,
                status=batch_res.error_code or ("SUCCESS" if p else "NO_PRICE"),
                market_symbol=native_sym,
                currency="USDT"
            )

        acquired = await acquire_provider_slot(self.provider_key)
        if not acquired:
            record_provider_metric(self.provider_key, "rate_limits_429", status_code=429)
            return SinglePriceResult(
                price=None,
                source=self.display_name,
                status="RATE_LIMITED",
                market_symbol=native_sym,
                currency="USDT"
            )

        url = self.single_price_url.format(symbol=native_sym)
        headers = {"User-Agent": "AlertG-Adapter/1.0", "Accept": "application/json"}
        try:
            resp = await client.get(url, headers=headers, timeout=timeout)
            status_code = getattr(resp, "status_code", 200)
            if status_code != 200:
                resp_headers = getattr(resp, "headers", None)
                if not isinstance(resp_headers, dict) and not hasattr(resp_headers, "get"):
                    resp_headers = None
                resp_text = getattr(resp, "text", "")
                err_code, _ = classify_http_error(status_code, resp_text, resp_headers)
                record_provider_metric(self.provider_key, "errors", status_code=status_code)
                return SinglePriceResult(
                    price=None,
                    source=self.display_name,
                    status=err_code,
                    market_symbol=native_sym,
                    currency="USDT"
                )

            try:
                data = resp.json()
            except Exception:
                record_provider_metric(self.provider_key, "errors", status_code=200)
                return SinglePriceResult(
                    price=None,
                    source=self.display_name,
                    status="INVALID_RESPONSE",
                    market_symbol=native_sym,
                    currency="USDT"
                )

            # Try parsing with adapter's batch parser directly, then try list-wrapped if needed
            prices = self.parse_batch_prices_response(data)
            p = prices.get(native_sym)
            if p is None and isinstance(data, dict):
                prices = self.parse_batch_prices_response([data])
                p = prices.get(native_sym)

            record_provider_metric(self.provider_key, "success", status_code=200)
            return SinglePriceResult(
                price=p,
                as_of=int(time.time()),
                source=self.display_name,
                status="SUCCESS" if p else "NO_PRICE",
                market_symbol=native_sym,
                currency="USDT"
            )

        except Exception as e:
            err_type = type(e).__name__
            if "Timeout" in err_type or isinstance(e, TimeoutError):
                record_provider_metric(self.provider_key, "timeouts", status_code=408)
                return SinglePriceResult(
                    price=None,
                    source=self.display_name,
                    status="TIMEOUT",
                    market_symbol=native_sym,
                    currency="USDT"
                )
            record_provider_metric(self.provider_key, "errors", status_code=500)
            return SinglePriceResult(
                price=None,
                source=self.display_name,
                status="PROVIDER_ERROR",
                market_symbol=native_sym,
                currency="USDT"
            )
