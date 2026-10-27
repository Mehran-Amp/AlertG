# -*- coding: utf-8 -*-
"""
AlertG — Strict Crypto Price Core (Phase 3).
Enforces Rule R1 (Exchange Isolation & Zero Fallbacks):
1. Every query strictly targets the designated exchange's own public API.
2. An unknown exchange immediately returns status='UNKNOWN_EXCHANGE'; NEVER defaults to Binance.
3. If the selected exchange returns no price, the query immediately terminates with status='NO_PRICE';
   NEVER steals or falls back to another exchange.
4. Returns a structured CryptoPriceResult: (price, asOf, source, status, currency).
"""

import time
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
import httpx

from app.markets.common import normalize_symbol
from app.markets.crypto_registry import get_crypto_exchange, is_supported_crypto_exchange


@dataclass
class CryptoPriceResult:
    price: Optional[float]
    asOf: Optional[int]
    source: Optional[str]
    status: str  # 'SUCCESS' | 'UNKNOWN_EXCHANGE' | 'SYMBOL_NOT_LISTED' | 'NO_PRICE' | 'STALE_PRICE' | 'PROVIDER_BLOCKED'
    currency: str = "USDT"


def _format_native_symbol(exchange_id: str, symbol: str) -> str:
    """Formats clean symbol into the native representation required by each exchange API."""
    sym_clean = normalize_symbol(symbol).upper()
    if not any(sym_clean.endswith(q) for q in ['USDT', 'BUSD', 'USDC', 'BTC', 'ETH', 'EUR', 'USD']):
        sym_clean = sym_clean + 'USDT'

    ex = exchange_id.lower().strip()
    base = sym_clean[:-4] if sym_clean.endswith('USDT') else sym_clean

    if ex in ('kucoin', 'okx'):
        return f"{base}-USDT"
    elif ex in ('gateio', 'gate'):
        return f"{base}_USDT"
    elif ex == 'lbank':
        return f"{base.lower()}_usdt"
    elif ex == 'kraken':
        k_base = 'XBT' if base == 'BTC' else base
        return f"{k_base}USDT"
    else:
        return sym_clean


