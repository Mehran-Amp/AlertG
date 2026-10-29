# -*- coding: utf-8 -*-
"""
AlertG — Strict Crypto Price Core (Phase 1 Fix / Version 2).
Enforces Rule R1 (Exchange Isolation & Zero Fallbacks):
1. Every query strictly targets the designated exchange's own public API.
2. An unknown exchange immediately returns status='UNKNOWN_EXCHANGE'; NEVER defaults to Binance.
3. If the selected exchange returns no price, the query immediately terminates with status='NO_PRICE';
   NEVER steals or falls back to another exchange.
4. Uses resolve_pair from crypto_catalog with alias index (Rule R1 / Task 6).
5. Source labels contain the lowercase exchange ID as a substring (Rule R11).
6. CoinEx branch is completely removed (Owner Decision E1.2).
"""

import time
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
import httpx

import app.config as config
from app.markets.common import normalize_symbol
from app.markets.crypto_registry import get_crypto_exchange, is_supported_crypto_exchange
from app.markets.crypto_catalog import resolve_pair


@dataclass
class CryptoPriceResult:
    price: Optional[float]
    asOf: Optional[int]
    source: Optional[str]
    status: str  # 'OK' | 'UNKNOWN_EXCHANGE' | 'SYMBOL_NOT_LISTED' | 'NO_PRICE' | 'STALE_PRICE' | 'PROVIDER_BLOCKED' | 'RATE_LIMITED'
    currency: str = "USDT"


def _format_native_symbol(exchange_id: str, symbol: str) -> str:
    """
    Formats symbol into the native representation required by each exchange API.
    Uses resolve_pair if available, otherwise applies exact suffix rules without
    breaking tokens like WBTC and STETH.
    """
    res_status, pair_data = resolve_pair(exchange_id, symbol)
    if res_status == "OK" and pair_data and pair_data.get("native_symbol"):
        return pair_data["native_symbol"]

    # Suffix fallback when catalog is not yet populated
    raw = (symbol or "").strip()
    raw_upper = raw.upper()
    if raw_upper.endswith("USDT") and len(raw_upper) > 4:
        base = raw_upper[:-4]
    else:
        base = raw_upper

    ex = (exchange_id or "").lower().strip()
    if ex in ('kucoin', 'okx'):
        return f"{base}-USDT"
    elif ex in ('gateio', 'gate'):
        return f"{base}_USDT"
    elif ex == 'lbank':
        return f"{base.lower()}_usdt"
    elif ex == 'kraken':
        k_base = 'XBT' if base in ('BTC', 'XBT') else base
        return f"{k_base}USDT"
    elif ex == 'bybit':
        return f"{base}USDT"
    elif ex == 'bitget':
        return f"{base}USDT"
    return f"{base}USDT"


