# -*- coding: utf-8 -*-
"""
AlertG — Exchange Adapters Package (Phase 4).
Contains isolated exchange adapters enforcing Rule R1 and single-bulk price queries.
"""
from app.markets.adapters.base import (
    BaseExchangeAdapter,
    AdapterSpecification,
    validate_adapter_specification,
    SymbolInfo,
    BatchPriceResult,
    SinglePriceResult,
    classify_http_error,
)
from app.markets.adapters.binance import BinanceAdapter
from app.markets.adapters.mexc import MEXCAdapter
from app.markets.adapters.kucoin import KuCoinAdapter
from app.markets.adapters.gateio import GateioAdapter
from app.markets.adapters.lbank import LBankAdapter
from app.markets.adapters.okx import OKXAdapter
from app.markets.adapters.kraken import KrakenAdapter
from app.markets.adapters.bybit import BybitAdapter
from app.markets.adapters.bitget import BitgetAdapter

__all__ = [
    "BaseExchangeAdapter",
    "AdapterSpecification",
    "validate_adapter_specification",
    "SymbolInfo",
    "BatchPriceResult",
    "SinglePriceResult",
    "classify_http_error",
    "BinanceAdapter",
    "MEXCAdapter",
    "KuCoinAdapter",
    "GateioAdapter",
    "LBankAdapter",
    "OKXAdapter",
    "KrakenAdapter",
    "BybitAdapter",
    "BitgetAdapter",
]
