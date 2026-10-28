# -*- coding: utf-8 -*-
"""
AlertG — OKX Crypto Exchange Adapter (Sub-phase 4f).
Fully isolated adapter for OKX Spot USDT pairs:
1. Market list from https://www.okx.com/api/v5/public/instruments?instType=SPOT
2. Bulk prices from https://www.okx.com/api/v5/market/tickers?instType=SPOT
3. Single price from https://www.okx.com/api/v5/market/ticker?instId={instId}
4. Two-way symbol mapping (BTC <-> BTC-USDT, OKB <-> OKB-USDT, 1INCH <-> 1INCH-USDT)
5. Strict spot-only, USDT-only, live-only filtering (instType == 'SPOT', quoteCcy == 'USDT', state == 'live').
6. Detection of leveraged/ETF tokens (e.g. 3L, 3S, 2L, 2S, 4L, 4S, 5L, 5S tokens).
7. Granular error classification (429 / 50011 rate limit, 403 / 451 / 50005 geo-block, timeout, invalid payload).
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


class OKXAdapter(BaseExchangeAdapter):
    """OKX Spot USDT Market Adapter."""

    exchange_id = "okx"
    display_name = "OKX (okx) Spot API"
    market_list_url = "https://www.okx.com/api/v5/public/instruments?instType=SPOT"
    batch_price_url = "https://www.okx.com/api/v5/market/tickers?instType=SPOT"
    single_price_url = "https://www.okx.com/api/v5/market/ticker?instId={instId}"
    provider_key = "crypto_okx"

    def to_native_symbol(self, base_or_symbol: str) -> str:
        """
        Converts base currency or raw symbol to OKX-native symbol (BASE-USDT).
        Examples:
        'BTC' -> 'BTC-USDT'
        'btc' -> 'BTC-USDT'
        'BTCUSDT' -> 'BTC-USDT'
        'BTC_USDT' -> 'BTC-USDT'
        'BTC-USDT' -> 'BTC-USDT'
        'OKB' -> 'OKB-USDT'
        '1INCH' -> '1INCH-USDT'
        """
        sym = (base_or_symbol or '').strip().upper()
        if not sym:
            return ""
        if sym.endswith("-USDT"):
            return sym
        if sym.endswith("_USDT"):
            return f"{sym[:-5]}-USDT"
        if sym.endswith("USDT"):
            return f"{sym[:-4]}-USDT"
        return f"{sym}-USDT"

    def to_canonical_base(self, native_symbol: str) -> str:
        """
        Converts OKX-native market symbol back to canonical uppercase base currency.
        Examples:
        'BTC-USDT' -> 'BTC'
        'OKB-USDT' -> 'OKB'
        '1INCH-USDT' -> '1INCH'
        """
        sym = (native_symbol or '').strip().upper()
        if sym.endswith("-USDT"):
            return sym[:-5]
        if sym.endswith("_USDT"):
            return sym[:-5]
        if sym.endswith("USDT"):
            return sym[:-4]
        return sym

    def is_leveraged_token(self, base: str, symbol_entry: Optional[Any] = None) -> bool:
        """
        Detects OKX leveraged / ETF tokens (matches ^[A-Z0-9]+[0-9][LS]$).
        Tokens like JUP and SYRUP are explicitly NOT leveraged.
        """
        from app.markets.adapters.base import is_leveraged_token
        return is_leveraged_token(base)

    def _classify_okx_payload_error(self, code: str, msg: str) -> Tuple[str, str]:
        """
        Classifies OKX API v5 error payload codes.
        code == '50011' -> Rate limit exceeded
        code in ('50005', '50100', '50102') or geo restriction -> PROVIDER_BLOCKED
        code in ('51001', '51002') -> SYMBOL_NOT_LISTED
        """
        code_str = str(code).strip()
        msg_lower = (msg or "").lower()
        if code_str == "50011" or "too many requests" in msg_lower or "rate limit" in msg_lower:
            return "RATE_LIMITED", f"OKX Rate Limit ({code_str}): {msg}"
        if code_str in ("50005", "50100", "50102") or "access denied" in msg_lower or "ip" in msg_lower or "restricted" in msg_lower or "region" in msg_lower:
            return "PROVIDER_BLOCKED", f"OKX Geo/Access Restriction ({code_str}): {msg}"
        if code_str in ("51001", "51002") or "instrument id does not exist" in msg_lower:
            return "SYMBOL_NOT_LISTED", f"OKX Symbol Not Listed ({code_str}): {msg}"
        return "PROVIDER_ERROR", f"OKX API Error ({code_str}): {msg}"

    def parse_symbols_response(self, raw_data: Any) -> List[SymbolInfo]:
        """
        Parses OKX /api/v5/public/instruments response.
        Enforces rules:
        - instType == 'SPOT'
        - quoteCcy == 'USDT'
        - state == 'live'
        - Identifies leveraged ETF tokens.
        """
        items: List[Any] = []
        if isinstance(raw_data, dict):
            if raw_data.get("code") != "0":
                return []
            items = raw_data.get("data", [])
        elif isinstance(raw_data, list):
            items = raw_data
        else:
            return []

        results: List[SymbolInfo] = []
        for s in items:
            if not isinstance(s, dict):
                continue

            inst_type = str(s.get("instType", "")).upper()
            if inst_type != "SPOT":
                continue

            quote = str(s.get("quoteCcy", "")).upper()
            if quote != "USDT":
                continue

            state = str(s.get("state", "")).lower()
            if state != "live":
                continue

            base = str(s.get("baseCcy", "")).upper()
            market_sym = str(s.get("instId", f"{base}-USDT")).upper()

            min_price = None
            min_qty = None
            try:
                if s.get("tickSz"):
                    min_price = float(s["tickSz"])
            except (ValueError, TypeError):
                pass

            try:
                if s.get("minSz"):
                    min_qty = float(s["minSz"])
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
        Parses OKX /api/v5/market/tickers response.
        Expected format: {'code': '0', 'msg': '', 'data': [{'instType': 'SPOT', 'instId': 'BTC-USDT', 'last': '68520.4'}, ...]}
        Returns dict: {'BTC-USDT': 68520.4, ...}
        """
        prices: Dict[str, float] = {}
        items: List[Any] = []
        if isinstance(raw_data, dict):
            if raw_data.get("code") != "0":
                return prices
            items = raw_data.get("data", [])
        elif isinstance(raw_data, list):
            items = raw_data
        else:
            return prices

        for item in items:
            if not isinstance(item, dict):
                continue
            inst_type = str(item.get("instType", "")).upper()
            if inst_type and inst_type != "SPOT":
                continue
            sym = str(item.get("instId", "")).upper()
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
        Fetches active USDT spot pairs from OKX public instruments API.
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
            if isinstance(data, dict) and data.get("code") not in (0, "0", None):
                code = str(data.get("code"))
                msg = str(data.get("msg", ""))
                err_code, err_msg = self._classify_okx_payload_error(code, msg)
                record_provider_metric(self.provider_key, "errors")
                return [], err_code, err_msg

            symbols = self.parse_symbols_response(data)
            record_provider_metric(self.provider_key, "success")
            return symbols, None, None

        except _TimeoutBase as e:
            record_provider_metric(self.provider_key, "errors")
            return [], "TIMEOUT", f"OKX symbols query timed out: {e}"
        except Exception as e:
            record_provider_metric(self.provider_key, "errors")
            return [], "INVALID_RESPONSE", f"OKX symbols request failed: {e}"

    async def fetch_batch_prices(
        self,
        client: httpx.AsyncClient,
        timeout: float = 8.0
    ) -> BatchPriceResult:
        """
        Fetches all current ticker prices from OKX with a SINGLE HTTP request.
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
            if isinstance(data, dict) and data.get("code") not in (0, "0", None):
                code = str(data.get("code"))
                msg = str(data.get("msg", ""))
                err_code, err_msg = self._classify_okx_payload_error(code, msg)
                record_provider_metric(self.provider_key, "errors")
                return BatchPriceResult(
                    prices={},
                    as_of=now_ts,
                    source=self.display_name,
                    error=err_msg,
                    error_code=err_code
                )

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
        Fetches price for a single trading pair from OKX.
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

        url = self.single_price_url.format(instId=native_sym)
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
            if isinstance(data, dict):
                code = data.get("code")
                if code not in (0, "0", None):
                    err_code, _ = self._classify_okx_payload_error(str(code), str(data.get("msg", "")))
                    record_provider_metric(self.provider_key, "errors")
                    return SinglePriceResult(
                        price=None,
                        as_of=now_ts,
                        source=self.display_name,
                        status=err_code,
                        market_symbol=native_sym
                    )

                items = data.get("data", [])
                if isinstance(items, list) and len(items) > 0:
                    item = items[0]
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
