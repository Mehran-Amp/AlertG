import time
import asyncio
from typing import Optional, List, Dict, Any, Tuple
import httpx
from app.config import (
    APP_VERSION, KILL_SWITCH_PROVIDERS, KILL_SWITCH_CATEGORIES, KILL_SWITCHES
)
from app.state import BULK_MARKET_RESPONSE_CACHE, FAILED_SYMBOLS
from app.markets.common import normalize_symbol
from app.engine.categories import resolve_symbol_category
from app.markets.iran import fetch_iran
from app.markets.global_stocks import fetch_global_stocks
from app.markets.crypto import fetch_crypto
from app.markets.limiter import acquire_provider_slot, record_provider_metric

def _map_source_to_provider_key(source_name: str, url: str) -> str:
    s = source_name.lower()
    u = url.lower()
    if 'yahoo' in s or 'yahoo' in u:
        return 'yahoo'
    if 'finnhub' in s or 'finnhub' in u:
        return 'finnhub'
    if 'twelve' in s or 'twelvedata' in u:
        return 'twelvedata'
    if 'fred' in s or 'stlouisfed' in u:
        return 'fred'
    if 'nobitex' in s or 'nobitex' in u:
        return 'nobitex'
    if 'bonbast' in s or 'bonbast' in u:
        return 'bonbast'
    if 'aegkala' in s or 'bridge' in s or 'market-bridge' in u:
        return 'iran_bridge'
    if 'binance' in s or 'binance' in u:
        return 'binance'
    if any(c in u for c in ['mexc', 'kucoin', 'gateio', 'coinex', 'bitstamp', 'dexscreener', 'geckoterminal']):
        return 'crypto_global'
    return 'default'

