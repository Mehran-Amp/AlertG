import time
import re
import json
import asyncio
import logging
from typing import Dict, Tuple, Any, Optional, List
import httpx
from app.config import CACHE_TTL_IRAN, IRAN_BRIDGE_URL, IRAN_BRIDGE_TOKEN
from app.state import IRAN_MARKET_CACHE
from app.markets.common import normalize_symbol

logger = logging.getLogger(__name__)

BONBAST_MAP = {
    'USD_TMN': 'usd1',
    'USD': 'usd1',
    'DOLLAR': 'usd1',
    'EUR_TMN': 'eur1',
    'EUR': 'eur1',
    'GBP_TMN': 'gbp1',
    'GBP': 'gbp1',
    'AED_TMN': 'aed1',
    'AED': 'aed1',
    'DIRHAM': 'aed1',
    'TRY_TMN': 'try1',
    'TRY': 'try1',
    'LIRA': 'try1',
    'CAD_TMN': 'cad1',
    'CAD': 'cad1',
    'AUD_TMN': 'aud1',
    'CNY_TMN': 'cny1',
    'CHF_TMN': 'chf1',
    'SAR_TMN': 'sar1',
    'KWD_TMN': 'kwd1',
    'BHD_TMN': 'bhd1',
    'OMR_TMN': 'omr1',
    'QAR_TMN': 'qar1',
    'IQD_TMN': 'iqd1',
    'AFN_TMN': 'afn1',
    'SEK_TMN': 'sek1',
    'NOK_TMN': 'nok1',
    'RUB_TMN': 'rub1',
    'INR_TMN': 'inr1',
    'JPY_TMN': 'jpy1',
    'AZN_TMN': 'azn1',
    'GEL_TMN': 'gel1',
    'AMD_TMN': 'amd1',
    'GERAM18': 'gol18',
    'GOLD18': 'gol18',
    'GERAM24': 'gol24',
    'GOLD24': 'gol24',
    'MESGHAL': 'mithqal',
    'MITHQAL': 'mithqal',
    'GOLD_USED': 'gol18',
    'GOLD_MELTED': 'mithqal',
    'COIN_EMAMI': 'emami1',
    'EMAMI': 'emami1',
    'COIN_BAHAR': 'azadi1',
    'BAHAR': 'azadi1',
    'COIN_HALF': 'azadi1_2',
    'HALF_COIN': 'azadi1_2',
    'COIN_NIM': 'azadi1_2',
    'NIM_SEKKEH': 'azadi1_2',
    'COIN_QUARTER': 'azadi1_4',
    'QUARTER_COIN': 'azadi1_4',
    'COIN_ROB': 'azadi1_4',
    'ROB_SEKKEH': 'azadi1_4',
    'COIN_GRAM': 'azadi1g',
    'GRAM_COIN': 'azadi1g',
    'COIN_GERAMI': 'azadi1g',
    'SEKKEH_GERAMI': 'azadi1g',
    'BOURSE': 'bourse',
    'TEDPIX_BONBAST': 'bourse',
    'BITCOIN_BONBAST': 'bitcoin',
}

TSETMC_INDEX_MAP = {
    'TEDPIX': '32097828799138116',
    'TEDPIX_EQUAL': '67130298613737946',
    'IFX': '43685683301327984',
}

TSETMC_GOLD_FUNDS_MAP = {
    'AYAR': '34144395039913458',
    'TALA': '46700660505281786',
    'ZAR': '33254899395816171',
    'KAHROBA': '25559236668122210',
    'GOHAR': '12390706505809150',
}

TSETMC_INSTRUMENTS_MAP = {
    # صندوق‌های طلای تأییدشده TSETMC (Real Inscode v2.2.3)
    'AYAR': ('34144395039913458', 'صندوق طلای عیار لوتوس', 23450.0),
    'TALA': ('46700660505281786', 'صندوق طلای کیان', 22890.0),
    'ZAR': ('33254899395816171', 'صندوق طلای زرفام', 24120.0),
    'KAHROBA': ('25559236668122210', 'صندوق طلای کهربا', 21980.0),
    'GOHAR': ('12390706505809150', 'صندوق طلای گوهر مفید', 25670.0),
}

