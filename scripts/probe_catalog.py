#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SignalAlert Catalog Probe & Pre-Apply Reporting Engine (Phase 6 / v3.4.0)

Capabilities:
1. Batch Probing:
   - Batches of 50 to 100 symbols with configurable concurrency (asyncio.Semaphore).
2. Resumable Execution:
   - Checkpoint-based state saved to reports/probe_checkpoint.json.
   - Safely resumes upon rerun; skips already completed symbols.
3. Provider & Quota Strategy:
   - Yahoo Finance: probed for all symbols.
   - Twelve Data & Finnhub: probed ONLY for tier=major symbols at ~10% sample rate,
     budgeted to stay strictly within free-tier quotas (Twelve Data: 800/day, Finnhub: 60/min).
   - FRED: authoritative for macroeconomic indicators and Treasury Yields.
4. Comprehensive Output Reports:
   - reports/pre_apply_report.json: per-symbol ok/failed, price, actual currency, provider, latency, single_source.
   - reports/rejected.json: symbols without successful responses from any provider.
   - reports/yields_table.json: side-by-side Treasury Yields (13W, 2Y [FRED only], 5Y, 10Y, 30Y) with timestamps.
   - reports/summary_report.json: owner summary with category breakdown, single_source count, currency mismatches, and rejections.
5. Offline Mode:
   - --offline flag for local/CI test validation without network calls.
