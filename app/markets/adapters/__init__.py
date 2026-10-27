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

__all__ = [
    "BaseExchangeAdapter",
    "SymbolInfo",
    "BatchPriceResult",
    "SinglePriceResult",
    "classify_http_error",
]
