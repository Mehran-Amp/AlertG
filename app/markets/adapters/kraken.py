# -*- coding: utf-8 -*-
"""
AlertG — Kraken Crypto Exchange Adapter (Sub-phase 4g).
Fully isolated adapter for Kraken Spot USDT pairs:
1. Market list from https://api.kraken.com/0/public/AssetPairs
2. Bulk prices from https://api.kraken.com/0/public/Ticker
3. Single price from https://api.kraken.com/0/public/Ticker?pair={pair}
4. Two-way symbol mapping (BTC <-> XBTUSDT, ETH <-> ETHUSDT, SOL <-> SOLUSDT)
5. Strict spot-only, USDT-only, online-only filtering (quote == 'USDT', status == 'online').
6. Extraction of Kraken's 'c' (last trade closed) price array.
7. Granular error classification (429 / Too many requests, 403 / Permission denied, timeout, invalid payload).
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


class KrakenAdapter(BaseExchangeAdapter):
    """Kraken Spot USDT Market Adapter."""

    exchange_id = "kraken"
    display_name = "Kraken (kraken) Spot API"
    market_list_url = "https://api.kraken.com/0/public/AssetPairs"
    batch_price_url = "https://api.kraken.com/0/public/Ticker"
    single_price_url = "https://api.kraken.com/0/public/Ticker?pair={pair}"
    provider_key = "crypto_kraken"

    def to_native_symbol(self, base_or_symbol: str) -> str:
        """
        Converts base currency or raw symbol to Kraken-native symbol (e.g. XBTUSDT, ETHUSDT).
        Kraken uses XBT instead of BTC.
        Examples:
        'BTC' -> 'XBTUSDT'
        'btc' -> 'XBTUSDT'
        'XBT' -> 'XBTUSDT'
        'BTCUSDT' -> 'XBTUSDT'
        'BTC-USDT' -> 'XBTUSDT'
        'BTC_USDT' -> 'XBTUSDT'
        'ETH' -> 'ETHUSDT'
        'SOL' -> 'SOLUSDT'
        'ADA' -> 'ADAUSDT'
        """
        sym = (base_or_symbol or '').strip().upper()
        if not sym:
            return ""

        # Normalize delimiter-separated symbols
        if sym.endswith("-USDT"):
            base = sym[:-5]
        elif sym.endswith("_USDT"):
            base = sym[:-5]
        elif sym.endswith("/USDT"):
            base = sym[:-5]
        elif sym.endswith("USDT") and len(sym) > 4:
            base = sym[:-4]
        else:
            base = sym

        if base in ("BTC", "XBT", "XXBT"):
            return "XBTUSDT"
        if base in ("ETH", "XETH"):
            return "ETHUSDT"
        if base in ("DOGE", "XDG", "XXDG"):
            return "DOGEUSDT"

        return f"{base}USDT"

    def to_canonical_base(self, native_symbol: str) -> str:
        """
        Converts Kraken-native market symbol back to canonical uppercase base currency.
        Examples:
        'XBTUSDT' -> 'BTC'
        'XXBTZUSD' -> 'BTC'
        'XBT/USDT' -> 'BTC'
        'ETHUSDT' -> 'ETH'
        'SOLUSDT' -> 'SOL'
        'ADAUSDT' -> 'ADA'
        """
        sym = (native_symbol or '').strip().upper()
        if sym.endswith("-USDT"):
            base = sym[:-5]
        elif sym.endswith("_USDT"):
            base = sym[:-5]
        elif sym.endswith("/USDT"):
            base = sym[:-5]
        elif sym.endswith("USDT") and len(sym) > 4:
            base = sym[:-4]
        else:
            base = sym

        if base in ("XBT", "XXBT"):
            return "BTC"
        if base in ("XETH",):
            return "ETH"
        if base in ("XXDG", "XDG"):
            return "DOGE"
        if base in ("XXLM",):
            return "XLM"
        if base in ("XXRP",):
            return "XRP"
        return base

    def is_leveraged_token(self, base: str, symbol_entry: Optional[Any] = None) -> bool:
        """
        Detects leveraged tokens (matches ^[A-Z0-9]+[0-9][LS]$).
        Tokens like JUP and SYRUP are explicitly NOT leveraged.
        """
        from app.markets.adapters.base import is_leveraged_token
        return is_leveraged_token(base)

    def _classify_kraken_errors(self, error_list: List[str]) -> Tuple[str, str]:
        """
        Classifies Kraken API error strings.
        e.g. ['EGeneral:Too many requests'] -> RATE_LIMITED
        ['EGeneral:Permission denied'] -> PROVIDER_BLOCKED
        ['EQuery:Unknown asset pair'] -> SYMBOL_NOT_LISTED
        """
        err_msg = ", ".join(error_list)
        err_lower = err_msg.lower()
        if "rate limit" in err_lower or "too many requests" in err_lower:
            return "RATE_LIMITED", f"Kraken Rate Limit: {err_msg}"
        if "permission denied" in err_lower or "access denied" in err_lower or "ip" in err_lower or "cloudflare" in err_lower:
            return "PROVIDER_BLOCKED", f"Kraken Access Restriction: {err_msg}"
        if "unknown asset pair" in err_lower or "invalid symbol" in err_lower:
            return "SYMBOL_NOT_LISTED", f"Kraken Unknown Symbol: {err_msg}"
        return "PROVIDER_ERROR", f"Kraken Error: {err_msg}"

    def parse_symbols_response(self, raw_data: Any) -> List[SymbolInfo]:
        """
        Parses Kraken /0/public/AssetPairs response.
        Enforces rules:
        - status == 'online'
        - quote == 'USDT' (or wsname ends with '/USDT' or altname ends with 'USDT')
        - Identifies canonical base currency.
        """
        if not isinstance(raw_data, dict):
            return []

        errors = raw_data.get("error", [])
        if errors and len(errors) > 0:
            return []

        result_dict = raw_data.get("result", {})
        if not isinstance(result_dict, dict):
            return []

        results: List[SymbolInfo] = []
        for pair_key, s in result_dict.items():
            if not isinstance(s, dict):
                continue

            status = str(s.get("status", "")).lower()
            if status != "online":
                continue

            quote = str(s.get("quote", "")).upper()
            altname = str(s.get("altname", pair_key)).upper()
            wsname = str(s.get("wsname", "")).upper()

            # Must be USDT quoted
            is_usdt = quote == "USDT" or altname.endswith("USDT") or wsname.endswith("/USDT")
            if not is_usdt:
                continue

            market_sym = altname if altname.endswith("USDT") else pair_key
            base = self.to_canonical_base(altname)

            min_price = None
            min_qty = None
            try:
                if s.get("tick_size"):
                    min_price = float(s["tick_size"])
            except (ValueError, TypeError):
                pass

            try:
                if s.get("ordermin"):
                    min_qty = float(s["ordermin"])
            except (ValueError, TypeError):
                pass

            is_etf = self.is_leveraged_token(base, s)

            results.append(SymbolInfo(
                base=base,
                quote="USDT",
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
        Parses Kraken /0/public/Ticker response.
        Expected format: {'error': [], 'result': {'XBTUSDT': {'c': ['68450.2', '0.05']}, ...}}
        Returns dict: {'XBTUSDT': 68450.2, ...}
        """
        prices: Dict[str, float] = {}
        if not isinstance(raw_data, dict):
            return prices

        errors = raw_data.get("error", [])
        if errors and len(errors) > 0:
            return prices

        result_dict = raw_data.get("result", {})
        if not isinstance(result_dict, dict):
            return prices

        for pair_key, t in result_dict.items():
            if not isinstance(t, dict):
                continue

            sym = str(pair_key).upper()
            # Only consider USDT pairs
            if not (sym.endswith("USDT") or sym.endswith("/USDT")):
                continue

            c = t.get("c")
            if isinstance(c, list) and len(c) > 0:
                try:
                    p_val = float(c[0])
                    if p_val > 0:
                        prices[sym] = p_val
                        # Also register normalized altname if applicable
                        if sym.endswith("/USDT"):
                            norm_sym = sym.replace("/", "")
                            prices[norm_sym] = p_val
                except (ValueError, TypeError):
                    continue

        return prices

    async def fetch_symbols(
        self,
        client: httpx.AsyncClient,
        timeout: float = 12.0
    ) -> Tuple[List[SymbolInfo], Optional[str], Optional[str]]:
        """
        Fetches active USDT spot pairs from Kraken public AssetPairs API.
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
            if isinstance(data, dict):
                errs = data.get("error", [])
                if errs and len(errs) > 0:
                    err_code, err_msg = self._classify_kraken_errors(errs)
                    record_provider_metric(self.provider_key, "errors")
                    return [], err_code, err_msg

            symbols = self.parse_symbols_response(data)
            record_provider_metric(self.provider_key, "success")
            return symbols, None, None

        except _TimeoutBase as e:
            record_provider_metric(self.provider_key, "errors")
            return [], "TIMEOUT", f"Kraken symbols query timed out: {e}"
        except Exception as e:
            record_provider_metric(self.provider_key, "errors")
            return [], "INVALID_RESPONSE", f"Kraken symbols request failed: {e}"

    async def fetch_batch_prices(
        self,
        client: httpx.AsyncClient,
        timeout: float = 8.0
    ) -> BatchPriceResult:
        """
        Fetches all current ticker prices from Kraken with a SINGLE HTTP request.
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
            if isinstance(data, dict):
                errs = data.get("error", [])
                if errs and len(errs) > 0:
                    err_code, err_msg = self._classify_kraken_errors(errs)
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
        Fetches price for a single trading pair from Kraken.
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

        url = self.single_price_url.format(pair=native_sym)
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
                errs = data.get("error", [])
                if errs and len(errs) > 0:
                    err_code, _ = self._classify_kraken_errors(errs)
                    record_provider_metric(self.provider_key, "errors")
                    return SinglePriceResult(
                        price=None,
                        as_of=now_ts,
                        source=self.display_name,
                        status=err_code,
                        market_symbol=native_sym
                    )

                result_dict = data.get("result", {})
                if isinstance(result_dict, dict) and len(result_dict) > 0:
                    for _, t in result_dict.items():
                        c = t.get("c")
                        if isinstance(c, list) and len(c) > 0:
                            val = float(c[0])
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
