# -*- coding: utf-8 -*-
"""
AlertG — BingX Crypto Exchange Adapter (Wave 2 / Version 2).
Official BingX Spot API integration:
1. Markets: https://open-api.bingx.com/openApi/spot/v1/common/symbols
2. Bulk Tickers: https://open-api.bingx.com/openApi/spot/v1/ticker/24hr
3. Single Ticker: https://open-api.bingx.com/openApi/spot/v1/ticker/24hr?symbol={symbol}
4. Strict spot-only, USDT-only, active-only (status == 1).
"""
from typing import Dict, Any, List
from app.markets.adapters.base import (
    BaseExchangeAdapter,
    AdapterSpecification,
    SymbolInfo,
)


class BingXAdapter(BaseExchangeAdapter):
    """BingX Spot USDT Market Adapter."""

    exchange_id = "bingx"
    display_name = "BingX (bingx) Spot API"
    market_list_url = "https://open-api.bingx.com/openApi/spot/v1/common/symbols"
    batch_price_url = "https://open-api.bingx.com/openApi/spot/v1/ticker/24hr"
    single_price_url = "https://open-api.bingx.com/openApi/spot/v1/ticker/24hr?symbol={symbol}"
    provider_key = "crypto_bingx"

    specification = AdapterSpecification(
        exchange_id="bingx",
        display_name="BingX (bingx) Spot API",
        provider_key="crypto_bingx",
        market_list_url="https://open-api.bingx.com/openApi/spot/v1/common/symbols",
        batch_price_url="https://open-api.bingx.com/openApi/spot/v1/ticker/24hr",
        single_price_url="https://open-api.bingx.com/openApi/spot/v1/ticker/24hr?symbol={symbol}",
        rate_limit_rps=20.0,
        quote_currency="USDT",
        status="active",
        has_leveraged_tokens=False,
        aliases=(),
        notes="Official BingX Spot open API"
    )

    def to_native_symbol(self, base_or_symbol: str) -> str:
        """
        Formats symbol to BingX native symbol (hyphenated uppercase, e.g. BTC-USDT).
        """
        sym = (base_or_symbol or "").strip().upper()
        if not sym:
            return ""
        if "-" in sym:
            return sym
        if "_" in sym:
            return sym.replace("_", "-")
        if sym.endswith("USDT") and len(sym) > 4:
            return f"{sym[:-4]}-USDT"
        return f"{sym}-USDT"

    def to_canonical_base(self, native_symbol: str) -> str:
        sym = (native_symbol or "").strip().upper()
        if "-" in sym:
            parts = sym.split("-")
            return parts[0]
        if sym.endswith("USDT") and len(sym) > 4:
            return sym[:-4]
        return sym

    def parse_symbols_response(self, raw_data: Any) -> List[SymbolInfo]:
        results: List[SymbolInfo] = []
        if not isinstance(raw_data, dict):
            return results

        data_obj = raw_data.get("data")
        symbols_list = []
        if isinstance(data_obj, dict):
            symbols_list = data_obj.get("symbols", [])
        elif isinstance(data_obj, list):
            symbols_list = data_obj

        for s in symbols_list:
            if not isinstance(s, dict):
                continue

            market_sym = str(s.get("symbol", "")).strip().upper()
            if not market_sym or "-" not in market_sym:
                continue

            parts = market_sym.split("-")
            if len(parts) != 2:
                continue

            base, quote = parts[0], parts[1]
            if quote != "USDT":
                continue

            status = s.get("status")
            if status is not None and status != 1 and str(status).lower() not in ("1", "true", "online", "trading"):
                continue

            min_qty = None
            if s.get("minQty"):
                try:
                    min_qty = float(s["minQty"])
                except (ValueError, TypeError):
                    pass

            min_price = None
            if s.get("minNotional"):
                try:
                    min_price = float(s["minNotional"])
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
        prices: Dict[str, float] = {}
        if not isinstance(raw_data, dict):
            return prices

        ticker_list = raw_data.get("data")
        if not isinstance(ticker_list, list):
            return prices

        for item in ticker_list:
            if not isinstance(item, dict):
                continue
            sym = str(item.get("symbol", "")).strip().upper()
            if not sym or "USDT" not in sym:
                continue

            raw_p = item.get("lastPrice")
            if raw_p is None:
                continue
            try:
                p_val = float(raw_p)
                if p_val > 0:
                    prices[sym] = p_val
                    prices[sym.lower()] = p_val
                    flat = sym.replace("-", "").replace("_", "")
                    prices[flat] = p_val
                    prices[flat.lower()] = p_val
            except (ValueError, TypeError):
                continue

        return prices
