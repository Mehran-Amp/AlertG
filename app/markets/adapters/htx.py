# -*- coding: utf-8 -*-
"""
AlertG — HTX / Huobi Crypto Exchange Adapter (Phase 6 / Wave 2).
Fully isolated adapter for HTX Spot USDT pairs:
1. Market list from https://api.huobi.pro/v1/common/symbols
2. Bulk prices from https://api.huobi.pro/market/tickers
3. Single price from https://api.huobi.pro/market/detail/merged?symbol={symbol}
4. Two-way symbol mapping (BTC <-> btcusdt, 1INCH <-> 1inchusdt)
5. Strict spot-only, USDT-only, active-only ('online' & api-trading != 'disabled') filtering.
6. Leveraged/ETF token detection via is_leveraged_token.
7. Granular error classification (429 rate limit, 403 provider blocked, timeout, invalid payload).
"""
import time
from typing import Dict, Any, Optional, List, Tuple
import httpx

from app.markets.adapters.base import (
    BaseExchangeAdapter,
    AdapterSpecification,
    SymbolInfo,
    BatchPriceResult,
    SinglePriceResult,
    classify_http_error,
    is_leveraged_token,
)


class HTXAdapter(BaseExchangeAdapter):
    """HTX Spot USDT Market Adapter."""

    exchange_id = "htx"
    display_name = "HTX (htx) Spot API"
    market_list_url = "https://api.huobi.pro/v1/common/symbols"
    batch_price_url = "https://api.huobi.pro/market/tickers"
    single_price_url = "https://api.huobi.pro/market/detail/merged?symbol={symbol}"
    provider_key = "crypto_htx"

    specification = AdapterSpecification(
        exchange_id="htx",
        display_name="HTX (htx) Spot API",
        provider_key="crypto_htx",
        market_list_url="https://api.huobi.pro/v1/common/symbols",
        batch_price_url="https://api.huobi.pro/market/tickers",
        single_price_url="https://api.huobi.pro/market/detail/merged?symbol={symbol}",
        rate_limit_rps=20.0,
        quote_currency="USDT",
        status="active",
        has_leveraged_tokens=False,
        aliases=("huobi", "htx_global"),
        notes="High liquidity Tier 1 global spot exchange"
    )

    def to_native_symbol(self, base_or_symbol: str) -> str:
        """
        Converts base currency or raw symbol to HTX-native symbol (lowercase: btcusdt).
        Examples:
        'BTC' -> 'btcusdt'
        'BTCUSDT' -> 'btcusdt'
        'BTC-USDT' -> 'btcusdt'
        'BTC_USDT' -> 'btcusdt'
        '1INCH' -> '1inchusdt'
        """
        sym = (base_or_symbol or '').strip().lower()
        if not sym:
            return ""
        sym = sym.replace("-", "").replace("_", "")
        if sym.endswith("usdt"):
            return sym
        return f"{sym}usdt"

    def to_canonical_base(self, native_symbol: str) -> str:
        """
        Converts HTX-native market symbol back to canonical uppercase base currency.
        Examples:
        'btcusdt' -> 'BTC'
        '1inchusdt' -> '1INCH'
        """
        sym = (native_symbol or '').strip().upper()
        sym = sym.replace("-", "").replace("_", "")
        if sym.endswith("USDT") and len(sym) > 4:
            return sym[:-4]
        return sym

    def parse_symbols_response(self, raw_data: Any) -> List[SymbolInfo]:
        """
        Parses HTX /v1/common/symbols response.
        Expected format:
        {
            "status": "ok",
            "data": [
                {
                    "base-currency": "btc",
                    "quote-currency": "usdt",
                    "symbol": "btcusdt",
                    "state": "online",
                    "api-trading": "enabled",
                    "min-order-amt": 0.0001
                }, ...
            ]
        }
        """
        results: List[SymbolInfo] = []
        if not isinstance(raw_data, dict):
            return results

        if raw_data.get("status") != "ok":
            return results

        symbols_list = raw_data.get("data", [])
        if not isinstance(symbols_list, list):
            return results

        for s in symbols_list:
            if not isinstance(s, dict):
                continue

            quote = str(s.get("quote-currency", "")).strip().upper()
            if quote != "USDT":
                continue

            state = str(s.get("state", "")).strip().lower()
            if state != "online":
                continue

            api_trading = str(s.get("api-trading", "")).strip().lower()
            if api_trading == "disabled":
                continue

            base = str(s.get("base-currency", "")).strip().upper()
            market_sym = str(s.get("symbol", "")).strip().lower()
            if not base or not market_sym:
                continue

            min_qty = None
            if s.get("min-order-amt"):
                try:
                    min_qty = float(s["min-order-amt"])
                except (ValueError, TypeError):
                    pass

            min_price = None
            if s.get("min-order-value"):
                try:
                    min_price = float(s["min-order-value"])
                except (ValueError, TypeError):
                    pass

            is_etf = self.is_leveraged_token(base)

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
        Parses HTX /market/tickers response or single ticker merged detail.
        Expected format for bulk:
        {
            "status": "ok",
            "data": [
                {"symbol": "btcusdt", "close": 76910.95},
                ...
            ]
        }
        Expected format for single merged:
        {
            "status": "ok",
            "ch": "market.btcusdt.detail.merged",
            "tick": {"close": 76910.95}
        }
        """
        prices: Dict[str, float] = {}
        if not isinstance(raw_data, dict):
            return prices

        # Case 1: Bulk tickers response
        ticker_list = raw_data.get("data")
        if isinstance(ticker_list, list):
            for item in ticker_list:
                if not isinstance(item, dict):
                    continue
                sym = str(item.get("symbol", "")).strip().lower()
                if not sym.endswith("usdt"):
                    continue
                raw_p = item.get("close")
                try:
                    p_val = float(raw_p)
                    if p_val > 0:
                        prices[sym] = p_val
                        prices[sym.upper()] = p_val
                except (ValueError, TypeError):
                    continue
            return prices

        # Case 2: Single merged detail response
        tick = raw_data.get("tick")
        ch = str(raw_data.get("ch", ""))
        if isinstance(tick, dict) and "market." in ch:
            parts = ch.split(".")
            if len(parts) >= 2:
                sym = parts[1].strip().lower()
                raw_p = tick.get("close")
                try:
                    p_val = float(raw_p)
                    if p_val > 0:
                        prices[sym] = p_val
                        prices[sym.upper()] = p_val
                except (ValueError, TypeError):
                    pass

        return prices
