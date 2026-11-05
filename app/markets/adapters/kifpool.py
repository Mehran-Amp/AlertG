# -*- coding: utf-8 -*-
"""
AlertG — Kifpool.me Crypto Exchange Adapter (Phase 10 / Iranian Crypto).
Dedicated, isolated adapter for Kifpool (kifpool.me / api.kifpool.app):
1. Official Public REST endpoint: https://api.kifpool.app/api/spot/price
2. Over 1,200 spot pairs with dual-quote architecture:
   - USDT quote: item['price'] (direct USD/USDT price)
   - TMN quote: (item['priceBuyIRT'] + item['priceSellIRT']) / 2.0 / 10.0 (converted from IRT Rials to Tomans)
3. Strict exchange isolation (Rule R1: zero cross-exchange fallback).
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


class KifpoolAdapter(BaseExchangeAdapter):
    """Kifpool Spot Market Adapter (Approved Iranian Crypto Exchange)."""

    exchange_id = "kifpool"
    display_name = "Kifpool (kifpool) Spot API"
    market_list_url = "https://api.kifpool.app/api/spot/price"
    batch_price_url = "https://api.kifpool.app/api/spot/price"
    single_price_url = "https://api.kifpool.app/api/spot/price"
    provider_key = "crypto_kifpool"

    specification = AdapterSpecification(
        exchange_id="kifpool",
        display_name="Kifpool (kifpool) Spot API",
        provider_key="crypto_kifpool",
        market_list_url="https://api.kifpool.app/api/spot/price",
        batch_price_url="https://api.kifpool.app/api/spot/price",
        single_price_url="https://api.kifpool.app/api/spot/price",
        rate_limit_rps=10.0,
        quote_currency="USDT",  # Supports both USDT and TMN
        status="active",
        has_leveraged_tokens=False,
        aliases=("kifpool_spot", "kifpool_iran", "kifpool_me"),
        notes="Official Iranian exchange adapter with 1,200+ coins in dual USDT & TMN quotes"
    )

    def to_native_symbol(self, base_or_symbol: str, quote: str = "USDT") -> str:
        """Converts base currency or symbol to Kifpool native representation."""
        sym = (base_or_symbol or '').strip().upper()
        if not sym:
            return ""
        sym = sym.replace("_", "").replace("-", "").replace("/", "")
        if sym.endswith("TMN") or sym.endswith("USDT") or sym.endswith("IRT"):
            return sym
        target_quote = "TMN" if quote.upper() in ("TMN", "IRT") else "USDT"
        return f"{sym}{target_quote}"

    def to_canonical_base(self, native_symbol: str) -> str:
        """Converts native market symbol back to canonical base currency (e.g. BTCTMN -> BTC)."""
        base, _ = self.to_canonical_base_and_quote(native_symbol)
        return base

    def to_canonical_base_and_quote(self, native_or_clean: str) -> Tuple[str, str]:
        """
        Splits clean symbol into base and quote ('USDT' or 'TMN').
        Examples:
        'BTCUSDT' -> ('BTC', 'USDT')
        'BTCTMN'  -> ('BTC', 'TMN')
        'BTC_USDT' -> ('BTC', 'USDT')
        'BTC_TMN'  -> ('BTC', 'TMN')
        'BTCIRT'   -> ('BTC', 'TMN')
        """
        sym = (native_or_clean or '').strip().upper().replace("_", "").replace("-", "").replace("/", "")
        if sym.endswith("USDT") and len(sym) > 4:
            return sym[:-4], "USDT"
        if sym.endswith("TMN") and len(sym) > 3:
            return sym[:-3], "TMN"
        if sym.endswith("IRT") and len(sym) > 3:
            return sym[:-3], "TMN"
        return sym, "USDT"

    def parse_symbols_response(self, raw_data: Any) -> List[SymbolInfo]:
        """
        Parses GET https://api.kifpool.app/api/spot/price response.
        Generates two active symbols for each listed currency:
        1. <BASE>USDT (quote=USDT)
        2. <BASE>TMN  (quote=TMN)
        """
        if not isinstance(raw_data, list):
            return []

        results: List[SymbolInfo] = []
        seen = set()

        for item in raw_data:
            if not isinstance(item, dict):
                continue
            base = (item.get("symbol") or "").strip().upper()
            if not base:
                continue

            # 1. Add USDT pair
            usdt_sym = f"{base}USDT"
            if usdt_sym not in seen:
                seen.add(usdt_sym)
                results.append(SymbolInfo(
                    base=base,
                    quote="USDT",
                    market_symbol=usdt_sym,
                    is_active=True,
                    is_etf=False,
                    min_price=1e-12,
                    min_qty=None,
                    raw=item
                ))

            # 2. Add TMN pair (if IRT price is present)
            tmn_sym = f"{base}TMN"
            if tmn_sym not in seen and (item.get("priceBuyIRT") is not None or item.get("priceSellIRT") is not None):
                seen.add(tmn_sym)
                results.append(SymbolInfo(
                    base=base,
                    quote="TMN",
                    market_symbol=tmn_sym,
                    is_active=True,
                    is_etf=False,
                    min_price=1e-6,
                    min_qty=None,
                    raw=item
                ))

        return results

    def parse_batch_prices_response(self, raw_data: Any) -> Dict[str, float]:
        """Implements BaseExchangeAdapter.parse_batch_prices_response."""
        res = self.parse_batch_prices(raw_data)
        return res.prices

    def parse_batch_prices(self, raw_data: Any) -> BatchPriceResult:
        """
        Parses bulk spot prices from https://api.kifpool.app/api/spot/price.
        Extracts both USDT and TMN prices for each coin.
        """
        if not isinstance(raw_data, list):
            return BatchPriceResult(prices={}, as_of=int(time.time()), error_code="INVALID_RESPONSE")

        prices: Dict[str, float] = {}
        for item in raw_data:
            if not isinstance(item, dict):
                continue
            base = (item.get("symbol") or "").strip().upper()
            if not base:
                continue

            # A. USDT Price
            usdt_val = item.get("price")
            if usdt_val is not None:
                try:
                    p_float = float(usdt_val)
                    if p_float > 0:
                        prices[f"{base}USDT"] = p_float
                        prices[f"{base}_USDT"] = p_float
                        prices[f"{base}-USDT"] = p_float
                        if base != "USDT":
                            prices[base] = p_float
                except (ValueError, TypeError):
                    pass

            # B. TMN Price (Average of Buy and Sell IRT / 10 to get Tomans)
            buy_irt = item.get("priceBuyIRT")
            sell_irt = item.get("priceSellIRT")
            tmn_val: Optional[float] = None

            if buy_irt is not None and sell_irt is not None:
                try:
                    b_f = float(buy_irt)
                    s_f = float(sell_irt)
                    if b_f > 0 and s_f > 0:
                        # 1 Toman = 10 Rials (IRT)
                        tmn_val = ((b_f + s_f) / 2.0) / 10.0
                    elif b_f > 0:
                        tmn_val = b_f / 10.0
                    elif s_f > 0:
                        tmn_val = s_f / 10.0
                except (ValueError, TypeError):
                    pass
            elif buy_irt is not None:
                try:
                    b_f = float(buy_irt)
                    if b_f > 0:
                        tmn_val = b_f / 10.0
                except (ValueError, TypeError):
                    pass

            if tmn_val is not None and tmn_val > 0:
                prices[f"{base}TMN"] = tmn_val
                prices[f"{base}_TMN"] = tmn_val
                prices[f"{base}-TMN"] = tmn_val
                prices[f"{base}IRT"] = tmn_val
                prices[f"{base}_IRT"] = tmn_val

        if not prices:
            return BatchPriceResult(prices={}, as_of=int(time.time()), error_code="NO_PRICE")

        return BatchPriceResult(prices=prices, as_of=int(time.time()), error_code="OK")

    def parse_single_price(self, raw_data: Any, symbol: str) -> SinglePriceResult:
        """Parses single price response for Kifpool."""
        batch_res = self.parse_batch_prices(raw_data)
        if batch_res.error_code != "OK":
            return SinglePriceResult(price=None, as_of=batch_res.as_of, status=batch_res.error_code or "NO_PRICE")

        sym_upper = (symbol or "").strip().upper()
        p = batch_res.prices.get(sym_upper)
        if p is not None:
            return SinglePriceResult(price=p, as_of=batch_res.as_of, status="OK")

        # Try base resolution
        base, quote = self.to_canonical_base_and_quote(sym_upper)
        target_key = f"{base}{quote}"
        p = batch_res.prices.get(target_key)
        if p is not None:
            return SinglePriceResult(price=p, as_of=batch_res.as_of, status="OK")

        return SinglePriceResult(price=None, as_of=batch_res.as_of, status="SYMBOL_NOT_LISTED")

