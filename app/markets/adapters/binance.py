# -*- coding: utf-8 -*-
"""
AlertG — Binance Crypto Exchange Adapter (Sub-phase 4a).
Fully isolated adapter for Binance Spot USDT pairs:
1. Market list from https://api.binance.com/api/v3/exchangeInfo
2. Bulk prices from https://api.binance.com/api/v3/ticker/price
3. Two-way symbol mapping (BTC <-> BTCUSDT, 1INCH <-> 1INCHUSDT)
4. Strict spot-only, USDT-only, active-only filtering.
5. Detection of leveraged/ETF tokens (UP/DOWN tokens).
6. Granular error classification (429 rate limit, 451/403 geo-block, timeout, invalid payload).
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


class BinanceAdapter(BaseExchangeAdapter):
    """Binance Spot USDT Market Adapter."""

    exchange_id = "binance"
    display_name = "Binance"
    market_list_url = "https://api.binance.com/api/v3/exchangeInfo"
    batch_price_url = "https://api.binance.com/api/v3/ticker/price"
    single_price_url = "https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    provider_key = "crypto_binance"

    def to_native_symbol(self, base_or_symbol: str) -> str:
        """
        Converts base currency or raw symbol to Binance-native symbol.
        Examples:
        'BTC' -> 'BTCUSDT'
        'btcusdt' -> 'BTCUSDT'
        '1INCH' -> '1INCHUSDT'
        """
        sym = (base_or_symbol or '').strip().upper()
        if not sym:
            return ""
        if sym.endswith("USDT"):
            return sym
        return f"{sym}USDT"

    def to_canonical_base(self, native_symbol: str) -> str:
        """
        Converts Binance-native market symbol back to canonical base currency.
        Examples:
        'BTCUSDT' -> 'BTC'
        '1INCHUSDT' -> '1INCH'
        '1000SATSUSDT' -> '1000SATS'
        """
        sym = (native_symbol or '').strip().upper()
        if sym.endswith("USDT"):
            return sym[:-4]
        return sym

    def is_leveraged_token(self, base: str, symbol_entry: Optional[Dict[str, Any]] = None) -> bool:
        """
        Detects Binance leveraged tokens (e.g. BTCUP, BTCDOWN, ETHUP, ETHDOWN).
        """
        b = base.upper()
        if b.endswith("UP") or b.endswith("DOWN") or b.endswith("BEAR") or b.endswith("BULL"):
            return True
        if symbol_entry:
            tags = symbol_entry.get("tags", [])
            if any("etf" in str(t).lower() or "leveraged" in str(t).lower() for t in tags):
                return True
        return False

    def parse_symbols_response(self, raw_data: Any) -> List[SymbolInfo]:
        """
        Parses Binance exchangeInfo payload.
        Rules:
        - Must be status == 'TRADING'
        - Must be quoteAsset == 'USDT'
        - Must have isSpotTradingAllowed == True (or permissions contain 'SPOT')
        - Identifies leveraged tokens.
        """
        if not isinstance(raw_data, dict):
            return []

        symbols_raw = raw_data.get("symbols", [])
        if not isinstance(symbols_raw, list):
            return []

        results: List[SymbolInfo] = []
        for s in symbols_raw:
            if not isinstance(s, dict):
                continue

            quote = s.get("quoteAsset", "").upper()
            if quote != "USDT":
                continue

            status = s.get("status", "").upper()
            if status != "TRADING":
                continue

            # Check spot trading allowance
            is_spot = s.get("isSpotTradingAllowed", True)
            permissions = s.get("permissions", [])
            if permissions and "SPOT" not in [str(p).upper() for p in permissions]:
                is_spot = False

            if not is_spot:
                continue

            base = s.get("baseAsset", "").upper()
            market_sym = s.get("symbol", "").upper()

            # Parse minimum price / qty if available
            min_price = None
            min_qty = None
            for f in s.get("filters", []):
                if f.get("filterType") == "PRICE_FILTER":
                    try:
                        min_price = float(f.get("minPrice", 0))
                    except (ValueError, TypeError):
                        pass
                elif f.get("filterType") == "LOT_SIZE":
                    try:
                        min_qty = float(f.get("minQty", 0))
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
        Parses Binance /api/v3/ticker/price response.
        Expected format: list of dicts [{'symbol': 'BTCUSDT', 'price': '67200.50'}, ...]
        Returns dict: {'BTCUSDT': 67200.50, ...}
        """
        prices: Dict[str, float] = {}
        if not isinstance(raw_data, list):
            return prices

        for item in raw_data:
            if not isinstance(item, dict):
                continue
            sym = item.get("symbol", "")
            if not sym.endswith("USDT"):
                continue
            raw_p = item.get("price")
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
        Fetches active USDT spot pairs from Binance public API.
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
            return [], "TIMEOUT", f"Binance symbols query timed out: {e}"
        except Exception as e:
            record_provider_metric(self.provider_key, "errors")
            return [], "INVALID_RESPONSE", f"Binance symbols request failed: {e}"

    async def fetch_batch_prices(
        self,
        client: httpx.AsyncClient,
        timeout: float = 8.0
    ) -> BatchPriceResult:
        """
        Fetches all current ticker prices from Binance with a SINGLE HTTP request.
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
        Fetches price for a single trading pair from Binance.
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

        url = self.single_price_url.format(symbol=native_sym)
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
            if isinstance(data, dict) and data.get("price"):
                val = float(data["price"])
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
