# -*- coding: utf-8 -*-
"""
AlertG — Bitfinex Crypto Exchange Adapter (Wave 2 / Version 2).
Official Bitfinex Spot API v2 integration:
1. Markets: https://api-pub.bitfinex.com/v2/conf/pub:list:pair:exchange
2. Bulk Tickers: https://api-pub.bitfinex.com/v2/tickers?symbols=ALL
3. Single Ticker: https://api-pub.bitfinex.com/v2/ticker/{symbol}
4. Strict spot-only, USDT (Bitfinex UST) pairs.
"""
from typing import Dict, Any, List
from app.markets.adapters.base import (
    BaseExchangeAdapter,
    AdapterSpecification,
    SymbolInfo,
)


class BitfinexAdapter(BaseExchangeAdapter):
    """Bitfinex Spot USDT (UST) Market Adapter."""

    exchange_id = "bitfinex"
    display_name = "Bitfinex (bitfinex) Spot API"
    market_list_url = "https://api-pub.bitfinex.com/v2/conf/pub:list:pair:exchange"
    batch_price_url = "https://api-pub.bitfinex.com/v2/tickers?symbols=ALL"
    single_price_url = "https://api-pub.bitfinex.com/v2/ticker/{symbol}"
    provider_key = "crypto_bitfinex"

    specification = AdapterSpecification(
        exchange_id="bitfinex",
        display_name="Bitfinex (bitfinex) Spot API",
        provider_key="crypto_bitfinex",
        market_list_url="https://api-pub.bitfinex.com/v2/conf/pub:list:pair:exchange",
        batch_price_url="https://api-pub.bitfinex.com/v2/tickers?symbols=ALL",
        single_price_url="https://api-pub.bitfinex.com/v2/ticker/{symbol}",
        rate_limit_rps=15.0,
        quote_currency="USDT",
        status="active",
        has_leveraged_tokens=False,
        aliases=(),
        notes="Official Bitfinex Spot v2 public API"
    )

    def to_native_symbol(self, base_or_symbol: str) -> str:
        """
        Formats symbol to Bitfinex native ticker symbol (prefixed with 't', e.g. tBTCUST).
        """
        sym = (base_or_symbol or "").strip().upper()
        if not sym:
            return ""
        if sym.startswith("T") and (sym.endswith("UST") or sym.endswith("USDT")):
            return sym

        sym = sym.replace("-", "").replace("_", "")
        if sym.endswith("USDT") and len(sym) > 4:
            base = sym[:-4]
        elif sym.endswith("UST") and len(sym) > 3:
            base = sym[:-3]
        else:
            base = sym

        if len(base) > 3:
            return f"t{base}:UST"
        return f"t{base}UST"

    def to_canonical_base(self, native_symbol: str) -> str:
        sym = (native_symbol or "").strip().upper()
        if sym.startswith("T"):
            sym = sym[1:]
        if ":UST" in sym:
            return sym.split(":UST")[0]
        if ":USDT" in sym:
            return sym.split(":USDT")[0]
        if sym.endswith("USDT") and len(sym) > 4:
            return sym[:-4]
        if sym.endswith("UST") and len(sym) > 3:
            return sym[:-3]
        return sym

    def parse_symbols_response(self, raw_data: Any) -> List[SymbolInfo]:
        results: List[SymbolInfo] = []
        pairs_list = []
        if isinstance(raw_data, list) and raw_data:
            if isinstance(raw_data[0], list):
                pairs_list = raw_data[0]
            else:
                pairs_list = raw_data

        for p in pairs_list:
            if not isinstance(p, str):
                continue
            pair_str = p.strip().upper()
            if not (pair_str.endswith("UST") or pair_str.endswith("USDT") or ":UST" in pair_str or ":USDT" in pair_str):
                continue

            base = self.to_canonical_base(pair_str)
            if not base:
                continue

            market_sym = f"t{pair_str}"

            results.append(SymbolInfo(
                base=base,
                quote="USDT",
                market_symbol=market_sym,
                is_active=True,
                is_etf=False,
                raw={"pair": pair_str},
            ))

        return results

    def parse_batch_prices_response(self, raw_data: Any) -> Dict[str, float]:
        prices: Dict[str, float] = {}
        if not isinstance(raw_data, list):
            return prices

        for item in raw_data:
            if not isinstance(item, list) or len(item) < 8:
                continue
            raw_sym = str(item[0]).strip()
            sym = raw_sym.upper()
            if not sym.startswith("T") or not (sym.endswith("UST") or sym.endswith("USDT") or ":UST" in sym or ":USDT" in sym):
                continue

            raw_p = item[7]  # index 7 is last price in Bitfinex ticker array
            if raw_p is None:
                continue
            try:
                p_val = float(raw_p)
                if p_val > 0:
                    prices[raw_sym] = p_val
                    prices[sym] = p_val
                    prices[sym.lower()] = p_val
                    base = self.to_canonical_base(sym)
                    if base:
                        prices[f"{base}USDT"] = p_val
                        prices[f"{base}-USDT"] = p_val
                        prices[f"{base}_USDT"] = p_val
            except (ValueError, TypeError):
                continue


        return prices
