import time
import re
import json
import asyncio
import logging
from fastapi import APIRouter, HTTPException

from app.config import CACHE_TTL_IRAN, IRAN_BRIDGE_URL, IRAN_BRIDGE_TOKEN
from app.security import API_DEP, _validate_market_args
from app.state import PRICE_CACHE, IRAN_MARKET_CACHE
from app.markets.base import normalize_symbol
from app.engine.checker import get_cached_price
from app.engine.calendar import get_all_markets_status
import app.state as state

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/api/price/{exchange}/{symbol}", dependencies=API_DEP)
@router.get("/price/{exchange}/{symbol}", dependencies=API_DEP)
async def get_live_price(exchange: str, symbol: str):
    client = state.http_client
    if client is None:
        raise HTTPException(status_code=503, detail="Server client initializing...")
    _validate_market_args(exchange, symbol)
    price = await get_cached_price(client, exchange, symbol)
    cache_key = f"{exchange.lower()}:{normalize_symbol(symbol)}"
    cached_entry = PRICE_CACHE.get(cache_key)
    meta = cached_entry[2] if (cached_entry and len(cached_entry) > 2 and isinstance(cached_entry[2], dict)) else {}

    if (price is not None and price > 0) or meta.get('state') in ['no_data', 'no_trade_today', 'closed']:
        res = {
            "status": "ok",
            "exchange": exchange,
            "symbol": symbol,
            "price": price if (price is not None and price > 0) else None,
            "source": meta.get("source", "Market API"),
            "asOf": meta.get("asOf", int(time.time())),
            "state": meta.get("state", "LIVE"),
            "currency": meta.get("currency", "TMN" if exchange in ['iran_market', 'tse'] else "USD"),
            "timestamp": time.time()
        }
        for key in ['state_fa', 'market_open', 'carried_over', 'alert_eligible', 'category', 'ticker', 'name', 'change_pct', 'prev_close', 'high', 'low', 'volume']:
            if key in meta:
                res[key] = meta[key]
        return res
    raise HTTPException(status_code=502, detail="Unable to fetch live price from market sources.")

@router.get("/api/bonbast")
@router.get("/bonbast")
async def get_bonbast_live_data():
    """Returns real-time free market currency, gold, and coin rates directly from Bonbast.com (Primary Reference)"""
    now_bb = time.time()
    cached = IRAN_MARKET_CACHE.get('__bonbast_bulk__')
    if cached and (now_bb - cached[1]) < CACHE_TTL_IRAN:
        return {"status": "ok", "source": "bonbast.com (cached)", **cached[2]}

    loop = asyncio.get_event_loop()
    def _fetch_bb_sync():
        import urllib.request, urllib.parse, http.cookiejar, json
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        req1 = urllib.request.Request('https://bonbast.com/', headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })
        with opener.open(req1, timeout=6) as r1:
            html = r1.read().decode('utf-8', errors='ignore')
        m = re.search(r'param:\s*[\'"]([^\'"]+)[\'"]', html)
        if m:
            data_bytes = urllib.parse.urlencode({'param': m.group(1)}).encode('utf-8')
            req2 = urllib.request.Request('https://bonbast.com/json', data=data_bytes, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://bonbast.com/',
                'Origin': 'https://bonbast.com',
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            })
            with opener.open(req2, timeout=6) as r2:
                parsed = json.loads(r2.read().decode('utf-8'))
                if isinstance(parsed, dict) and ('usd1' in parsed or 'mithqal' in parsed or 'gol18' in parsed):
                    return parsed
        return None

    try:
        data = await loop.run_in_executor(None, _fetch_bb_sync)
        if data:
            IRAN_MARKET_CACHE['__bonbast_bulk__'] = (0.0, time.time(), data)
            return {"status": "ok", "source": "bonbast.com (live)", **data}
        if cached:
            return {"status": "ok", "source": "bonbast.com (stale-fallback)", **cached[2]}
    except Exception as e:
        logger.warning(f"Bonbast endpoint error: {e}")
        if cached:
            return {"status": "ok", "source": "bonbast.com (stale-fallback)", **cached[2]}
    raise HTTPException(status_code=502, detail="Failed to fetch live rates from Bonbast")

@router.get("/api/markets/status", dependencies=API_DEP)
@router.get("/markets/status", dependencies=API_DEP)
async def get_markets_status():
    """Returns real-time status of markets (TSE open/closed schedule, next_open, crypto, US, Forex, Commodities) along with symbol states"""
    calendar_status = get_all_markets_status()
    cached_overview = IRAN_MARKET_CACHE.get('__markets_overview__')
    if cached_overview and len(cached_overview) > 2 and isinstance(cached_overview[2], dict) and (time.time() - cached_overview[1]) < CACHE_TTL_IRAN:
        ov = cached_overview[2]
        cached_markets = ov.get("markets") or {}
        merged_markets = {**calendar_status, **cached_markets}
        return {
            "status": "ok",
            "cached": True,
            "markets": merged_markets,
            "state_counts": ov.get("state_counts", {}),
            "symbols_count": ov.get("symbols_count", 0),
            "symbols_with_price": ov.get("symbols_with_price", 0),
            "items": ov.get("items", {})
        }

    cached_markets = IRAN_MARKET_CACHE.get('__markets_status__')
    if state.http_client and IRAN_BRIDGE_URL:
        try:
            headers = {'Authorization': f'Bearer {IRAN_BRIDGE_TOKEN}'}
            resp = await state.http_client.get(IRAN_BRIDGE_URL, headers=headers, timeout=30.0)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    markets = data.get('markets') or {}
                    items = data.get('data') or {}
                    state_counts = data.get('state_counts') or {}
                    symbols_count = data.get('symbols_count') or len(items)
                    symbols_with_price = data.get('symbols_with_price') or len([v for v in items.values() if isinstance(v, dict) and v.get('price') is not None])

                    merged_markets = {**calendar_status, **markets}
                    IRAN_MARKET_CACHE['__markets_status__'] = (0.0, time.time(), merged_markets)
                    IRAN_MARKET_CACHE['__markets_overview__'] = (0.0, time.time(), {
                        "markets": merged_markets,
                        "state_counts": state_counts,
                        "symbols_count": symbols_count,
                        "symbols_with_price": symbols_with_price,
                        "items": items
                    })

                    # Warm up PRICE_CACHE for all symbols from bridge
                    now = time.time()
                    for sym_name, item_dict in items.items():
                        if isinstance(item_dict, dict):
                            p = float(item_dict.get('price')) if item_dict.get('price') is not None else None
                            PRICE_CACHE[f"iran_market:{sym_name.lower()}"] = (p, now, item_dict)

                    return {
                        "status": "ok",
                        "cached": False,
                        "markets": merged_markets,
                        "state_counts": state_counts,
                        "symbols_count": symbols_count,
                        "symbols_with_price": symbols_with_price,
                        "items": items,
                        "tse_fresh_count": data.get('tse_fresh_count', 0),
                        "tse_carried_count": data.get('tse_carried_count', 0)
                    }
        except Exception as e:
            logger.warning(f"Error fetching market status from bridge: {e}")

    # Fallback status if bridge not immediately reachable
    prev_markets = cached_markets[2] if (cached_markets and len(cached_markets) > 2 and isinstance(cached_markets[2], dict)) else {}
    fallback_markets = {**calendar_status, **prev_markets}
    return {
        "status": "ok",
        "cached": True,
        "markets": fallback_markets,
        "state_counts": {},
        "symbols_count": 0,
        "symbols_with_price": 0,
        "items": {}
    }