async def fetch_crypto_strict(
    client: httpx.AsyncClient,
    exchange: str,
    symbol: str,
    _try_fetch,
    traces: List[Dict[str, Any]],
    base_currency: Optional[str] = None,
    counter_currency: Optional[str] = None,
    market_symbol: Optional[str] = None,
) -> CryptoPriceResult:
    """
    Executes Rule R1 Strict Price Fetch:
    - Verifies exchange registration in crypto_registry.
    - Resolves pair using catalog alias index (prioritizing market_symbol & base_currency).
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

    # 2. Resolve pair from catalog
    resolve_status, pair_data = resolve_pair(
        exchange_id=ex,
        symbol_or_base=symbol,
        base_currency=base_currency,
        counter_currency=counter_currency,
        market_symbol=market_symbol,
    )
    if resolve_status == "SYMBOL_NOT_LISTED":
        err_msg = f"SYMBOL_NOT_LISTED: Symbol '{symbol}' is not listed on {meta.name}"
        traces.append({
            'source': meta.source_label,
            'symbol': symbol,
            'status_code': 404,
            'error': err_msg
        })
        return CryptoPriceResult(
            price=None,
            asOf=None,
            source=meta.name,
            status='SYMBOL_NOT_LISTED'
        )

    native_sym = pair_data["native_symbol"] if pair_data else _format_native_symbol(ex, symbol)
    source_label = meta.source_label
    now_ts = int(time.time())

    # Phase 3: Stage A Price Engine (Read O(1) in-memory snapshot with ZERO outbound HTTP calls)
    if getattr(config, "CRYPTO_ENGINE_V2", False):
        from app.markets.crypto_snapshot import get_snapshot_price
        max_age = getattr(config, "CRYPTO_SNAPSHOT_MAX_AGE_SECONDS", 10.0)
        snap_price, snap_as_of, snap_status, latency_ms = get_snapshot_price(ex, native_sym, max_age_seconds=max_age)

        if snap_status == "OK" and snap_price is not None and snap_price > 0:
            traces.append({
                'source': source_label,
                'url': f"snapshot:{ex}",
                'status_code': 200,
                'duration_ms': latency_ms,
                'parsed_price': snap_price,
                'asOf': snap_as_of,
                'state': 'LIVE',
                'currency': 'USDT',
                'success': True
            })
            return CryptoPriceResult(
                price=snap_price,
                asOf=int(snap_as_of) if snap_as_of else None,
                source=meta.name,
                status='OK'
            )
        else:
            traces.append({
                'source': source_label,
                'url': f"snapshot:{ex}",
                'status_code': 503 if snap_status in ('STALE_PRICE', 'RATE_LIMITED', 'PROVIDER_BLOCKED') else 404,
                'error': f"{snap_status}: price not available in snapshot for {ex}:{native_sym}",
                'duration_ms': latency_ms,
            })
            return CryptoPriceResult(
                price=None,
                asOf=int(snap_as_of) if snap_as_of else None,
                source=meta.name,
                status=snap_status
            )

    # 3. Single-target isolated fetch per exchange (R1 / R11 fallback when engine flag is OFF)
    if ex == 'binance':
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={native_sym}"
        p = await _try_fetch(
            source_label,
            url,
            lambda d: {'price': float(d.get('price')), 'state': 'LIVE', 'currency': 'USDT'}
            if isinstance(d, dict) and d.get('price') else None
        )
    elif ex == 'mexc':
        url = f"https://api.mexc.com/api/v3/ticker/price?symbol={native_sym}"
        p = await _try_fetch(
            source_label,
            url,
            lambda d: {'price': float(d.get('price')), 'state': 'LIVE', 'currency': 'USDT'}
            if isinstance(d, dict) and d.get('price') else None
        )
    elif ex == 'kucoin':
        url = f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={native_sym}"
        p = await _try_fetch(
            source_label,
            url,
            lambda d: {'price': float(d.get('data', {}).get('price')), 'state': 'LIVE', 'currency': 'USDT'}
            if isinstance(d, dict) and d.get('data', {}).get('price') else None
        )
    elif ex in ('gateio', 'gate'):
        url = f"https://api.gateio.ws/api/v4/spot/tickers?currency_pair={native_sym}"
        p = await _try_fetch(
            source_label,
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
        p = await _try_fetch(source_label, url, _extract_lbank)
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
        p = await _try_fetch(source_label, url, _extract_okx)
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
        p = await _try_fetch(source_label, url, _extract_bybit)
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
        p = await _try_fetch(source_label, url, _extract_bitget)
    elif ex == 'kraken':
        url = f"https://api.kraken.com/0/public/Ticker?pair={native_sym}"
        def _extract_kraken(d):
            if isinstance(d, dict) and not d.get('error') and d.get('result'):
                for _, t in d['result'].items():
                    c = t.get('c', [])
                    if c and len(c) > 0 and float(c[0]) > 0:
                        return {'price': float(c[0]), 'state': 'LIVE', 'currency': 'USDT'}
            return None
        p = await _try_fetch(source_label, url, _extract_kraken)
    else:
        p = None

    # 4. Check result: price must be valid positive float, otherwise NO_PRICE
    if p is not None and float(p) > 0:
        return CryptoPriceResult(
            price=float(p),
            asOf=now_ts,
            source=meta.name,
            status='OK',
            currency='USDT'
        )

    # 5. Failed: Strictly terminate with NO_PRICE. ZERO cross-exchange fallback!
    traces.append({
        'source': source_label,
        'symbol': native_sym,
        'error': f"NO_PRICE: No price returned from {meta.name} for {native_sym}"
    })
    return CryptoPriceResult(
        price=None,
        asOf=None,
        source=meta.name,
        status='NO_PRICE'
    )
