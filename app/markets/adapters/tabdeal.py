# -*- coding: utf-8 -*-
"""
AlertG — Tabdeal Crypto Exchange Adapter (Phase 11 / Wave 1).
Dedicated, isolated adapter for Tabdeal Spot (USDT & IRT/TMN pairs):
1. Market list from https://api1.tabdeal.org/r/api/v1/exchangeInfo
2. Bulk prices from https://api1.tabdeal.org/r/plots/market_information/
3. Individual trades from https://api1.tabdeal.org/r/api/v1/trades?symbol={symbol}
4. Conversion: Tabdeal IRT pairs are quoted in Rials on the API (e.g. 271,250 Rials);
   converted to canonical Tomans (TMN) by dividing by 10 (27,125 TMN).
   USDT pairs remain direct 1:1.
5. Strict exchange isolation (Rule R1: zero cross-exchange fallback).
"""
import time
from typing import Dict, Any, Optional, List, Tuple
import httpx

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


class TabdealAdapter(BaseExchangeAdapter):
    """Tabdeal Spot Market Adapter (Iranian Exchange Wave 1)."""

    exchange_id = "tabdeal"
    display_name = "Tabdeal (tabdeal) Spot API"
    market_list_url = "https://api1.tabdeal.org/r/api/v1/exchangeInfo"
    batch_price_url = "https://api1.tabdeal.org/r/plots/market_information/"
    single_price_url = "https://api1.tabdeal.org/r/api/v1/trades?symbol={symbol}"
    provider_key = "crypto_tabdeal"

    specification = AdapterSpecification(
        exchange_id="tabdeal",
        display_name="Tabdeal (tabdeal) Spot API",
        provider_key="crypto_tabdeal",
        market_list_url="https://api1.tabdeal.org/r/api/v1/exchangeInfo",
        batch_price_url="https://api1.tabdeal.org/r/plots/market_information/",
        single_price_url="https://api1.tabdeal.org/r/api/v1/trades?symbol={symbol}",
        rate_limit_rps=10.0,
        quote_currency="USDT",  # Supports both USDT and TMN
        status="active",
        has_leveraged_tokens=False,
        aliases=("tabdeal_spot", "tabdeal_iran"),
        notes="Approved Tier 1 Iranian exchange adapter with dual USDT & TMN quote support"
    )

    def to_native_symbol(self, base_or_symbol: str, quote: str = "USDT") -> str:
        """
        Converts base currency or raw symbol to Tabdeal-native symbol (no underscore for trade/depth API).
        Examples:
        'BTC', quote='USDT' -> 'BTCUSDT'
        'BTC', quote='TMN'  -> 'BTCIRT'
        'BTC_USDT'          -> 'BTCUSDT'
        'BTC_IRT'           -> 'BTCIRT'
        'BTCTMN'            -> 'BTCIRT'
        """
        sym = (base_or_symbol or '').strip().upper()
        if not sym:
            return ""
        sym = sym.replace("_", "").replace("-", "").replace("/", "")
        if sym.endswith("TMN"):
            sym = sym[:-3] + "IRT"
        if not sym.endswith("USDT") and not sym.endswith("IRT"):
            target_quote = "IRT" if quote.upper() in ("TMN", "IRT") else "USDT"
            sym = f"{sym}{target_quote}"
        return sym

    def to_tabdeal_plot_symbol(self, native_symbol: str) -> str:
        """
        Converts native symbol ('BTCIRT', 'BTCUSDT') to market_information symbol with underscore ('BTC_IRT', 'BTC_USDT').
        """
        sym = (native_symbol or '').strip().upper().replace("-", "").replace("/", "")
        if "_" in sym:
            return sym
        if sym.endswith("TMN"):
            sym = sym[:-3] + "IRT"
        if sym.endswith("USDT"):
            return f"{sym[:-4]}_USDT"
        if sym.endswith("IRT"):
            return f"{sym[:-3]}_IRT"
        return sym

    def to_canonical_base(self, native_symbol: str) -> str:
        """Converts native market symbol back to canonical base currency (e.g. BTCIRT -> BTC)."""
        base, _ = self.to_canonical_base_and_quote(native_symbol)
        return base

    def to_canonical_base_and_quote(self, native_symbol: str) -> Tuple[str, str]:
        """
        Extracts canonical base asset and quote currency ('USDT' or 'TMN').
        Examples:
        'BTCUSDT' -> ('BTC', 'USDT')
        'BTCIRT'  -> ('BTC', 'TMN')
        'USDTIRT' -> ('USDT', 'TMN')
        """
        sym = (native_symbol or '').strip().upper().replace("_", "").replace("-", "")
        if sym.endswith("USDT"):
            return sym[:-4], "USDT"
        if sym.endswith("IRT"):
            return sym[:-3], "TMN"
        if sym.endswith("TMN"):
            return sym[:-3], "TMN"
        return sym, "USDT"

    def parse_symbols_response(self, raw_data: Any) -> List[SymbolInfo]:
        """Implements BaseExchangeAdapter.parse_symbols_response."""
        return self.parse_market_list(raw_data)

    def parse_market_list(self, raw_data: Any) -> List[SymbolInfo]:
        """
        Parses GET /r/api/v1/exchangeInfo response.
        Filters for status == 'TRADING' and isSpotTradingAllowed == True.
        """
        if not isinstance(raw_data, list):
            return []

        results: List[SymbolInfo] = []
        for item in raw_data:
            if not isinstance(item, dict):
                continue
            status = item.get("status")
            spot_allowed = item.get("isSpotTradingAllowed", False)
            if status != "TRADING" or not spot_allowed:
                continue

            base = (item.get("baseAsset") or "").strip().upper()
            quote_raw = (item.get("quoteAsset") or "").strip().upper()
            if not base or not quote_raw:
                continue

            # Quote must be either USDT or IRT (mapped to TMN)
            quote = "TMN" if quote_raw in ("IRT", "TMN") else quote_raw
            if quote not in ("USDT", "TMN"):
                continue

            market_symbol = item.get("symbol") or f"{base}{quote_raw}"

            # Extract filter constraints
            min_price: Optional[float] = None
            min_qty: Optional[float] = None
            filters = item.get("filters", [])
            for f in filters:
                if isinstance(f, dict):
                    ftype = f.get("filterType")
                    if ftype == "PRICE_FILTER" and f.get("minPrice"):
                        try:
                            min_price = float(f["minPrice"])
                            if quote == "TMN" and min_price:
                                min_price /= 10.0
                        except (ValueError, TypeError):
                            pass
                    elif ftype == "LOT_SIZE" and f.get("minQty"):
                        try:
                            min_qty = float(f["minQty"])
                        except (ValueError, TypeError):
                            pass

            results.append(SymbolInfo(
                base=base,
                quote=quote,
                market_symbol=market_symbol,
                is_active=True,
                is_etf=False,
                min_price=min_price,
                min_qty=min_qty,
                raw=item
            ))

        return results

    def parse_batch_prices_response(self, raw_data: Any) -> Dict[str, float]:
        """Implements BaseExchangeAdapter.parse_batch_prices_response."""
        res = self.parse_batch_prices(raw_data)
        return res.prices

    def parse_batch_prices(self, raw_data: Any) -> BatchPriceResult:
        """
        Parses GET /r/plots/market_information/ response into a normalized BatchPriceResult.
        Tabdeal IRT prices are divided by 10 to yield canonical Tomans.
        """
        now = int(time.time())
        if not isinstance(raw_data, list):
            return BatchPriceResult(
                prices={}, as_of=now, source=self.display_name,
                error="Expected a list of market objects", error_code="INVALID_RESPONSE"
            )

        prices: Dict[str, float] = {}
        for item in raw_data:
            if not isinstance(item, dict):
                continue
            raw_sym = item.get("symbol")
            raw_p = item.get("price")
            if not raw_sym or raw_p is None:
                continue
            try:
                p = float(raw_p)
                if p <= 0:
                    continue
                # IRT pairs are quoted in Rials on Tabdeal -> divide by 10 for Tomans
                if raw_sym.endswith("_IRT") or raw_sym.endswith("IRT"):
                    p = p / 10.0
                native_sym = raw_sym.replace("_", "").upper()
                prices[native_sym] = p
                # Also store canonical TMN representation
                if native_sym.endswith("IRT"):
                    prices[native_sym[:-3] + "TMN"] = p
            except (ValueError, TypeError):
                continue

        return BatchPriceResult(prices=prices, as_of=now, source=self.display_name, error_code="OK")

    def parse_single_price(self, raw_data: Any, market_symbol: str) -> SinglePriceResult:
        """
        Parses GET /r/api/v1/trades?symbol={symbol} response into SinglePriceResult (Last Traded Price).
        """
        now = int(time.time())
        sym_clean = market_symbol.replace("_", "").upper()
        is_tmn = sym_clean.endswith("IRT") or sym_clean.endswith("TMN")
        currency = "TMN" if is_tmn else "USDT"

        if isinstance(raw_data, list) and len(raw_data) > 0:
            first_trade = raw_data[0]
            if isinstance(first_trade, dict) and first_trade.get("price"):
                try:
                    price = float(first_trade["price"])
                    if price > 0:
                        if is_tmn:
                            price /= 10.0
                        trade_time = first_trade.get("time")
                        as_of = int(trade_time / 1000) if trade_time else now
                        return SinglePriceResult(
                            price=price,
                            as_of=as_of,
                            source=self.display_name,
                            status="OK",
                            market_symbol=sym_clean,
                            currency=currency
                        )
                except (ValueError, TypeError):
                    pass

        return SinglePriceResult(
            price=None,
            as_of=now,
            source=self.display_name,
            status="NO_PRICE",
            market_symbol=sym_clean,
            currency=currency
        )

    async def fetch_market_list(self, client: httpx.AsyncClient) -> Tuple[List[SymbolInfo], Optional[str]]:
        """Fetches active spot symbols from Tabdeal."""
        await acquire_provider_slot(self.provider_key, wait=True)
        try:
            res = await client.get(self.market_list_url, timeout=15.0)
            if res.status_code == 200:
                record_provider_metric(self.provider_key, "success")
                symbols = self.parse_market_list(res.json())
                return symbols, None
            else:
                err_code, err_desc = classify_http_error(res.status_code, res.text, res.headers)
                record_provider_metric(self.provider_key, "errors", status_code=res.status_code)
                return [], err_code
        except _TimeoutBase:
            record_provider_metric(self.provider_key, "errors")
            return [], "TIMEOUT"
        except Exception as e:
            record_provider_metric(self.provider_key, "errors")
            return [], "PROVIDER_ERROR"

    async def fetch_batch_prices(self, client: httpx.AsyncClient) -> BatchPriceResult:
        """Fetches full market bulk prices in a single call."""
        await acquire_provider_slot(self.provider_key, wait=True)
        try:
            res = await client.get(self.batch_price_url, timeout=12.0)
            if res.status_code == 200:
                record_provider_metric(self.provider_key, "success")
                return self.parse_batch_prices(res.json())
            else:
                err_code, err_desc = classify_http_error(res.status_code, res.text, res.headers)
                record_provider_metric(self.provider_key, "errors", status_code=res.status_code)
                return BatchPriceResult(prices={}, source=self.display_name, error=err_desc, error_code=err_code)
        except _TimeoutBase:
            record_provider_metric(self.provider_key, "errors")
            return BatchPriceResult(prices={}, source=self.display_name, error="Request timed out", error_code="TIMEOUT")
        except Exception as e:
            record_provider_metric(self.provider_key, "errors")
            return BatchPriceResult(prices={}, source=self.display_name, error=str(e), error_code="PROVIDER_ERROR")

    async def fetch_single_price(self, client: httpx.AsyncClient, market_symbol: str) -> SinglePriceResult:
        """Fetches last traded price for an individual symbol."""
        native_sym = self.to_native_symbol(market_symbol)
        url = self.single_price_url.format(symbol=native_sym)
        await acquire_provider_slot(self.provider_key, wait=True)
        try:
            res = await client.get(url, timeout=10.0)
            if res.status_code == 200:
                record_provider_metric(self.provider_key, "success")
                return self.parse_single_price(res.json(), native_sym)
            else:
                err_code, _ = classify_http_error(res.status_code, res.text, res.headers)
                record_provider_metric(self.provider_key, "errors", status_code=res.status_code)
                return SinglePriceResult(price=None, source=self.display_name, status=err_code, market_symbol=native_sym)
        except _TimeoutBase:
            record_provider_metric(self.provider_key, "errors")
            return SinglePriceResult(price=None, source=self.display_name, status="TIMEOUT", market_symbol=native_sym)
        except Exception:
            record_provider_metric(self.provider_key, "errors")
            return SinglePriceResult(price=None, source=self.display_name, status="PROVIDER_ERROR", market_symbol=native_sym)
