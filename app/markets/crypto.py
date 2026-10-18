from typing import List, Dict, Any, Optional
import httpx
from app.markets.common import normalize_symbol

async def fetch_crypto(
    client: httpx.AsyncClient,
    exchange: str,
    symbol: str,
    _try_fetch,
    traces: List[Dict[str, Any]],
    collect_all_traces: bool
) -> Optional[float]:
    ex = (exchange or '').lower()
    sym_clean = normalize_symbol(symbol)

    # 2c. DEX (DexScreener & GeckoTerminal On-Chain Tokens)
    if ex in ['dex', 'dexscreener', 'geckoterminal']:
        def _extract_dexscreener(data):
            if isinstance(data, dict):
                pairs = data.get('pairs', [])
                if pairs and len(pairs) > 0:
                    p = pairs[0].get('priceUsd')
                    if p and float(p) > 0:
                        return {'price': float(p), 'state': 'LIVE', 'currency': 'USD'}
            return None

        clean_dex_sym = sym_clean.lower()
        if clean_dex_sym.startswith('0x') or len(clean_dex_sym) >= 32:
            p = await _try_fetch('DexScreener Tokens API', f'https://api.dexscreener.com/latest/dex/tokens/{clean_dex_sym}', _extract_dexscreener)
        else:
            p = await _try_fetch('DexScreener Search API', f'https://api.dexscreener.com/latest/dex/search?q={sym_clean}', _extract_dexscreener)
        if p and not collect_all_traces: return p

        def _extract_geckoterminal(data):
            if isinstance(data, dict):
                attrs = data.get('data', {}).get('attributes', {})
                prices = attrs.get('token_prices', {})
                if prices:
                    first_p = next(iter(prices.values()), None)
                    if first_p and float(first_p) > 0:
                        return {'price': float(first_p), 'state': 'LIVE', 'currency': 'USD'}
            return None

        if clean_dex_sym.startswith('0x'):
            p = await _try_fetch('GeckoTerminal Token API', f'https://api.geckoterminal.com/api/v2/simple/networks/eth/token_price/{clean_dex_sym}', _extract_geckoterminal)
            if p and not collect_all_traces: return p
        return None

    # 3. GLOBAL CRYPTO (Binance, MEXC, KuCoin, Gate.io, CoinEx)
    crypto_sym = sym_clean
    if not any(crypto_sym.endswith(q) for q in ['USDT', 'BUSD', 'USDC', 'BTC', 'ETH', 'EUR', 'USD']):
        crypto_sym = crypto_sym + 'USDT'

    kucoin_sym = f"{crypto_sym[:-4]}-USDT" if crypto_sym.endswith('USDT') else crypto_sym
    gate_sym = f"{crypto_sym[:-4]}_USDT" if crypto_sym.endswith('USDT') else crypto_sym

    # Providers definitions
    async def _fetch_binance():
        return await _try_fetch(
            'Binance Spot API',
            f'https://api.binance.com/api/v3/ticker/price?symbol={crypto_sym}',
            lambda d: {'price': float(d.get('price')), 'state': 'LIVE', 'currency': 'USDT'} if isinstance(d, dict) and d.get('price') else None
        )

    async def _fetch_mexc():
        return await _try_fetch(
            'MEXC Spot API',
            f'https://api.mexc.com/api/v3/ticker/price?symbol={crypto_sym}',
            lambda d: {'price': float(d.get('price')), 'state': 'LIVE', 'currency': 'USDT'} if isinstance(d, dict) and d.get('price') else None
        )

    async def _fetch_kucoin():
        return await _try_fetch(
            'KuCoin Spot API',
            f'https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={kucoin_sym}',
            lambda d: {'price': float(d.get('data', {}).get('price')), 'state': 'LIVE', 'currency': 'USDT'} if isinstance(d, dict) and d.get('data', {}).get('price') else None
        )

    async def _fetch_gateio():
        return await _try_fetch(
            'Gate.io Spot API',
            f'https://api.gateio.ws/api/v4/spot/tickers?currency_pair={gate_sym}',
            lambda d: {'price': float(d[0].get('last')), 'state': 'LIVE', 'currency': 'USDT'} if isinstance(d, list) and len(d) > 0 and d[0].get('last') else None
        )

    async def _fetch_coinex():
        return await _try_fetch(
            'CoinEx Spot API',
            f'https://api.coinex.com/v1/market/ticker?market={crypto_sym}',
            lambda d: {'price': float(d.get('data', {}).get('ticker', {}).get('last')), 'state': 'LIVE', 'currency': 'USDT'} if isinstance(d, dict) and d.get('data', {}).get('ticker', {}).get('last') else None
        )

    providers = [
        ('binance', _fetch_binance),
        ('mexc', _fetch_mexc),
        ('kucoin', _fetch_kucoin),
        ('gateio', _fetch_gateio),
        ('coinex', _fetch_coinex),
    ]

    # Prioritize selected exchange if specified
    if ex in ['mexc']:
        providers.sort(key=lambda x: 0 if x[0] == 'mexc' else 1)
    elif ex in ['kucoin']:
        providers.sort(key=lambda x: 0 if x[0] == 'kucoin' else 1)
    elif ex in ['gateio', 'gate']:
        providers.sort(key=lambda x: 0 if x[0] == 'gateio' else 1)
    elif ex in ['coinex']:
        providers.sort(key=lambda x: 0 if x[0] == 'coinex' else 1)
    elif ex in ['binance']:
        providers.sort(key=lambda x: 0 if x[0] == 'binance' else 1)

    for _, fetch_func in providers:
        p = await fetch_func()
        if p and not collect_all_traces:
            return p

    return None