async def fetch_crypto_strict(
    client: httpx.AsyncClient,
    exchange: str,
    symbol: str,
    _try_fetch,
    traces: List[Dict[str, Any]]
) -> CryptoPriceResult:
    """
    Executes Rule R1 Strict Price Fetch:
    - Verifies exchange registration in crypto_registry.
    - Resolves native symbol format.
    - Queries ONLY the target exchange endpoint.
    - Zero cross-exchange fallbacks.
    """
    ex = (exchange or '').lower().strip()

    # 1. Unknown exchange guard: Immediate failure, NEVER default to Binance
    meta = get_crypto_exchange(ex)
    if not meta:
        err_msg = f"UNKNOWN_EXCHANGE: '{exchange}' is not a registered crypto exchange"
        traces.append({
            'source': f"{ex.upper()} (Unregistered)",
            'url': None,
            'status_code': 404,
            'error': err_msg,
            'duration_ms': 0.0
        })
        return CryptoPriceResult(
            price=None,
            asOf=None,
            source=None,
            status='UNKNOWN_EXCHANGE'
        )

    native_sym = _format_native_symbol(ex, symbol)
    now_ts = int(time.time())

    # 2. Single-target isolated fetch per exchange
    if ex == 'binance':
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={native_sym}"
        p = await _try_fetch(
            'Binance Spot API',
            url,
            lambda d: {'price': float(d.get('price')), 'state': 'LIVE', 'currency': 'USDT'}
            if isinstance(d, dict) and d.get('price') else None
        )
    elif ex == 'mexc':
        url = f"https://api.mexc.com/api/v3/ticker/price?symbol={native_sym}"
        p = await _try_fetch(
            'MEXC Spot API',
            url,
            lambda d: {'price': float(d.get('price')), 'state': 'LIVE', 'currency': 'USDT'}
            if isinstance(d, dict) and d.get('price') else None
        )
    elif ex == 'kucoin':
        url = f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={native_sym}"
        p = await _try_fetch(
            'KuCoin Spot API',
            url,
            lambda d: {'price': float(d.get('data', {}).get('price')), 'state': 'LIVE', 'currency': 'USDT'}
            if isinstance(d, dict) and d.get('data', {}).get('price') else None
        )
    elif ex in ('gateio', 'gate'):
        url = f"https://api.gateio.ws/api/v4/spot/tickers?currency_pair={native_sym}"
        p = await _try_fetch(
            'Gate.io Spot API',
            url,
            lambda d: {'price': float(d[0].get('last')), 'state': 'LIVE', 'currency': 'USDT'}
            if isinstance(d, list) and len(d) > 0 and d[0].get('last') else None
        )
    elif ex == 'lbank':
        url = f"https://api.lbank.info/v2/ticker/24hr.do?symbol={native_sym}"
        def _extract_lbank(d):
            if isinstance(d, dict) and d.get('result') == 'true' and d.get('data'):
                items = d.get('data', [])
                if items and isinstance(items, list):
                    val = items[0].get('ticker', {}).get('latest')
                    if val and float(val) > 0:
                        return {'price': float(val), 'state': 'LIVE', 'currency': 'USDT'}
            return None
        p = await _try_fetch('LBank Spot API', url, _extract_lbank)
    elif ex == 'okx':
        url = f"https://www.okx.com/api/v5/market/ticker?instId={native_sym}"
        def _extract_okx(d):
            if isinstance(d, dict) and d.get('code') == '0' and d.get('data'):
                items = d.get('data', [])
                if items and isinstance(items, list):
                    val = items[0].get('last')
                    if val and float(val) > 0:
                        return {'price': float(val), 'state': 'LIVE', 'currency': 'USDT'}
            return None
        p = await _try_fetch('OKX Spot API', url, _extract_okx)
    elif ex == 'bybit':
        url = f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={native_sym}"
        def _extract_bybit(d):
            if isinstance(d, dict) and d.get('retCode') == 0 and d.get('result', {}).get('list'):
                items = d.get('result', {}).get('list', [])
                if items and isinstance(items, list):
                    val = items[0].get('lastPrice')
                    if val and float(val) > 0:
                        return {'price': float(val), 'state': 'LIVE', 'currency': 'USDT'}
            return None
        p = await _try_fetch('Bybit Spot API', url, _extract_bybit)
    elif ex == 'bitget':
        url = f"https://api.bitget.com/api/v2/spot/market/tickers?symbol={native_sym}"
        def _extract_bitget(d):
            if isinstance(d, dict) and d.get('code') == '00000' and d.get('data'):
                items = d.get('data', [])
                if items and isinstance(items, list):
                    val = items[0].get('lastPr')
                    if val and float(val) > 0:
                        return {'price': float(val), 'state': 'LIVE', 'currency': 'USDT'}
            return None
        p = await _try_fetch('Bitget Spot API', url, _extract_bitget)
    elif ex == 'kraken':
        url = f"https://api.kraken.com/0/public/Ticker?pair={native_sym}"
        def _extract_kraken(d):
            if isinstance(d, dict) and not d.get('error') and d.get('result'):
                for _, t in d['result'].items():
                    c = t.get('c', [])
                    if c and len(c) > 0 and float(c[0]) > 0:
                        return {'price': float(c[0]), 'state': 'LIVE', 'currency': 'USDT'}
            return None
        p = await _try_fetch('Kraken Spot API', url, _extract_kraken)
    elif ex == 'coinex':
        url = f"https://api.coinex.com/v1/market/ticker?market={native_sym}"
        p = await _try_fetch(
            'CoinEx Spot API',
            url,
            lambda d: {'price': float(d.get('data', {}).get('ticker', {}).get('last')), 'state': 'LIVE', 'currency': 'USDT'}
            if isinstance(d, dict) and d.get('data', {}).get('ticker', {}).get('last') else None
        )
    else:
        p = None

    # 3. Check result: price must be valid positive float, otherwise NO_PRICE
    if p is not None and float(p) > 0:
        return CryptoPriceResult(
            price=float(p),
            asOf=now_ts,
            source=meta.name,
            status='SUCCESS',
            currency='USDT'
        )

    # 4. Failed: Strictly terminate with NO_PRICE. ZERO cross-exchange fallback!
    traces.append({
        'source': meta.name,
        'symbol': native_sym,
        'error': f"NO_PRICE: No price returned from {meta.name} for {native_sym}"
    })
    return CryptoPriceResult(
        price=None,
        asOf=None,
        source=meta.name,
        status='NO_PRICE'
    )