async def fetch_price_with_trace(
    client: httpx.AsyncClient,
    exchange: str,
    symbol: str,
    collect_all_traces: bool = False
) -> Tuple[Optional[float], List[Dict[str, Any]]]:
    """
    Unified multi-source price engine with Bulk Ticker Cache & Fast Parallel Fallback.
    - Fast Mode (collect_all_traces=False): Returns on first valid price immediately.
    - Diagnostic Mode (collect_all_traces=True): Tests all sources, collecting latency & trace stats.
    - Token Bucket Rate Limiting per provider.
    - Metric counters for requests, errors, 429 rate limits.
    """
    ex = (exchange or '').lower()
    sym_clean = normalize_symbol(symbol)
    category = resolve_symbol_category(exchange, symbol)
    from app.markets.kill_switch import is_category_killed, is_provider_killed

    traces: List[Dict[str, Any]] = []
    final_price: Optional[float] = None
    final_meta: Dict[str, Any] = {}

    if is_category_killed(category):
        traces.append({
            'source': 'kill_switch',
            'url': '',
            'status_code': 503,
            'latency_ms': 0.0,
            'error': f"Category '{category}' is disabled by kill switch",
            'success': False
        })
        return None, traces

    # Category kill switch check from env
    if category.lower() in KILL_SWITCH_CATEGORIES or category.lower() in KILL_SWITCHES:
        traces.append({
            'source': 'kill_switch',
            'url': f'{ex}:{sym_clean}',
            'status_code': 503,
            'latency_ms': 0.1,
            'error': f'Category {category} is disabled by kill switch',
            'success': False
        })
        return None, traces

    # Helper function for tracing with Bulk Response Caching, Rate Limiting and metadata extraction
    async def _try_fetch(source_name: str, url: str, extractor_func, headers=None, timeout_sec: float = 3.5) -> Optional[float]:
        nonlocal final_price, final_meta
        prov_key = _map_source_to_provider_key(source_name, url)

        # Provider kill switch check from env
        if prov_key in KILL_SWITCH_PROVIDERS or prov_key in KILL_SWITCHES:
            traces.append({
                'source': source_name,
                'url': url,
                'status_code': 503,
                'latency_ms': 0.1,
                'error': f'Provider {prov_key} is disabled by kill switch',
                'success': False
            })
            return None

        t0 = time.time()
        now = time.time()

        # Check Bulk Response Cache (3 second TTL for full-market endpoints)
        cached_bulk = BULK_MARKET_RESPONSE_CACHE.get(url)
        if cached_bulk and (now - cached_bulk[1]) < 3.0:
            try:
                raw_extracted = extractor_func(cached_bulk[0])
                if raw_extracted is not None:
                    if isinstance(raw_extracted, dict):
                        val = float(raw_extracted.get('price', 0))
                        item_meta = {k: v for k, v in raw_extracted.items() if k != 'price'}
                    else:
                        val = float(raw_extracted)
                        item_meta = {}
                    if val > 0:
                        item_meta['source'] = source_name
                        traces.append({
                            'source': source_name,
                            'url': url,
                            'status_code': 200,
                            'latency_ms': 0.1,
                            'parsed_price': val,
                            'asOf': item_meta.get('asOf', int(now)),
                            'state': item_meta.get('state', 'LIVE'),
                            'currency': item_meta.get('currency', 'USD'),
                            'success': True,
                            'cached_bulk': True
                        })
                        if final_price is None:
                            final_price = val
                            final_meta = item_meta
                        return val
            except Exception:
                pass

        # Apply Token Bucket Rate Limiter before network call
        prov_key = _map_source_to_provider_key(source_name, url)
        if is_provider_killed(prov_key):
            traces.append({'source': source_name, 'url': url, 'status_code': 503, 'latency_ms': 0.0, 'error': f"Provider '{prov_key}' is disabled by kill switch", 'success': False})
            return None
        await acquire_provider_slot(prov_key, wait=True)

        req_headers = {'User-Agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) SignalAlert/{APP_VERSION}'}
        if headers:
            req_headers.update(headers)
        try:
            res = await client.get(url, headers=req_headers, timeout=timeout_sec)
            latency = round((time.time() - t0) * 1000, 2)
            if res.status_code == 200:
                record_provider_metric(prov_key, "success")
                data = res.json()
                BULK_MARKET_RESPONSE_CACHE[url] = (data, now)
                raw_extracted = extractor_func(data)
                if raw_extracted is not None:
                    if isinstance(raw_extracted, dict):
                        raw_p = raw_extracted.get('price')
                        val = float(raw_p) if (raw_p is not None and str(raw_p).strip() != '') else None
                        item_meta = {k: v for k, v in raw_extracted.items() if k != 'price'}
                    else:
                        val = float(raw_extracted) if raw_extracted is not None else None
                        item_meta = {}
                    if val is not None and val > 0:
                        item_meta['source'] = source_name
                        traces.append({
                            'source': source_name,
                            'url': url,
                            'status_code': 200,
                            'latency_ms': latency,
                            'parsed_price': val,
                            'asOf': item_meta.get('asOf', int(now)),
                            'state': item_meta.get('state', 'LIVE'),
                            'currency': item_meta.get('currency', 'USD'),
                            'success': True
                        })
                        if final_price is None:
                            final_price = val
                            final_meta = item_meta
                        return val
                    elif isinstance(raw_extracted, dict) and raw_extracted.get('state') in ['no_data', 'no_trade_today', 'closed']:
                        item_meta['source'] = source_name
                        traces.append({
                            'source': source_name,
                            'url': url,
                            'status_code': 200,
                            'latency_ms': latency,
                            'parsed_price': None,
                            'asOf': item_meta.get('asOf', int(now)),
                            'state': item_meta.get('state', 'no_data'),
                            'currency': item_meta.get('currency', 'TMN'),
                            'success': True
                        })
                        if final_meta is None or not final_meta:
                            final_meta = item_meta
                        return None
                    else:
                        traces.append({'source': source_name, 'url': url, 'status_code': 200, 'latency_ms': latency, 'error': 'Symbol not found or 0 price', 'success': False})
                else:
                    traces.append({'source': source_name, 'url': url, 'status_code': 200, 'latency_ms': latency, 'error': 'Extractor returned null', 'success': False})
            elif res.status_code == 429:
                record_provider_metric(prov_key, "rate_limits_429")
                record_provider_metric(prov_key, "errors")
                traces.append({'source': source_name, 'url': url, 'status_code': 429, 'latency_ms': latency, 'error': 'Rate limited (HTTP 429)', 'success': False})
                await asyncio.sleep(0.15)
            else:
                record_provider_metric(prov_key, "errors")
                traces.append({'source': source_name, 'url': url, 'status_code': res.status_code, 'latency_ms': latency, 'error': f'HTTP {res.status_code}', 'success': False})
        except Exception as e:
            record_provider_metric(prov_key, "errors")
            traces.append({'source': source_name, 'url': url, 'status_code': 0, 'latency_ms': round((time.time() - t0) * 1000, 2), 'error': str(e), 'success': False})
        return None

    # 1. IRANIAN EXCHANGES & TOMAN MARKETS
    is_iranian = ex in ['tabdeal', 'nobitex', 'wallex', 'bitpin', 'tetherland', 'abantether', 'ramzinex', 'bitbarg', 'sarmayex', 'exir', 'iran_market', 'bonbast'] or \
                 sym_clean.endswith('TMN') or sym_clean.endswith('IRT') or sym_clean.endswith('RLS') or \
                 sym_clean.startswith('USDT_') or sym_clean.startswith('GOLD_')

    if is_iranian:
        p = await fetch_iran(client, exchange, symbol, _try_fetch, traces, collect_all_traces)
        if p and not collect_all_traces:
            return p, traces

    # 2. GLOBAL MACRO / FOREX / US BONDS / STOCKS (Yahoo Finance)
    elif ex in ['global_stocks', 'stocks', 'macro', 'forex', 'bonds', 'wallstreet']:
        p = await fetch_global_stocks(client, exchange, symbol, _try_fetch, traces, collect_all_traces)
        if p and not collect_all_traces:
            return p, traces

    # 3. GLOBAL CRYPTO / DEX
    else:
        p = await fetch_crypto(client, exchange, symbol, _try_fetch, traces, collect_all_traces)
        if p and not collect_all_traces:
            return p, traces

    sym_key = f"{ex}:{sym_clean}"
    if final_price is not None and final_price > 0:
        FAILED_SYMBOLS.pop(sym_key, None)
    else:
        last_err = "No price returned"
        for tr in reversed(traces):
            if tr.get('error'):
                last_err = tr['error']
                break
        curr_fail = FAILED_SYMBOLS.get(sym_key, {"symbol": symbol, "exchange": exchange, "attempts": 0})
        curr_fail["attempts"] = curr_fail.get("attempts", 0) + 1
        curr_fail["error"] = last_err
        curr_fail["failed_at"] = time.time()
        curr_fail["category"] = category
        FAILED_SYMBOLS[sym_key] = curr_fail

    return final_price, traces
