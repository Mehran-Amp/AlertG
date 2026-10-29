# -*- coding: utf-8 -*-
"""
AlertG — Bybit Crypto Exchange Adapter (Phase 2 / Wave 1).
Fully isolated adapter for Bybit Spot USDT pairs (V5 Market API):
1. Market list from https://api.bybit.com/v5/market/instruments-info?category=spot
2. Bulk prices from https://api.bybit.com/v5/market/tickers?category=spot
3. Single price from https://api.bybit.com/v5/market/tickers?category=spot&symbol={symbol}
4. Two-way symbol mapping (BTC <-> BTCUSDT, 1INCH <-> 1INCHUSDT)
5. Strict spot-only, USDT-only, active-only ('Trading') filtering.
6. Detection of leveraged/ETF tokens via is_leveraged_token.
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


class BybitAdapter(BaseExchangeAdapter):
    """Bybit Spot USDT Market Adapter (V5 API)."""

    exchange_id = "bybit"
    display_name = "Bybit (bybit) Spot API"
    market_list_url = "https://api.bybit.com/v5/market/instruments-info?category=spot"
    batch_price_url = "https://api.bybit.com/v5/market/tickers?category=spot"
    single_price_url = "https://api.bybit.com/v5/market/tickers?category=spot&symbol={symbol}"
    provider_key = "crypto_bybit"

    specification = AdapterSpecification(
        exchange_id="bybit",
        display_name="Bybit (bybit) Spot API",
        provider_key="crypto_bybit",
        market_list_url="https://api.bybit.com/v5/market/instruments-info?category=spot",
        batch_price_url="https://api.bybit.com/v5/market/tickers?category=spot",
        single_price_url="https://api.bybit.com/v5/market/tickers?category=spot&symbol={symbol}",
        rate_limit_rps=20.0,
        quote_currency="USDT",
        status="active",
        has_leveraged_tokens=False,
        aliases=(),
        notes="Tier 1 global liquidity and deep orderbooks"
    )

    def to_native_symbol(self, base_or_symbol: str) -> str:
        """
        Converts base currency or raw symbol to Bybit-native symbol.
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
        Converts Bybit-native market symbol back to canonical base currency.
        Examples:
        'BTCUSDT' -> 'BTC'
        'ETHUSDT' -> 'ETH'
        """
        sym = (native_symbol or '').strip().upper()
        if sym.endswith("USDT") and len(sym) > 4:
            return sym[:-4]
        return sym

    def parse_symbols_response(self, raw_data: Any) -> List[SymbolInfo]:
        """
        Parses Bybit /v5/market/instruments-info?category=spot response.
        Expected format:
        {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "baseCoin": "BTC",
                        "quoteCoin": "USDT",
                        "status": "Trading",
                        "priceFilter": {"minPrice": "0.01"},
                        "lotSizeFilter": {"minOrderQty": "0.00001"}
                    }, ...
                ]
            }
        }
        """
        results: List[SymbolInfo] = []
        if not isinstance(raw_data, dict):
            return results

        if raw_data.get("retCode") != 0:
            return results

        result_obj = raw_data.get("result", {})
        if not isinstance(result_obj, dict):
            return results

        symbols_list = result_obj.get("list", [])
        if not isinstance(symbols_list, list):
            return results

        for s in symbols_list:
            if not isinstance(s, dict):
                continue

            quote = (s.get("quoteCoin") or "").upper().strip()
            if quote != "USDT":
                continue

            status = s.get("status")
            if status != "Trading":
                continue

            base = (s.get("baseCoin") or "").upper().strip()
            market_sym = (s.get("symbol") or "").upper().strip()
            if not base or not market_sym:
                continue

            # Price and size limits
            min_price = None
            price_filter = s.get("priceFilter", {})
            if isinstance(price_filter, dict) and price_filter.get("minPrice"):
                try:
                    min_price = float(price_filter["minPrice"])
                except (ValueError, TypeError):
                    pass

            min_qty = None
            lot_filter = s.get("lotSizeFilter", {})
            if isinstance(lot_filter, dict) and lot_filter.get("minOrderQty"):
                try:
                    min_qty = float(lot_filter["minOrderQty"])
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
        Parses Bybit /v5/market/tickers?category=spot response.
        Expected format:
        {
            "retCode": 0,
            "result": {
                "list": [
                    {"symbol": "BTCUSDT", "lastPrice": "68520.40"},
                    ...
                ]
            }
        }
        """
        prices: Dict[str, float] = {}
        if not isinstance(raw_data, dict):
            return prices

        if raw_data.get("retCode") != 0:
            return prices

        result_obj = raw_data.get("result", {})
        if not isinstance(result_obj, dict):
            return prices

        ticker_list = result_obj.get("list", [])
        if not isinstance(ticker_list, list):
            return prices

        for item in ticker_list:
            if not isinstance(item, dict):
                continue
            sym = (item.get("symbol") or "").strip().upper()
            if not sym.endswith("USDT"):
                continue
            raw_p = item.get("lastPrice")
            try:
                p_val = float(raw_p)
                if p_val > 0:
                    prices[sym] = p_val
            except (ValueError, TypeError):
                continue

        return prices
