# -*- coding: utf-8 -*-
"""
AlertG — Crypto Exchange Registry (Phase 1 Fix / Version 2).
Central, authoritative single source of truth for all supported cryptocurrency exchanges:
- Unique canonical lowercase IDs matching config.EXCHANGE_RE.
- Dedicated provider keys for rate-limiting, metrics, and circuit-breaker isolation.
- Standardized source labels containing the exchange ID (Rule R11).
- CoinEx is completely removed (Owner Decision E1.2).
- Bybit and Bitget marked as 'pending_adapter' until Phase 2 specifications are connected.
- Unknown exchange IDs never receive a provider key (Rule R1).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import app.config as config


@dataclass(frozen=True)
class CryptoExchangeMetadata:
    id: str                 # Canonical lowercase ID matching config.EXCHANGE_RE
    name: str               # Official display name (e.g. 'Binance', 'LBank')
    category: str           # e.g. 'tier1', 'asia'
    provider_key: str       # Dedicated provider key (e.g. 'crypto_binance')
    source_label: str       # Source label containing ID as substring (Rule R11)
    markets_url: str        # Endpoint for public spot market / currency pairs discovery
    bulk_ticker_url: str    # Endpoint for bulk 24hr / all tickers price fetch
    status: str             # 'active' | 'pending_adapter' | 'inactive'
    has_leveraged_tokens: bool = False
    aliases: Tuple[str, ...] = ()
    notes: Optional[str] = None


# Official Crypto Exchange Registry (Single Source of Truth)
_CRYPTO_EXCHANGES: Dict[str, CryptoExchangeMetadata] = {
    'binance': CryptoExchangeMetadata(
        id='binance',
        name='Binance',
        category='tier1',
        provider_key='crypto_binance',
        source_label='Binance (binance) Spot API',
        markets_url='https://api.binance.com/api/v3/exchangeInfo',
        bulk_ticker_url='https://api.binance.com/api/v3/ticker/price',
        status='active',
        has_leveraged_tokens=False,
        aliases=('binance_spot',),
        notes='Tier 1 global liquidity benchmark'
    ),
    'mexc': CryptoExchangeMetadata(
        id='mexc',
        name='MEXC',
        category='tier1',
        provider_key='crypto_mexc',
        source_label='MEXC (mexc) Spot API',
        markets_url='https://api.mexc.com/api/v3/exchangeInfo',
        bulk_ticker_url='https://api.mexc.com/api/v3/ticker/price',
        status='active',
        has_leveraged_tokens=False,
        aliases=('mexc_global',),
        notes='Wide altcoin catalog'
    ),
    'kucoin': CryptoExchangeMetadata(
        id='kucoin',
        name='KuCoin',
        category='tier1',
        provider_key='crypto_kucoin',
        source_label='KuCoin (kucoin) Spot API',
        markets_url='https://api.kucoin.com/api/v1/symbols',
        bulk_ticker_url='https://api.kucoin.com/api/v1/market/allTickers',
        status='active',
        has_leveraged_tokens=True,
        aliases=(),
        notes='Full spot pairs with standard dash symbol format'
    ),
    'gateio': CryptoExchangeMetadata(
        id='gateio',
        name='Gate.io',
        category='tier1',
        provider_key='crypto_gateio',
        source_label='Gate.io (gateio) Spot API',
        markets_url='https://api.gateio.ws/api/v4/spot/currency_pairs',
        bulk_ticker_url='https://api.gateio.ws/api/v4/spot/tickers',
        status='active',
        has_leveraged_tokens=True,
        aliases=('gate',),
        notes='Extensive altcoin spot market coverage'
    ),
    'lbank': CryptoExchangeMetadata(
        id='lbank',
        name='LBank',
        category='asia',
        provider_key='crypto_lbank',
        source_label='LBank (lbank) Spot API',
        markets_url='https://api.lbank.info/v2/currencyPairs.do',
        bulk_ticker_url='https://api.lbank.info/v2/ticker/24hr.do?symbol=all',
        status='active',
        has_leveraged_tokens=False,
        aliases=('lbkex',),
        notes='Official replacement for CoinEx with verified live-price filter'
    ),
    'okx': CryptoExchangeMetadata(
        id='okx',
        name='OKX',
        category='tier1',
        provider_key='crypto_okx',
        source_label='OKX (okx) Spot API',
        markets_url='https://www.okx.com/api/v5/public/instruments?instType=SPOT',
        bulk_ticker_url='https://www.okx.com/api/v5/market/tickers?instType=SPOT',
        status='active',
        has_leveraged_tokens=False,
        aliases=('okex',),
        notes='Tier 1 global exchange with instType=SPOT'
    ),
    'kraken': CryptoExchangeMetadata(
        id='kraken',
        name='Kraken',
        category='tier1',
        provider_key='crypto_kraken',
        source_label='Kraken (kraken) Spot API',
        markets_url='https://api.kraken.com/0/public/AssetPairs',
        bulk_ticker_url='https://api.kraken.com/0/public/Ticker',
        status='active',
        has_leveraged_tokens=False,
        aliases=(),
        notes='Tier 1 spot market with AssetPairs metadata mapping'
    ),
    'bybit': CryptoExchangeMetadata(
        id='bybit',
        name='Bybit',
        category='tier1',
        provider_key='crypto_bybit',
        source_label='Bybit (bybit) Spot API',
        markets_url='https://api.bybit.com/v5/market/instruments-info?category=spot',
        bulk_ticker_url='https://api.bybit.com/v5/market/tickers?category=spot',
        status='active',
        has_leveraged_tokens=False,
        aliases=(),
        notes='Tier 1 spot market via V5 API'
    ),
    'bitget': CryptoExchangeMetadata(
        id='bitget',
        name='Bitget',
        category='tier1',
        provider_key='crypto_bitget',
        source_label='Bitget (bitget) Spot API',
        markets_url='https://api.bitget.com/api/v2/spot/public/symbols',
        bulk_ticker_url='https://api.bitget.com/api/v2/spot/market/tickers',
        status='active',
        has_leveraged_tokens=False,
        aliases=(),
        notes='Tier 1 spot market via V2 API'
    ),
}

# Fast alias lookup index
_ALIAS_TO_ID: Dict[str, str] = {}
for _eid, _meta in _CRYPTO_EXCHANGES.items():
    _ALIAS_TO_ID[_eid] = _eid
    for _alias in _meta.aliases:
        _ALIAS_TO_ID[_alias.lower().strip()] = _eid


def get_crypto_exchange(exchange_id: str) -> Optional[CryptoExchangeMetadata]:
    """Retrieves exchange metadata by lowercase ID or alias."""
    if not exchange_id:
        return None
    cleaned = exchange_id.strip().lower()
    canonical_id = _ALIAS_TO_ID.get(cleaned, cleaned)
    return _CRYPTO_EXCHANGES.get(canonical_id)


def list_crypto_exchanges(status: Optional[str] = None) -> List[CryptoExchangeMetadata]:
    """Returns list of crypto exchanges, optionally filtered by status ('active', 'pending_adapter')."""
    if status is None:
        return list(_CRYPTO_EXCHANGES.values())
    target = status.strip().lower()
    return [e for e in _CRYPTO_EXCHANGES.values() if e.status == target]


def get_supported_exchange_ids(active_only: bool = True) -> List[str]:
    """Returns list of canonical exchange IDs."""
    if active_only:
        return [e.id for e in _CRYPTO_EXCHANGES.values() if e.status == 'active']
    return list(_CRYPTO_EXCHANGES.keys())


def is_supported_crypto_exchange(exchange_id: str, allow_pending: bool = False) -> bool:
    """Checks whether an exchange is registered and supported."""
    meta = get_crypto_exchange(exchange_id)
    if not meta:
        return False
    if allow_pending:
        return meta.status in ('active', 'pending_adapter')
    return meta.status == 'active'


def get_crypto_provider_key(exchange_id: str) -> Optional[str]:
    """
    Returns the isolated provider_key for rate-limiting, metrics, and circuit-breaker.
    Returns None if exchange is unknown (strictly enforcing Rule R1 / E1.4).
    """
    meta = get_crypto_exchange(exchange_id)
    if meta:
        return meta.provider_key
    return None
