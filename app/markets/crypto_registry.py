# -*- coding: utf-8 -*-
"""
AlertG — Crypto Exchange Registry (Phase 2).
Central registry defining all supported cryptocurrency exchanges, their public API endpoints,
dedicated provider keys for rate-limiting and circuit breakers, and operating status.

Design Principles:
- Single source of truth in backend for crypto exchange metadata.
- Strict isolation: Each exchange has a dedicated provider_key for rate limiting and outage tracking.
- CoinEx is maintained with status='closing', while LBank is added as its active replacement.
- Zero change to existing price paths or stock/forex/iran systems.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import re
import app.config as config


@dataclass(frozen=True)
class CryptoExchangeMetadata:
    id: str                 # Canonical lowercase ID matching config.EXCHANGE_RE
    name: str               # Official display name (e.g. 'Binance', 'LBank')
    category: str           # e.g. 'tier1', 'asia'
    provider_key: str       # Dedicated provider key for rate limiting and kill-switch isolation
    markets_url: str        # Endpoint for public spot market / currency pairs discovery
    bulk_ticker_url: str    # Endpoint for bulk 24hr / all tickers price fetch
    status: str             # 'active' | 'closing' | 'inactive'
    has_leveraged_tokens: bool = False
    notes: Optional[str] = None


# Official Crypto Exchange Registry (Ordered by priority and tier)
_CRYPTO_EXCHANGES: Dict[str, CryptoExchangeMetadata] = {
    'binance': CryptoExchangeMetadata(
        id='binance',
        name='Binance',
        category='tier1',
        provider_key='crypto_binance',
        markets_url='https://api.binance.com/api/v3/exchangeInfo',
        bulk_ticker_url='https://api.binance.com/api/v3/ticker/price',
        status='active',
        has_leveraged_tokens=False,
        notes='Market depth and liquidity benchmark'
    ),
    'mexc': CryptoExchangeMetadata(
        id='mexc',
        name='MEXC',
        category='tier1',
        provider_key='crypto_mexc',
        markets_url='https://api.mexc.com/api/v3/exchangeInfo',
        bulk_ticker_url='https://api.mexc.com/api/v3/ticker/price',
        status='active',
        has_leveraged_tokens=False,
        notes='Wide altcoin catalog and high speed (105ms)'
    ),
    'kucoin': CryptoExchangeMetadata(
        id='kucoin',
        name='KuCoin',
        category='tier1',
        provider_key='crypto_kucoin',
        markets_url='https://api.kucoin.com/api/v1/symbols',
        bulk_ticker_url='https://api.kucoin.com/api/v1/market/allTickers',
        status='active',
        has_leveraged_tokens=True,
        notes='Full spot pairs with standard dash symbol format'
    ),
    'gateio': CryptoExchangeMetadata(
        id='gateio',
        name='Gate.io',
        category='tier1',
        provider_key='crypto_gateio',
        markets_url='https://api.gateio.ws/api/v4/spot/currency_pairs',
        bulk_ticker_url='https://api.gateio.ws/api/v4/spot/tickers',
        status='active',
        has_leveraged_tokens=True,
        notes='2000+ active USDT spot pairs'
    ),
    'lbank': CryptoExchangeMetadata(
        id='lbank',
        name='LBank',
        category='asia',
        provider_key='crypto_lbank',
        markets_url='https://api.lbank.info/v2/currencyPairs.do',
        bulk_ticker_url='https://api.lbank.info/v2/ticker/24hr.do?symbol=all',
        status='active',
        has_leveraged_tokens=False,
        notes='Official replacement for CoinEx; unpriced ETF pairs filtered in catalog'
    ),
    'okx': CryptoExchangeMetadata(
        id='okx',
        name='OKX',
        category='tier1',
        provider_key='crypto_okx',
        markets_url='https://www.okx.com/api/v5/public/instruments?instType=SPOT',
        bulk_ticker_url='https://www.okx.com/api/v5/market/tickers?instType=SPOT',
        status='active',
        has_leveraged_tokens=False,
        notes='Tier 1 global exchange with instType=SPOT'
    ),
    'bybit': CryptoExchangeMetadata(
        id='bybit',
        name='Bybit',
        category='tier1',
        provider_key='crypto_bybit',
        markets_url='https://api.bybit.com/v5/market/instruments-info?category=spot',
        bulk_ticker_url='https://api.bybit.com/v5/market/tickers?category=spot',
        status='active',
        has_leveraged_tokens=False,
        notes='High-liquidity spot USDT markets'
    ),
    'bitget': CryptoExchangeMetadata(
        id='bitget',
        name='Bitget',
        category='tier1',
        provider_key='crypto_bitget',
        markets_url='https://api.bitget.com/api/v2/spot/public/symbols',
        bulk_ticker_url='https://api.bitget.com/api/v2/spot/market/tickers',
        status='active',
        has_leveraged_tokens=False,
        notes='Over 3500 verified spot pairs'
    ),
    'kraken': CryptoExchangeMetadata(
        id='kraken',
        name='Kraken',
        category='tier1',
        provider_key='crypto_kraken',
        markets_url='https://api.kraken.com/0/public/AssetPairs',
        bulk_ticker_url='https://api.kraken.com/0/public/Ticker',
        status='active',
        has_leveraged_tokens=False,
        notes='Fastest response latency (56ms) with native pair mapping'
    ),
    'coinex': CryptoExchangeMetadata(
        id='coinex',
        name='CoinEx',
        category='tier1',
        provider_key='crypto_coinex',
        markets_url='https://api.coinex.com/v1/market/list',
        bulk_ticker_url='https://api.coinex.com/v1/market/ticker/all',
        status='closing',
        has_leveraged_tokens=False,
        notes='Deprecated and currently returning 503; preserved for migration in Phase 12'
    ),
}


def get_crypto_exchange(exchange_id: str) -> Optional[CryptoExchangeMetadata]:
    """Retrieves exchange metadata by lowercase ID."""
    if not exchange_id:
        return None
    return _CRYPTO_EXCHANGES.get(exchange_id.strip().lower())


def list_crypto_exchanges(status: Optional[str] = None) -> List[CryptoExchangeMetadata]:
    """Returns list of crypto exchanges, optionally filtered by status ('active', 'closing')."""
    if status is None:
        return list(_CRYPTO_EXCHANGES.values())
    target = status.strip().lower()
    return [e for e in _CRYPTO_EXCHANGES.values() if e.status == target]


def is_supported_crypto_exchange(exchange_id: str) -> bool:
    """Checks whether an exchange is registered in the crypto registry."""
    if not exchange_id:
        return False
    return exchange_id.strip().lower() in _CRYPTO_EXCHANGES


def get_crypto_provider_key(exchange_id: str) -> str:
    """
    Returns the isolated provider_key for rate-limiting, metrics, and kill-switch.
    Defaults to 'crypto_global' for backward compatibility.
    """
    meta = get_crypto_exchange(exchange_id)
    if meta:
        return meta.provider_key
    return 'crypto_global'
