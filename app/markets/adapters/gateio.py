# -*- coding: utf-8 -*-
"""
AlertG — Gate.io Crypto Exchange Adapter (Sub-phase 4d).
Fully isolated adapter for Gate.io Spot USDT pairs:
1. Market list from https://api.gateio.ws/api/v4/spot/currency_pairs
2. Bulk prices from https://api.gateio.ws/api/v4/spot/tickers
3. Single price from https://api.gateio.ws/api/v4/spot/tickers?currency_pair={currency_pair}
4. Two-way symbol mapping (BTC <-> BTC_USDT, 1INCH <-> 1INCH_USDT)
5. Strict spot-only, USDT-only, active-only filtering (quote == 'USDT', trade_status == 'tradable').
6. Detection of leveraged/ETF tokens (e.g. 3L, 3S, 5L, 5S tokens).
7. Granular error classification (429 rate limit, 451/403 geo-block, timeout, invalid payload).
"""
import time
from typing import Dict, Any, Optional, List, Tuple
import httpx

# Resolve TimeoutException class safely across real and mocked environments
_TimeoutBase = getattr(httpx, 'TimeoutException', TimeoutError)
if not isinstance(_TimeoutBase, type) or not issubclass(_TimeoutBase, BaseException):
    _TimeoutBase = TimeoutError

from app.markets.adapters.base import (
    BaseExchangeAdapter,
    SymbolInfo,
    BatchPriceResult,
    SinglePriceResult,
    classify_http_error,
)
from app.markets.limiter import acquire_provider_slot, record_provider_metric