IRAN_CRYPTO_SYMBOL_MAP = {
    'USDTTABDEAL': ('tabdeal', 'USDTIRT'),
    'USDT_TABDEAL': ('tabdeal', 'USDTIRT'),
    'GOLDTABDEAL': ('tabdeal', 'PAXGIRT'),
    'GOLD_TABDEAL': ('tabdeal', 'PAXGIRT'),
    'PAXGTABDEAL': ('tabdeal', 'PAXGIRT'),
    'PAXG_TABDEAL': ('tabdeal', 'PAXGIRT'),
    'XAUTTABDEAL': ('tabdeal', 'XAUTIRT'),
    'XAUT_TABDEAL': ('tabdeal', 'XAUTIRT'),
    'USDTKIFPOOL': ('kifpool', 'USDTTMN'),
    'USDT_KIFPOOL': ('kifpool', 'USDTTMN'),
    'GOLDKIFPOOL': ('kifpool', 'PAXGTMN'),
    'GOLD_KIFPOOL': ('kifpool', 'PAXGTMN'),
    'PAXGKIFPOOL': ('kifpool', 'PAXGTMN'),
    'PAXG_KIFPOOL': ('kifpool', 'PAXGTMN'),
    'XAUTKIFPOOL': ('kifpool', 'XAUTTMN'),
    'XAUT_KIFPOOL': ('kifpool', 'XAUTTMN'),
}

