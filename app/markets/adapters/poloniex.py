# -*- coding: utf-8 -*-
"""
AlertG — Poloniex Crypto Exchange Adapter (Wave 2 / Version 2).
Official Poloniex Spot API integration:
1. Markets: https://api.poloniex.com/markets
2. Bulk Tickers: https://api.poloniex.com/markets/ticker24h
3. Single Ticker: https://api.poloniex.com/markets/{symbol}/ticker24h
4. Strict spot-only, USDT-only, active-only (state == 'NORMAL').
"""
from typing import Dict, Any, List
from app.markets.adapters.base import (
    BaseExchangeAdapter,
    AdapterSpecification,
    SymbolInfo,
)


class PoloniexAdapter(BaseExchangeAdapter):
    """Poloniex Spot USDT Market Adapter."""

    exchange_id = "poloniex"
    display_name = "Poloniex (poloniex) Spot API"
    market_list_url = "https://api.poloniex.com/markets"
    batch_price_url = "https://api.poloniex.com/markets/ticker24h"
    single_price_url = "https://api.poloniex.com/markets/{symbol}/ticker24h"
    provider_key = "crypto_poloniex"

    specification = AdapterSpecification(
        exchange_id="poloniex",
        display_name="Poloniex (poloniex) Spot API",
        provider_key="crypto_poloniex",
        market_list_url="https://api.poloniex.com/markets",
        batch_price_url="https://api.poloniex.com/markets/ticker24h",
        single_price_url="https://api.poloniex.com/markets/{symbol}/ticker24h",
        rate_limit_rps=20.0,
        quote_currency="USDT",
        status="active",
        has_leveraged_tokens=False,
        aliases=(),
        notes="Official Poloniex Spot public API"
    )

    def to_native_symbol(self, base_or_symbol: str) -> str:
        """
        Formats symbol to Poloniex native symbol (uppercase with underscore, e.g. BTC_USDT).
        """
        sym = (base_or_symbol or "").strip().upper()
        if not sym:
            return ""
        if "_" in sym:
            return sym
        if "-" in sym:
            return sym.replace("-", "_")
        if sym.endswith("USDT") and len(sym) > 4:
            return f"{sym[:-4]}_USDT"
        return f"{sym}_USDT"

    def to_canonical_base(self, native_symbol: str) -> str:
        sym = (native_symbol or "").strip().upper()
        if "_" in sym:
            return sym.split("_")[0]
        if sym.endswith("USDT") and len(sym) > 4:
            return sym[:-4]
        return sym

    def parse_symbols_response(self, raw_data: Any) -> List[SymbolInfo]:
        results: List[SymbolInfo] = []
        symbols_list = raw_data if isinstance(raw_data, list) else (
            raw_data.get("data") if isinstance(raw_data, dict) else []
        )
        if not isinstance(symbols_list, list):
            return results

        for s in symbols_list:
            if not isinstance(s, dict):
                continue

            base = str(s.get("baseCurrencyName") or s.get("baseCurrency", "")).strip().upper()
            quote = str(s.get("quoteCurrencyName") or s.get("quoteCurrency", "")).strip().upper()
            market_sym = str(s.get("symbol", "")).strip().upper()

            if quote != "USDT" or not base or not market_sym:
                continue

            state = str(s.get("state", "")).strip().upper()
            if state and state not in ("NORMAL", "ONLINE", "ACTIVE", "TRADING"):
                continue

            min_qty = None
            if s.get("minQuantity"):
                try:
                    min_qty = float(s["minQuantity"])
                except (ValueError, TypeError):
                    pass

            is_etf = self.is_leveraged_token(base)

            results.append(SymbolInfo(
                base=base,
                quote=quote,
                market_symbol=market_sym,
                is_active=True,
                is_etf=is_etf,
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
            sym = str(item.get("symbol", "")).strip().upper()
            if not sym or "USDT" not in sym:
                continue

            raw_p = item.get("close") or item.get("last") or item.get("price")
            if raw_p is None:
                continue
            try:
                p_val = float(raw_p)
                if p_val > 0:
                    prices[sym] = p_val
                    prices[sym.lower()] = p_val
                    flat = sym.replace("_", "").replace("-", "")
                    prices[flat] = p_val
                    prices[flat.lower()] = p_val
            except (ValueError, TypeError):
                continue

        return prices
