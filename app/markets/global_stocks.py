import time
import random
import asyncio
from typing import Dict, Any, List, Optional, Tuple
import httpx

from app.config import (
    APP_VERSION,
    FINNHUB_API_KEY,
    TWELVE_DATA_API_KEY,
    FRED_API_KEY,
)
from app.markets.common import normalize_symbol
from app.markets.limiter import record_provider_metric, acquire_provider_slot
from app.state import METRICS


# ===================================================================
# 1. EXACT MAPS & SYMBOL RESOLUTION (PRESERVED 100%)
# ===================================================================
EXACT_YF_MAP: Dict[str, str] = {
    'DXY': 'DX-Y.NYB',
    'DX-Y.NYB': 'DX-Y.NYB',
    'USDX': 'DX-Y.NYB',
    'US10Y': '^TNX',
    '^TNX': '^TNX',
    'TNX': '^TNX',
    'US13W': '^IRX',
    '^IRX': '^IRX',
    'VIX': '^VIX',
    '^VIX': '^VIX',
    'SPX': '^GSPC',
    'SP500': '^GSPC',
    '^GSPC': '^GSPC',
    'NDX': '^NDX',
    'NASDAQ': '^NDX',
    '^NDX': '^NDX',
    'DJI': '^DJI',
    'DOW': '^DJI',
    '^DJI': '^DJI',
    'RUT': '^RUT',
    '^RUT': '^RUT',
    'DAX': '^GDAXI',
    '^GDAXI': '^GDAXI',
    'FTSE': '^FTSE',
    '^FTSE': '^FTSE',
    'CAC40': '^FCHI',
    '^FCHI': '^FCHI',
    'NIKKEI': '^N225',
    '^N225': '^N225',
    'NIFTY': '^NSEI',
    'NIFTY50': '^NSEI',
    '^NSEI': '^NSEI',
    'KOSPI': '^KS11',
    '^KS11': '^KS11',
    'GOLD': 'GC=F',
    'XAU': 'GC=F',
    'XAUUSD': 'GC=F',
    'GC=F': 'GC=F',
    'SILVER': 'SI=F',
    'XAG': 'SI=F',
    'XAGUSD': 'SI=F',
    'SI=F': 'SI=F',
    'BRENT': 'BZ=F',
    'OILBRENT': 'BZ=F',
    'BZ=F': 'BZ=F',
    'WTI': 'CL=F',
    'OILWTI': 'CL=F',
    'OIL': 'CL=F',
    'CRUDE': 'CL=F',
    'CL=F': 'CL=F',
    'NATGAS': 'NG=F',
    'NG=F': 'NG=F',
    'COPPER': 'HG=F',
    'HG=F': 'HG=F',
    'PLATINUM': 'PL=F',
    'PL=F': 'PL=F',
    'BTC.D': 'BTC.D',
    'USDT.D': 'USDT.D',
    'ETH.D': 'ETH.D',
    'TOTAL': 'TOTAL',
    'TOTAL2': 'TOTAL2',
    'TOTAL3': 'TOTAL3',
    'CRYPTO_FGI': 'CRYPTO_FGI',
}

FOREX_PAIRS = {
    'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD',
    'EURGBP', 'EURJPY', 'GBPJPY', 'EURCHF', 'AUDJPY', 'GBPAUD', 'USDCNY',
    'USDTRY', 'USDMXN', 'USDZAR', 'EURCAD', 'EURAUD'
}

# 2-year Treasury yield exists only on FRED (DGS2). Yahoo's ^IRX is the 13-week bill, never a 2Y proxy.
FRED_ONLY_SYMBOLS = frozenset({'US02Y', 'US2Y', '^2YY'})


def resolve_yf_symbol(symbol: str) -> str:
    """
    Standardizes user/UI symbols into clean Yahoo Finance query symbols:
    - Strips /USD, -USD, USD quote suffixes from stock pairs (AAPL/USD -> AAPL)
    - Preserves share classes with dash (BRK-B) and foreign exchanges with dot (7203.T)
    - Maps major Forex pairs to {PAIR}=X (EUR/USD -> EURUSD=X)
    - Resolves Macro, Yields & Commodities to exact futures tickers
    """
    s = (symbol or '').upper().strip()

    # 0. Already standard Yahoo format with =X
    if s.endswith('=X'):
        return s

    s_clean = s.replace('/', '').replace(' ', '')

    # 1. Exact map check (handles XAUUSD -> GC=F, DXY -> DX-Y.NYB, etc.)
    if s in EXACT_YF_MAP:
        return EXACT_YF_MAP[s]
    if s_clean in EXACT_YF_MAP:
        return EXACT_YF_MAP[s_clean]

    # 2. Forex pair check (BEFORE any quote stripping so EURUSD is never stripped to EUR!)
    if s_clean in FOREX_PAIRS:
        return f'{s_clean}=X'

    # 3. Explicit pair with slash (e.g. AAPL/USD -> AAPL, EUR/USD -> handled in forex or base)
    if '/' in s:
        base, quote = s.split('/', 1)
        base = base.strip()
        quote = quote.strip()
        pair_candidate = f'{base}{quote}'
        if pair_candidate in EXACT_YF_MAP:
            return EXACT_YF_MAP[pair_candidate]
        if pair_candidate in FOREX_PAIRS:
            return f'{pair_candidate}=X'
        return EXACT_YF_MAP.get(base, base)

    # 4. Trailing USD or USDT on equities (e.g. TSLAUSD -> TSLA, AAPLUSDT -> AAPL)
    # Notice: Do NOT strip if starts with ^ or contains dot (7203.T) or dash (BRK-B)
    if not s.startswith('^') and '.' not in s and '-' not in s:
        for q in ['USDT', 'USD']:
            if s.endswith(q) and len(s) > len(q):
                candidate = s[:-len(q)]
                if candidate in EXACT_YF_MAP:
                    return EXACT_YF_MAP[candidate]
                return candidate

    return s

