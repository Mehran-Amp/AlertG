# -*- coding: utf-8 -*-
"""
AlertG — KuCoin Crypto Exchange Adapter (Sub-phase 4c).
Fully isolated adapter for KuCoin Spot USDT pairs:
1. Market list from https://api.kucoin.com/api/v1/symbols
2. Bulk prices from https://api.kucoin.com/api/v1/market/allTickers
3. Single price from https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={symbol}
4. Two-way symbol mapping (BTC <-> BTC-USDT, 1INCH <-> 1INCH-USDT)
5. Strict spot-only, USDT-only, active-only filtering (quoteCurrency == 'USDT', enableTrading is True).
6. Detection of leveraged/ETF tokens (e.g. 3L, 3S tokens).
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
    AdapterSpecification,
    SymbolInfo,
    BatchPriceResult,
    SinglePriceResult,
    classify_http_error,
)
from app.markets.limiter import acquire_provider_slot, record_provider_metric


class KuCoinAdapter(BaseExchangeAdapter):
    """KuCoin Spot USDT Market Adapter."""

    exchange_id = "kucoin"
    display_name = "KuCoin (kucoin) Spot API"
    market_list_url = "https://api.kucoin.com/api/v1/symbols"
    batch_price_url = "https://api.kucoin.com/api/v1/market/allTickers"
    single_price_url = "https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={symbol}"
    provider_key = "crypto_kucoin"

    specification = AdapterSpecification(
        exchange_id="kucoin",
        display_name="KuCoin (kucoin) Spot API",
        provider_key="crypto_kucoin",
        market_list_url="https://api.kucoin.com/api/v1/symbols",
        batch_price_url="https://api.kucoin.com/api/v1/market/allTickers",
        single_price_url="https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={symbol}",
        rate_limit_rps=10.0,
        quote_currency="USDT",
        status="active",
        has_leveraged_tokens=False,
        aliases=(),
        notes="Global altcoin marketplace with allTickers endpoint"
    )

    def to_native_symbol(self, base_or_symbol: str) -> str:
        """
        Converts base currency or raw symbol to KuCoin-native symbol (BASE-USDT).
        Examples:
        'BTC' -> 'BTC-USDT'
        'btcusdt' -> 'BTC-USDT'
        'BTC-USDT' -> 'BTC-USDT'
        '1INCH' -> '1INCH-USDT'
        """
        sym = (base_or_symbol or '').strip().upper()
        if not sym:
            return ""
        if sym.endswith("-USDT"):
            return sym
        if sym.endswith("USDT"):
            return f"{sym[:-4]}-USDT"
        return f"{sym}-USDT"

    def to_canonical_base(self, native_symbol: str) -> str:
        """
        Converts KuCoin-native market symbol back to canonical base currency.
        Examples:
        'BTC-USDT' -> 'BTC'
        '1INCH-USDT' -> '1INCH'
        'BTCUSDT' -> 'BTC'
        """
        sym = (native_symbol or '').strip().upper()
        if sym.endswith("-USDT"):
            return sym[:-5]
        if sym.endswith("USDT"):
            return sym[:-4]
        return sym

    def is_leveraged_token(self, base: str, symbol_entry: Optional[Dict[str, Any]] = None) -> bool:
        """
        Detects KuCoin leveraged / ETF tokens (matches ^[A-Z0-9]+[0-9][LS]$ or explicit metadata tags).
        Tokens like JUP and SYRUP are explicitly NOT leveraged.
        """
        is_meta = False
        if symbol_entry:
            cat = str(symbol_entry.get("category", "")).lower()
            market = str(symbol_entry.get("market", "")).lower()
            if "etf" in cat or "leveraged" in cat or "etf" in market:
                is_meta = True
        from app.markets.adapters.base import is_leveraged_token
        return is_leveraged_token(base, is_meta)

    def parse_symbols_response(self, raw_data: Any) -> List[SymbolInfo]:
        """
        Parses KuCoin /api/v1/symbols payload.
        Rules:
        - code must be '200000'
        - quoteCurrency == 'USDT'
        - enableTrading is True
        - Identifies leveraged ETF tokens.
        """
        if not isinstance(raw_data, dict):
            return []

        if str(raw_data.get("code")) != "200000":
            return []

        symbols_raw = raw_data.get("data", [])
        if not isinstance(symbols_raw, list):
            return []

        results: List[SymbolInfo] = []
        for s in symbols_raw:
            if not isinstance(s, dict):
                continue

            quote = s.get("quoteCurrency", "").upper()
            if quote != "USDT":
                continue

            if not s.get("enableTrading", False):
                continue

            base = s.get("baseCurrency", "").upper()
            market_sym = s.get("symbol", "").upper()

            min_price = None
            min_qty = None
            try:
                if s.get("priceIncrement"):
                    min_price = float(s["priceIncrement"])
            except (ValueError, TypeError):
                pass

            try:
                if s.get("baseMinSize"):
                    min_qty = float(s["baseMinSize"])
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
        Parses KuCoin /api/v1/market/allTickers response.
        Expected format: {'code': '200000', 'data': {'ticker': [{'symbol': 'BTC-USDT', 'last': '67400.10'}, ...]}}
        Returns dict: {'BTC-USDT': 67400.10, ...}
        """
        prices: Dict[str, float] = {}
        if not isinstance(raw_data, dict):
            return prices

        if str(raw_data.get("code")) != "200000":
            return prices

        tickers = raw_data.get("data", {}).get("ticker", [])
        if not isinstance(tickers, list):
            return prices

        for item in tickers:
            if not isinstance(item, dict):
                continue
            sym = item.get("symbol", "")
            if not sym.endswith("-USDT"):
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
        Fetches active USDT spot pairs from KuCoin public API.
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
            return [], "TIMEOUT", f"KuCoin symbols query timed out: {e}"
        except Exception as e:
            record_provider_metric(self.provider_key, "errors")
            return [], "INVALID_RESPONSE", f"KuCoin symbols request failed: {e}"

    async def fetch_batch_prices(
        self,
        client: httpx.AsyncClient,
        timeout: float = 8.0
    ) -> BatchPriceResult:
        """
        Fetches all current ticker prices from KuCoin with a SINGLE HTTP request.
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
        Fetches price for a single trading pair from KuCoin.
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
            if isinstance(data, dict) and data.get("code") == "200000" and data.get("data"):
                val = data["data"].get("price")
                if val:
                    p_val = float(val)
                    if p_val > 0:
                        record_provider_metric(self.provider_key, "success")
                        return SinglePriceResult(
                            price=p_val,
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
