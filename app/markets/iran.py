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
    # 1. Free Market Currencies (both underscored and normalize_symbol stripped keys)
    'USD_TMN': 'usd1', 'USDTMN': 'usd1', 'USD': 'usd1', 'DOLLAR': 'usd1',
    'EUR_TMN': 'eur1', 'EURTMN': 'eur1', 'EUR': 'eur1',
    'GBP_TMN': 'gbp1', 'GBPTMN': 'gbp1', 'GBP': 'gbp1',
    'AED_TMN': 'aed1', 'AEDTMN': 'aed1', 'AED': 'aed1', 'DIRHAM': 'aed1',
    'AED_REMIT_DUB': 'aed1', 'AEDREMITDUB': 'aed1', 'AED_REMIT': 'aed1', 'AEDREMIT': 'aed1',
    'TRY_TMN': 'try1', 'TRYTMN': 'try1', 'TRY': 'try1', 'LIRA': 'try1',
    'CAD_TMN': 'cad1', 'CADTMN': 'cad1', 'CAD': 'cad1',
    'AUD_TMN': 'aud1', 'AUDTMN': 'aud1', 'AUD': 'aud1',
    'CNY_TMN': 'cny1', 'CNYTMN': 'cny1', 'CNY': 'cny1',
    'CNY_REMIT': 'cny1', 'CNYREMIT': 'cny1',
    'CHF_TMN': 'chf1', 'CHFTMN': 'chf1', 'CHF': 'chf1',
    'SAR_TMN': 'sar1', 'SARTMN': 'sar1', 'SAR': 'sar1',
    'KWD_TMN': 'kwd1', 'KWDTMN': 'kwd1', 'KWD': 'kwd1',
    'BHD_TMN': 'bhd1', 'BHDTMN': 'bhd1', 'BHD': 'bhd1',
    'OMR_TMN': 'omr1', 'OMRTMN': 'omr1', 'OMR': 'omr1',
    'QAR_TMN': 'qar1', 'QARTMN': 'qar1', 'QAR': 'qar1',
    'IQD_TMN': 'iqd1', 'IQDTMN': 'iqd1', 'IQD': 'iqd1',
    'AFN_TMN': 'afn1', 'AFNTMN': 'afn1', 'AFN': 'afn1',
    'SEK_TMN': 'sek1', 'SEKTMN': 'sek1', 'SEK': 'sek1',
    'NOK_TMN': 'nok1', 'NOKTMN': 'nok1', 'NOK': 'nok1',
    'DKK_TMN': 'dkk1', 'DKKTMN': 'dkk1', 'DKK': 'dkk1',
    'HKD_TMN': 'hkd1', 'HKDTMN': 'hkd1', 'HKD': 'hkd1',
    'SGD_TMN': 'sgd1', 'SGDTMN': 'sgd1', 'SGD': 'sgd1',
    'MYR_TMN': 'myr1', 'MYRTMN': 'myr1', 'MYR': 'myr1',
    'THB_TMN': 'thb1', 'THBTMN': 'thb1', 'THB': 'thb1',
    'RUB_TMN': 'rub1', 'RUBTMN': 'rub1', 'RUB': 'rub1',
    'INR_TMN': 'inr1', 'INRTMN': 'inr1', 'INR': 'inr1',
    'JPY_TMN': 'jpy1', 'JPYTMN': 'jpy1', 'JPY': 'jpy1',
    'AZN_TMN': 'azn1', 'AZNTMN': 'azn1', 'AZN': 'azn1',
    'AMD_TMN': 'amd1', 'AMDTMN': 'amd1', 'AMD': 'amd1',

    # 2. Physical Gold & Coins (both underscored and normalize_symbol stripped keys)
    'GERAM18': 'gol18', 'GOLD18': 'gol18',
    'GERAM24': 'gol18', 'GOLD24': 'gol18',
    'MESGHAL': 'mithqal', 'MITHQAL': 'mithqal',
    'GOLD_USED': 'gol18', 'GOLDUSED': 'gol18',
    'GOLD_MELTED': 'mithqal', 'GOLDMELTED': 'mithqal',
    'OUNCE': 'ounce', 'GOLD_OUNCE': 'ounce', 'GOLDOUNCE': 'ounce',
    'COIN_EMAMI': 'emami1', 'COINEMAMI': 'emami1', 'EMAMI': 'emami1',
    'COIN_BAHAR': 'azadi1', 'COINBAHAR': 'azadi1', 'BAHAR': 'azadi1',
    'COIN_HALF': 'azadi1_2', 'COINHALF': 'azadi1_2', 'HALF_COIN': 'azadi1_2', 'HALFCOIN': 'azadi1_2',
    'COIN_NIM': 'azadi1_2', 'COINNIM': 'azadi1_2', 'NIM_SEKKEH': 'azadi1_2', 'NIMSEKKEH': 'azadi1_2',
    'COIN_QUARTER': 'azadi1_4', 'COINQUARTER': 'azadi1_4', 'QUARTER_COIN': 'azadi1_4', 'QUARTERCOIN': 'azadi1_4',
    'COIN_ROB': 'azadi1_4', 'COINROB': 'azadi1_4', 'ROB_SEKKEH': 'azadi1_4', 'ROBSEKKEH': 'azadi1_4',
    'COIN_GRAM': 'azadi1g', 'COINGRAM': 'azadi1g', 'GRAM_COIN': 'azadi1g', 'GRAMCOIN': 'azadi1g',
    'COIN_GERAMI': 'azadi1g', 'COINGERAMI': 'azadi1g', 'SEKKEH_GERAMI': 'azadi1g', 'SEKKEHGERAMI': 'azadi1g',
    'BOURSE': 'bourse', 'TEDPIX_BONBAST': 'bourse', 'TEDPIXBONBAST': 'bourse',
    'BITCOIN_BONBAST': 'bitcoin', 'BITCOINBONBAST': 'bitcoin',
}

