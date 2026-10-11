import time
from datetime import datetime, time as dtime, timezone
from typing import Dict, Any, Optional, Tuple
import zoneinfo

from app.state import PRICE_CACHE
from app.engine.categories import resolve_symbol_category


# Timezone singletons
NY_TZ = zoneinfo.ZoneInfo("America/New_York")
TEHRAN_TZ = zoneinfo.ZoneInfo("Asia/Tehran")


def get_ny_now(now_dt: Optional[datetime] = None) -> datetime:
    """Returns datetime in America/New_York (Eastern Time)."""
    if now_dt is not None:
        if now_dt.tzinfo is None:
            return now_dt.replace(tzinfo=timezone.utc).astimezone(NY_TZ)
        return now_dt.astimezone(NY_TZ)
    return datetime.now(NY_TZ)


def get_tehran_now(now_dt: Optional[datetime] = None) -> datetime:
    """Returns datetime in Asia/Tehran."""
    if now_dt is not None:
        if now_dt.tzinfo is None:
            return now_dt.replace(tzinfo=timezone.utc).astimezone(TEHRAN_TZ)
        return now_dt.astimezone(TEHRAN_TZ)
    return datetime.now(TEHRAN_TZ)


# ===================================================================
# 1. US EQUITIES & INDICES (Yahoo marketState + NYSE/NASDAQ Schedule)
# ===================================================================

def is_us_market_open(now_dt: Optional[datetime] = None, check_cache: bool = True) -> Tuple[bool, str]:
    """
    US Market Calendar (Phase 6):
    - Primary: Evaluates 'marketState' from Yahoo Finance in PRICE_CACHE.
      States: REGULAR (open), CLOSED (closed), PRE (pre-market), POST (after-hours).
    - Fallback: NYSE/NASDAQ standard hours:
      Monday - Friday, 09:30 to 16:00 ET.
      Weekends and outside 09:30-16:00 are CLOSED for regular polling.
    """
    # 1. Check live Yahoo marketState in PRICE_CACHE for benchmark tickers
    if check_cache and now_dt is None:
        for benchmark_key in [
            'global_stocks:^gspc', 'global_stocks:aapl', 'global_stocks:msft',
            'stocks:^gspc', 'stocks:aapl', 'yahoo:^gspc'
        ]:
            entry = PRICE_CACHE.get(benchmark_key)
            if entry and len(entry) > 2 and isinstance(entry[2], dict):
                meta = entry[2]
                state = (meta.get('state') or meta.get('marketState') or '').upper()
                if state:
                    if state == 'REGULAR':
                        return True, 'REGULAR'
                    elif state in ('CLOSED', 'POST', 'PRE'):
                        return False, state

    # 2. Schedule-based check in Eastern Time
    ny_time = get_ny_now(now_dt)
    weekday = ny_time.weekday()  # Monday=0, Friday=4, Saturday=5, Sunday=6
    t = ny_time.time()

    # Weekend (Saturday, Sunday)
    if weekday in (5, 6):
        return False, 'CLOSED'

    # Weekday regular hours: 09:30 - 16:00 ET
    reg_start = dtime(9, 30)
    reg_end = dtime(16, 0)
    pre_start = dtime(4, 0)
    post_end = dtime(20, 0)

    if reg_start <= t < reg_end:
        return True, 'REGULAR'
    elif pre_start <= t < reg_start:
        return False, 'PRE'
    elif reg_end <= t < post_end:
        return False, 'POST'
    else:
        return False, 'CLOSED'


# ===================================================================
# 2. FOREX (24 hours continuously from Sunday night to Friday night)
# ===================================================================

def is_forex_market_open(now_dt: Optional[datetime] = None) -> Tuple[bool, str]:
    """
    Forex Calendar (Phase 6):
    - 24 hours continuously from Sunday evening (17:00 ET) to Friday evening (17:00 ET).
    - Weekend closed: Friday 17:00 ET to Sunday 17:00 ET.
    """
    ny_time = get_ny_now(now_dt)
    weekday = ny_time.weekday()
    t = ny_time.time()
    border_17 = dtime(17, 0)

    if weekday == 6:  # Sunday
        if t >= border_17:
            return True, 'OPEN'
        return False, 'CLOSED'
    elif weekday == 5:  # Saturday
        return False, 'CLOSED'
    elif weekday == 4:  # Friday
        if t < border_17:
            return True, 'OPEN'
        return False, 'CLOSED'
    else:  # Monday (0), Tuesday (1), Wednesday (2), Thursday (3)
        return True, 'OPEN'


# ===================================================================
# 3. COMMODITIES (24/5 with 1-hour Daily Break)
# ===================================================================

