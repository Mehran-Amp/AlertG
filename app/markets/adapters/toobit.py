# -*- coding: utf-8 -*-
"""
AlertG — Toobit Crypto Exchange Adapter (Wave 2 / Version 2).
Official Toobit Spot API integration:
1. Markets: https://api.toobit.com/api/v1/exchangeInfo
2. Bulk Tickers: https://api.toobit.com/quote/v1/ticker/price
3. Single Ticker: https://api.toobit.com/quote/v1/ticker/price?symbol={symbol}
4. Strict spot-only, USDT-only, active-only (status == 'TRADING').
"""
from typing import Dict, Any, List
from app.markets.adapters.base import (
    BaseExchangeAdapter,
    AdapterSpecification,
    SymbolInfo,
)


class ToobitAdapter(BaseExchangeAdapter):
    """Toobit Spot USDT Market Adapter."""

    exchange_id = "toobit"
    display_name = "Toobit (toobit) Spot API"
    market_list_url = "https://api.toobit.com/api/v1/exchangeInfo"
    batch_price_url = "https://api.toobit.com/quote/v1/ticker/price"
    single_price_url = "https://api.toobit.com/quote/v1/ticker/price?symbol={symbol}"
    provider_key = "crypto_toobit"

    specification = AdapterSpecification(
        exchange_id="toobit",
        display_name="Toobit (toobit) Spot API",
        provider_key="crypto_toobit",
        market_list_url="https://api.toobit.com/api/v1/exchangeInfo",
        batch_price_url="https://api.toobit.com/quote/v1/ticker/price",
        single_price_url="https://api.toobit.com/quote/v1/ticker/price?symbol={symbol}",
        rate_limit_rps=20.0,
        quote_currency="USDT",
        status="active",
        has_leveraged_tokens=False,
        aliases=(),
        notes="Official Toobit Spot public API"
    )

    def to_native_symbol(self, base_or_symbol: str) -> str:
        """
        Formats symbol to Toobit native symbol (uppercase contiguous, e.g. BTCUSDT).
        """
        sym = (base_or_symbol or "").strip().upper()
        if not sym:
            return ""
        sym = sym.replace("-", "").replace("_", "")
        if sym.endswith("USDT"):
            return sym
        return f"{sym}USDT"

    def to_canonical_base(self, native_symbol: str) -> str:
        sym = (native_symbol or "").strip().upper()
        sym = sym.replace("-", "").replace("_", "")
        if sym.endswith("USDT") and len(sym) > 4:
            return sym[:-4]
        return sym

    def parse_symbols_response(self, raw_data: Any) -> List[SymbolInfo]:
        results: List[SymbolInfo] = []
        if not isinstance(raw_data, dict):
            return results

        symbols_list = raw_data.get("symbols", [])
        if not isinstance(symbols_list, list):
            return results

        for s in symbols_list:
            if not isinstance(s, dict):
                continue

            base = str(s.get("baseAsset", "")).strip().upper()
            quote = str(s.get("quoteAsset", "")).strip().upper()
            market_sym = str(s.get("symbol", "")).strip().upper()

            if quote != "USDT" or not base or not market_sym:
                continue

            status = str(s.get("status", "")).strip().upper()
            if status and status != "TRADING":
                continue

            min_qty = None
            min_price = None
            filters = s.get("filters", [])
            if isinstance(filters, list):
                for f in filters:
                    if not isinstance(f, dict):
                        continue
                    ftype = f.get("filterType")
                    if ftype == "LOT_SIZE" and f.get("minQty"):
                        try:
                            min_qty = float(f["minQty"])
                        except (ValueError, TypeError):
                            pass
                    elif ftype == "PRICE_FILTER" and f.get("minPrice"):
                        try:
                            min_price = float(f["minPrice"])
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
        ticker_list = raw_data if isinstance(raw_data, list) else (
            raw_data.get("data") if isinstance(raw_data, dict) else []
        )
        if not isinstance(ticker_list, list):
            return prices

        for item in ticker_list:
            if not isinstance(item, dict):
                continue
            sym = str(item.get("s") or item.get("symbol", "")).strip().upper()
            if not sym or not sym.endswith("USDT"):
                continue

            raw_p = item.get("p") or item.get("price")
            if raw_p is None:
                continue
            try:
                p_val = float(raw_p)
                if p_val > 0:
                    prices[sym] = p_val
                    prices[sym.lower()] = p_val
            except (ValueError, TypeError):
                continue

        return prices
