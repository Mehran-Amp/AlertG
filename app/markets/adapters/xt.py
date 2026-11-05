# -*- coding: utf-8 -*-
"""
AlertG — XT.COM Crypto Exchange Adapter (Wave 2 / Version 2).
Official XT.COM Spot API v4 integration:
1. Markets: https://sapi.xt.com/v4/public/symbol
2. Bulk Tickers: https://sapi.xt.com/v4/public/ticker/price
3. Single Ticker: https://sapi.xt.com/v4/public/ticker/price?symbol={symbol}
4. Strict spot-only, USDT-only, active-only (state == 'ONLINE').
"""
from typing import Dict, Any, List
from app.markets.adapters.base import (
    BaseExchangeAdapter,
    AdapterSpecification,
    SymbolInfo,
)


class XTAdapter(BaseExchangeAdapter):
    """XT.COM Spot USDT Market Adapter."""

    exchange_id = "xt"
    display_name = "XT.COM (xt) Spot API"
    market_list_url = "https://sapi.xt.com/v4/public/symbol"
    batch_price_url = "https://sapi.xt.com/v4/public/ticker/price"
    single_price_url = "https://sapi.xt.com/v4/public/ticker/price?symbol={symbol}"
    provider_key = "crypto_xt"

    specification = AdapterSpecification(
        exchange_id="xt",
        display_name="XT.COM (xt) Spot API",
        provider_key="crypto_xt",
        market_list_url="https://sapi.xt.com/v4/public/symbol",
        batch_price_url="https://sapi.xt.com/v4/public/ticker/price",
        single_price_url="https://sapi.xt.com/v4/public/ticker/price?symbol={symbol}",
        rate_limit_rps=20.0,
        quote_currency="USDT",
        status="active",
        has_leveraged_tokens=False,
        aliases=("xt_com",),
        notes="Official XT.COM Spot v4 public API"
    )

    def to_native_symbol(self, base_or_symbol: str) -> str:
        """
        Formats symbol to XT native symbol (lowercase with underscore, e.g. btc_usdt).
        """
        sym = (base_or_symbol or "").strip().lower()
        if not sym:
            return ""
        if "_" in sym:
            return sym
        if "-" in sym:
            return sym.replace("-", "_")
        if sym.endswith("usdt") and len(sym) > 4:
            return f"{sym[:-4]}_usdt"
        return f"{sym}_usdt"

    def to_canonical_base(self, native_symbol: str) -> str:
        sym = (native_symbol or "").strip().upper()
        if "_" in sym:
            return sym.split("_")[0]
        if sym.endswith("USDT") and len(sym) > 4:
            return sym[:-4]
        return sym

    def parse_symbols_response(self, raw_data: Any) -> List[SymbolInfo]:
        results: List[SymbolInfo] = []
        if not isinstance(raw_data, dict):
            return results

        result_obj = raw_data.get("result")
        symbols_list = []
        if isinstance(result_obj, dict):
            symbols_list = result_obj.get("symbols", [])
        elif isinstance(result_obj, list):
            symbols_list = result_obj

        for s in symbols_list:
            if not isinstance(s, dict):
                continue

            base = str(s.get("baseCurrency", "")).strip().upper()
            quote = str(s.get("quoteCurrency", "")).strip().upper()
            market_sym = str(s.get("symbol", "")).strip().lower()

            if quote != "USDT" or not base or not market_sym:
                continue

            state = str(s.get("state", "")).strip().upper()
            if state and state != "ONLINE":
                continue

            # Skip derivatives/leveraged tokens if indicated
            item_type = str(s.get("type", "")).strip().lower()
            if item_type and item_type not in ("normal", "spot"):
                continue

            is_etf = self.is_leveraged_token(base)

            results.append(SymbolInfo(
                base=base,
                quote=quote,
                market_symbol=market_sym,
                is_active=True,
                is_etf=is_etf,
                raw=s,
            ))

        return results

    def parse_batch_prices_response(self, raw_data: Any) -> Dict[str, float]:
        prices: Dict[str, float] = {}
        if not isinstance(raw_data, dict):
            return prices

        ticker_list = raw_data.get("result")
        if not isinstance(ticker_list, list):
            return prices

        for item in ticker_list:
            if not isinstance(item, dict):
                continue
            sym = str(item.get("s", "")).strip().lower()
            if not sym or "usdt" not in sym:
                continue

            raw_p = item.get("p")
            if raw_p is None:
                continue
            try:
                p_val = float(raw_p)
                if p_val > 0:
                    prices[sym] = p_val
                    prices[sym.upper()] = p_val
                    flat = sym.replace("_", "").replace("-", "")
                    prices[flat] = p_val
                    prices[flat.upper()] = p_val
            except (ValueError, TypeError):
                continue

        return prices
