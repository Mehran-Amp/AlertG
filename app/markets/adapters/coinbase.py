# -*- coding: utf-8 -*-
"""
AlertG — Coinbase Crypto Exchange Adapter (Wave 2 / Version 2).
Official Coinbase Spot API integration:
1. Markets: https://api.exchange.coinbase.com/products
2. Bulk Tickers: https://api.coinbase.com/v2/exchange-rates?currency=USDT
3. Single Ticker: https://api.exchange.coinbase.com/products/{symbol}/ticker
4. Strict spot-only, USDT pairs, active-only (status == 'online').
"""
from typing import Dict, Any, List
from app.markets.adapters.base import (
    BaseExchangeAdapter,
    AdapterSpecification,
    SymbolInfo,
)


class CoinbaseAdapter(BaseExchangeAdapter):
    """Coinbase Spot USDT Market Adapter."""

    exchange_id = "coinbase"
    display_name = "Coinbase (coinbase) Spot API"
    market_list_url = "https://api.exchange.coinbase.com/products"
    batch_price_url = "https://api.coinbase.com/v2/exchange-rates?currency=USDT"
    single_price_url = "https://api.exchange.coinbase.com/products/{symbol}/ticker"
    provider_key = "crypto_coinbase"

    specification = AdapterSpecification(
        exchange_id="coinbase",
        display_name="Coinbase (coinbase) Spot API",
        provider_key="crypto_coinbase",
        market_list_url="https://api.exchange.coinbase.com/products",
        batch_price_url="https://api.coinbase.com/v2/exchange-rates?currency=USDT",
        single_price_url="https://api.exchange.coinbase.com/products/{symbol}/ticker",
        rate_limit_rps=15.0,
        quote_currency="USDT",
        status="active",
        has_leveraged_tokens=False,
        aliases=("coinbase_pro", "coinbase_exchange"),
        notes="Official Coinbase Spot public API"
    )

    def to_native_symbol(self, base_or_symbol: str) -> str:
        """
        Formats symbol to Coinbase native product ID (hyphenated uppercase, e.g. BTC-USDT).
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
            return sym.split("-")[0]
        if sym.endswith("USDT") and len(sym) > 4:
            return sym[:-4]
        return sym

    def parse_symbols_response(self, raw_data: Any) -> List[SymbolInfo]:
        results: List[SymbolInfo] = []
        products_list = raw_data if isinstance(raw_data, list) else (
            raw_data.get("data") if isinstance(raw_data, dict) else []
        )
        if not isinstance(products_list, list):
            return results

        for p in products_list:
            if not isinstance(p, dict):
                continue

            base = str(p.get("base_currency", "")).strip().upper()
            quote = str(p.get("quote_currency", "")).strip().upper()
            market_sym = str(p.get("id", "")).strip().upper()

            if quote != "USDT" or not base or not market_sym:
                continue

            status = str(p.get("status", "")).strip().lower()
            if status and status != "online":
                continue

            min_qty = None
            if p.get("base_min_size"):
                try:
                    min_qty = float(p["base_min_size"])
                except (ValueError, TypeError):
                    pass

            min_price = None
            if p.get("min_market_funds"):
                try:
                    min_price = float(p["min_market_funds"])
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
                raw=p,
            ))

        return results

    def parse_batch_prices_response(self, raw_data: Any) -> Dict[str, float]:
        prices: Dict[str, float] = {}

        # Case 1: /v2/exchange-rates?currency=USDT response
        if isinstance(raw_data, dict) and "data" in raw_data and isinstance(raw_data["data"], dict):
            rates = raw_data["data"].get("rates", {})
            if isinstance(rates, dict):
                for base_sym, rate_str in rates.items():
                    try:
                        rate_val = float(rate_str)
                        if rate_val > 0:
                            price_in_usdt = 1.0 / rate_val
                            base_upper = base_sym.upper()
                            prices[f"{base_upper}-USDT"] = price_in_usdt
                            prices[f"{base_upper}USDT"] = price_in_usdt
                            prices[f"{base_upper.lower()}-usdt"] = price_in_usdt
                            prices[f"{base_upper.lower()}usdt"] = price_in_usdt
                    except (ValueError, TypeError, ZeroDivisionError):
                        continue
                return prices

        # Case 2: Direct /products/{symbol}/ticker response
        if isinstance(raw_data, dict) and raw_data.get("price"):
            try:
                p_val = float(raw_data["price"])
                if p_val > 0:
                    prices["single"] = p_val
            except (ValueError, TypeError):
                pass

        return prices