"""

import os
import sys
import json
import time
import hashlib
import argparse
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Set

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    import httpx
except ImportError:
    httpx = None

from app.config import (
    APP_VERSION,
    CATALOG_FILE,
    FINNHUB_API_KEY,
    TWELVE_DATA_API_KEY,
    FRED_API_KEY,
)
from app.engine.categories import resolve_symbol_category
from app.markets.global_stocks import (
    resolve_yf_symbol,
    resolve_symbol_alias,
    # resolve_symbol_category moved
    yahoo_adapter,
    finnhub_adapter,
    twelve_data_adapter,
    fred_adapter,
    EXACT_YF_MAP,
    FOREX_PAIRS,
    FRED_ONLY_SYMBOLS,
    FRED_SERIES_FREQUENCY,
    WALLSTREET_MACRO_SYMBOLS,
)
from app.markets.limiter import (
    PROVIDER_LIMITERS,
    PROVIDER_QUOTAS,
    acquire_provider_slot,
)


# Quota definitions reference from official plans
OFFICIAL_QUOTAS = {
    'twelvedata': {
        'name': 'Twelve Data (Basic Free)',
        'daily_limit': 800,
        'rate_limit': '8 req/min',
        'ref_url': 'https://twelvedata.com/pricing'
    },
    'finnhub': {
        'name': 'Finnhub (Free Tier)',
        'daily_limit': 86400,
        'rate_limit': '60 req/min (30 req/sec)',
        'ref_url': 'https://finnhub.io/pricing'
    },
    'fred': {
        'name': 'FRED Economic Data',
        'daily_limit': 7200,
        'rate_limit': '120 req/min',
        'ref_url': 'https://fred.stlouisfed.org/docs/api/fred/'
    },
    'yahoo': {
        'name': 'Yahoo Finance (Direct Query)',
        'daily_limit': 50000,
        'rate_limit': '10 req/sec soft limit',
        'ref_url': 'https://finance.yahoo.com'
    }
}

TREASURY_TENORS = [
    {
        'tenor': '13-Week Treasury Bill',
        'id': 'US13W',
        'yahoo_symbol': '^IRX',
        'fred_series': 'DTB3',
        'fred_only': False,
        'note': 'Short-term 13-week T-Bill yield (Yahoo ^IRX / FRED DTB3)'
    },
    {
        'tenor': '2-Year Treasury Yield',
        'id': 'US02Y',
        'yahoo_symbol': None,
        'fred_series': 'DGS2',
        'fred_only': True,
        'note': 'Strictly FRED-only (DGS2). Yahoo ^IRX is the 13-week bill, never 2Y; Yahoo has no 2Y ticker.'
    },
    {
        'tenor': '5-Year Treasury Yield',
        'id': 'US05Y',
        'yahoo_symbol': '^FVX',
        'fred_series': 'DGS5',
        'fred_only': False,
        'note': '5-Year Treasury Constant Maturity (Yahoo ^FVX / FRED DGS5)'
    },
    {
        'tenor': '10-Year Treasury Yield',
        'id': 'US10Y',
        'yahoo_symbol': '^TNX',
        'fred_series': 'DGS10',
        'fred_only': False,
        'note': 'Benchmark 10-Year Treasury Yield (Yahoo ^TNX / FRED DGS10)'
    },
    {
        'tenor': '30-Year Treasury Bond',
        'id': 'US30Y',
        'yahoo_symbol': '^TYX',
        'fred_series': 'DGS30',
        'fred_only': False,
        'note': '30-Year Treasury Bond Yield (Yahoo ^TYX / FRED DGS30)'
    },
]


def load_catalog(catalog_path: str) -> List[Dict[str, Any]]:
    """Loads symbols from catalog.json or seed files."""
    if os.path.exists(catalog_path):
        try:
            with open(catalog_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                symbols = data.get('symbols', [])
                if symbols:
                    return symbols
        except Exception as e:
            print(f"[WARN] Failed to load catalog from {catalog_path}: {e}")

    # Fallback to WALLSTREET_MACRO_SYMBOLS
    return WALLSTREET_MACRO_SYMBOLS


def is_tier_major(item: Dict[str, Any]) -> bool:
    """Determines whether a symbol is major tier."""
    t = str(item.get('tier', '')).strip().lower()
    if t in ('1', 'major', 'true'):
        return True
    if item.get('is_major') or item.get('isMajor'):
        return True
    market_name = str(item.get('marketName', '')).lower()
    if 'major' in market_name or 'treasury' in market_name or 'forex' in market_name:
        return True
    sym = (item.get('symbol') or item.get('id') or '').upper().replace('/', '').replace('.', '').replace('-', '')
    cat = str(item.get('category', '')).lower()
    if cat in ('bond', 'macro') or sym in FOREX_PAIRS:
        return True
    major_equities = {'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'BRKB', 'BRKB', 'SP500', 'GOLD', 'OIL', 'EURUSD', 'GBPUSD', 'USDJPY', 'US10Y', 'US02Y', 'US30Y'}
    if sym in major_equities or item.get('id', '').upper().replace('.', '').replace('-', '') in major_equities:
        return True
    return False


def is_sampled_for_secondary(symbol_id: str, sample_rate: float = 0.10) -> bool:
    """
    Deterministically selects ~sample_rate of major items using MD5 hashing.
    Consistent across resumed runs.
    """
    if sample_rate >= 1.0:
        return True
    if sample_rate <= 0.0:
        return False
    digest = hashlib.md5(symbol_id.encode('utf-8')).hexdigest()
    int_val = int(digest[:6], 16)
    threshold = int(sample_rate * 0xFFFFFF)
    return int_val < threshold


def normalize_expected_currency(unit: Optional[str], category: Optional[str] = None) -> str:
    """Normalizes catalog unit/currency into ISO 4217 standard currency code or standard unit indicator."""
    if not unit:
        return 'USD'
    u = unit.strip().upper()
    if u in ('$', 'USD', 'DOLLAR'):
        return 'USD'
    if u in ('€', 'EUR', 'EURO'):
        return 'EUR'
    if u in ('£', 'GBP', 'POUND'):
        return 'GBP'
    if u in ('¥', 'JPY', 'YEN'):
        return 'JPY'
    if u in ('CNY', 'RMB', 'YUAN'):
        return 'CNY'
    if u in ('FR', 'CHF', 'FRANC'):
        return 'CHF'
    if u in ('C$', 'CAD'):
        return 'CAD'
    if u in ('A$', 'AUD'):
        return 'AUD'
    if u in ('AED', 'DIRHAM'):
        return 'AED'
    if u in ('HKD',):
        return 'HKD'
    if u in ('ت', 'TMN', 'TOMAN', 'IRT', 'IRR'):
        return 'TMN'
    if u in ('%', 'PERCENT', 'PCT'):
        return '%'
    if 'INDEX' in u or u in ('PTS', 'POINT', 'POINTS'):
        return 'PTS'
    if 'MILLION' in u or 'BILLION' in u:
        return 'USD'
    return u


def check_unit_match(expected_unit: Optional[str], received_unit: Optional[str], category: Optional[str] = None) -> bool:
    """Checks whether received unit matches catalog expected unit (distinct from currency)."""
    if not expected_unit or not received_unit:
        return True
    exp = expected_unit.strip().lower()
    rec = received_unit.strip().lower()
    if exp == rec:
        return True
    if ('%' in exp or 'percent' in exp) and ('%' in rec or 'percent' in rec):
        return True
    if ('index' in exp or 'pts' in exp or 'point' in exp) and ('index' in rec or 'pts' in rec or 'point' in rec):
        return True
    if ('million' in exp or 'mil' in exp) and ('million' in rec or 'mil' in rec or 'usd' in rec or '$' in rec):
        return True
    if ('billion' in exp or 'bil' in exp) and ('billion' in rec or 'bil' in rec or 'usd' in rec or '$' in rec):
        return True
    if category == 'bond' and ('%' in exp or 'percent' in exp or 'yield' in exp):
        return True
    return False


def check_currency_match(expected_currency: Optional[str], received_currency: Optional[str], category: Optional[str] = None) -> bool:
    """Checks whether received currency matches catalog expected currency code."""
    if not received_currency or not expected_currency:
        return True
    exp_iso = normalize_expected_currency(expected_currency, category)
    rec_iso = normalize_expected_currency(received_currency, category)

    if exp_iso == rec_iso:
        return True

    # Multi-currency allowances:
    # ¥ represents both JPY and CNY
    if exp_iso in ('JPY', 'CNY') and rec_iso in ('JPY', 'CNY'):
        return True
    # Forex major pairings
    if category == 'forex':
        if exp_iso in ('USD', 'EUR', 'GBP', 'CHF', 'CAD', 'AUD', 'JPY', 'CNY', 'AED', 'TMN'):
            return True
    # Indices often have expected PTS while quote API tags quotes with currency
    if category == 'index' and (exp_iso in ('PTS', 'USD') or rec_iso in ('PTS', 'USD', 'EUR', 'GBP', 'JPY')):
        return True
    # Bonds often have expected % while Yahoo quote API tags quotes with currency='USD'
    if category == 'bond' and (exp_iso == '%' or rec_iso in ('%', 'USD')):
        return True
    # Macro indicators (CPI points vs USD or %)
    if category == 'macro':
        if exp_iso in ('PTS', 'USD', '%') and rec_iso in ('PTS', 'USD', '%'):
            return True

    return False


def is_sampled_for_secondary_rotation(symbol_id: str, daily_batch_size: int = 50, total_symbols: int = 580) -> bool:
    """
    Deterministically rotates ~daily_batch_size symbols per day over Finnhub/Twelve Data.
    Allows all fallback mappings to be gradually validated over weekly sync runs.
    """
    today_int = int(datetime.now(timezone.utc).strftime("%Y%j"))
    sym_hash = int(hashlib.md5(symbol_id.encode('utf-8')).hexdigest()[:6], 16)
    slots = max(1, total_symbols // daily_batch_size)
    return (sym_hash % slots) == (today_int % slots)


class ProbeCheckpoint:
    """Manages resumable checkpoint file on disk."""
    def __init__(self, checkpoint_path: str):
        self.path = checkpoint_path
        self.data: Dict[str, Any] = {
            'started_at': datetime.now(timezone.utc).isoformat(),
            'last_updated_at': datetime.now(timezone.utc).isoformat(),
            'completed': False,
            'processed_ids': [],
            'results': {},
            'rejected': [],
            'yields_data': {},
            'secondary_requests_count': {'twelvedata': 0, 'finnhub': 0, 'fred': 0, 'yahoo': 0}
        }
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict) and 'processed_ids' in loaded:
                        self.data.update(loaded)
            except Exception as e:
                print(f"[WARN] Could not load checkpoint from {self.path}: {e}")

    def save(self):
        self.data['last_updated_at'] = datetime.now(timezone.utc).isoformat()
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        temp_path = self.path + ".tmp"
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        os.replace(temp_path, self.path)

    def is_processed(self, symbol_id: str) -> bool:
        return symbol_id in self.data['processed_ids']

    def record_symbol_result(self, item_id: str, result: Dict[str, Any], is_rejected: bool = False, reject_item: Optional[Dict[str, Any]] = None):
        if item_id not in self.data['processed_ids']:
            self.data['processed_ids'].append(item_id)
        self.data['results'][item_id] = result
        if is_rejected and reject_item:
            # Check not already in rejected list
            if not any(r.get('id') == item_id for r in self.data['rejected']):
                self.data['rejected'].append(reject_item)

    def mark_completed(self):
        self.data['completed'] = True
        self.save()


class CatalogProbeRunner:
    """Async catalog probe runner with rate-limiting, batching, and reporting."""

    def __init__(
        self,
        catalog_path: str = CATALOG_FILE,
        checkpoint_path: str = "reports/probe_checkpoint.json",
        report_path: str = "reports/pre_apply_report.json",
        rejected_path: str = "reports/rejected.json",
        yields_path: str = "reports/yields_table.json",
        summary_path: str = "reports/summary_report.json",
        batch_size: int = 50,
        concurrency: int = 5,
        sample_rate_secondary: float = 0.10,
        offline: bool = False,
        symbols_filter: Optional[List[str]] = None,
        force_restart: bool = False,
    ):
        self.catalog_path = catalog_path
        self.checkpoint_path = checkpoint_path
        self.report_path = report_path
        self.rejected_path = rejected_path
        self.yields_path = yields_path
        self.summary_path = summary_path
        self.batch_size = max(10, min(100, batch_size))
        self.concurrency = max(1, concurrency)
        self.sample_rate_secondary = sample_rate_secondary
        self.offline = offline
        self.symbols_filter = symbols_filter
        self.semaphore = asyncio.Semaphore(self.concurrency)

        # Ensure reports directory exists
        for p in (checkpoint_path, report_path, rejected_path, yields_path, summary_path):
            os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)

        if force_restart and os.path.exists(self.checkpoint_path):
            try:
                os.remove(self.checkpoint_path)
            except Exception:
                pass

        self.checkpoint = ProbeCheckpoint(self.checkpoint_path)
        self.secondary_counts = self.checkpoint.data.get('secondary_requests_count', {'twelvedata': 0, 'finnhub': 0, 'fred': 0, 'yahoo': 0})

    async def probe_single_symbol(
        self,
        item: Dict[str, Any],
        client: Any = None
    ) -> Tuple[Dict[str, Any], bool, Optional[Dict[str, Any]]]:
        """
        Probes a single catalog item across relevant providers.
        Returns: (result_dict, is_rejected, reject_record)
        """
        item_id = item.get('id', '')
        symbol_raw = item.get('symbol', item_id)
        name_en = item.get('nameEn', '')
        category = item.get('category') or item.get('asset_class') or resolve_symbol_category(item.get('exchange', 'global_stocks'), symbol_raw)
        unit = item.get('unit', '')
        is_major = is_tier_major(item)
        probe_secondary = is_major and (is_sampled_for_secondary(item_id, self.sample_rate_secondary) or is_sampled_for_secondary_rotation(item_id, daily_batch_size=50))

        clean_sym = symbol_raw.upper().strip()
        canonical = resolve_symbol_alias(clean_sym)
        is_fred_only = (clean_sym in FRED_ONLY_SYMBOLS or canonical in FRED_ONLY_SYMBOLS)

        attempts: List[Dict[str, Any]] = []
        successful_quotes: List[Dict[str, Any]] = []

        if self.offline:
            # Offline simulation mode
            await asyncio.sleep(0.005)
            # Simulate Yahoo probe
            if not is_fred_only:
                yf_sym = resolve_yf_symbol(symbol_raw)
                if yf_sym and yf_sym != 'UNKNOWN_REJECT':
                    simulated_curr = 'USD'
                    if yf_sym.endswith('.HK'):
                        simulated_curr = 'HKD'
                    elif yf_sym.endswith('.PA') or yf_sym.endswith('.DE'):
                        simulated_curr = 'EUR'
                    elif category in ('bond', 'macro'):
                        simulated_curr = '%'
                    
                    successful_quotes.append({
                        'provider': 'yahoo',
                        'price': 100.50,
                        'currency': simulated_curr,
                        'latency_ms': 42.0,
                        'as_of': int(time.time()),
                        'state': 'LIVE'
                    })
                    attempts.append({'provider': 'yahoo', 'status': 'ok', 'latency_ms': 42.0})
                else:
                    attempts.append({'provider': 'yahoo', 'status': 'failed', 'error': 'Not mapped in Yahoo'})

            # Secondary providers simulation
            if probe_secondary and not is_fred_only:
                if category in ('stock', 'forex'):
                    self.secondary_counts['finnhub'] += 1
                    successful_quotes.append({
                        'provider': 'finnhub',
                        'price': 100.52,
                        'currency': 'USD',
                        'latency_ms': 55.0,
                        'as_of': int(time.time()),
                        'state': 'LIVE'
                    })
                    attempts.append({'provider': 'finnhub', 'status': 'ok', 'latency_ms': 55.0})

                if category in ('stock', 'forex', 'index', 'commodity'):
                    self.secondary_counts['twelvedata'] += 1
                    successful_quotes.append({
                        'provider': 'twelvedata',
                        'price': 100.49,
                        'currency': 'USD',
                        'latency_ms': 60.0,
                        'as_of': int(time.time()),
                        'state': 'LIVE'
                    })
                    attempts.append({'provider': 'twelvedata', 'status': 'ok', 'latency_ms': 60.0})

            # FRED simulation for bond/macro
            if category in ('bond', 'macro') or clean_sym in fred_adapter.FRED_SERIES_MAP:
                self.secondary_counts['fred'] += 1
                sim_units = '%'
                sim_unit = '%'
                sim_curr = '%'
                sim_price = 4.25
                if clean_sym in ('CPIAUCSL', 'CPI'):
                    sim_units = 'Index 1982-1984=100'
                    sim_unit = 'Index 1982-1984=100'
                    sim_curr = 'PTS'
                    sim_price = 314.50
                elif clean_sym == 'WALCL':
                    sim_units = 'Millions of U.S. Dollars'
                    sim_unit = 'Mil. of U.S. $'
                    sim_curr = 'USD'
                    sim_price = 7120000.0
                elif clean_sym in ('M2SL', 'M2'):
                    sim_units = 'Billions of U.S. Dollars'
                    sim_unit = 'Bil. of U.S. $'
                    sim_curr = 'USD'
                    sim_price = 21400.0

                successful_quotes.append({
                    'provider': 'fred',
                    'price': sim_price,
                    'currency': sim_curr,
                    'units': sim_units,
                    'unit': sim_unit,
                    'latency_ms': 80.0,
                    'as_of': int(time.time()),
                    'state': 'LIVE'
                })
                attempts.append({'provider': 'fred', 'status': 'ok', 'latency_ms': 80.0})

        else:
            # LIVE NETWORK MODE (With strict rate limiters and semaphores)
            # 1. Yahoo Finance (All non-FRED-only symbols)
            if not is_fred_only:
                try:
                    await acquire_provider_slot('yahoo', wait=True)
                    t0 = time.time()
                    q_yf = await yahoo_adapter.fetch_quote(symbol_raw, client)
                    lat = round((time.time() - t0) * 1000, 2)
                    self.secondary_counts['yahoo'] += 1

                    if q_yf and q_yf.get('price'):
                        successful_quotes.append({
                            'provider': 'yahoo',
                            'price': q_yf.get('price'),
                            'currency': q_yf.get('currency', 'USD'),
                            'latency_ms': lat,
                            'as_of': q_yf.get('asOf'),
                            'state': q_yf.get('state', 'LIVE')
                        })
                        attempts.append({'provider': 'yahoo', 'status': 'ok', 'latency_ms': lat})
                    else:
                        attempts.append({'provider': 'yahoo', 'status': 'failed', 'error': 'No price returned', 'latency_ms': lat})
                except Exception as e:
                    attempts.append({'provider': 'yahoo', 'status': 'error', 'error': str(e)})

            # 2. Secondary Providers (Twelve Data / Finnhub)
            if probe_secondary and not is_fred_only:
                # Finnhub
                if category in ('stock', 'forex'):
                    try:
                        await acquire_provider_slot('finnhub', wait=True)
                        t0 = time.time()
                        q_fh = await finnhub_adapter.fetch_quote(symbol_raw, client)
                        lat = round((time.time() - t0) * 1000, 2)
                        self.secondary_counts['finnhub'] += 1

                        if q_fh and q_fh.get('price'):
                            successful_quotes.append({
                                'provider': 'finnhub',
                                'price': q_fh.get('price'),
                                'currency': q_fh.get('currency', 'USD'),
                                'latency_ms': lat,
                                'as_of': q_fh.get('asOf'),
                                'state': q_fh.get('state', 'LIVE')
                            })
                            attempts.append({'provider': 'finnhub', 'status': 'ok', 'latency_ms': lat})
                        else:
                            attempts.append({'provider': 'finnhub', 'status': 'failed', 'error': 'No price returned', 'latency_ms': lat})
                    except Exception as e:
                        attempts.append({'provider': 'finnhub', 'status': 'error', 'error': str(e)})

                # Twelve Data
                if category in ('stock', 'forex', 'index', 'commodity'):
                    try:
                        await acquire_provider_slot('twelvedata', wait=True)
                        t0 = time.time()
                        q_td = await twelve_data_adapter.fetch_quote(symbol_raw, client)
                        lat = round((time.time() - t0) * 1000, 2)
                        self.secondary_counts['twelvedata'] += 1

                        if q_td and q_td.get('price'):
                            successful_quotes.append({
                                'provider': 'twelvedata',
                                'price': q_td.get('price'),
                                'currency': q_td.get('currency', 'USD'),
                                'latency_ms': lat,
                                'as_of': q_td.get('asOf'),
                                'state': q_td.get('state', 'LIVE')
                            })
                            attempts.append({'provider': 'twelvedata', 'status': 'ok', 'latency_ms': lat})
                        else:
                            attempts.append({'provider': 'twelvedata', 'status': 'failed', 'error': 'No price returned', 'latency_ms': lat})
                    except Exception as e:
                        attempts.append({'provider': 'twelvedata', 'status': 'error', 'error': str(e)})

            # 3. FRED for Macro and Treasury Yields
            if (category in ('bond', 'macro') or clean_sym in fred_adapter.FRED_SERIES_MAP):
                try:
                    await acquire_provider_slot('fred', wait=True)
                    t0 = time.time()
                    q_fred = await fred_adapter.fetch_quote(symbol_raw, client)
                    lat = round((time.time() - t0) * 1000, 2)
                    self.secondary_counts['fred'] += 1

                    if q_fred and q_fred.get('price'):
                        successful_quotes.append({
                            'provider': 'fred',
                            'price': q_fred.get('price'),
                            'currency': q_fred.get('currency', '%'),
                            'latency_ms': lat,
                            'as_of': q_fred.get('asOf'),
                            'state': q_fred.get('state', 'LIVE')
                        })
                        attempts.append({'provider': 'fred', 'status': 'ok', 'latency_ms': lat})
                    else:
                        attempts.append({'provider': 'fred', 'status': 'failed', 'error': 'No series data returned', 'latency_ms': lat})
                except Exception as e:
                    attempts.append({'provider': 'fred', 'status': 'error', 'error': str(e)})

        # Evaluate Probe Result
        successful_providers = [q['provider'] for q in successful_quotes]
        is_ok = len(successful_quotes) > 0

        # Provider prices & spread calculation
        provider_prices: Dict[str, float] = {}
        for q in successful_quotes:
            if 'provider' in q and q.get('price') is not None:
                provider_prices[q['provider']] = q['price']

        price_difference_pct: Optional[float] = None
        if len(provider_prices) >= 2:
            p_vals = list(provider_prices.values())
            p1, p2 = p_vals[0], p_vals[1]
            avg = (p1 + p2) / 2.0
            if avg > 0:
                price_difference_pct = round(abs(p1 - p2) / avg * 100.0, 4)

        secondary_probed = bool(probe_secondary)
        confirmed_single_source = (len(successful_quotes) == 1) if secondary_probed else None
        is_single_source = (len(successful_quotes) == 1)

        primary_quote = successful_quotes[0] if successful_quotes else {}
        resp_currency = primary_quote.get('currency')
        resp_units = primary_quote.get('units') or primary_quote.get('unit')

        expected_iso = normalize_expected_currency(item.get('currency') or unit, category=category)
        curr_match = check_currency_match(expected_iso, resp_currency, category=category)
        unit_match = check_unit_match(unit, resp_units or resp_currency, category=category)

        result_record = {
            'id': item_id,
            'symbol': symbol_raw,
            'nameEn': name_en,
            'nameFa': item.get('nameFa') or name_en,
            'marketName': item.get('marketName') or 'Global',
            'category': category,
            'status': 'ok' if is_ok else 'failed',
            'price': primary_quote.get('price'),
            'currency': resp_currency,
            'expected_currency': expected_iso,
            'currency_match': curr_match,
            'unit_match': unit_match,
            'provider': primary_quote.get('provider'),
            'successful_providers': successful_providers,
            'provider_prices': provider_prices,
            'price_difference_pct': price_difference_pct,
            'secondary_probed': secondary_probed,
            'confirmed_single_source': confirmed_single_source,
            'single_source': is_single_source if is_ok else None,
            'latency_ms': primary_quote.get('latency_ms') if is_ok and primary_quote.get('latency_ms') is not None else None,
            'as_of': primary_quote.get('as_of'),
            'state': primary_quote.get('state', 'unknown'),
            'attempts_count': len(attempts),
            'probed_at': datetime.now(timezone.utc).isoformat(),
        }

        if not is_ok:
            result_record['error'] = 'No provider returned valid quote'
            reject_record = {
                'id': item_id,
                'symbol': symbol_raw,
                'nameEn': name_en,
                'category': category,
                'marketName': item.get('marketName', ''),
                'reason': 'Zero successful provider quotes during probe',
                'attempts': attempts,
                'rejected_at': datetime.now(timezone.utc).isoformat()
            }
            return result_record, True, reject_record

        return result_record, False, None

    async def probe_treasury_yields(self, client: Any = None) -> List[Dict[str, Any]]:
        """
        Builds side-by-side Treasury Yields table (13W, 2Y [FRED-only], 5Y, 10Y, 30Y).
        Captures Yahoo and FRED values with timestamps.
        """
        yields_table = []

        for item in TREASURY_TENORS:
            tenor = item['tenor']
            tid = item['id']
            yf_sym = item['yahoo_symbol']
            fred_id = item['fred_series']
            fred_only = item['fred_only']

            yf_val = None
            yf_time = None
            fred_val = None
            fred_time = None

            if self.offline:
                await asyncio.sleep(0.005)
                # Simulated realistic yield values
                mock_vals = {
                    'US13W': (5.24, 5.25),
                    'US02Y': (None, 4.48),
                    'US05Y': (4.12, 4.14),
                    'US10Y': (4.28, 4.29),
                    'US30Y': (4.52, 4.51),
                }
                pair = mock_vals.get(tid, (None, 4.0))
                if not fred_only:
                    yf_val = pair[0]
                    yf_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
                fred_val = pair[1]
                fred_time = datetime.now(timezone.utc).strftime('%Y-%m-%d (Daily Close)')

            else:
                # Live FRED Probe
                try:
                    await acquire_provider_slot('fred', wait=True)
                    q_f = await fred_adapter.fetch_quote(fred_id, client)
                    if q_f and q_f.get('price'):
                        fred_val = q_f.get('price')
                        fred_time = q_f.get('date') or str(q_f.get('asOf'))
                except Exception as e:
                    print(f"[WARN] FRED probe error for {fred_id}: {e}")

                # Live Yahoo Probe
                if not fred_only and yf_sym:
                    try:
                        await acquire_provider_slot('yahoo', wait=True)
                        q_y = await yahoo_adapter.fetch_quote(yf_sym, client)
                        if q_y and q_y.get('price'):
                            yf_val = q_y.get('price')
                            as_of_ts = q_y.get('asOf')
                            if as_of_ts:
                                yf_time = datetime.fromtimestamp(as_of_ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
                            else:
                                yf_time = "Live"
                    except Exception as e:
                        print(f"[WARN] Yahoo probe error for {yf_sym}: {e}")

            delta = None
            if yf_val is not None and fred_val is not None:
                delta = round(yf_val - fred_val, 4)

            yields_table.append({
                'tenor': tenor,
                'id': tid,
                'yahoo_symbol': yf_sym if not fred_only else 'N/A (FRED-only)',
                'yahoo_yield': yf_val,
                'yahoo_recorded_at': yf_time if not fred_only else 'N/A',
                'fred_series': fred_id,
                'fred_yield': fred_val,
                'fred_recorded_at': fred_time,
                'delta': delta,
                'fred_only': fred_only,
                'note': item['note']
            })

        return yields_table

    async def run(self) -> Dict[str, Any]:
        """Main execution loop chunked into batches with checkpoint preservation."""
        all_symbols = load_catalog(self.catalog_path)
        if self.symbols_filter:
            filt = set(s.upper() for s in self.symbols_filter)
            all_symbols = [s for s in all_symbols if s.get('id', '').upper() in filt or s.get('symbol', '').upper() in filt]

        total_count = len(all_symbols)
        unprocessed = [s for s in all_symbols if not self.checkpoint.is_processed(s.get('id', ''))]

        print("=" * 75)
        print(f"SignalAlert Catalog Probe & Report Engine v{APP_VERSION}")
        print(f"Mode: {'OFFLINE (SIMULATED)' if self.offline else 'LIVE NETWORK'}")
        print(f"Catalog Total Symbols: {total_count}")
        print(f"Already Processed in Checkpoint: {len(self.checkpoint.data['processed_ids'])}")
        print(f"Remaining to Probe: {len(unprocessed)}")
        print(f"Batch Size: {self.batch_size} | Concurrency: {self.concurrency}")
        print(f"Secondary Sample Rate: {int(self.sample_rate_secondary * 100)}% (tier=major)")
        print("=" * 75)

        async def _execute_with_client(client):
            # 1. Probe Treasury Yields Table
            print("\n📊 Probing US Treasury Yields (13W, 2Y [FRED only], 5Y, 10Y, 30Y)...")
            yields_table = await self.probe_treasury_yields(client)
            self.checkpoint.data['yields_data'] = yields_table
            self.checkpoint.save()

            # 2. Process Symbols in Batches (50 to 100 items)
            for batch_start in range(0, len(unprocessed), self.batch_size):
                batch = unprocessed[batch_start:batch_start + self.batch_size]
                batch_num = (batch_start // self.batch_size) + 1
                total_batches = ((len(unprocessed) - 1) // self.batch_size) + 1

                print(f"\n🚀 Processing Batch {batch_num}/{total_batches} ({len(batch)} symbols)...")

                async def _worker(item):
                    async with self.semaphore:
                        return await self.probe_single_symbol(item, client)

                results = await asyncio.gather(*[_worker(item) for item in batch])

                for item, (res, is_rej, rej_item) in zip(batch, results):
                    item_id = item.get('id', '')
                    self.checkpoint.record_symbol_result(item_id, res, is_rej, rej_item)

                # Persist checkpoint at end of each batch
                self.checkpoint.data['secondary_requests_count'] = self.secondary_counts
                self.checkpoint.save()
                print(f"💾 Checkpoint saved. Progress: {len(self.checkpoint.data['processed_ids'])}/{total_count} symbols.")

            # Mark complete
            self.checkpoint.mark_completed()

        if httpx is not None:
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=30)
            timeout = httpx.Timeout(10.0, connect=5.0)
            async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
                await _execute_with_client(client)
        else:
            await _execute_with_client(None)

        # 3. Generate Final Deliverables
        summary = self.generate_reports()
        return summary

    def generate_reports(self) -> Dict[str, Any]:
        """Compiles pre_apply_report.json, rejected.json, yields_table.json, and summary_report.json."""
        results_map = self.checkpoint.data.get('results', {})
        results_list = list(results_map.values())
        rejected_list = self.checkpoint.data.get('rejected', [])
        yields_table = self.checkpoint.data.get('yields_data', [])

        # Dynamically refresh currency_match and unit_match using latest rules so resumed checkpoint reflects updated logic
        for r in results_list:
            r['currency_match'] = check_currency_match(
                r.get('expected_currency'),
                r.get('currency'),
                category=r.get('category')
            )
            r['unit_match'] = check_unit_match(
                r.get('expected_currency'),
                r.get('currency'),
                category=r.get('category')
            )
            # Keep checkpoint in sync
            item_id = r.get('id')
            if item_id and item_id in results_map:
                results_map[item_id]['currency_match'] = r['currency_match']
                results_map[item_id]['unit_match'] = r['unit_match']

        total = len(results_list)
        ok_count = sum(1 for r in results_list if r.get('status') == 'ok')
        failed_count = sum(1 for r in results_list if r.get('status') == 'failed')
        single_source_count = sum(1 for r in results_list if r.get('single_source') is True)
        multi_source_count = sum(1 for r in results_list if r.get('single_source') is False)
        secondary_probed_count = sum(1 for r in results_list if r.get('secondary_probed') is True)
        confirmed_single_source_count = sum(1 for r in results_list if r.get('confirmed_single_source') is True)
        curr_mismatches = [r for r in results_list if r.get('currency_match') is False]
        unit_mismatches = [r for r in results_list if r.get('unit_match') is False]

        # Breakdown by category
        categories: Dict[str, Dict[str, int]] = {}
        for r in results_list:
            c = r.get('category', 'unknown')
            if c not in categories:
                categories[c] = {'total': 0, 'ok': 0, 'failed': 0, 'single_source': 0, 'secondary_probed': 0, 'confirmed_single_source': 0}
            categories[c]['total'] += 1
            if r.get('status') == 'ok':
                categories[c]['ok'] += 1
            else:
                categories[c]['failed'] += 1
            if r.get('single_source') is True:
                categories[c]['single_source'] += 1
            if r.get('secondary_probed') is True:
                categories[c]['secondary_probed'] += 1
            if r.get('confirmed_single_source') is True:
                categories[c]['confirmed_single_source'] += 1

        summary = {
            'app_version': APP_VERSION,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'total_symbols_probed': total,
            'ok_count': ok_count,
            'failed_count': failed_count,
            'success_rate_pct': round((ok_count / total * 100) if total else 0.0, 2),
            'single_source_count': single_source_count,
            'multi_source_count': multi_source_count,
            'secondary_probed_count': secondary_probed_count,
            'confirmed_single_source_count': confirmed_single_source_count,
            'currency_mismatches_count': len(curr_mismatches),
            'unit_mismatches_count': len(unit_mismatches),
            'category_breakdown': categories,
            'quota_usage': {
                'twelvedata': {
                    'used': self.secondary_counts.get('twelvedata', 0),
                    'official_limit': OFFICIAL_QUOTAS['twelvedata']['daily_limit'],
                    'pct': round((self.secondary_counts.get('twelvedata', 0) / OFFICIAL_QUOTAS['twelvedata']['daily_limit']) * 100, 2)
                },
                'finnhub': {
                    'used': self.secondary_counts.get('finnhub', 0),
                    'official_limit': OFFICIAL_QUOTAS['finnhub']['daily_limit'],
                    'pct': round((self.secondary_counts.get('finnhub', 0) / OFFICIAL_QUOTAS['finnhub']['daily_limit']) * 100, 2)
                },
                'fred': {
                    'used': self.secondary_counts.get('fred', 0),
                    'official_limit': OFFICIAL_QUOTAS['fred']['daily_limit'],
                    'pct': round((self.secondary_counts.get('fred', 0) / OFFICIAL_QUOTAS['fred']['daily_limit']) * 100, 2)
                },
                'yahoo': {
                    'used': self.secondary_counts.get('yahoo', 0),
                    'official_limit': OFFICIAL_QUOTAS['yahoo']['daily_limit'],
                    'pct': round((self.secondary_counts.get('yahoo', 0) / OFFICIAL_QUOTAS['yahoo']['daily_limit']) * 100, 2)
                }
            },
            'single_source_symbols': [
                {
                    'id': r['id'],
                    'symbol': r['symbol'],
                    'category': r['category'],
                    'provider': r['provider']
                }
                for r in results_list if r.get('single_source') is True
            ],
            'confirmed_single_source_symbols': [
                {
                    'id': r['id'],
                    'symbol': r['symbol'],
                    'category': r['category'],
                    'provider': r['provider']
                }
                for r in results_list if r.get('confirmed_single_source') is True
            ],
            'currency_mismatches': [
                {
                    'id': r['id'],
                    'symbol': r['symbol'],
                    'expected': r.get('expected_currency'),
                    'received': r.get('currency'),
                    'provider': r.get('provider')
                }
                for r in curr_mismatches
            ],
            'unit_mismatches': [
                {
                    'id': r['id'],
                    'symbol': r['symbol'],
                    'expected': r.get('expected_currency'),
                    'received': r.get('currency'),
                    'provider': r.get('provider')
                }
                for r in unit_mismatches
            ],
            'rejected_symbols': rejected_list,
            'treasury_yields': yields_table
        }

        # 1. Write reports/pre_apply_report.json
        with open(self.report_path, 'w', encoding='utf-8') as f:
            json.dump(results_list, f, indent=2, ensure_ascii=False)

        # 2. Write reports/rejected.json
        with open(self.rejected_path, 'w', encoding='utf-8') as f:
            json.dump(rejected_list, f, indent=2, ensure_ascii=False)

        # 3. Write reports/yields_table.json
        with open(self.yields_path, 'w', encoding='utf-8') as f:
            json.dump(yields_table, f, indent=2, ensure_ascii=False)

        # 4. Write reports/summary_report.json
        with open(self.summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 75)
        print("📑 OWNER SUMMARY REPORT (Phase 6 / Stage 8)")
        print("=" * 75)
        print(f"• Total Symbols: {total}")
        print(f"• OK (Resolved): {ok_count} ({summary['success_rate_pct']}%)")
        print(f"• Failed / Rejected: {failed_count}")
        print(f"• Single Source (Sole Provider): {single_source_count}")
        print(f"• Multi Source (Redundant): {multi_source_count}")
        print(f"• Currency Mismatches: {len(curr_mismatches)}")
        print("\n📂 Category Breakdown:")
        for cat, st in categories.items():
            print(f"   - {cat:<12}: Total {st['total']:<3} | OK {st['ok']:<3} | Failed {st['failed']:<2} | SingleSource {st['single_source']}")

        print("\n🏛️ Treasury Yields Comparison (Yahoo vs FRED):")
        for yt in yields_table:
            y_val = f"{yt['yahoo_yield']}%" if yt['yahoo_yield'] is not None else "N/A"
            f_val = f"{yt['fred_yield']}%" if yt['fred_yield'] is not None else "N/A"
            d_val = f"{yt['delta']:+.4f}" if yt['delta'] is not None else "N/A"
            print(f"   [{yt['id']:<5}] {yt['tenor']:<28} | Yahoo: {y_val:<7} | FRED: {f_val:<7} | Delta: {d_val:<7} | Note: {yt['note']}")

        print("\n✅ Deliverables generated successfully:")
        print(f"   1. {self.report_path}")
        print(f"   2. {self.rejected_path}")
        print(f"   3. {self.yields_path}")
        print(f"   4. {self.summary_path}")
        print("=" * 75)

        return summary


def parse_args():
    parser = argparse.ArgumentParser(description=f"SignalAlert Catalog Probe & Report Engine v{APP_VERSION}")
    parser.add_argument("--catalog", default=CATALOG_FILE, help="Path to catalog.json file")
    parser.add_argument("--checkpoint", default="reports/probe_checkpoint.json", help="Path to checkpoint file")
    parser.add_argument("--report", default="reports/pre_apply_report.json", help="Path to pre_apply_report.json output")
    parser.add_argument("--rejected", default="reports/rejected.json", help="Path to rejected.json output")
    parser.add_argument("--yields-table", default="reports/yields_table.json", help="Path to yields_table.json output")
    parser.add_argument("--summary", default="reports/summary_report.json", help="Path to summary_report.json output")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size (50 to 100)")
    parser.add_argument("--concurrency", type=int, default=5, help="Concurrent workers")
    parser.add_argument("--sample-rate-secondary", type=float, default=0.10, help="Sample rate for secondary providers (0.10 = 10%%)")
    parser.add_argument("--offline", action="store_true", help="Run offline simulation without outbound requests")
    parser.add_argument("--force-restart", action="store_true", help="Clear existing checkpoint and restart fresh")
    parser.add_argument("--symbols", help="Comma-separated symbol IDs to filter")
    return parser.parse_args()


def main():
    args = parse_args()
    sym_filter = [s.strip() for s in args.symbols.split(",")] if args.symbols else None

    runner = CatalogProbeRunner(
        catalog_path=args.catalog,
        checkpoint_path=args.checkpoint,
        report_path=args.report,
        rejected_path=args.rejected,
        yields_path=args.yields_table,
        summary_path=args.summary,
        batch_size=args.batch_size,
        concurrency=args.concurrency,
        sample_rate_secondary=args.sample_rate_secondary,
        offline=args.offline,
        symbols_filter=sym_filter,
        force_restart=args.force_restart
    )

    asyncio.run(runner.run())


if __name__ == "__main__":
    main()