def is_commodity_market_open(now_dt: Optional[datetime] = None) -> Tuple[bool, str]:
    """
    Commodities Calendar (Phase 6):
    - 24/5 trading: Opens Sunday 18:00 ET, Closes Friday 17:00 ET.
    - Daily Maintenance Break: Monday through Thursday from 17:00 to 18:00 ET.
    - During daily break and weekends: CLOSED.
    """
    ny_time = get_ny_now(now_dt)
    weekday = ny_time.weekday()
    t = ny_time.time()
    t_17 = dtime(17, 0)
    t_18 = dtime(18, 0)

    if weekday == 6:  # Sunday
        if t >= t_18:
            return True, 'OPEN'
        return False, 'CLOSED'
    elif weekday == 5:  # Saturday
        return False, 'CLOSED'
    elif weekday == 4:  # Friday
        if t < t_17:
            return True, 'OPEN'
        return False, 'CLOSED'
    else:  # Monday (0), Tuesday (1), Wednesday (2), Thursday (3)
        # Daily break between 17:00 and 18:00 ET
        if t_17 <= t < t_18:
            return False, 'DAILY_BREAK'
        return True, 'OPEN'


# ===================================================================
# 4. TEHRAN STOCK EXCHANGE (TSE - Saturday to Wednesday 09:00 - 12:30)
# ===================================================================

def is_tse_market_open(now_dt: Optional[datetime] = None) -> Tuple[bool, str]:
    """
    Tehran Stock Exchange (TSE) Calendar:
    - Saturday to Wednesday, 09:00 to 12:30 Tehran time.
    - Thursday and Friday closed.
    """
    teh_time = get_tehran_now(now_dt)
    weekday = teh_time.weekday()  # Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4, Saturday=5, Sunday=6
    t = teh_time.time()

    # Saturday (5), Sunday (6), Monday (0), Tuesday (1), Wednesday (2)
    if weekday in (5, 6, 0, 1, 2):
        if dtime(9, 0) <= t < dtime(12, 30):
            return True, 'OPEN'
    return False, 'CLOSED'


# ===================================================================
# 5. CRYPTO (24/7 Always Open)
# ===================================================================

def is_crypto_market_open() -> Tuple[bool, str]:
    return True, 'OPEN'


# ===================================================================
# 6. UNIFIED DISPATCHER & STATUS REPORTING
# ===================================================================

def is_market_open(exchange: str, symbol: str, now_dt: Optional[datetime] = None) -> bool:
    """
    Unified Market Open/Closed Decider:
    Determines whether polling should proceed for an alert pair.
    When False: polling MUST be paused to avoid wasted requests on closed markets.
    """
    cat = resolve_symbol_category(exchange, symbol)

    if cat == 'crypto':
        return True

    if cat == 'forex':
        return is_forex_market_open(now_dt)[0]

    if cat == 'commodity':
        return is_commodity_market_open(now_dt)[0]

    if cat in ('stock', 'index'):
        return is_us_market_open(now_dt)[0]

    if cat == 'iran_market':
        s_upper = (symbol or '').upper().strip()
        # Crypto on Iranian exchanges is 24/7
        if any(c in s_upper for c in ['USDT', 'BTC', 'ETH', 'TON', 'TRX', 'DOGE', 'SOL']):
            return True
        return is_tse_market_open(now_dt)[0]

    if cat in ('macro', 'bond'):
        # Macro indicators / bonds follow US market calendar
        return is_us_market_open(now_dt)[0]

    return True


