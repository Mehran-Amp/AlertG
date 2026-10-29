# -*- coding: utf-8 -*-
"""
AlertG — LBank Crypto Exchange Adapter (Sub-phase 4e).
Complete, production-grade replacement for deprecated CoinEx:
1. Market list from https://api.lbank.info/v2/currencyPairs.do (fallback: api.lbkex.com)
2. Bulk prices from https://api.lbank.info/v2/ticker/24hr.do?symbol=all
3. Single price from https://api.lbank.info/v2/ticker/24hr.do?symbol={symbol}
4. Two-way symbol mapping (BTC <-> btc_usdt, 1INCH <-> 1inch_usdt)
5. Strict spot-only, USDT-only, active-only filtering.
6. Crucial Rule: Eliminates unpriced pairs (e.g. leveraged ETF pairs without ticker data).
7. Leveraged/ETF token detection (3L, 3S, 5L, 5S).
8. Granular error classification (429, 403/451, timeout, invalid payload).
"""
import time
from typing import Dict, Any, Optional, List, Tuple, Set
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


class LBankAdapter(BaseExchangeAdapter):
    """LBank Spot USDT Market Adapter (CoinEx Replacement)."""

    exchange_id = "lbank"
    display_name = "LBank (lbank) Spot API"
    market_list_url = "https://api.lbank.info/v2/currencyPairs.do"
    batch_price_url = "https://api.lbank.info/v2/ticker/24hr.do?symbol=all"
    single_price_url = "https://api.lbank.info/v2/ticker/24hr.do?symbol={symbol}"
    fallback_market_list_url = "https://api.lbkex.com/v2/currencyPairs.do"
    fallback_batch_price_url = "https://api.lbkex.com/v2/ticker/24hr.do?symbol=all"
    provider_key = "crypto_lbank"

    specification = AdapterSpecification(
        exchange_id="lbank",
        display_name="LBank (lbank) Spot API",
        provider_key="crypto_lbank",
        market_list_url="https://api.lbank.info/v2/currencyPairs.do",
        batch_price_url="https://api.lbank.info/v2/ticker/24hr.do?symbol=all",
        single_price_url="https://api.lbank.info/v2/ticker/24hr.do?symbol={symbol}",
        rate_limit_rps=20.0,
        quote_currency="USDT",
        status="active",
        has_leveraged_tokens=False,
        aliases=("lbank_info", "lbkex"),
        notes="Official CoinEx replacement for Asia category"
    )

    def to_native_symbol(self, base_or_symbol: str) -> str:
        """
        Converts base currency or raw symbol to LBank-native symbol (base_usdt in lowercase).
        Examples:
        'BTC' -> 'btc_usdt'
        'btc' -> 'btc_usdt'
        'BTCUSDT' -> 'btc_usdt'
        'BTC-USDT' -> 'btc_usdt'
        'BTC_USDT' -> 'btc_usdt'
        '1INCH' -> '1inch_usdt'
        'LBK' -> 'lbk_usdt'
        """
        sym = (base_or_symbol or '').strip().lower()
        if not sym:
            return ""
        if sym.endswith("_usdt"):
            return sym
        if sym.endswith("-usdt"):
            return f"{sym[:-5]}_usdt"
        if sym.endswith("usdt"):
            return f"{sym[:-4]}_usdt"
        return f"{sym}_usdt"

    def to_canonical_base(self, native_symbol: str) -> str:
        """
        Converts LBank-native market symbol back to canonical uppercase base currency.
        Examples:
        'btc_usdt' -> 'BTC'
        '1inch_usdt' -> '1INCH'
        'lbk_usdt' -> 'LBK'
        """
        sym = (native_symbol or '').strip().lower()
        if sym.endswith("_usdt"):
            return sym[:-5].upper()
        if sym.endswith("-usdt"):
            return sym[:-5].upper()
        if sym.endswith("usdt"):
            return sym[:-4].upper()
        return sym.upper()

    def is_leveraged_token(self, base: str, symbol_entry: Optional[Any] = None) -> bool:
        """
        Detects LBank leveraged / ETF tokens (matches ^[A-Z0-9]+[0-9][LS]$).
        Tokens like JUP and SYRUP are explicitly NOT leveraged.
        """
        from app.markets.adapters.base import is_leveraged_token
        return is_leveraged_token(base)

    def parse_symbols_response(
        self,
        raw_data: Any,
        priced_symbols: Optional[Set[str]] = None
    ) -> List[SymbolInfo]:
        """
        Parses LBank currencyPairs payload.
        LBank response: {'result': 'true', 'data': ['btc_usdt', 'eth_usdt', ...]}
        Rules:
        - Keeps only strings ending in '_usdt'.
        - If priced_symbols is provided, strictly removes pairs without live price (Rule 1 of Phase 4).
        - Identifies leveraged ETF tokens.
        """
        if not isinstance(raw_data, dict):
            return []

        pairs_raw = raw_data.get("data", [])
        if not isinstance(pairs_raw, list):
            return []

        results: List[SymbolInfo] = []
        for item in pairs_raw:
            pair_str = ""
            if isinstance(item, str):
                pair_str = item.strip().lower()
            elif isinstance(item, dict) and item.get("symbol"):
                pair_str = str(item.get("symbol")).strip().lower()

            if not pair_str or not pair_str.endswith("_usdt"):
                continue

            # Crucial LBank Filter: if priced_symbols set is supplied, eliminate unpriced pairs
            if priced_symbols is not None and pair_str not in priced_symbols:
                continue

            base = pair_str[:-5].upper()
            quote = "USDT"
            is_etf = self.is_leveraged_token(base)

            results.append(SymbolInfo(
                base=base,
                quote=quote,
                market_symbol=pair_str,
                is_active=True,
                is_etf=is_etf,
                raw=item if isinstance(item, dict) else {"symbol": pair_str}
            ))

        return results

    def parse_batch_prices_response(self, raw_data: Any) -> Dict[str, float]:
        """
        Parses LBank /v2/ticker/24hr.do?symbol=all payload.
        Format: {'result': 'true', 'data': [{'symbol': 'btc_usdt', 'ticker': {'latest': '67415.5'}}, ...]}
        Returns dict: {'btc_usdt': 67415.5, ...}
        """
        prices: Dict[str, float] = {}
        if not isinstance(raw_data, dict):
            return prices

        items = raw_data.get("data", [])
        if not isinstance(items, list):
            return prices

        for item in items:
            if not isinstance(item, dict):
                continue
            sym = str(item.get("symbol", "")).strip().lower()
            if not sym.endswith("_usdt"):
                continue

            ticker = item.get("ticker", {})
            if not isinstance(ticker, dict):
                continue

            raw_p = ticker.get("latest")
            try:
                p_val = float(raw_p)
                if p_val > 0:
                    prices[sym] = p_val
            except (ValueError, TypeError):
                continue

        return prices

    async def fetch_batch_prices(
        self,
        client: httpx.AsyncClient,
        timeout: float = 8.0
    ) -> BatchPriceResult:
        """
        Fetches all current ticker prices from LBank with a SINGLE HTTP request.
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
        urls = [self.batch_price_url, self.fallback_batch_price_url]
        last_err = ""
        last_code = "INVALID_RESPONSE"

        for url in urls:
            try:
                resp = await client.get(url, headers=headers, timeout=timeout)
                status_code = resp.status_code
                if status_code != 200:
                    if status_code == 429:
                        record_provider_metric(self.provider_key, "rate_limits_429", status_code=429)
                    else:
                        record_provider_metric(self.provider_key, "errors", status_code=status_code)
                    last_code, last_err = classify_http_error(status_code, resp.text[:200])
                    continue

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
                last_code = "TIMEOUT"
                last_err = f"Timeout: {e}"
            except Exception as e:
                record_provider_metric(self.provider_key, "errors")
                last_code = "INVALID_RESPONSE"
                last_err = f"Request error: {e}"

        return BatchPriceResult(
            prices={},
            as_of=now_ts,
            source=self.display_name,
            error=last_err,
            error_code=last_code
        )

    async def fetch_symbols(
        self,
        client: httpx.AsyncClient,
        filter_unpriced: bool = True,
        timeout: float = 12.0
    ) -> Tuple[List[SymbolInfo], Optional[str], Optional[str]]:
        """
        Fetches active USDT spot pairs from LBank public API.
        When filter_unpriced is True, cross-verifies with live ticker to filter out unpriced pairs.
        Returns: (symbols_list, error_code, error_message)
        """
        acquired = await acquire_provider_slot(self.provider_key)
        if not acquired:
            record_provider_metric(self.provider_key, "rate_limits_429", status_code=429)
            return [], "RATE_LIMITED", "Provider local rate limiter reached"

        headers = {"User-Agent": "AlertG-Adapter/1.0", "Accept": "application/json"}
        urls = [self.market_list_url, self.fallback_market_list_url]
        data = None
        err_code = "INVALID_RESPONSE"
        err_msg = ""

        for url in urls:
            try:
                resp = await client.get(url, headers=headers, timeout=timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    break
                else:
                    if resp.status_code == 429:
                        record_provider_metric(self.provider_key, "rate_limits_429", status_code=429)
                    else:
                        record_provider_metric(self.provider_key, "errors", status_code=resp.status_code)
                    err_code, err_msg = classify_http_error(resp.status_code, resp.text[:200])
            except _TimeoutBase as e:
                record_provider_metric(self.provider_key, "errors")
                err_code = "TIMEOUT"
                err_msg = str(e)
            except Exception as e:
                record_provider_metric(self.provider_key, "errors")
                err_code = "INVALID_RESPONSE"
                err_msg = str(e)

        if not data:
            return [], err_code, err_msg

        priced_set = None
        if filter_unpriced:
            # Fetch bulk prices to eliminate unpriced / ETF pairs without live quotes
            bulk = await self.fetch_batch_prices(client, timeout=timeout)
            if not bulk.prices:
                return [], bulk.error_code or "NO_PRICE", f"LBank price verification failed: {bulk.error or 'No prices returned'}"
            priced_set = set(bulk.prices.keys())

        symbols = self.parse_symbols_response(data, priced_symbols=priced_set)
        record_provider_metric(self.provider_key, "success")
        return symbols, None, None

    async def fetch_single_price(
        self,
        client: httpx.AsyncClient,
        symbol: str,
        timeout: float = 6.0
    ) -> SinglePriceResult:
        """
        Fetches price for a single trading pair from LBank.
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
            if isinstance(data, dict) and data.get("result") == "true" and data.get("data"):
                items = data.get("data", [])
                if items and isinstance(items, list):
                    val = items[0].get("ticker", {}).get("latest")
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
