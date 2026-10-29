# -*- coding: utf-8 -*-
"""
AlertG — Bitget Crypto Exchange Adapter (Phase 2 / Wave 1).
Fully isolated adapter for Bitget Spot USDT pairs (V2 Market API):
1. Market list from https://api.bitget.com/api/v2/spot/public/symbols
2. Bulk prices from https://api.bitget.com/api/v2/spot/market/tickers
3. Single price from https://api.bitget.com/api/v2/spot/market/tickers?symbol={symbol}
4. Two-way symbol mapping (BTC <-> BTCUSDT, 1INCH <-> 1INCHUSDT)
5. Strict spot-only, USDT-only, active-only ('online') filtering.
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


class BitgetAdapter(BaseExchangeAdapter):
    """Bitget Spot USDT Market Adapter (V2 API)."""

    exchange_id = "bitget"
    display_name = "Bitget (bitget) Spot API"
    market_list_url = "https://api.bitget.com/api/v2/spot/public/symbols"
    batch_price_url = "https://api.bitget.com/api/v2/spot/market/tickers"
    single_price_url = "https://api.bitget.com/api/v2/spot/market/tickers?symbol={symbol}"
    provider_key = "crypto_bitget"

    specification = AdapterSpecification(
        exchange_id="bitget",
        display_name="Bitget (bitget) Spot API",
        provider_key="crypto_bitget",
        market_list_url="https://api.bitget.com/api/v2/spot/public/symbols",
        batch_price_url="https://api.bitget.com/api/v2/spot/market/tickers",
        single_price_url="https://api.bitget.com/api/v2/spot/market/tickers?symbol={symbol}",
        rate_limit_rps=20.0,
        quote_currency="USDT",
        status="active",
        has_leveraged_tokens=False,
        aliases=(),
        notes="High volume Asian and global liquidity benchmark"
    )

    def to_native_symbol(self, base_or_symbol: str) -> str:
        """
        Converts base currency or raw symbol to Bitget-native symbol.
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
        Converts Bitget-native market symbol back to canonical base currency.
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
        Parses Bitget /api/v2/spot/public/symbols response.
        Expected format:
        {
            "code": "00000",
            "msg": "success",
            "data": [
                {
                    "symbol": "BTCUSDT",
                    "baseCoin": "BTC",
                    "quoteCoin": "USDT",
                    "status": "online",
                    "minTradeAmount": "0.0001",
                    "pricePrecision": "2"
                }, ...
            ]
        }
        """
        results: List[SymbolInfo] = []
        if not isinstance(raw_data, dict):
            return results

        if raw_data.get("code") != "00000":
            return results

        symbols_list = raw_data.get("data", [])
        if not isinstance(symbols_list, list):
            return results

        for s in symbols_list:
            if not isinstance(s, dict):
                continue

            quote = (s.get("quoteCoin") or "").upper().strip()
            if quote != "USDT":
                continue

            status = s.get("status")
            if status != "online":
                continue

            base = (s.get("baseCoin") or "").upper().strip()
            market_sym = (s.get("symbol") or "").upper().strip()
            if not base or not market_sym:
                continue

            min_qty = None
            if s.get("minTradeAmount"):
                try:
                    min_qty = float(s["minTradeAmount"])
                except (ValueError, TypeError):
                    pass

            is_etf = self.is_leveraged_token(base)

            results.append(SymbolInfo(
                base=base,
                quote=quote,
                market_symbol=market_sym,
                is_active=True,
                is_etf=is_etf,
                min_price=None,
                min_qty=min_qty,
                raw=s,
            ))

        return results

    def parse_batch_prices_response(self, raw_data: Any) -> Dict[str, float]:
        """
        Parses Bitget /api/v2/spot/market/tickers response.
        Expected format:
        {
            "code": "00000",
            "msg": "success",
            "data": [
                {"symbol": "BTCUSDT", "lastPr": "68520.40"},
                ...
            ]
        }
        """
        prices: Dict[str, float] = {}
        if not isinstance(raw_data, dict):
            return prices

        if raw_data.get("code") != "00000":
            return prices

        ticker_list = raw_data.get("data", [])
        if not isinstance(ticker_list, list):
            return prices

        for item in ticker_list:
            if not isinstance(item, dict):
                continue
            sym = (item.get("symbol") or "").strip().upper()
            if not sym.endswith("USDT"):
                continue
            raw_p = item.get("lastPr")
            try:
                p_val = float(raw_p)
                if p_val > 0:
                    prices[sym] = p_val
            except (ValueError, TypeError):
                continue

        return prices