def get_all_markets_status(now_dt: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Constructs real-time market calendar status object for /api/markets/status.
    Matches Requirement 3:
    Market closed -> 'closed' / 'بسته'.
    """
    us_open, us_state = is_us_market_open(now_dt)
    fx_open, fx_state = is_forex_market_open(now_dt)
    com_open, com_state = is_commodity_market_open(now_dt)
    tse_open, tse_state = is_tse_market_open(now_dt)

    return {
        "us_stocks": {
            "name": "سهام و شاخص‌های آمریکا (NYSE/NASDAQ)",
            "status": "open" if us_open else "closed",
            "status_fa": "باز" if us_open else "بسته",
            "state": us_state,
            "state_fa": "باز" if us_open else "بسته",
            "is_open": us_open,
            "schedule": "Monday-Friday 09:30-16:00 ET",
            "schedule_fa": "دوشنبه تا جمعه ۰۹:۳۰ تا ۱۶:۰۰ به وقت نیویورک",
            "source": "Yahoo marketState / NYSE Calendar"
        },
        "forex": {
            "name": "بازار جهانی ارز (Forex)",
            "status": "open" if fx_open else "closed",
            "status_fa": "باز" if fx_open else "بسته",
            "state": fx_state,
            "state_fa": "باز" if fx_open else "بسته",
            "is_open": fx_open,
            "schedule": "24/5 Sunday 17:00 ET - Friday 17:00 ET",
            "schedule_fa": "۲۴ ساعته از یکشنبه شب تا جمعه شب",
            "source": "Interbank FX Market Hours"
        },
        "commodities": {
            "name": "کامودیتی، فلزات و انرژی (Commodities)",
            "status": "open" if com_open else "closed",
            "status_fa": "باز" if com_open else "بسته",
            "state": com_state,
            "state_fa": "باز" if com_open else "بسته",
            "is_open": com_open,
            "schedule": "24/5 Sunday 18:00 ET - Friday 17:00 ET (Daily break 17:00-18:00 ET)",
            "schedule_fa": "۲۴/۵ با وقفه روزانه ۱۷:۰۰ تا ۱۸:۰۰ به وقت نیویورک",
            "source": "CME / COMEX Market Schedule"
        },
        "crypto": {
            "name": "بازار رمزارزها (Cryptocurrency)",
            "status": "open",
            "status_fa": "باز",
            "state": "OPEN",
            "state_fa": "باز",
            "is_open": True,
            "schedule": "24/7/365",
            "schedule_fa": "۲۴ ساعته ۷ روز هفته",
            "description": "بازار ۲۴ ساعته",
            "source": "Global Crypto Spot & Perpetuals"
        },
        "tse": {
            "name": "بورس اوراق بهادار تهران (TSE)",
            "status": "open" if tse_open else "closed",
            "status_fa": "باز" if tse_open else "بسته",
            "state": tse_state,
            "state_fa": "باز" if tse_open else "بسته",
            "is_open": tse_open,
            "schedule": "Saturday-Wednesday 09:00-12:30 IRST",
            "schedule_fa": "شنبه تا چهارشنبه ۰۹:۰۰ تا ۱۲:۳۰",
            "source": "Tehran Stock Exchange Official Schedule"
        }
    }


def get_symbol_market_detail(exchange: str, symbol: str, now_dt: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Returns rich symbol market information (Phase 8):
    - is_open, status, status_fa, state, state_fa
    - schedule, schedule_fa
    - next_open_fa: Persian time until or datetime of next opening session
    - source: data provider label (e.g. Yahoo Finance, FRED, Finnhub, Nobitex, TSETMC, Binance)
    - delay: latency label (e.g. بلادرنگ, تأخیر ۱۵ دقیقه, روزانه, ماهانه)
    """
    cat = resolve_symbol_category(exchange, symbol)
    s_upper = (symbol or "").strip().upper()
    ex_lower = (exchange or "").strip().lower()

    if cat == 'crypto':
        source = "Nobitex / رمزارز ایرانی" if ex_lower in ('nobitex', 'wallex', 'tabdeal', 'ramzinex', 'tetherland', 'bitbarg', 'abantether') else "Binance / Global Crypto"
        return {
            "symbol": s_upper,
            "category": "crypto",
            "category_fa": "رمزارز",
            "is_open": True,
            "status": "open",
            "status_fa": "باز",
            "state": "OPEN",
            "state_fa": "باز",
            "schedule": "24/7/365 Non-stop",
            "schedule_fa": "۲۴ ساعته و بدون تعطیلی (۷ روز هفته)",
            "next_open_fa": "بازار هم‌اکنون فعال و باز است",
            "source": source,
            "delay": "بلادرنگ (Real-Time)"
        }

    if cat == 'forex':
        fx_open, fx_state = is_forex_market_open(now_dt)
        return {
            "symbol": s_upper,
            "category": "forex",
            "category_fa": "فارکس و ارزهای جهانی",
            "is_open": fx_open,
            "status": "open" if fx_open else "closed",
            "status_fa": "باز" if fx_open else "بسته",
            "state": fx_state,
            "state_fa": "باز" if fx_open else "بسته",
            "schedule": "24/5 Sunday 17:00 ET - Friday 17:00 ET",
            "schedule_fa": "۲۴ ساعته از یکشنبه شب تا جمعه شب",
            "next_open_fa": "معاملات فعال است" if fx_open else "یکشنبه ساعت ۲۱:۳۰ به وقت ایران (17:00 ET)",
            "source": "Yahoo Finance / Twelve Data",
            "delay": "بلادرنگ (Real-Time)"
        }

    if cat == 'commodity':
        com_open, com_state = is_commodity_market_open(now_dt)
        return {
            "symbol": s_upper,
            "category": "commodity",
            "category_fa": "کالاها و کامودیتی",
            "is_open": com_open,
            "status": "open" if com_open else "closed",
            "status_fa": "باز" if com_open else "بسته",
            "state": com_state,
            "state_fa": "باز" if com_open else "بسته",
            "schedule": "24/5 Sunday 18:00 ET - Friday 17:00 ET",
            "schedule_fa": "۲۴/۵ یکشنبه تا جمعه (با وقفه روزانه ۱۷:۰۰ تا ۱۸:۰۰ ET)",
            "next_open_fa": "معاملات فعال است" if com_open else "یکشنبه ساعت ۲۲:۳۰ به وقت ایران",
            "source": "CME / COMEX / Yahoo Finance",
            "delay": "تأخیر ۱۵ دقیقه (15m Delayed)"
        }

    if cat in ('stock', 'index'):
        us_open, us_state = is_us_market_open(now_dt)
        return {
            "symbol": s_upper,
            "category": cat,
            "category_fa": "سهام بین‌المللی" if cat == "stock" else "شاخص بورس جهانی",
            "is_open": us_open,
            "status": "open" if us_open else "closed",
            "status_fa": "باز" if us_open else "بسته",
            "state": us_state,
            "state_fa": "باز" if us_open else "بسته",
            "schedule": "Monday-Friday 09:30-16:00 ET",
            "schedule_fa": "دوشنبه تا جمعه ۰۹:۳۰ تا ۱۶:۰۰ به وقت نیویورک (۱۸:۰۰ تا ۰۰:۳۰ به وقت ایران)",
            "next_open_fa": "جلسه معاملاتی فعال است" if us_open else "جلسه بعدی: دوشنبه ساعت ۱۸:۰۰ به وقت ایران",
            "source": "Yahoo Finance / Finnhub",
            "delay": "تأخیر ۱۵ دقیقه (15m Delayed)"
        }

    if cat in ('macro', 'bond'):
        us_open, us_state = is_us_market_open(now_dt)
        return {
            "symbol": s_upper,
            "category": cat,
            "category_fa": "شاخص کلان اقتصادی" if cat == "macro" else "اوراق قرضه",
            "is_open": us_open,
            "status": "open" if us_open else "closed",
            "status_fa": "باز" if us_open else "بسته",
            "state": us_state,
            "state_fa": "باز" if us_open else "بسته",
            "schedule": "Federal Reserve & Treasury Reporting Calendar",
            "schedule_fa": "تقویم رسمی انتشار فدرال رزرو و خزانه‌داری آمریکا",
            "next_open_fa": "انتشار دوره‌ای ماهانه/هفتگی بر اساس تقویم FRED",
            "source": "Federal Reserve (FRED) / BLS",
            "delay": "ماهانه و دوره‌ای (Monthly/Periodic)"
        }

    if cat == 'iran_market':
        if any(c in s_upper for c in ['USDT', 'BTC', 'ETH', 'TON', 'TRX', 'DOGE', 'SOL']):
            return {
                "symbol": s_upper,
                "category": "iran_market",
                "category_fa": "کریپتو تومانی و تتری ایران",
                "is_open": True,
                "status": "open",
                "status_fa": "باز",
                "state": "OPEN",
                "state_fa": "باز",
                "schedule": "24/7/365",
                "schedule_fa": "۲۴ ساعته ۷ روز هفته",
                "next_open_fa": "معاملات فعال است",
                "source": "Nobitex / Wallex / Tabdeal",
                "delay": "بلادرنگ (Real-Time)"
            }
        tse_open, tse_state = is_tse_market_open(now_dt)
        return {
            "symbol": s_upper,
            "category": "iran_market",
            "category_fa": "طلا، ارز و بورس تهران",
            "is_open": tse_open,
            "status": "open" if tse_open else "closed",
            "status_fa": "باز" if tse_open else "بسته",
            "state": tse_state,
            "state_fa": "باز" if tse_open else "بسته",
            "schedule": "Saturday-Wednesday 09:00-12:30 IRST",
            "schedule_fa": "شنبه تا چهارشنبه ۰۹:۰۰ تا ۱۲:۳۰",
            "next_open_fa": "جلسه معاملاتی فعال است" if tse_open else "جلسه بعدی: ساعت ۰۹:۰۰ روز کاری بعد",
            "source": "TSETMC / TGJU",
            "delay": "بلادرنگ (Real-Time)"
        }

    return {
        "symbol": s_upper,
        "category": cat,
        "category_fa": "عمومی",
        "is_open": True,
        "status": "open",
        "status_fa": "باز",
        "state": "OPEN",
        "state_fa": "باز",
        "schedule": "Global Calendar",
        "schedule_fa": "تقویم عمومی",
        "next_open_fa": "فعال",
        "source": "Global Data Provider",
        "delay": "بلادرنگ (Real-Time)"
    }
