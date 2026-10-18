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

    # 0. Iran High-Speed Bridge (aegkala.com Host in Iran for domestic market & special tokens)
    if IRAN_BRIDGE_URL and (ex in ['iran_market', 'bridge', 'tse', 'bonbast'] or sym_clean.startswith('USDT_') or sym_clean.startswith('GOLD_') or sym_clean.startswith('BTC_') or sym_clean.startswith('ETH_') or sym_clean in TSETMC_INDEX_MAP or sym_clean in TSETMC_INSTRUMENTS_MAP):
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

    # 0-b. Specialized Exchange Tethers & Digital Gold routing
    if sym_clean == 'USDT_TETHERLAND':
        def _extract_tetherland_direct(data):
            if isinstance(data, dict):
                usdt_info = data.get('data', {}).get('currencies', {}).get('USDT', {})
                p = usdt_info.get('price') or usdt_info.get('last_price')
                if p and float(p) > 0:
                    return {'price': float(p), 'state': 'LIVE', 'currency': 'TMN', 'source': 'تترلند (Tetherland)'}
            return None
        p = await _try_fetch('Tetherland API', 'https://api.tetherland.com/currencies', _extract_tetherland_direct)
        if p and not collect_all_traces: return p

    if sym_clean in ['USDT_WALLEX', 'GOLD_WALLEX']:
        def _extract_wallex_direct(data):
            if isinstance(data, dict):
                sym_target = 'PAXGTMN' if sym_clean == 'GOLD_WALLEX' else 'USDTTMN'
                symbols = data.get('result', {}).get('symbols', {})
                if sym_target in symbols:
                    p = symbols[sym_target].get('stats', {}).get('lastPrice')
                    if p and float(p) > 0:
                        return {'price': float(p), 'state': 'LIVE', 'currency': 'TMN', 'source': 'والکس (Wallex)'}
            return None
        p = await _try_fetch('Wallex API', 'https://api.wallex.ir/v1/markets', _extract_wallex_direct)
        if p and not collect_all_traces: return p

    if sym_clean in ['USDT_NOBITEX', 'GOLD_NOBITEX']:
        def _extract_nobitex_direct(data):
            if isinstance(data, dict):
                stats = data.get('stats', {})
                pair_k = 'pm-irt' if sym_clean == 'GOLD_NOBITEX' else 'usdt-irt'
                item = stats.get(pair_k)
                if not item:
                    pair_k = 'pm-rls' if sym_clean == 'GOLD_NOBITEX' else 'usdt-rls'
                    item = stats.get(pair_k)
                if item and item.get('latest'):
                    val = float(item['latest'])
                    if 'rls' in pair_k or 'irt' in pair_k or val > 1000000:
                        val = val / 10.0
                    while sym_clean in ['USDT_NOBITEX', 'USDT'] and val > 1000000:
                        val = val / 10.0
                    return {'price': val, 'state': 'LIVE', 'currency': 'TMN', 'source': 'نوبیتکس (Nobitex)'}
            return None
        p = await _try_fetch('Nobitex Stats API', 'https://apiv2.nobitex.ir/market/stats', _extract_nobitex_direct)
        if p and not collect_all_traces: return p

    nobitex_sym = 'USDTIRT' if sym_clean in ['USDTTMN', 'USDTIRT', 'USDT'] else (sym_clean[:-3] + 'IRT' if sym_clean.endswith('TMN') else sym_clean)
    matching_keys = [sym_clean, nobitex_sym]
    if sym_clean in ['USDT', 'USDTTMN', 'USDTIRT']:
        matching_keys.extend(['USDTTMN', 'USDTIRT', 'USDT_IRT', 'USDT_TMN'])

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

    # 1a. Nobitex Market Stats API (Official aggregated prices for all markets)
    def _extract_nobitex_stats(data):
        if isinstance(data, dict):
            stats = data.get('stats', {})
            search_targets = [
                sym_clean.lower(),
                nobitex_sym.lower(),
                f"{sym_clean.replace('IRT', '').replace('TMN', '').lower()}-rls",
                f"{sym_clean.replace('IRT', '').replace('TMN', '').lower()}-irt",
                f"{sym_clean.replace('IRT', '').replace('TMN', '').lower()}-usdt"
            ]
            if sym_clean in ['USDT', 'USDTTMN', 'USDTIRT']:
                search_targets = ['usdt-rls', 'usdt-irt']

            for tgt in search_targets:
                if tgt in stats:
                    item = stats[tgt]
                    latest_raw = item.get('latest')
                    if latest_raw and float(latest_raw) > 0:
                        raw_val = float(latest_raw)
                        is_domestic = tgt.endswith('-rls') or tgt.endswith('rls') or tgt.endswith('-irt') or tgt.endswith('irt')
                        final_val = (raw_val / 10.0) if is_domestic else raw_val
                        while sym_clean in ['USDT', 'USDTTMN', 'USDTIRT'] and final_val > 1000000:
                            final_val = final_val / 10.0
                        return {
                            'price': final_val,
                            'state': 'LIVE',
                            'currency': 'TMN' if is_domestic else 'USDT'
                        }
        return None

    p = await _try_fetch('Nobitex Stats API', 'https://apiv2.nobitex.ir/market/stats', _extract_nobitex_stats)
    if p and not collect_all_traces: return p

    # 1b. Nobitex Orderbook (Using lastTradePrice, with bids fallback)
    for domain, label in [('apiv2.nobitex.ir', 'Nobitex Global Net'), ('api.nobitex.ir', 'Nobitex Local IR')]:
        def _extract_nobitex_ob(data):
            if isinstance(data, dict):
                p_val = data.get('lastTradePrice')
                if not p_val and 'bids' in data and len(data['bids']) > 0:
                    p_val = data['bids'][0][0]
                if p_val and float(p_val) > 0:
                    raw_val = float(p_val)
                    is_domestic_rial = nobitex_sym.upper().endswith('RLS') or nobitex_sym.upper().endswith('IRT') or 'TMN' in nobitex_sym.upper()
                    final_val = (raw_val / 10.0) if is_domestic_rial else raw_val
                    while sym_clean in ['USDT', 'USDTTMN', 'USDTIRT'] and final_val > 1000000:
                        final_val = final_val / 10.0
                    return {
                        'price': final_val,
                        'state': 'LIVE',
                        'currency': 'TMN' if is_domestic_rial else 'USDT'
                    }
            return None
        p = await _try_fetch(f'{label} Orderbook', f'https://{domain}/v2/orderbook/{nobitex_sym}', _extract_nobitex_ob)
        if p and not collect_all_traces: return p

    # 1c. Tabdeal
    tabdeal_sym = 'USDTIRT' if sym_clean in ['USDTTMN', 'USDTIRT', 'USDT'] else (sym_clean[:-3] + 'IRT' if sym_clean.endswith('TMN') else sym_clean)
    def _extract_tabdeal(data):
        if isinstance(data, dict):
            bids = data.get('bids', [])
            if bids and len(bids) > 0:
                val = float(bids[0][0])
                if val > 0:
                    return {'price': val, 'state': 'LIVE', 'currency': 'TMN'}
        return None

    p = await _try_fetch('Tabdeal Depth API', f'https://api1.tabdeal.org/r/api/v1/depth?symbol={tabdeal_sym}', _extract_tabdeal)
    if p and not collect_all_traces: return p

    # 1d. Bitpin
    def _extract_bitpin(data):
        if isinstance(data, dict):
            for m in data.get('results', []):
                code = m.get('code', '')
                if normalize_symbol(code) in matching_keys:
                    raw_val = float(m.get('price', 0))
                    if raw_val > 0:
                        is_rls = code.upper().endswith('RLS') or code.upper().endswith('IRR')
                        final_val = (raw_val / 10.0) if is_rls else raw_val
                        return {'price': final_val, 'state': 'LIVE', 'currency': 'TMN'}
        return None

    p = await _try_fetch('Bitpin Markets API', 'https://api.bitpin.org/v1/mkt/markets/', _extract_bitpin)
    if p and not collect_all_traces: return p

    # 1e. Wallex
    def _extract_wallex(data):
        if isinstance(data, dict):
            symbols = data.get('result', {}).get('symbols', {})
            for k, v in symbols.items():
                if normalize_symbol(k) == sym_clean:
                    p = v.get('stats', {}).get('lastPrice')
                    if p and float(p) > 0:
                        return {'price': float(p), 'state': 'LIVE', 'currency': 'TMN' if 'TMN' in k else 'USDT'}
        return None

    p = await _try_fetch('Wallex Markets API', 'https://api.wallex.ir/v1/markets', _extract_wallex)
    if p and not collect_all_traces: return p

    # 1f. Tetherland (For USDT/TMN direct)
    if sym_clean in ['USDTTMN', 'USDTIRT', 'USDT']:
        def _extract_tetherland(data):
            if isinstance(data, dict):
                usdt_info = data.get('data', {}).get('currencies', {}).get('USDT', {})
                p = usdt_info.get('price') or usdt_info.get('last_price')
                if p and float(p) > 0:
                    return {'price': float(p), 'state': 'LIVE', 'currency': 'TMN'}
            return None

        p = await _try_fetch('Tetherland API', 'https://api.tetherland.com/currencies', _extract_tetherland)
        if p and not collect_all_traces: return p

    return None