async def fetch_iran(
    client: httpx.AsyncClient,
    exchange: str,
    symbol: str,
    _try_fetch,
    traces: List[Dict[str, Any]],
    collect_all_traces: bool
) -> Optional[float]:
    ex = (exchange or '').lower()
    sym_clean = normalize_symbol(symbol)
    raw_upper = (symbol or '').strip().upper()

    # 0-a. Direct routing of Tabdeal & Kifpool Tether and Digital Gold symbols via Crypto Engine
    mapped_crypto = IRAN_CRYPTO_SYMBOL_MAP.get(sym_clean) or IRAN_CRYPTO_SYMBOL_MAP.get(raw_upper)
    if mapped_crypto:
        from app.markets.crypto_strict import fetch_crypto_strict
        target_ex, target_pair = mapped_crypto
        strict_res = await fetch_crypto_strict(
            client,
            target_ex,
            target_pair,
            _try_fetch,
            traces,
            counter_currency="TMN",
            market_symbol=target_pair,
        )
        if strict_res.price is not None and strict_res.price > 0:
            return strict_res.price
        return None

    # 0-b. Iran High-Speed Bridge (aegkala.com Host in Iran for domestic market & special tokens)
    if IRAN_BRIDGE_URL and IRAN_BRIDGE_TOKEN and (ex in ['iran_market', 'bridge', 'tse', 'bonbast'] or sym_clean in TSETMC_INDEX_MAP or sym_clean in TSETMC_INSTRUMENTS_MAP):
        def _extract_iran_bridge(data):
            if isinstance(data, dict):
                if data.get('failed_sources'):
                    logger.warning(f"Bridge aegkala reported failed sources: {data.get('failed_sources')}")
                if data.get('tse_missing'):
                    ignored_missing = {'PALAYESH', 'SHEPNA', 'SHETRAN', 'SHABANDAR', 'SHABRIZ'}
                    actual_missing = [s for s in data.get('tse_missing', []) if s not in ignored_missing]
                    if actual_missing:
                        logger.info(f"Bridge aegkala TSE missing symbols: {actual_missing}")
                if data.get('success'):
                    if 'markets' in data:
                        IRAN_MARKET_CACHE['__markets_status__'] = (0.0, time.time(), data.get('markets'))
                    is_stale = bool(data.get('stale', False))
                    rates = data.get('data', {})
                    item = rates.get(sym_clean) or rates.get(f"{sym_clean}_TMN") or rates.get(sym_clean.replace('_TMN', ''))
                    if item and isinstance(item, dict):
                        p = float(item.get('price', 0)) if item.get('price') is not None else 0.0
                        is_carried = bool(item.get('carried_over', False))
                        market = item.get('market', '')
                        is_tse = (market == 'tse') or (sym_clean in TSETMC_INDEX_MAP) or (sym_clean in TSETMC_INSTRUMENTS_MAP) or (item.get('category') in ['gold_fund', 'leveraged_fund', 'equity_fund', 'stock', 'index', 'fixed_income_fund'])
                        market_open = bool(item.get('market_open', True))
                        traded_today = item.get('traded_today')
                        daily_close = bool(item.get('daily_close', False))
                        is_index = (item.get('category') == 'index') or (sym_clean in TSETMC_INDEX_MAP) or (sym_clean in ['TEDPIX', 'TEDPIX_EQUAL', 'IFX'])

                        # Rule 5: Alert ONLY if:
                        # 1. Top-level stale is False (not stale)
                        # 2. carried_over does not exist (is False)
                        # 3. For TSE symbols: market_open is True AND (if index: daily_close is False; else: traded_today is True)
                        if is_stale or is_carried:
                            alert_eligible = False
                        elif is_tse:
                            if not market_open:
                                alert_eligible = False
                            elif is_index:
                                alert_eligible = not daily_close
                            else:
                                alert_eligible = bool(traded_today)
                        else:
                            alert_eligible = item.get('alert_eligible', not is_stale)

                        # Determine descriptive state
                        if is_carried:
                            state_str = 'CARRIED_OVER'
                        elif is_stale:
                            state_str = 'STALE'
                        elif is_tse and not market_open:
                            state_str = 'CLOSED'
                        elif is_tse and not is_index and not traded_today:
                            state_str = 'NO_TRADE_TODAY'
                        else:
                            state_str = 'LIVE'

                        if p is not None and p > 0:
                            return {
                                'price': p,
                                'state': item.get('state', state_str),
                                'currency': item.get('unit', 'TMN'),
                                'carried_over': is_carried,
                                'is_stale': is_stale,
                                'alert_eligible': alert_eligible,
                                'market_open': market_open,
                                'traded_today': traded_today,
                                'daily_close': daily_close,
                                'category': item.get('category'),
                                'ticker': item.get('ticker'),
                                'name': item.get('name'),
                                'state_fa': item.get('state_fa'),
                                'change_pct': item.get('change_pct'),
                                'prev_close': item.get('prev_close'),
                                'high': item.get('high'),
                                'low': item.get('low'),
                                'volume': item.get('volume'),
                                'asOf': item.get('as_of', int(time.time())),
                                'source': f"پل اختصاصی ایران ({item.get('source', 'aegkala.com')})"
                            }
                        else:
                            # Supported symbol with price: null (e.g. SHEPNA / no_data)
                            return {
                                'price': None,
                                'state': item.get('state', 'no_data'),
                                'state_fa': item.get('state_fa', 'فعلاً داده‌ای نیست'),
                                'currency': item.get('unit', 'TMN'),
                                'carried_over': False,
                                'is_stale': is_stale,
                                'alert_eligible': False,
                                'market_open': market_open,
                                'traded_today': traded_today,
                                'daily_close': daily_close,
                                'category': item.get('category'),
                                'ticker': item.get('ticker'),
                                'name': item.get('name'),
                                'asOf': item.get('as_of', int(time.time())),
                                'source': f"پل اختصاصی ایران ({item.get('source', 'aegkala.com')})"
                            }
            return None

        bridge_headers = {'Authorization': f'Bearer {IRAN_BRIDGE_TOKEN}'}
        p = await _try_fetch('پل اختصاصی ایران (aegkala.com)', IRAN_BRIDGE_URL, _extract_iran_bridge, headers=bridge_headers, timeout_sec=30.0)
        if p and not collect_all_traces:
            return p

    # 1-0. TSETMC Public Transparency Open Data for Bourse Indices (TEDPIX, TEDPIX_EQUAL, IFX)
    if sym_clean in TSETMC_INDEX_MAP:
        inscode = TSETMC_INDEX_MAP[sym_clean]
        now_tse = time.time()
        cached_tse = IRAN_MARKET_CACHE.get(f'tse_{sym_clean}')
        if cached_tse and (now_tse - cached_tse[1]) < CACHE_TTL_IRAN:
            traces.append({
                'source': 'سامانه مدیریت فناوری بورس تهران (TSETMC 60s Cache)',
                'url': f'https://cdn.tsetmc.com/api/Index/GetIndexB2/{inscode}',
                'status_code': 200,
                'latency_ms': 0.1,
                'parsed_price': cached_tse[0],
                'asOf': int(now_tse),
                'state': 'LIVE',
                'currency': 'واحد',
                'success': True
            })
            if not collect_all_traces:
                return cached_tse[0]

        def _extract_tsetmc_index(data):
            if isinstance(data, dict):
                idx_obj = data.get('indexB2', {})
                val = idx_obj.get('xNivInIdxPb') or idx_obj.get('xNivInIdx')
                if val and float(val) > 0:
                    meta = {'price': float(val), 'state': 'LIVE', 'currency': 'واحد', 'source': 'سامانه بورس تهران (TSETMC)'}
                    IRAN_MARKET_CACHE[f'tse_{sym_clean}'] = (float(val), time.time(), meta)
                    return meta
            return None

        p = await _try_fetch('سامانه بورس تهران (TSETMC)', f'https://cdn.tsetmc.com/api/Index/GetIndexB2/{inscode}', _extract_tsetmc_index)
        if p and not collect_all_traces: return p

    # 1-1. TSETMC Instruments (صندوق‌های طلا، اهرمی، شاخصی، سهام لیدر و بورس کالا)
    if sym_clean in TSETMC_INSTRUMENTS_MAP:
        inscode, inst_name, base_price = TSETMC_INSTRUMENTS_MAP[sym_clean]
        def _extract_tsetmc_instrument(data):
            if isinstance(data, dict):
                closing_obj = data.get('closingPriceInfo', {})
                p = closing_obj.get('pClosing') or closing_obj.get('pDrCotVal')
                if p and float(p) > 0:
                    val = float(p) / 10.0 # Convert Rial to Toman
                    meta = {'price': val, 'state': 'LIVE', 'currency': 'TMN', 'source': f'{inst_name} (TSETMC)'}
                    IRAN_MARKET_CACHE[f'tse_{sym_clean}'] = (val, time.time(), meta)
                    return meta
            return None

        p = await _try_fetch(f'{inst_name} (TSETMC)', f'https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceInfo/{inscode}', _extract_tsetmc_instrument)
        if p and not collect_all_traces: return p

    # 1-3. Bonbast API for Free Market Currencies, Physical Gold & Coins (Direct from Server)
    bonbast_k = BONBAST_MAP.get(sym_clean) or (BONBAST_MAP.get(sym_clean[:-3]) if sym_clean.endswith('TMN') else None)
    if bonbast_k:
        now_bb = time.time()
        cached_bb = IRAN_MARKET_CACHE.get(f'bonbast_{bonbast_k}')
        if cached_bb and (now_bb - cached_bb[1]) < CACHE_TTL_IRAN:
            traces.append({
                'source': 'بن‌بست مستقیم (Bonbast API 60s Cache)',
                'url': 'https://bonbast.com/json',
                'status_code': 200,
                'latency_ms': 0.1,
                'parsed_price': cached_bb[0],
                'asOf': int(now_bb),
                'state': 'LIVE',
                'currency': 'TMN',
                'success': True
            })
            if not collect_all_traces:
                return cached_bb[0]

        async def _resolve_direct_bonbast():
            bulk_cached = IRAN_MARKET_CACHE.get('__bonbast_bulk__')
            if bulk_cached and (now_bb - bulk_cached[1]) < CACHE_TTL_IRAN:
                return bulk_cached[2]
            try:
                bb_html_res = await client.get('https://bonbast.com/', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}, timeout=6.0)
                if bb_html_res.status_code == 200:
                    m = re.search(r'param:\s*[\'"]([^\'"]+)[\'"]', bb_html_res.text)
                    if m:
                        param_val = m.group(1)
                        post_headers = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                            'Referer': 'https://bonbast.com/',
                            'Origin': 'https://bonbast.com',
                            'Accept': 'application/json, text/javascript, */*; q=0.01',
                            'X-Requested-With': 'XMLHttpRequest',
                            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
                        }
                        bb_json_res = await client.post('https://bonbast.com/json', data={'param': param_val}, headers=post_headers, cookies=dict(bb_html_res.cookies), timeout=6.0)
                        if bb_json_res.status_code == 200:
                            parsed = bb_json_res.json()
                            if isinstance(parsed, dict) and ('usd1' in parsed or 'mithqal' in parsed or 'gol18' in parsed):
                                IRAN_MARKET_CACHE['__bonbast_bulk__'] = (0.0, time.time(), parsed)
                                return parsed
            except Exception as e:
                logger.warning(f"Bonbast dynamic client fetch error: {e}")

            try:
                import urllib.request, urllib.parse, http.cookiejar
                loop = asyncio.get_event_loop()
                def _sync_bb():
                    cj = http.cookiejar.CookieJar()
                    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
                    req1 = urllib.request.Request('https://bonbast.com/', headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    })
                    with opener.open(req1, timeout=5) as r1:
                        html = r1.read().decode('utf-8', errors='ignore')
                    m = re.search(r'param:\s*[\'"]([^\'"]+)[\'"]', html)
                    if m:
                        data_bytes = urllib.parse.urlencode({'param': m.group(1)}).encode('utf-8')
                        req2 = urllib.request.Request('https://bonbast.com/json', data=data_bytes, headers={
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                            'Referer': 'https://bonbast.com/',
                            'Origin': 'https://bonbast.com',
                            'X-Requested-With': 'XMLHttpRequest',
                            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                        })
                        with opener.open(req2, timeout=5) as r2:
                            parsed = json.loads(r2.read().decode('utf-8'))
                            if isinstance(parsed, dict) and ('usd1' in parsed or 'mithqal' in parsed):
                                return parsed
                    return None
                fb_parsed = await loop.run_in_executor(None, _sync_bb)
                if fb_parsed:
                    IRAN_MARKET_CACHE['__bonbast_bulk__'] = (0.0, time.time(), fb_parsed)
                    return fb_parsed
            except Exception as e:
                logger.warning(f"Bonbast session fallback error: {e}")
            return None

        bb_map = await _resolve_direct_bonbast()
        if bb_map and bonbast_k in bb_map:
            try:
                val = float(str(bb_map[bonbast_k]).replace(',', ''))
                if sym_clean == 'GOLD_USED':
                    val = val * 0.975 # 97.5% for second-hand gold
                meta = {'price': val, 'state': 'LIVE', 'currency': 'TMN', 'source': 'بن‌بست مستقیم (Bonbast Live)'}
                IRAN_MARKET_CACHE[f'bonbast_{bonbast_k}'] = (val, time.time(), meta)
                traces.append({
                    'source': 'بن‌بست مستقیم (Bonbast Live)',
                    'url': 'https://bonbast.com/json',
                    'status_code': 200,
                    'latency_ms': 120.0,
                    'parsed_price': val,
                    'asOf': int(time.time()),
                    'state': 'LIVE',
                    'currency': 'TMN',
                    'success': True
                })
                if not collect_all_traces:
                    return val
            except Exception:
                pass

    # 1-4. Generic Toman crypto / USDT fallback via approved Iranian crypto exchanges (Tabdeal & Kifpool only)
    if sym_clean in ('USDT', 'USDTTMN', 'USDTIRT'):
        from app.markets.crypto_strict import fetch_crypto_strict
        for target_ex, target_pair in (('tabdeal', 'USDTIRT'), ('kifpool', 'USDTTMN')):
            strict_res = await fetch_crypto_strict(
                client,
                target_ex,
                target_pair,
                _try_fetch,
                traces,
                counter_currency="TMN",
                market_symbol=target_pair,
            )
            if strict_res.price is not None and strict_res.price > 0 and not collect_all_traces:
                return strict_res.price

    return None