class GateioAdapter(BaseExchangeAdapter):
    """Gate.io Spot USDT Market Adapter."""

    exchange_id = "gateio"
    display_name = "Gate.io"
    market_list_url = "https://api.gateio.ws/api/v4/spot/currency_pairs"
    batch_price_url = "https://api.gateio.ws/api/v4/spot/tickers"
    single_price_url = "https://api.gateio.ws/api/v4/spot/tickers?currency_pair={currency_pair}"
    provider_key = "crypto_gateio"

    def to_native_symbol(self, base_or_symbol: str) -> str:
        """
        Converts base currency or raw symbol to Gate.io-native symbol (BASE_USDT).
        Examples:
        'BTC' -> 'BTC_USDT'
        'btcusdt' -> 'BTC_USDT'
        'BTC-USDT' -> 'BTC_USDT'
        'BTC_USDT' -> 'BTC_USDT'
        '1INCH' -> '1INCH_USDT'
        """
        sym = (base_or_symbol or '').strip().upper()
        if not sym:
            return ""
        if sym.endswith("_USDT"):
            return sym
        if sym.endswith("-USDT"):
            return f"{sym[:-5]}_USDT"
        if sym.endswith("USDT"):
            return f"{sym[:-4]}_USDT"
        return f"{sym}_USDT"

    def to_canonical_base(self, native_symbol: str) -> str:
        """
        Converts Gate.io-native market symbol back to canonical base currency.
        Examples:
        'BTC_USDT' -> 'BTC'
        '1INCH_USDT' -> '1INCH'
        'BTC-USDT' -> 'BTC'
        'BTCUSDT' -> 'BTC'
        """
        sym = (native_symbol or '').strip().upper()
        if sym.endswith("_USDT"):
            return sym[:-5]
        if sym.endswith("-USDT"):
            return sym[:-5]
        if sym.endswith("USDT"):
            return sym[:-4]
        return sym

    def is_leveraged_token(self, base: str, symbol_entry: Optional[Dict[str, Any]] = None) -> bool:
        """
        Detects Gate.io leveraged / ETF tokens (e.g. BTC3L, BTC3S, ETH5L, ETH5S).
        """
        b = base.upper()
        leveraged_suffixes = ("3L", "3S", "4L", "4S", "5L", "5S", "UP", "DOWN", "BULL", "BEAR")
        if any(b.endswith(suf) for suf in leveraged_suffixes):
            return True
        if symbol_entry:
            # Check leveraged token tags or margin disabled flags
            tags = symbol_entry.get("tags", [])
            if any("etf" in str(t).lower() or "leveraged" in str(t).lower() for t in tags):
                return True
        return False

    def parse_symbols_response(self, raw_data: Any) -> List[SymbolInfo]:
        """
        Parses Gate.io /api/v4/spot/currency_pairs payload.
        Expected format: list of dicts.
        Rules:
        - quote == 'USDT'
        - trade_status == 'tradable'
        - Identifies leveraged ETF tokens.
        """
        if not isinstance(raw_data, list):
            return []

        results: List[SymbolInfo] = []
        for s in raw_data:
            if not isinstance(s, dict):
                continue

            quote = str(s.get("quote", "")).upper()
            if quote != "USDT":
                continue

            status = str(s.get("trade_status", "")).lower()
            if status != "tradable":
                continue

            base = str(s.get("base", "")).upper()
            market_sym = str(s.get("id", f"{base}_USDT")).upper()

            min_price = None
            min_qty = None
            try:
                if s.get("min_quote_amount"):
                    min_price = float(s["min_quote_amount"])
            except (ValueError, TypeError):
                pass

            try:
                if s.get("min_base_amount"):
                    min_qty = float(s["min_base_amount"])
            except (ValueError, TypeError):
                pass

            is_etf = self.is_leveraged_token(base, s)

            results.append(SymbolInfo(
                base=base,
                quote=quote,
                market_symbol=market_sym,
                is_active=True,
                is_etf=is_etf,
                min_price=min_price,
                min_qty=min_qty,
                raw=s,
            ))

        return results

    def parse_batch_prices_response(self, raw_data: Any) -> Dict[str, float]:
        """
        Parses Gate.io /api/v4/spot/tickers response.
        Expected format: list of dicts [{'currency_pair': 'BTC_USDT', 'last': '67425.5'}, ...]
        Returns dict: {'BTC_USDT': 67425.5, ...}
        """
        prices: Dict[str, float] = {}
        if not isinstance(raw_data, list):
            return prices

        for item in raw_data:
            if not isinstance(item, dict):
                continue
            sym = str(item.get("currency_pair", "")).upper()
            if not sym.endswith("_USDT"):
                continue
            raw_p = item.get("last")
            try:
                p_val = float(raw_p)
                if p_val > 0:
                    prices[sym] = p_val
            except (ValueError, TypeError):
                continue

        return prices

    async def fetch_symbols(
        self,
        client: httpx.AsyncClient,
        timeout: float = 12.0
    ) -> Tuple[List[SymbolInfo], Optional[str], Optional[str]]:
        """
        Fetches active USDT spot pairs from Gate.io public API.
        Returns: (symbols_list, error_code, error_message)
        """
        acquired = await acquire_provider_slot(self.provider_key)
        if not acquired:
            record_provider_metric(self.provider_key, "rate_limits_429", status_code=429)
            return [], "RATE_LIMITED", "Provider local rate limiter reached"

        headers = {"User-Agent": "AlertG-Adapter/1.0", "Accept": "application/json"}
        try:
            resp = await client.get(self.market_list_url, headers=headers, timeout=timeout)
            status_code = resp.status_code
            if status_code != 200:
                if status_code == 429:
                    record_provider_metric(self.provider_key, "rate_limits_429", status_code=429)
                else:
                    record_provider_metric(self.provider_key, "errors", status_code=status_code)
                err_code, err_msg = classify_http_error(status_code, resp.text[:200])
                return [], err_code, err_msg

            data = resp.json()
            symbols = self.parse_symbols_response(data)
            record_provider_metric(self.provider_key, "success")
            return symbols, None, None

        except _TimeoutBase as e:
            record_provider_metric(self.provider_key, "errors")
            return [], "TIMEOUT", f"Gate.io symbols query timed out: {e}"
        except Exception as e:
            record_provider_metric(self.provider_key, "errors")
            return [], "INVALID_RESPONSE", f"Gate.io symbols request failed: {e}"

    async def fetch_batch_prices(
        self,
        client: httpx.AsyncClient,
        timeout: float = 8.0
    ) -> BatchPriceResult:
        """
        Fetches all current ticker prices from Gate.io with a SINGLE HTTP request.
        """
        acquired = await acquire_provider_slot(self.provider_key)
        now_ts = int(time.time())
        if not acquired:
            record_provider_metric(self.provider_key, "rate_limits_429", status_code=429)
            return BatchPriceResult(
                prices={},
                as_of=now_ts,
                source=self.display_name,
                error="Local rate limit reached",
                error_code="RATE_LIMITED"
            )

        headers = {"User-Agent": "AlertG-Adapter/1.0", "Accept": "application/json"}
        try:
            resp = await client.get(self.batch_price_url, headers=headers, timeout=timeout)
            status_code = resp.status_code
            if status_code != 200:
                if status_code == 429:
                    record_provider_metric(self.provider_key, "rate_limits_429", status_code=429)
                else:
                    record_provider_metric(self.provider_key, "errors", status_code=status_code)
                err_code, err_msg = classify_http_error(status_code, resp.text[:200])
                return BatchPriceResult(
                    prices={},
                    as_of=now_ts,
                    source=self.display_name,
                    error=err_msg,
                    error_code=err_code
                )

            data = resp.json()
            prices = self.parse_batch_prices_response(data)
            record_provider_metric(self.provider_key, "success")
            return BatchPriceResult(
                prices=prices,
                as_of=now_ts,
                source=self.display_name,
                error=None,
                error_code="SUCCESS"
            )

        except _TimeoutBase as e:
            record_provider_metric(self.provider_key, "errors")
            return BatchPriceResult(
                prices={},
                as_of=now_ts,
                source=self.display_name,
                error=f"Timeout: {e}",
                error_code="TIMEOUT"
            )
        except Exception as e:
            record_provider_metric(self.provider_key, "errors")
            return BatchPriceResult(
                prices={},
                as_of=now_ts,
                source=self.display_name,
                error=f"Request error: {e}",
                error_code="INVALID_RESPONSE"
            )

    async def fetch_single_price(
        self,
        client: httpx.AsyncClient,
        symbol: str,
        timeout: float = 6.0
    ) -> SinglePriceResult:
        """
        Fetches price for a single trading pair from Gate.io.
        """
        native_sym = self.to_native_symbol(symbol)
        now_ts = int(time.time())
        acquired = await acquire_provider_slot(self.provider_key)
        if not acquired:
            record_provider_metric(self.provider_key, "rate_limits_429", status_code=429)
            return SinglePriceResult(
                price=None,
                as_of=now_ts,
                source=self.display_name,
                status="RATE_LIMITED",
                market_symbol=native_sym
            )

        url = self.single_price_url.format(currency_pair=native_sym)
        headers = {"User-Agent": "AlertG-Adapter/1.0", "Accept": "application/json"}
        try:
            resp = await client.get(url, headers=headers, timeout=timeout)
            status_code = resp.status_code
            if status_code != 200:
                if status_code == 429:
                    record_provider_metric(self.provider_key, "rate_limits_429", status_code=429)
                else:
                    record_provider_metric(self.provider_key, "errors", status_code=status_code)
                err_code, _ = classify_http_error(status_code, resp.text[:200])
                return SinglePriceResult(
                    price=None,
                    as_of=now_ts,
                    source=self.display_name,
                    status=err_code,
                    market_symbol=native_sym
                )

            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                item = data[0]
                if isinstance(item, dict) and item.get("last"):
                    val = float(item["last"])
                    if val > 0:
                        record_provider_metric(self.provider_key, "success")
                        return SinglePriceResult(
                            price=val,
                            as_of=now_ts,
                            source=self.display_name,
                            status="SUCCESS",
                            market_symbol=native_sym
                        )

            record_provider_metric(self.provider_key, "errors")
            return SinglePriceResult(
                price=None,
                as_of=now_ts,
                source=self.display_name,
                status="NO_PRICE",
                market_symbol=native_sym
            )

        except _TimeoutBase:
            record_provider_metric(self.provider_key, "errors")
            return SinglePriceResult(
                price=None,
                as_of=now_ts,
                source=self.display_name,
                status="TIMEOUT",
                market_symbol=native_sym
            )
        except Exception:
            record_provider_metric(self.provider_key, "errors")
            return SinglePriceResult(
                price=None,
                as_of=now_ts,
                source=self.display_name,
                status="INVALID_RESPONSE",
                market_symbol=native_sym
            )