# Bonbast quotes certain minor-unit currencies per 10 or 100 units:
# - jpy1, amd1: per 10 units on Bonbast
# - iqd1: per 100 units on Bonbast (e.g. 20,800 TMN per 100 IQD -> 208 TMN per 1 IQD)
# We divide by these factors so all currency prices represent 1 single unit of the foreign currency in Tomans.
BONBAST_UNIT_DIVISORS = {
    'iqd1': 100.0,
    'jpy1': 10.0,
    'amd1': 10.0,
}

def compute_bonbast_symbol_price(sym_clean: str, bonbast_k: str, bb_map: Dict[str, Any]) -> Optional[float]:
    """Computes canonical 1-unit Toman price for a symbol from raw Bonbast JSON dict."""
    if not bb_map or bonbast_k not in bb_map:
        return None
    try:
        val = float(str(bb_map[bonbast_k]).replace(',', ''))
        if val <= 0:
            return None
        if sym_clean in ('GERAM24', 'GOLD24'):
            # 24K gold derived from 18K gold: gol18 * 24 / 18
            val = round(val * (24.0 / 18.0))
        elif sym_clean in ('GOLD_USED', 'GOLDUSED'):
            # Second-hand gold (740/750 standard market formula = 98.6667% of 18K)
            val = round(val * (740.0 / 750.0))
        elif bonbast_k in BONBAST_UNIT_DIVISORS:
            val = round(val / BONBAST_UNIT_DIVISORS[bonbast_k], 2)
        return val
    except Exception:
        return None

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
    bonbast_k = (
        BONBAST_MAP.get(sym_clean)
        or BONBAST_MAP.get(raw_upper)
        or (BONBAST_MAP.get(sym_clean[:-3]) if sym_clean.endswith('TMN') else None)
    )
    if bonbast_k:
        now_bb = time.time()
        cache_slot = f'bonbast_{sym_clean}'
        cached_bb = IRAN_MARKET_CACHE.get(cache_slot)
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

        bb_map = await resolve_direct_bonbast_bulk(client)
        val = compute_bonbast_symbol_price(sym_clean, bonbast_k, bb_map) if bb_map else None
        if val is not None and val > 0:
            meta = {'price': val, 'state': 'LIVE', 'currency': 'TMN', 'source': 'بن‌بست مستقیم (Bonbast Live)'}
            IRAN_MARKET_CACHE[cache_slot] = (val, time.time(), meta)
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


async def resolve_direct_bonbast_bulk(client: Optional[httpx.AsyncClient] = None) -> Optional[Dict[str, Any]]:
    """Fetches and caches the full Bonbast JSON bulk payload for 60 seconds."""
    now_bb = time.time()
    bulk_cached = IRAN_MARKET_CACHE.get('__bonbast_bulk__')
    if bulk_cached and (now_bb - bulk_cached[1]) < CACHE_TTL_IRAN:
        return bulk_cached[2]

    if client is not None:
        try:
            bb_html_res = await client.get(
                'https://bonbast.com/',
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                timeout=6.0,
            )
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
                        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    }
                    bb_json_res = await client.post(
                        'https://bonbast.com/json',
                        data={'param': param_val},
                        headers=post_headers,
                        cookies=dict(bb_html_res.cookies),
                        timeout=6.0,
                    )
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