WALLSTREET_MACRO_SYMBOLS = [
    {"id": "GOLD18_BONBAST", "symbol": "GOLD18", "nameEn": "Gold 18K (Gram)", "nameFa": "طلای ۱۸ عیار - هر گرم (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "MITHQAL_BONBAST", "symbol": "MITHQAL", "nameEn": "Gold Mithqal (Melted)", "nameFa": "مظنه آبشده / مثقال طلا تهران (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "EMAMI_BONBAST", "symbol": "EMAMI", "nameEn": "Emami Gold Coin", "nameFa": "سکه تمام طرح جدید / امامی (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "BAHAR_BONBAST", "symbol": "AZADI", "nameEn": "Bahar Azadi Coin", "nameFa": "سکه تمام بهار آزادی طرح قدیم (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "HALF_BONBAST", "symbol": "HALF", "nameEn": "Half Azadi Coin", "nameFa": "نیم‌سکه بهار آزادی (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "QUARTER_BONBAST", "symbol": "QUARTER", "nameEn": "Quarter Azadi Coin", "nameFa": "ربع‌سکه بهار آزادی (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "GRAM_BONBAST", "symbol": "GRAM", "nameEn": "Central Bank Gram Coin", "nameFa": "سکه یک گرمی بانک مرکزی (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "USD_BONBAST", "symbol": "USD/TMN", "nameEn": "US Dollar (Tehran Cash)", "nameFa": "دلار آزاد تهران - اسکناس (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "EUR_BONBAST", "symbol": "EUR/TMN", "nameEn": "Euro Cash", "nameFa": "یورو آزاد تهران - اسکناس (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "AED_BONBAST", "symbol": "AED/TMN", "nameEn": "UAE Dirham Cash", "nameFa": "درهم امارات - اسکناس/حواله (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "GBP_BONBAST", "symbol": "GBP/TMN", "nameEn": "British Pound Cash", "nameFa": "پوند انگلیس - اسکناس (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "TRY_BONBAST", "symbol": "TRY/TMN", "nameEn": "Turkish Lira", "nameFa": "لیر ترکیه (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "IQD_BONBAST", "symbol": "IQD/TMN", "nameEn": "Iraqi Dinar (100)", "nameFa": "۱۰۰ دینار عراق (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "BOURSE_BONBAST", "symbol": "TEDPIX", "nameEn": "Tehran Stock Exchange Index", "nameFa": "شاخص کل بورس اوراق بهادار تهران (TEDPIX)", "category": "iran_market", "marketName": "بورس تهران (مرجع بن‌بست)", "unit": "واحد"},
    {"id": "AFN_BONBAST", "symbol": "AFN/TMN", "nameEn": "Afghan Afghani (Herat)", "nameFa": "افغانی افغانستان - بازار هرات (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "CAD_BONBAST", "symbol": "CAD/TMN", "nameEn": "Canadian Dollar Cash", "nameFa": "دلار کانادا - اسکناس آزاد (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "AUD_BONBAST", "symbol": "AUD/TMN", "nameEn": "Australian Dollar Cash", "nameFa": "دلار استرالیا - اسکناس آزاد (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "CHF_BONBAST", "symbol": "CHF/TMN", "nameEn": "Swiss Franc Cash", "nameFa": "فرانک سوئیس - اسکناس آزاد (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "CNY_BONBAST", "symbol": "CNY/TMN", "nameEn": "Chinese Yuan Cash", "nameFa": "یوان چین - اسکناس آزاد (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "KWD_BONBAST", "symbol": "KWD/TMN", "nameEn": "Kuwaiti Dinar", "nameFa": "دینار کویت (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "SAR_BONBAST", "symbol": "SAR/TMN", "nameEn": "Saudi Riyal Cash", "nameFa": "ریال عربستان (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "QAR_BONBAST", "symbol": "QAR/TMN", "nameEn": "Qatari Riyal Cash", "nameFa": "ریال قطر (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "OMR_BONBAST", "symbol": "OMR/TMN", "nameEn": "Omani Rial Cash", "nameFa": "ریال عمان (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "JPY_BONBAST", "symbol": "JPY/TMN", "nameEn": "Japanese Yen (10)", "nameFa": "۱۰ ین ژاپن (مرجع بن‌بست)", "category": "iran_market", "marketName": "بن‌بست (bonbast.com)", "unit": "ت"},
    {"id": "US10Y", "symbol": "US10Y (^TNX)", "nameEn": "US 10-Year Treasury Yield", "nameFa": "بازده اوراق قرضه ۱۰ ساله آمریکا (US10Y)", "category": "bond", "marketName": "US Treasury", "unit": "%"},
    {"id": "US02Y", "symbol": "US02Y (DGS2)", "nameEn": "US 2-Year Treasury Yield", "nameFa": "بازده اوراق قرضه ۲ ساله آمریکا (US02Y)", "category": "bond", "marketName": "US Treasury", "unit": "%"},
    {"id": "US13W", "symbol": "US13W (^IRX)", "nameEn": "US 13-Week Treasury Bill Yield", "nameFa": "بازده اوراق ۱۳ هفته‌ای خزانه‌داری آمریکا (US13W)", "category": "bond", "marketName": "US Treasury", "unit": "%"},
    {"id": "US30Y", "symbol": "US30Y (^TYX)", "nameEn": "US 30-Year Treasury Bond", "nameFa": "بازده اوراق قرضه ۳۰ ساله آمریکا (US30Y)", "category": "bond", "marketName": "US Treasury", "unit": "%"},
    {"id": "EURUSD", "symbol": "EUR/USD", "nameEn": "Euro / US Dollar", "nameFa": "یورو به دلار آمریکا (EUR/USD)", "category": "forex", "marketName": "Forex Major", "unit": "$"},
    {"id": "GBPUSD", "symbol": "GBP/USD", "nameEn": "British Pound / US Dollar", "nameFa": "پوند انگلیس به دلار (GBP/USD)", "category": "forex", "marketName": "Forex Major", "unit": "$"},
    {"id": "USDJPY", "symbol": "USD/JPY", "nameEn": "US Dollar / Japanese Yen", "nameFa": "دلار به ین ژاپن (USD/JPY)", "category": "forex", "marketName": "Forex Major", "unit": "¥"},
    {"id": "USDCHF", "symbol": "USD/CHF", "nameEn": "US Dollar / Swiss Franc", "nameFa": "دلار به فرانک سوئیس (USD/CHF)", "category": "forex", "marketName": "Forex Major", "unit": "Fr"},
    {"id": "AUDUSD", "symbol": "AUD/USD", "nameEn": "Australian Dollar / USD", "nameFa": "دلار استرالیا به دلار آمریکا (AUD/USD)", "category": "forex", "marketName": "Forex Major", "unit": "$"},
    {"id": "USDCAD", "symbol": "USD/CAD", "nameEn": "US Dollar / Canadian Dollar", "nameFa": "دلار آمریکا به دلار کانادا (USD/CAD)", "category": "forex", "marketName": "Forex Major", "unit": "C$"},
    {"id": "NVDA", "symbol": "NVDA", "nameEn": "NVIDIA Corporation", "nameFa": "سهام انویدیا (NVIDIA)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "AAPL", "symbol": "AAPL", "nameEn": "Apple Inc.", "nameFa": "سهام اپل (Apple)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "MSFT", "symbol": "MSFT", "nameEn": "Microsoft Corporation", "nameFa": "سهام مایکروسافت (Microsoft)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "AMZN", "symbol": "AMZN", "nameEn": "Amazon.com Inc.", "nameFa": "سهام آمازون (Amazon)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "GOOGL", "symbol": "GOOGL", "nameEn": "Alphabet Inc. (Google)", "nameFa": "سهام گوگل (آلفابت)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "META", "symbol": "META", "nameEn": "Meta Platforms (Facebook)", "nameFa": "سهام متا (فیسبوک)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "PLTR", "symbol": "PLTR", "nameEn": "Palantir Technologies", "nameFa": "سهام پالانتیر (Palantir)", "category": "stock", "marketName": "NYSE", "unit": "$"},
    {"id": "BRKB", "symbol": "BRK.B", "nameEn": "Berkshire Hathaway", "nameFa": "برکشایر هاتاوی (وارن بافت)", "category": "stock", "marketName": "NYSE", "unit": "$"},
    {"id": "TSLA", "symbol": "TSLA", "nameEn": "Tesla Inc.", "nameFa": "سهام تسلا (خودروهای برقی، هوش مصنوعی، ربات اپتیموس و انرژی ایلان ماسک)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "SPACEX", "symbol": "SPACEX", "nameEn": "SpaceX (Starship & Space Exploration)", "nameFa": "اسپیس‌ایکس (فناوری‌های فضایی، استارشیپ و ماموریت‌های مریخ ایلان ماسک)", "category": "stock", "marketName": "Pre-IPO Benchmark", "unit": "$"},
    {"id": "STARLINK", "symbol": "STARLINK", "nameEn": "Starlink (SpaceX Satellite Constellation)", "nameFa": "استارلینک (شبکه اینترنت ماهواره‌ای جهانی ایلان ماسک)", "category": "stock", "marketName": "Pre-IPO Benchmark", "unit": "$"},
    {"id": "XAI", "symbol": "XAI", "nameEn": "xAI (Grok AI & Colossus)", "nameFa": "شرکت هوش مصنوعی xAI (خالق Grok و سوپرکامپیوتر کلوسوس ایلان ماسک)", "category": "stock", "marketName": "Pre-IPO Benchmark", "unit": "$"},
    {"id": "X_CORP", "symbol": "X_CORP", "nameEn": "X Corp (Twitter - Everything App)", "nameFa": "ایکس / توییتر سابق (شبکه اجتماعی جهانی و اپلیکیشن همه‌کاره ایلان ماسک)", "category": "stock", "marketName": "Pre-IPO Benchmark", "unit": "$"},
    {"id": "NEURALINK", "symbol": "NEURALINK", "nameEn": "Neuralink (Brain-Computer Interface)", "nameFa": "نورالینک (تراشه رابط مغز و رایانه و تله‌پاتی ایلان ماسک)", "category": "stock", "marketName": "Pre-IPO Benchmark", "unit": "$"},
    {"id": "BORING", "symbol": "BORING", "nameEn": "The Boring Company (Hyperloop & Tunneling)", "nameFa": "بورینگ کمپانی (تونل‌های زیرزمینی حمل‌ونقل سریع هایپرلوپ ایلان ماسک)", "category": "stock", "marketName": "Pre-IPO Benchmark", "unit": "$"},
    {"id": "DOGE_MUSK", "symbol": "DOGE", "nameEn": "Dogecoin (Elon Musk Ecosystem Crypto)", "nameFa": "دوج‌کوین (رمزارز محبوب و رسمی اکوسیستم تسلا و پلتفرم ایکس)", "category": "stock", "marketName": "Musk Ecosystem", "unit": "$"},
    {"id": "DXYZ", "symbol": "DXYZ", "nameEn": "Destiny Tech100 (SpaceX & OpenAI ETF)", "nameFa": "صندوق سرنوشت ۱۰۰ (سبد سهام عمومی اسپیس‌ایکس و اوپن‌ای‌آی)", "category": "stock", "marketName": "NYSE", "unit": "$"},
    {"id": "RKLB", "symbol": "RKLB", "nameEn": "Rocket Lab USA", "nameFa": "راکت لب (پرتاب‌های فضایی مداری تجاری و ماهواره‌های ناسا)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "ASTS", "symbol": "ASTS", "nameEn": "AST SpaceMobile", "nameFa": "ای‌اس‌تی اسپیس‌موبایل (شبکه پهن‌باند ماهواره‌ای به گوشی هوشمند)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "BA", "symbol": "BA", "nameEn": "The Boeing Company", "nameFa": "بوئینگ (غول هواپیماسازی، فضاپیما و کپسول فضایی استارلاینر)", "category": "stock", "marketName": "NYSE", "unit": "$"},
    {"id": "TSM", "symbol": "TSM", "nameEn": "Taiwan Semiconductor Manufacturing (TSMC)", "nameFa": "تی‌اس‌ام‌سی (سازنده انحصاری تراشه‌های پیشرفته جهان)", "category": "stock", "marketName": "NYSE", "unit": "$"},
    {"id": "ASML", "symbol": "ASML", "nameEn": "ASML Holding N.V.", "nameFa": "ای‌اس‌ام‌ال هلند (انحصار ۱۰۰٪ ماشین‌آلات لیتوگرافی فرابنفش چاپ تراشه)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "AMD", "symbol": "AMD", "nameEn": "Advanced Micro Devices Inc.", "nameFa": "ای‌ام‌دی (پردازنده‌های هوش مصنوعی و کارت‌های گرافیک)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "AVGO", "symbol": "AVGO", "nameEn": "Broadcom Inc.", "nameFa": "برودکام (غول تراشه‌های شبکه و هوش مصنوعی اختصاصی)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "LVMH", "symbol": "MC.PA", "nameEn": "LVMH Moët Hennessy Louis Vuitton", "nameFa": "ال‌وی‌ام‌اچ فرانسه (لویی ویتون، دیور، تیفانی، بولگاری - پادشاه برندهای لوکس)", "category": "stock", "marketName": "Euronext Paris", "unit": "€"},
    {"id": "HERMES", "symbol": "RMS.PA", "nameEn": "Hermès International", "nameFa": "هرمس فرانسه (گران‌قیمت‌ترین خانه مد، کیف برکین و چرم دست‌ساز)", "category": "stock", "marketName": "Euronext Paris", "unit": "€"},
    {"id": "PORSCHE", "symbol": "P911.DE", "nameEn": "Porsche AG", "nameFa": "پورشه آلمان (سوپراسپرت‌های لوکس اشتوتگارت)", "category": "stock", "marketName": "XETRA", "unit": "€"},
    {"id": "USDT_TMN", "symbol": "USDT/TMN", "nameEn": "Tether / Iranian Toman", "nameFa": "تتر به تومان ایران (نرخ لحظه‌ای بازار آزاد تهران)", "category": "forex", "marketName": "Tehran Free Market", "unit": "ت"},
    {"id": "USD_AED", "symbol": "USD/AED", "nameEn": "US Dollar / UAE Dirham", "nameFa": "دلار آمریکا به درهم امارات (USD/AED)", "category": "forex", "marketName": "Forex Major", "unit": "AED"},
    {"id": "USD_CNY", "symbol": "USD/CNY", "nameEn": "US Dollar / Chinese Yuan", "nameFa": "دلار آمریکا به یوان چین (USD/CNY)", "category": "forex", "marketName": "Forex Major", "unit": "¥"},
    {"id": "OPENAI", "symbol": "OPENAI", "nameEn": "OpenAI (ChatGPT & Frontier AI)", "nameFa": "اوپن‌ای‌آی (خالق چت‌جی‌پی‌تی و پیشتاز هوش مصنوعی عمومی AGI)", "category": "stock", "marketName": "Pre-IPO Benchmark", "unit": "$"},
    {"id": "ANTHROPIC", "symbol": "ANTHROPIC", "nameEn": "Anthropic (Claude AI)", "nameFa": "انتروپیک (خالق هوش مصنوعی کلود Claude)", "category": "stock", "marketName": "Pre-IPO Benchmark", "unit": "$"},
    {"id": "STRIPE", "symbol": "STRIPE", "nameEn": "Stripe Payments", "nameFa": "استریپ (زیرساخت پرداخت اینترنتی و تسویه رمزارزی جهان)", "category": "stock", "marketName": "Pre-IPO Benchmark", "unit": "$"},
    {"id": "BYTEDANCE", "symbol": "BYTEDANCE", "nameEn": "ByteDance (TikTok)", "nameFa": "بایت‌دنس (مالک تیک‌تاک و غول الگوریتم‌های هوش مصنوعی)", "category": "stock", "marketName": "Pre-IPO Benchmark", "unit": "$"},
    {"id": "MSTR", "symbol": "MSTR", "nameEn": "MicroStrategy Inc.", "nameFa": "میکرواستراتژی (بزرگ‌ترین خزانه‌داری بیت‌کوین سازمانی)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "COIN", "symbol": "COIN", "nameEn": "Coinbase Global Inc.", "nameFa": "کوین‌بیس (بزرگ‌ترین صرافی مجاز کریپتو آمریکا)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "MARA", "symbol": "MARA", "nameEn": "MARA Holdings (Marathon)", "nameFa": "ماراتون دیجیتال / MARA (بزرگ‌ترین استخراج‌کننده بیت‌کوین)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "RIOT", "symbol": "RIOT", "nameEn": "Riot Platforms Inc.", "nameFa": "رایوت پلتفرمز (زیرساخت استخراج و مزارع بیت‌کوین)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "CLSK", "symbol": "CLSK", "nameEn": "CleanSpark Inc.", "nameFa": "کلین‌اسپارک (استخراج سبز و پربازده بیت‌کوین)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "HOOD", "symbol": "HOOD", "nameEn": "Robinhood Markets", "nameFa": "رابین‌هود (کارگزاری معامله سهام و رمزارز)", "category": "stock", "marketName": "NASDAQ", "unit": "$"},
    {"id": "RDDT", "symbol": "RDDT", "nameEn": "Reddit Inc.", "nameFa": "ردیت (انجمن وب و مرجع داده‌های آموزش AI)", "category": "stock", "marketName": "NYSE", "unit": "$"},
    {"id": "SHOP", "symbol": "SHOP", "nameEn": "Shopify Inc.", "nameFa": "شاپیفای (فروشگاه‌ساز آنلاین جهانی)", "category": "stock", "marketName": "NYSE", "unit": "$"},
    {"id": "SNOW", "symbol": "SNOW", "nameEn": "Snowflake Inc.", "nameFa": "اسنوفلیک (انبار داده‌های کلاد هوش مصنوعی)", "category": "stock", "marketName": "NYSE", "unit": "$"},
    {"id": "RACE", "symbol": "RACE", "nameEn": "Ferrari N.V.", "nameFa": "فراری (سوپراسپرت‌های لوکس ایتالیا)", "category": "stock", "marketName": "NYSE", "unit": "$"},
    {"id": "GOLD", "symbol": "XAU/USD", "nameEn": "Gold Spot", "nameFa": "انس طلای جهانی (Gold XAU/USD)", "category": "commodity", "marketName": "Commodities", "unit": "$"},
    {"id": "SILVER", "symbol": "XAG/USD", "nameEn": "Silver Spot", "nameFa": "انس نقره جهانی (Silver XAG/USD)", "category": "commodity", "marketName": "Commodities", "unit": "$"},
    {"id": "COPPER", "symbol": "HG=F", "nameEn": "Copper Futures (Dr. Copper)", "nameFa": "مس صنعتی جهانی (دکتر مس - دماسنج اقتصاد)", "category": "commodity", "marketName": "COMEX", "unit": "$"},
    {"id": "NATGAS", "symbol": "NG=F", "nameEn": "Natural Gas Futures", "nameFa": "گاز طبیعی هنری هاب (Henry Hub)", "category": "commodity", "marketName": "NYMEX", "unit": "$"},
    {"id": "PLATINUM", "symbol": "PL=F", "nameEn": "Platinum Spot (XPT/USD)", "nameFa": "پلاتین جهانی (فلز فوق‌لوکس صنعتی)", "category": "commodity", "marketName": "NYMEX", "unit": "$"},
    {"id": "URANIUM", "symbol": "URNM", "nameEn": "Sprott Uranium Miners ETF", "nameFa": "صندوق اورانیوم و سوخت هسته‌ای هوش مصنوعی", "category": "commodity", "marketName": "NYSE", "unit": "$"},
    {"id": "OIL_WTI", "symbol": "WTI", "nameEn": "Crude Oil (WTI)", "nameFa": "نفت خام تگزاس (WTI Oil)", "category": "commodity", "marketName": "NYMEX", "unit": "$"},
    {"id": "OIL_BRENT", "symbol": "BRENT", "nameEn": "Brent Crude Oil", "nameFa": "نفت برنت دریای شمال", "category": "commodity", "marketName": "ICE", "unit": "$"},
    {"id": "VIX", "symbol": "^VIX", "nameEn": "CBOE Volatility Index (VIX)", "nameFa": "شاخص نوسان و ترس وال‌استریت (VIX)", "category": "index", "marketName": "CBOE", "unit": "pts"},
    {"id": "RUT", "symbol": "^RUT", "nameEn": "Russell 2000 Index", "nameFa": "شاخص ۲۰۰۰ شرکت کوچک آمریکا (Russell 2000)", "category": "index", "marketName": "US Indices", "unit": "pts"},
    {"id": "DAX", "symbol": "^GDAXI", "nameEn": "DAX 40 Germany", "nameFa": "شاخص ۴۰ غول صنعتی بورس آلمان (DAX)", "category": "index", "marketName": "Deutsche Börse", "unit": "pts"},
    {"id": "NIKKEI", "symbol": "^N225", "nameEn": "Nikkei 225 Japan", "nameFa": "شاخص ۲۲۵ شرکت برتر بورس توکیو ژاپن (Nikkei)", "category": "index", "marketName": "Tokyo Stock Exchange", "unit": "pts"},
    {"id": "FTSE", "symbol": "^FTSE", "nameEn": "FTSE 100 UK", "nameFa": "شاخص ۱۰۰ شرکت برتر بورس لندن انگلستان (FTSE)", "category": "index", "marketName": "London Stock Exchange", "unit": "pts"},
    {"id": "SP500", "symbol": "S&P 500", "nameEn": "S&P 500 Index", "nameFa": "شاخص ۵۰۰ شرکت برتر آمریکا (S&P 500)", "category": "index", "marketName": "US Indices", "unit": "pts"},
    {"id": "NASDAQ100", "symbol": "NDX", "nameEn": "NASDAQ 100 Index", "nameFa": "شاخص ۱۰۰ غول فناوری (Nasdaq 100)", "category": "index", "marketName": "NASDAQ", "unit": "pts"},
    {"id": "DOWJONES", "symbol": "DJI", "nameEn": "Dow Jones Industrial", "nameFa": "شاخص صنعتی داوجونز (Dow Jones)", "category": "index", "marketName": "NYSE", "unit": "pts"},
    {"id": "DXY", "symbol": "DXY", "nameEn": "US Dollar Index", "nameFa": "شاخص قدرت جهانی دلار (DXY)", "category": "index", "marketName": "ICE", "unit": "pts"}
]


# ===================================================================
# 2. CIRCUIT BREAKER & RESILIENCE INFRASTRUCTURE
# ===================================================================
class CircuitBreakerOpenError(Exception):
    """Raised when an adapter's circuit breaker is in OPEN state."""
    pass


class CircuitBreaker:
    """
    Standard Circuit Breaker pattern with CLOSED, OPEN, and HALF_OPEN states.
    - Trips to OPEN after failure_threshold consecutive failures.
    - Stays in OPEN for recovery_timeout seconds, then transitions to HALF_OPEN.
    - In HALF_OPEN, allows a single probe attempt; success closes, failure re-opens.
    """
    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = "CLOSED"  # "CLOSED", "OPEN", "HALF_OPEN"
        self.last_failure_time = 0.0

    def can_execute(self) -> bool:
        now = time.time()
        if self.state == "OPEN":
            if now - self.last_failure_time >= self.recovery_timeout:
                self.state = "HALF_OPEN"
                return True
            return False
        return True

    def record_success(self):
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"


# ===================================================================
# 3. BASE MARKET ADAPTER (COMMON CONTRACT)
# ===================================================================
class BaseMarketAdapter:
    """
    Abstract Base Class for Market Data Providers.
    Every provider provides:
      - fetch_quotes(symbols, client) -> Dict[str, Optional[Dict[str, Any]]]
      - fetch_catalog() -> List[Dict[str, Any]]
      - Resilient execution with timeout, exponential backoff, jitter, circuit breaker, quota logging.
    """
    name: str = "base"

    def __init__(self, api_key: str = "", timeout: float = 3.5, max_retries: int = 2):
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)

    async def fetch_quotes(
        self,
        symbols: List[str],
        client: httpx.AsyncClient
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        results: Dict[str, Optional[Dict[str, Any]]] = {}
        for s in symbols:
            results[s] = await self.fetch_quote(s, client)
        return results

    async def fetch_quote(
        self,
        symbol: str,
        client: httpx.AsyncClient
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def fetch_catalog(self) -> List[Dict[str, Any]]:
        return []

    async def _execute_http(
        self,
        url: str,
        extractor_func,
        client: httpx.AsyncClient,
        headers: Optional[Dict[str, str]] = None
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """
        Executes HTTP request with Circuit Breaker, Exponential Backoff + Jitter, and Quota metrics.
        Returns: (parsed_meta, trace_dict)
        """
        trace: Dict[str, Any] = {
            'source': self.name,
            'url': url,
            'status_code': 0,
            'latency_ms': 0.0,
            'success': False,
        }

        # 1. Circuit Breaker Check
        if not self.circuit_breaker.can_execute():
            trace['error'] = 'Circuit breaker OPEN'
            record_provider_metric(self.name, "errors")
            return None, trace

        # 2. Rate Limiting slot
        await acquire_provider_slot(self.name, wait=True)

        req_headers = {'User-Agent': f'SignalAlert/{APP_VERSION}'}
        if headers:
            req_headers.update(headers)

        last_error = None
        base_backoff = 0.2

        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                # Exponential backoff with random jitter
                backoff_wait = (base_backoff * (2 ** (attempt - 1))) + random.uniform(0.02, 0.08)
                await asyncio.sleep(backoff_wait)

            t0 = time.time()
            try:
                res = await client.get(url, headers=req_headers, timeout=self.timeout)
                trace['latency_ms'] = round((time.time() - t0) * 1000, 2)
                trace['status_code'] = res.status_code

                if res.status_code == 200:
                    try:
                        data = res.json()
                    except Exception as json_err:
                        self.circuit_breaker.record_failure()
                        record_provider_metric(self.name, "errors")
                        trace['error'] = f"Malformed JSON: {str(json_err)}"
                        return None, trace

                    parsed = extractor_func(data)
                    if parsed is not None and isinstance(parsed, dict):
                        self.circuit_breaker.record_success()
                        record_provider_metric(self.name, "success")
                        trace['success'] = True
                        trace['parsed_price'] = parsed.get('price')
                        trace['asOf'] = parsed.get('asOf')
                        trace['state'] = parsed.get('state', 'LIVE')
                        trace['currency'] = parsed.get('currency', 'USD')
                        return parsed, trace
                    else:
                        trace['error'] = 'Extractor returned None'
                        return None, trace

                elif res.status_code == 429:
                    self.circuit_breaker.record_failure()
                    record_provider_metric(self.name, "rate_limits_429")
                    record_provider_metric(self.name, "errors")
                    trace['error'] = 'HTTP 429 Rate Limit'
                    return None, trace

                elif res.status_code in (400, 401, 403, 404):
                    # Permanent client/auth/not-found error: do NOT retry
                    record_provider_metric(self.name, "errors")
                    trace['error'] = f'HTTP {res.status_code}'
                    return None, trace

                else:
                    # 5xx server error: eligible for retry
                    last_error = f'HTTP {res.status_code}'
                    trace['error'] = last_error

            except (httpx.TimeoutException, asyncio.TimeoutError) as te:
                last_error = f'Timeout: {str(te)}'
                trace['latency_ms'] = round((time.time() - t0) * 1000, 2)
                trace['error'] = last_error
            except Exception as exc:
                last_error = f'Network exception: {str(exc)}'
                trace['latency_ms'] = round((time.time() - t0) * 1000, 2)
                trace['error'] = last_error

        # If all retries exhausted
        self.circuit_breaker.record_failure()
        record_provider_metric(self.name, "errors")
        trace['error'] = f'Failed after {self.max_retries} retries ({last_error})'
        return None, trace


# ===================================================================
# 4. CONCRETE ADAPTERS: Yahoo, Finnhub, Twelve Data, FRED
# ===================================================================

class YahooFinanceAdapter(BaseMarketAdapter):
    """
    Adapter for Yahoo Finance (query1 with query2 fallback).
    Free, no API key required. Supports stocks, forex, indices, commodities, bonds.
    """
    name = "yahoo"

    def fetch_catalog(self) -> List[Dict[str, Any]]:
        return WALLSTREET_MACRO_SYMBOLS

    def _extract_yf(self, data):
        if isinstance(data, dict):
            chart = data.get('chart', {}).get('result', [])
            if chart and isinstance(chart, list) and len(chart) > 0:
                meta = chart[0].get('meta', {})
                p = meta.get('regularMarketPrice')
                as_of_ts = meta.get('regularMarketTime') or meta.get('currentTradingPeriod', {}).get('regular', {}).get('end')
                m_state = meta.get('marketState', 'REGULAR')
                currency = meta.get('currency', 'USD')
                if p is not None and float(p) > 0:
                    return {
                        'price': float(p),
                        'asOf': int(as_of_ts) if as_of_ts else int(time.time()),
                        'state': m_state,
                        'currency': currency,
                        'source': 'Yahoo Finance'
                    }
                elif m_state in ['CLOSED', 'closed', 'POST', 'PRE']:
                    prev_p = meta.get('chartPreviousClose') or meta.get('previousClose')
                    return {
                        'price': float(prev_p) if prev_p else None,
                        'asOf': int(as_of_ts) if as_of_ts else int(time.time()),
                        'state': 'closed',
                        'currency': currency,
                        'source': 'Yahoo Finance'
                    }
        return None

    async def fetch_quote(self, symbol: str, client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
        yf_symbol = resolve_yf_symbol(symbol)

        # 1. Primary: query1
        url1 = f'https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}?interval=1m&range=1d'
        parsed, trace = await self._execute_http(url1, self._extract_yf, client)
        if parsed:
            return parsed

        # 2. Secondary fallback: query2 (if not 404)
        if trace.get('status_code') != 404:
            url2 = f'https://query2.finance.yahoo.com/v8/finance/chart/{yf_symbol}?interval=1m&range=1d'
            parsed2, _ = await self._execute_http(url2, self._extract_yf, client)
            if parsed2:
                return parsed2

        return None


class FinnhubAdapter(BaseMarketAdapter):
    """
    Adapter for Finnhub Stock & Forex REST API.
    Supports US Equities (AAPL, TSLA, MSFT) and major Forex pairs.
    """
    name = "finnhub"

    def fetch_catalog(self) -> List[Dict[str, Any]]:
        return [s for s in WALLSTREET_MACRO_SYMBOLS if s.get('category') in ('stock', 'forex')]

    def _resolve_symbol(self, symbol: str) -> str:
        s = symbol.upper().strip().replace(' ', '')
        if '/' in s:
            parts = s.split('/')
            return f"OANDA:{parts[0]}_{parts[1]}"
        if s in FOREX_PAIRS:
            return f"OANDA:{s[:3]}_{s[3:]}"
        return s

    def _extract_finnhub(self, data):
        if isinstance(data, dict):
            c = data.get('c')
            if c is not None and float(c) > 0:
                t = data.get('t')
                return {
                    'price': float(c),
                    'asOf': int(t) if t else int(time.time()),
                    'state': 'LIVE',
                    'currency': 'USD',
                    'source': 'Finnhub',
                    'change_pct': float(data.get('dp', 0.0)),
                    'prev_close': float(data.get('pc', 0.0)),
                    'high': float(data.get('h', 0.0)),
                    'low': float(data.get('l', 0.0))
                }
            elif data.get('pc') and float(data.get('pc')) > 0:
                return {
                    'price': float(data.get('pc')),
                    'asOf': int(data.get('t') or time.time()),
                    'state': 'closed',
                    'currency': 'USD',
                    'source': 'Finnhub'
                }
        return None

    async def fetch_quote(self, symbol: str, client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            return None

        finnhub_sym = self._resolve_symbol(symbol)
        url = f"https://finnhub.io/api/v1/quote?symbol={finnhub_sym}&token={self.api_key}"
        parsed, _ = await self._execute_http(url, self._extract_finnhub, client)
        return parsed


class TwelveDataAdapter(BaseMarketAdapter):
    """
    Adapter for Twelve Data REST API.
    Supports Stocks, Forex, Indices, Commodities.
    """
    name = "twelvedata"

    def fetch_catalog(self) -> List[Dict[str, Any]]:
        return [s for s in WALLSTREET_MACRO_SYMBOLS if s.get('category') in ('stock', 'forex', 'index', 'commodity')]

    def _resolve_symbol(self, symbol: str) -> str:
        s = symbol.upper().strip()
        if s in ('GOLD', 'XAU', 'XAUUSD', 'GC=F'):
            return 'XAU/USD'
        if s in ('SILVER', 'XAG', 'XAGUSD', 'SI=F'):
            return 'XAG/USD'
        if s in ('WTI', 'CL=F', 'OIL'):
            return 'WTI/USD'
        if s in ('BRENT', 'BZ=F'):
            return 'BRENT/USD'
        if '/' in s:
            return s
        if s in FOREX_PAIRS:
            return f"{s[:3]}/{s[3:]}"
        if s.startswith('^'):
            return s[1:]
        return s

    def _extract_td(self, data):
        if isinstance(data, dict):
            if data.get('status') == 'error' or 'code' in data:
                return None
            close_p = data.get('close') or data.get('price')
            if close_p is not None and float(close_p) > 0:
                is_open = bool(data.get('is_market_open', True))
                ts = data.get('timestamp')
                return {
                    'price': float(close_p),
                    'asOf': int(ts) if ts else int(time.time()),
                    'state': 'LIVE' if is_open else 'closed',
                    'currency': data.get('currency', 'USD'),
                    'source': 'Twelve Data'
                }
        return None

    async def fetch_quote(self, symbol: str, client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            return None

        td_sym = self._resolve_symbol(symbol)
        url = f"https://api.twelvedata.com/quote?symbol={td_sym}&apikey={self.api_key}"
        parsed, _ = await self._execute_http(url, self._extract_td, client)
        return parsed


class FredAdapter(BaseMarketAdapter):
    """
    Adapter for Federal Reserve Economic Data (FRED).
    Authoritative provider for US Macroeconomic indicators and Treasury yields.
    """
    name = "fred"

    FRED_SERIES_MAP: Dict[str, str] = {
        'US10Y': 'DGS10',
        '^TNX': 'DGS10',
        'TNX': 'DGS10',
        'US02Y': 'DGS2',
        'US2Y': 'DGS2',
        '^2YY': 'DGS2',
        'US13W': 'DTB3',
        '^IRX': 'DTB3',
        'US30Y': 'DGS30',
        '^TYX': 'DGS30',
        'DXY': 'DTWEXBGS',
        'USDX': 'DTWEXBGS',
        'DX-Y.NYB': 'DTWEXBGS',
        'FEDFUNDS': 'FEDFUNDS',
        'CPI': 'CPIAUCSL',
        'UNRATE': 'UNRATE',
    }

    def fetch_catalog(self) -> List[Dict[str, Any]]:
        return [s for s in WALLSTREET_MACRO_SYMBOLS if s.get('category') in ('bond', 'macro')]

    def _make_extractor(self, series_id: str):
        def _extract(data):
            if isinstance(data, dict):
                obs = data.get('observations', [])
                if obs and isinstance(obs, list) and len(obs) > 0:
                    val_str = obs[0].get('value')
                    if val_str and val_str != '.':
                        try:
                            val = float(val_str)
                            return {
                                'price': val,
                                'asOf': int(time.time()),
                                'date': obs[0].get('date'),
                                'state': 'LIVE',
                                'currency': '%' if series_id.startswith(('DGS', 'DTB')) or series_id in ('FEDFUNDS', 'UNRATE') else 'pts',
                                'source': 'FRED'
                            }
                        except ValueError:
                            pass
            return None
        return _extract

    async def fetch_quote(self, symbol: str, client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            return None

        clean_sym = symbol.upper().strip().replace(' ', '')
        series_id = self.FRED_SERIES_MAP.get(clean_sym)
        if not series_id:
            if clean_sym in self.FRED_SERIES_MAP.values():
                series_id = clean_sym
            else:
                return None

        url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={self.api_key}&file_type=json&sort_order=desc&limit=1"
        parsed, _ = await self._execute_http(url, self._make_extractor(series_id), client)
        return parsed


# ===================================================================
# 5. PROVIDER INSTANCES & FALLBACK CHAIN CONFIGURATION
# ===================================================================
yahoo_adapter = YahooFinanceAdapter()
finnhub_adapter = FinnhubAdapter(api_key=FINNHUB_API_KEY)
twelve_data_adapter = TwelveDataAdapter(api_key=TWELVE_DATA_API_KEY)
fred_adapter = FredAdapter(api_key=FRED_API_KEY)

ALL_GLOBAL_ADAPTERS: Dict[str, BaseMarketAdapter] = {
    'yahoo': yahoo_adapter,
    'finnhub': finnhub_adapter,
    'twelvedata': twelve_data_adapter,
    'fred': fred_adapter,
}

def resolve_symbol_category(symbol: str) -> str:
    """Classifies a symbol into stock, forex, index, commodity, bond, or macro."""
    s = symbol.upper().strip()
    s_clean = s.replace('/', '').replace(' ', '')
    if s_clean in FOREX_PAIRS or '/' in s:
        return 'forex'
    if s in ('GOLD', 'SILVER', 'BRENT', 'WTI', 'OIL', 'NATGAS', 'COPPER', 'PLATINUM', 'GC=F', 'SI=F', 'CL=F', 'BZ=F', 'NG=F', 'HG=F', 'PL=F'):
        return 'commodity'
    if s.startswith('^') or s in ('SP500', 'SPX', 'NDX', 'NASDAQ', 'DJI', 'DOW', 'RUT', 'DAX', 'FTSE', 'NIKKEI', 'VIX', 'DXY'):
        return 'index'
    if s in ('US10Y', 'US02Y', 'US2Y', '^2YY', 'US13W', 'US30Y', '^TNX', '^IRX', '^TYX', 'FEDFUNDS', 'CPI', 'UNRATE'):
        return 'macro'

    for item in WALLSTREET_MACRO_SYMBOLS:
        if item['symbol'].upper() == s or item['id'].upper() == s:
            return item.get('category', 'stock')

    return 'stock'


def get_fallback_chain(symbol: str) -> List[BaseMarketAdapter]:
    """
    Returns ordered fallback chain based on Phase 0 baseline architecture:
    - Stocks / Forex: Yahoo -> Finnhub -> Twelve Data
    - Indices / Commodities: Yahoo -> Twelve Data
    - Macro / Bonds: FRED -> Yahoo -> Twelve Data
    """
    cat = resolve_symbol_category(symbol)
    if cat in ('macro', 'bond'):
        return [fred_adapter, yahoo_adapter, twelve_data_adapter]
    elif cat in ('index', 'commodity'):
        return [yahoo_adapter, twelve_data_adapter]
    else:  # stock or forex
        return [yahoo_adapter, finnhub_adapter, twelve_data_adapter]


# ===================================================================
# 6. MAIN DISPATCHER: fetch_global_stocks
# ===================================================================
async def fetch_global_stocks(
    client: httpx.AsyncClient,
    exchange: str,
    symbol: str,
    _try_fetch,
    traces: List[Dict[str, Any]],
    collect_all_traces: bool
) -> Optional[float]:
    """
    Multi-provider global stocks, macro, forex, index, and commodity dispatcher.
    Executes resilient Fallback Chain (Yahoo -> Finnhub -> Twelve Data -> FRED)
    Preserves exact meta keys (price, asOf, state, currency, source) and closed market guards.
    """
    yf_symbol = resolve_yf_symbol(symbol)
    cat = resolve_symbol_category(symbol)

    # 1. Macro with FRED (if FRED_API_KEY is configured and symbol is mapped)
    if (cat in ('macro', 'bond') or symbol in fred_adapter.FRED_SERIES_MAP) and fred_adapter.api_key:
        fred_series = fred_adapter.FRED_SERIES_MAP.get(symbol) or fred_adapter.FRED_SERIES_MAP.get(yf_symbol)
        if fred_series:
            fred_url = f"https://api.stlouisfed.org/fred/series/observations?series_id={fred_series}&api_key={fred_adapter.api_key}&file_type=json&sort_order=desc&limit=1"
            p_fred = await _try_fetch('FRED API', fred_url, fred_adapter._make_extractor(fred_series))
            if p_fred and not collect_all_traces:
                return p_fred

    # 2Y yield is FRED-only (DGS2): never fall through to Yahoo (^IRX is the 13-week bill)
    if symbol.upper().strip() in FRED_ONLY_SYMBOLS:
        return None

    # 2. Yahoo Finance: query1
    url1 = f'https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}?interval=1m&range=1d'
    p = await _try_fetch('Yahoo Finance API (query1)', url1, yahoo_adapter._extract_yf)
    if p and not collect_all_traces:
        return p

    # Rule: If query1 returned 404, STOP immediately. Do NOT retry query2 or other providers on 404.
    last_status = traces[-1].get('status_code', 0) if traces else 0
    if last_status == 404:
        return None

    # 3. Yahoo Finance: query2 secondary fallback (on 429, 5xx, or network failure)
    url2 = f'https://query2.finance.yahoo.com/v8/finance/chart/{yf_symbol}?interval=1m&range=1d'
    p2 = await _try_fetch('Yahoo Finance API (query2)', url2, yahoo_adapter._extract_yf)
    if p2 and not collect_all_traces:
        return p2

    # 4. Secondary Fallbacks (Finnhub, Twelve Data) when Yahoo fails (e.g. 429, 5xx, timeout)
    if cat in ('stock', 'forex'):
        # Fallback to Finnhub
        if finnhub_adapter.api_key:
            fh_sym = finnhub_adapter._resolve_symbol(symbol)
            fh_url = f"https://finnhub.io/api/v1/quote?symbol={fh_sym}&token={finnhub_adapter.api_key}"
            p_fh = await _try_fetch('Finnhub API', fh_url, finnhub_adapter._extract_finnhub)
            if p_fh and not collect_all_traces:
                return p_fh

        # Fallback to Twelve Data
        if twelve_data_adapter.api_key:
            td_sym = twelve_data_adapter._resolve_symbol(symbol)
            td_url = f"https://api.twelvedata.com/quote?symbol={td_sym}&apikey={twelve_data_adapter.api_key}"
            p_td = await _try_fetch('Twelve Data API', td_url, twelve_data_adapter._extract_td)
            if p_td and not collect_all_traces:
                return p_td

    elif cat in ('index', 'commodity'):
        # Fallback to Twelve Data
        if twelve_data_adapter.api_key:
            td_sym = twelve_data_adapter._resolve_symbol(symbol)
            td_url = f"https://api.twelvedata.com/quote?symbol={td_sym}&apikey={twelve_data_adapter.api_key}"
            p_td = await _try_fetch('Twelve Data API', td_url, twelve_data_adapter._extract_td)
            if p_td and not collect_all_traces:
                return p_td

    return None
