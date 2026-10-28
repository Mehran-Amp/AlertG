# -*- coding: utf-8 -*-
"""
AlertG — Exchange Adapters Package (Phase 4).
Contains isolated exchange adapters enforcing Rule R1 and single-bulk price queries.
"""
from app.markets.adapters.base import (
    BaseExchangeAdapter,
    SymbolInfo,
    BatchPriceResult,
    SinglePriceResult,
    classify_http_error,
)
from app.markets.adapters.binance import BinanceAdapter
from app.markets.adapters.mexc import MEXCAdapter
from app.markets.adapters.kucoin import KuCoinAdapter

__all__ = [
    "BaseExchangeAdapter",
    "SymbolInfo",
    "BatchPriceResult",
    "SinglePriceResult",
    "classify_http_error",
    "BinanceAdapter",
    "MEXCAdapter",
    "KuCoinAdapter",
]
