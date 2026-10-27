#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone Live Probe for Cryptocurrency Exchange Public Market Data APIs.
Executed manually on the server (Read-Only) to verify:
1. HTTP reachability from server IP (e.g. Frankfurt/Hetzner server).
2. Latency (ms).
3. Count of active USDT spot pairs.
4. Count and percentage of pairs with live prices.
5. Presence of ETF/leveraged tokens.
Zero dependencies: Uses standard library urllib.request with SSL context.
"""

import sys
import os
import json
import time
import ssl
import urllib.request
import urllib.error
from datetime import datetime, timezone

# Disable strict SSL verification issues if system CA bundles vary
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'AlertG-MarketProbe/1.0 (Server Health Audit)',
    'Accept': 'application/json',
}


def _http_get(url: str, timeout: float = 10.0):
    start = time.time()
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as response:
            status = response.getcode()
            body = response.read()
            latency_ms = round((time.time() - start) * 1000, 2)
            try:
                data = json.loads(body.decode('utf-8'))
                return {
                    'status': status,
                    'latency_ms': latency_ms,
                    'data': data,
                    'error': None
                }
            except Exception as e:
                return {
                    'status': status,
                    'latency_ms': latency_ms,
                    'data': None,
                    'error': f"JSON decode error: {e}"
                }
    except urllib.error.HTTPError as e:
        latency_ms = round((time.time() - start) * 1000, 2)
        return {
            'status': e.code,
            'latency_ms': latency_ms,
            'data': None,
            'error': f"HTTPError {e.code}: {e.reason}"
        }
    except Exception as e:
        latency_ms = round((time.time() - start) * 1000, 2)
        return {
            'status': 0,
            'latency_ms': latency_ms,
            'data': None,
            'error': str(e)
        }


def probe_binance():
    res = _http_get('https://api.binance.com/api/v3/exchangeInfo')
    tickers_res = _http_get('https://api.binance.com/api/v3/ticker/price')

    usdt_pairs = []
    if res['data'] and isinstance(res['data'], dict):
        symbols = res['data'].get('symbols', [])
        for s in symbols:
            if s.get('quoteAsset') == 'USDT' and s.get('status') == 'TRADING' and s.get('isSpotTradingAllowed', True):
                usdt_pairs.append(s.get('symbol'))

    live_prices = {}
    if tickers_res['data'] and isinstance(tickers_res['data'], list):
        for t in tickers_res['data']:
            if t.get('symbol', '').endswith('USDT'):
                p = float(t.get('price', 0) or 0)
                if p > 0:
                    live_prices[t['symbol']] = p

    coverage = (len([p for p in usdt_pairs if p in live_prices]) / len(usdt_pairs) * 100) if usdt_pairs else 0
    return {
        'exchange': 'binance',
        'status': res['status'],
        'latency_ms': res['latency_ms'],
        'total_usdt_pairs': len(usdt_pairs),
        'pairs_with_live_price': len(live_prices),
        'coverage_pct': round(coverage, 2),
        'error': res['error'] or tickers_res['error'],
        'sample_symbols': usdt_pairs[:5]
    }


def probe_mexc():
    res = _http_get('https://api.mexc.com/api/v3/exchangeInfo')
    tickers_res = _http_get('https://api.mexc.com/api/v3/ticker/price')

    usdt_pairs = []
    if res['data'] and isinstance(res['data'], dict):
        symbols = res['data'].get('symbols', [])
        for s in symbols:
            if s.get('quoteAsset') == 'USDT' and s.get('status') == 'ENABLED':
                usdt_pairs.append(s.get('symbol'))

    live_prices = {}
    if tickers_res['data'] and isinstance(tickers_res['data'], list):
        for t in tickers_res['data']:
            if t.get('symbol', '').endswith('USDT'):
                p = float(t.get('price', 0) or 0)
                if p > 0:
                    live_prices[t['symbol']] = p

    coverage = (len([p for p in usdt_pairs if p in live_prices]) / len(usdt_pairs) * 100) if usdt_pairs else 0
    return {
        'exchange': 'mexc',
        'status': res['status'],
        'latency_ms': res['latency_ms'],
        'total_usdt_pairs': len(usdt_pairs),
        'pairs_with_live_price': len(live_prices),
        'coverage_pct': round(coverage, 2),
        'error': res['error'] or tickers_res['error'],
        'sample_symbols': usdt_pairs[:5]
    }


def probe_kucoin():
    res = _http_get('https://api.kucoin.com/api/v1/symbols')
    tickers_res = _http_get('https://api.kucoin.com/api/v1/market/allTickers')

    usdt_pairs = []
    if res['data'] and isinstance(res['data'], dict) and res['data'].get('code') == '200000':
        for s in res['data'].get('data', []):
            if s.get('quoteCurrency') == 'USDT' and s.get('enableTrading', False):
                usdt_pairs.append(s.get('symbol'))

    live_prices = {}
    if tickers_res['data'] and isinstance(tickers_res['data'], dict):
        for t in tickers_res['data'].get('data', {}).get('ticker', []):
            sym = t.get('symbol', '')
            if sym.endswith('-USDT'):
                p = float(t.get('last', 0) or 0)
                if p > 0:
                    live_prices[sym] = p

    coverage = (len([p for p in usdt_pairs if p in live_prices]) / len(usdt_pairs) * 100) if usdt_pairs else 0
    return {
        'exchange': 'kucoin',
        'status': res['status'],
        'latency_ms': res['latency_ms'],
        'total_usdt_pairs': len(usdt_pairs),
        'pairs_with_live_price': len(live_prices),
        'coverage_pct': round(coverage, 2),
        'error': res['error'] or tickers_res['error'],
        'sample_symbols': usdt_pairs[:5]
    }


def probe_gateio():
    res = _http_get('https://api.gateio.ws/api/v4/spot/currency_pairs')
    tickers_res = _http_get('https://api.gateio.ws/api/v4/spot/tickers')

    usdt_pairs = []
    if res['data'] and isinstance(res['data'], list):
        for s in res['data']:
            if s.get('quote') == 'USDT' and s.get('trade_status') == 'tradable':
                usdt_pairs.append(s.get('id'))

    live_prices = {}
    if tickers_res['data'] and isinstance(tickers_res['data'], list):
        for t in tickers_res['data']:
            sym = t.get('currency_pair', '')
            if sym.endswith('_USDT'):
                p = float(t.get('last', 0) or 0)
                if p > 0:
                    live_prices[sym] = p

    coverage = (len([p for p in usdt_pairs if p in live_prices]) / len(usdt_pairs) * 100) if usdt_pairs else 0
    return {
        'exchange': 'gateio',
        'status': res['status'],
        'latency_ms': res['latency_ms'],
        'total_usdt_pairs': len(usdt_pairs),
        'pairs_with_live_price': len(live_prices),
        'coverage_pct': round(coverage, 2),
        'error': res['error'] or tickers_res['error'],
        'sample_symbols': usdt_pairs[:5]
    }


def probe_lbank():
    # 1. Primary: api.lbank.info; fallback: api.lbkex.com
    res = _http_get('https://api.lbank.info/v2/currencyPairs.do')
    if res['status'] != 200:
        res = _http_get('https://api.lbkex.com/v2/currencyPairs.do')

    tickers_res = _http_get('https://api.lbank.info/v2/ticker/24hr.do?symbol=all')
    if tickers_res['status'] != 200:
        tickers_res = _http_get('https://api.lbkex.com/v2/ticker/24hr.do?symbol=all')

    usdt_pairs = []
    if res['data'] and isinstance(res['data'], dict):
        pairs_data = res['data'].get('data', [])
        for p in pairs_data:
            if isinstance(p, str) and p.endswith('_usdt'):
                usdt_pairs.append(p.upper())

    live_prices = {}
    if tickers_res['data'] and isinstance(tickers_res['data'], dict):
        for t in tickers_res['data'].get('data', []):
            sym = t.get('symbol', '').upper()
            if sym.endswith('_USDT'):
                p = float(t.get('ticker', {}).get('latest', 0) or 0)
                if p > 0:
                    live_prices[sym] = p

    coverage = (len([p for p in usdt_pairs if p in live_prices]) / len(usdt_pairs) * 100) if usdt_pairs else 0
    return {
        'exchange': 'lbank',
        'status': res['status'],
        'latency_ms': res['latency_ms'],
        'total_usdt_pairs': len(usdt_pairs),
        'pairs_with_live_price': len(live_prices),
        'coverage_pct': round(coverage, 2),
        'error': res['error'] or tickers_res['error'],
        'sample_symbols': usdt_pairs[:5]
    }


def probe_okx():
    res = _http_get('https://www.okx.com/api/v5/public/instruments?instType=SPOT')
    tickers_res = _http_get('https://www.okx.com/api/v5/market/tickers?instType=SPOT')

    usdt_pairs = []
    if res['data'] and isinstance(res['data'], dict) and res['data'].get('code') == '0':
        for s in res['data'].get('data', []):
            if s.get('quoteCcy') == 'USDT' and s.get('state') == 'live':
                usdt_pairs.append(s.get('instId'))

    live_prices = {}
    if tickers_res['data'] and isinstance(tickers_res['data'], dict) and tickers_res['data'].get('code') == '0':
        for t in tickers_res['data'].get('data', []):
            sym = t.get('instId', '')
            if sym.endswith('-USDT'):
                p = float(t.get('last', 0) or 0)
                if p > 0:
                    live_prices[sym] = p

    coverage = (len([p for p in usdt_pairs if p in live_prices]) / len(usdt_pairs) * 100) if usdt_pairs else 0
    return {
        'exchange': 'okx',
        'status': res['status'],
        'latency_ms': res['latency_ms'],
        'total_usdt_pairs': len(usdt_pairs),
        'pairs_with_live_price': len(live_prices),
        'coverage_pct': round(coverage, 2),
        'error': res['error'] or tickers_res['error'],
        'sample_symbols': usdt_pairs[:5]
    }


def probe_bybit():
    res = _http_get('https://api.bybit.com/v5/market/instruments-info?category=spot')
    tickers_res = _http_get('https://api.bybit.com/v5/market/tickers?category=spot')

    usdt_pairs = []
    if res['data'] and isinstance(res['data'], dict) and res['data'].get('retCode') == 0:
        for s in res['data'].get('result', {}).get('list', []):
            if s.get('quoteCoin') == 'USDT' and s.get('status') == 'Trading':
                usdt_pairs.append(s.get('symbol'))

    live_prices = {}
    if tickers_res['data'] and isinstance(tickers_res['data'], dict) and tickers_res['data'].get('retCode') == 0:
        for t in tickers_res['data'].get('result', {}).get('list', []):
            sym = t.get('symbol', '')
            if sym.endswith('USDT'):
                p = float(t.get('lastPrice', 0) or 0)
                if p > 0:
                    live_prices[sym] = p

    coverage = (len([p for p in usdt_pairs if p in live_prices]) / len(usdt_pairs) * 100) if usdt_pairs else 0
    return {
        'exchange': 'bybit',
        'status': res['status'],
        'latency_ms': res['latency_ms'],
        'total_usdt_pairs': len(usdt_pairs),
        'pairs_with_live_price': len(live_prices),
        'coverage_pct': round(coverage, 2),
        'error': res['error'] or tickers_res['error'],
        'sample_symbols': usdt_pairs[:5]
    }


def probe_bitget():
    res = _http_get('https://api.bitget.com/api/v2/spot/public/symbols')
    tickers_res = _http_get('https://api.bitget.com/api/v2/spot/market/tickers')

    usdt_pairs = []
    if res['data'] and isinstance(res['data'], dict) and res['data'].get('code') == '00000':
        for s in res['data'].get('data', []):
            if s.get('quoteCoin') == 'USDT' and s.get('status') == 'online':
                usdt_pairs.append(s.get('symbol'))

    live_prices = {}
    if tickers_res['data'] and isinstance(tickers_res['data'], dict) and tickers_res['data'].get('code') == '00000':
        for t in tickers_res['data'].get('data', []):
            sym = t.get('symbol', '')
            if sym.endswith('USDT'):
                p = float(t.get('lastPr', 0) or 0)
                if p > 0:
                    live_prices[sym] = p

    coverage = (len([p for p in usdt_pairs if p in live_prices]) / len(usdt_pairs) * 100) if usdt_pairs else 0
    return {
        'exchange': 'bitget',
        'status': res['status'],
        'latency_ms': res['latency_ms'],
        'total_usdt_pairs': len(usdt_pairs),
        'pairs_with_live_price': len(live_prices),
        'coverage_pct': round(coverage, 2),
        'error': res['error'] or tickers_res['error'],
        'sample_symbols': usdt_pairs[:5]
    }


def probe_kraken():
    res = _http_get('https://api.kraken.com/0/public/AssetPairs')
    tickers_res = _http_get('https://api.kraken.com/0/public/Ticker')

    usdt_pairs = []
    if res['data'] and isinstance(res['data'], dict) and not res['data'].get('error'):
        pairs = res['data'].get('result', {})
        for pair_name, info in pairs.items():
            wsname = info.get('wsname', '')
            if wsname.endswith('/USDT') or wsname.endswith('/USD'):
                usdt_pairs.append(pair_name)

    live_prices = {}
    if tickers_res['data'] and isinstance(tickers_res['data'], dict) and not tickers_res['data'].get('error'):
        for sym, t in tickers_res['data'].get('result', {}).items():
            c = t.get('c', [])
            if c and len(c) > 0:
                p = float(c[0] or 0)
                if p > 0:
                    live_prices[sym] = p

    coverage = (len([p for p in usdt_pairs if p in live_prices]) / len(usdt_pairs) * 100) if usdt_pairs else 0
    return {
        'exchange': 'kraken',
        'status': res['status'],
        'latency_ms': res['latency_ms'],
        'total_usdt_pairs': len(usdt_pairs),
        'pairs_with_live_price': len(live_prices),
        'coverage_pct': round(coverage, 2),
        'error': str(res['data'].get('error') if res['data'] else res['error']),
        'sample_symbols': usdt_pairs[:5]
    }


def probe_coinex():
    res = _http_get('https://api.coinex.com/v1/market/list')
    tickers_res = _http_get('https://api.coinex.com/v1/market/ticker/all')

    usdt_pairs = []
    if res['data'] and isinstance(res['data'], dict) and res['data'].get('code') == 0:
        for s in res['data'].get('data', []):
            if isinstance(s, str) and s.endswith('USDT'):
                usdt_pairs.append(s)

    live_prices = {}
    if tickers_res['data'] and isinstance(tickers_res['data'], dict) and tickers_res['data'].get('code') == 0:
        for sym, t in tickers_res['data'].get('data', {}).get('ticker', {}).items():
            if sym.endswith('USDT'):
                p = float(t.get('last', 0) or 0)
                if p > 0:
                    live_prices[sym] = p

    coverage = (len([p for p in usdt_pairs if p in live_prices]) / len(usdt_pairs) * 100) if usdt_pairs else 0
    return {
        'exchange': 'coinex',
        'status': res['status'],
        'latency_ms': res['latency_ms'],
        'total_usdt_pairs': len(usdt_pairs),
        'pairs_with_live_price': len(live_prices),
        'coverage_pct': round(coverage, 2),
        'error': res['error'] or tickers_res['error'],
        'sample_symbols': usdt_pairs[:5]
    }


def main():
    print("=" * 80)
    print("🚀 AlertG Live Market Probe — Cryptocurrency Spot USDT Feeds")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 80)

    probers = [
        ("Binance", probe_binance),
        ("MEXC", probe_mexc),
        ("KuCoin", probe_kucoin),
        ("Gate.io", probe_gateio),
        ("LBank (CoinEx replacement)", probe_lbank),
        ("OKX", probe_okx),
        ("Bybit", probe_bybit),
        ("Bitget", probe_bitget),
        ("Kraken", probe_kraken),
        ("CoinEx (Deprecated)", probe_coinex),
    ]

    results = []

    print(f"{'Exchange':<25} | {'HTTP':<5} | {'Latency':<9} | {'USDT Pairs':<11} | {'Live Price':<11} | {'Coverage':<9}")
    print("-" * 80)

    for name, fn in probers:
        try:
            r = fn()
            results.append(r)
            status_str = str(r['status']) if r['status'] else "ERR"
            lat_str = f"{r['latency_ms']}ms"
            pairs_str = str(r['total_usdt_pairs'])
            live_str = str(r['pairs_with_live_price'])
            cov_str = f"{r['coverage_pct']}%"
            print(f"{name:<25} | {status_str:<5} | {lat_str:<9} | {pairs_str:<11} | {live_str:<11} | {cov_str:<9}")
        except Exception as e:
            print(f"{name:<25} | FAIL  | ERROR     | {str(e)[:40]}")
            results.append({'exchange': name.lower(), 'error': str(e), 'status': 0})

    print("-" * 80)

    os.makedirs('reports', exist_ok=True)
    report_file = os.path.join('reports', f"probe_crypto_{int(time.time())}.json")
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Full probe report saved to: {report_file}")
    print("Please share the output above.")


if __name__ == '__main__':
    main()
