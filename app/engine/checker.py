import time
import asyncio
import html
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import httpx

from app.state import (
    PRICE_CACHE, METRICS,
    OUTLIER_STREAK, _db_lock
)
from app.storage import ALERTS_DB, USER_PROFILES_DB, save_alerts_to_disk_async
from app.markets.common import normalize_symbol
from app.markets.base import fetch_price_with_trace
from app.engine.categories import (
    resolve_symbol_category, get_category_cache_ttl,
    get_category_outlier_threshold
)
from app.engine.calendar import is_market_open
from app.notifier import (
    get_exchange_display_name, enqueue_alert_push,
    send_telegram_alert, send_webhook_alert
)
from app.notifier.outbox import _spawn
import app.state as state

# Maximum concurrent price fetches allowed across the engine
PRICE_FETCH_CONCURRENCY = 20
_SEMAPHORES: Dict[Any, asyncio.Semaphore] = {}

class _DynamicSemaphore:
    def __init__(self, value: int):
        self.value = value

    def _get_sem(self) -> asyncio.Semaphore:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop not in _SEMAPHORES:
            _SEMAPHORES[loop] = asyncio.Semaphore(self.value)
        return _SEMAPHORES[loop]

    async def __aenter__(self):
        return await self._get_sem().__aenter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self._get_sem().__aexit__(exc_type, exc_val, exc_tb)

    async def acquire(self):
        return await self._get_sem().acquire()

    def release(self):
        return self._get_sem().release()

PRICE_FETCH_SEMAPHORE = _DynamicSemaphore(PRICE_FETCH_CONCURRENCY)

async def get_cached_price(client: httpx.AsyncClient, exchange: str, symbol: str) -> Optional[float]:
    """
    Fetches price with category-based TTL caching and Outlier Protection filter:
    - Forex: 20s TTL, 5% outlier jump limit
    - Stock / Index / Commodity: 30s TTL, 10-25% outlier jump limit
    - Macro / Bonds: 60s TTL, 15-20% outlier jump limit
    - Crypto / Iran: 2-60s TTL, 50% outlier jump limit
    - Level-crossing '3 consecutive confirmations' required for outlier swings.
    """
    now = time.time()
    cache_key = f"{exchange.lower()}:{normalize_symbol(symbol)}"
    category = resolve_symbol_category(exchange, symbol)
    cache_ttl = get_category_cache_ttl(category)
    outlier_threshold = get_category_outlier_threshold(category)

    cached = PRICE_CACHE.get(cache_key)
    if cached and (now - cached[1]) < cache_ttl:
        METRICS["cache_hits"] += 1
        return cached[0]

    METRICS["cache_misses"] += 1

    # Protected by Semaphore to guarantee concurrency does not exceed ceiling
    async with PRICE_FETCH_SEMAPHORE:
        price, traces = await fetch_price_with_trace(client, exchange, symbol, collect_all_traces=False)

    if price is not None and price > 0:
        # Category-based Outlier Protection: jumps exceeding threshold must be confirmed 3 times consecutively
        if cached and cached[0] > 0 and (now - cached[1]) < 300:
            last_p = cached[0]
            dev = abs(price - last_p) / last_p
            if dev > outlier_threshold and last_p > 0.0001:
                streak = OUTLIER_STREAK.get(cache_key, 0) + 1
                if streak < 3:
                    OUTLIER_STREAK[cache_key] = streak
                    print(f"⚠️ [Outlier Filter ({category})] {cache_key}: {last_p} -> {price} ({dev*100:.1f}% > {outlier_threshold*100:.0f}%), confirm {streak}/3")
                    return cached[0]

        OUTLIER_STREAK.pop(cache_key, None)
        # Store price, timestamp, and rich trace metadata
        meta = {}
        for tr in traces:
            if tr.get('success') and tr.get('parsed_price') == price:
                meta = {
                    'source': tr.get('source'),
                    'asOf': tr.get('asOf'),
                    'state': tr.get('state'),
                    'currency': tr.get('currency'),
                    'category': category,
                }
                break
        PRICE_CACHE[cache_key] = (price, now, meta)
        return price

    for tr in traces:
        if tr.get('success') and tr.get('state') in ['no_data', 'no_trade_today', 'closed']:
            meta = {
                'source': tr.get('source'),
                'asOf': tr.get('asOf'),
                'state': tr.get('state'),
                'currency': tr.get('currency', 'TMN'),
                'category': category,
                'alert_eligible': False,
            }
            PRICE_CACHE[cache_key] = (None, now, meta)
            break
    return None

async def check_alerts_job():
    client = state.http_client
    if client is None:
        return

    current_time = time.time()
    METRICS["total_checks"] += 1

    active_alerts = [
        a for a in ALERTS_DB
        if a.is_active and getattr(a, 'alert_nature', 'price') == 'price' and (
            a.target_price > 0 or 
            (a.upper_target_price is not None and a.upper_target_price > 0) or 
            (a.lower_target_price is not None and a.lower_target_price > 0) or
            (a.percent is not None and a.percent > 0 and (a.base_price or 0) > 0)
        ) and a.exchange.lower() not in ['timer', 'local', 'clock', 'none']
    ]
    ready_alerts = [
        a for a in active_alerts
        if (current_time - a.last_checked_at) >= a.check_interval_seconds
        and is_market_open(a.exchange, a.symbol)
    ]

    if not ready_alerts:
        return

    # Update last_checked_at pre-fetch to prevent any concurrent overlap
    for a in ready_alerts:
        a.last_checked_at = current_time

    # Group unique pairs to batch fetch concurrently
    unique_pairs = list({(a.exchange, a.symbol) for a in ready_alerts})
    tasks = [get_cached_price(client, ex, sym) for ex, sym in unique_pairs]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    prices: Dict[str, float] = {}
    for (ex, sym), price in zip(unique_pairs, results):
        if isinstance(price, (int, float)) and price > 0:
            prices[f"{ex.lower()}:{normalize_symbol(sym)}"] = float(price)

    updated = False

    async def _process(alert):
        nonlocal updated
        key = f"{alert.exchange.lower()}:{normalize_symbol(alert.symbol)}"
        current_price = prices.get(key)

        if current_price is None:
            # retry ~5s later instead of waiting a full interval
            alert.last_checked_at = current_time - max(0, alert.check_interval_seconds - 5)
            return

        cached_entry = PRICE_CACHE.get(key)
        cached_meta = cached_entry[2] if (cached_entry and len(cached_entry) > 2 and isinstance(cached_entry[2], dict)) else {}

        # 0. Rule 5 Alert Guard: Never trigger alerts on stale, carried-over, closed, or untraded market data
        if (cached_meta.get('alert_eligible') is False or 
            cached_meta.get('carried_over') is True or 
            cached_meta.get('is_stale') is True or 
            cached_meta.get('state') in ['CARRIED_OVER', 'STALE', 'CLOSED', 'NO_TRADE_TODAY', 'closed', 'no_trade_today', 'no_data']):
            return

        # 1. Closed-Market Policy (Option B):
        as_of = cached_meta.get('asOf')
        if as_of is not None:
            m_state = cached_meta.get('state')
            if m_state == 'REGULAR' and (time.time() - as_of) > 900:
                cached_meta['is_delayed'] = True

            last_asof = getattr(alert, 'last_eval_asof', None)
            if last_asof is not None and last_asof == as_of:
                return
            alert.last_eval_asof = as_of

        # Determine effective target parameters
        cond_type = getattr(alert, 'condition_type', 'priceThreshold') or 'priceThreshold'
        pct = getattr(alert, 'percent', None)
        base_p = getattr(alert, 'base_price', None)
        upper_t = getattr(alert, 'upper_target_price', None)
        lower_t = getattr(alert, 'lower_target_price', None)
        eff_cond = (alert.condition or 'ABOVE').upper()

        eff_target = alert.target_price
        eff_upper = upper_t
        eff_lower = lower_t

        if cond_type == 'percentChange' and pct is not None and pct > 0 and base_p and base_p > 0:
            eff_upper = base_p * (1.0 + pct / 100.0)
            eff_lower = base_p * (1.0 - pct / 100.0)
            if eff_cond in ['BOTHSIDES', 'BOTH']:
                eff_target = eff_upper if current_price >= base_p else eff_lower
            elif eff_cond == 'BELOW':
                eff_target = eff_lower
            else:
                eff_target = eff_upper
        elif eff_upper is not None and eff_lower is not None:
            eff_target = eff_upper if current_price >= ((eff_upper + eff_lower) / 2.0) else eff_lower

        # 2. Level-Crossing Guard (Edge-Trigger Hysteresis across ALL markets):
        if getattr(alert, 'last_eval_price', None) is None:
            alert.last_eval_price = current_price
            is_initially_triggered = False
            if eff_upper is not None and eff_lower is not None and eff_cond in ['BOTHSIDES', 'BOTH']:
                is_initially_triggered = (current_price >= eff_upper or current_price <= eff_lower)
            elif eff_cond == 'ABOVE' and current_price >= eff_target:
                is_initially_triggered = True
            elif eff_cond == 'BELOW' and current_price <= eff_target:
                is_initially_triggered = True

            if is_initially_triggered:
                alert.waiting_for_cross = True
                print(f"🛡️ [Edge Guard] {alert.symbol} ({alert.exchange}): initial price {current_price} already meets target {eff_target}. Armed for crossing.")
                return

        # If waiting for price to cross to the non-triggered side first:
        if getattr(alert, 'waiting_for_cross', False):
            if eff_upper is not None and eff_lower is not None and eff_cond in ['BOTHSIDES', 'BOTH']:
                if current_price < eff_upper and current_price > eff_lower:
                    alert.waiting_for_cross = False
                    print(f"🎯 [Edge Armed] {alert.symbol} entered corridor between {eff_lower} and {eff_upper} ({current_price}).")
            elif eff_cond == 'ABOVE' and current_price < eff_target:
                alert.waiting_for_cross = False
                print(f"🎯 [Edge Armed] {alert.symbol} dipped below {eff_target} ({current_price}). Ready to trigger on upward crossing.")
            elif eff_cond == 'BELOW' and current_price > eff_target:
                alert.waiting_for_cross = False
                print(f"🎯 [Edge Armed] {alert.symbol} rose above {eff_target} ({current_price}). Ready to trigger on downward crossing.")
            alert.last_eval_price = current_price
            return

        alert.last_eval_price = current_price

        triggered = False
        is_above = True
        triggered_target = eff_target
        triggered_note = alert.note

        if eff_upper is not None and eff_lower is not None and eff_cond in ['BOTHSIDES', 'BOTH']:
            if current_price >= eff_upper:
                triggered = True
                is_above = True
                triggered_target = eff_upper
                triggered_note = getattr(alert, 'upper_note', None) or alert.note
            elif current_price <= eff_lower:
                triggered = True
                is_above = False
                triggered_target = eff_lower
                triggered_note = getattr(alert, 'lower_note', None) or alert.note
        elif eff_cond == 'ABOVE' and current_price >= eff_target:
            triggered = True
            is_above = True
            triggered_target = eff_target
            triggered_note = getattr(alert, 'upper_note', None) or alert.note
        elif eff_cond == 'BELOW' and current_price <= eff_target:
            triggered = True
            is_above = False
            triggered_target = eff_target
            triggered_note = getattr(alert, 'lower_note', None) or alert.note

        if triggered:
            async with _db_lock:
                last_trig = getattr(alert, 'last_triggered_at', 0.0)
                is_one_shot = getattr(alert, 'trigger_mode', 'oneShot') == 'oneShot'
                min_cooldown = max(30.0, float(alert.check_interval_seconds))

                if is_one_shot:
                    if not alert.is_active or last_trig > 0:
                        return
                else:
                    if (current_time - last_trig) < min_cooldown:
                        return

                alert.last_triggered_at = current_time
                if is_one_shot:
                    alert.is_active = False
                updated = True

            METRICS["total_triggers"] += 1
            print(f"🔔 [TRIGGER] {alert.symbol} @ {current_price} (Target: {triggered_target})")

            emoji = '🟢' if is_above else '🔴'
            arrow = '▲' if is_above else '▼'
            sign = '+' if is_above else '-'

            display_symbol = alert.symbol
            pct_str = f"{sign}{abs(((current_price - triggered_target) / triggered_target) * 100.0):.2f}%" if (triggered_target and triggered_target > 0) else ""
            price_formatted = f"${current_price:,.4f}".rstrip('0').rstrip('.') if current_price < 1 else f"${current_price:,.2f}"
            if alert.symbol.endswith('TMN') or alert.symbol.endswith('IRT') or getattr(alert, 'exchange', '').lower() == 'nobitex':
                price_formatted = f"{int(current_price):,} تومان"
            if '/' not in display_symbol:
                for quote in ['USDT', 'USDC', 'BUSD', 'FDUSD', 'EUR', 'USD', 'TMN', 'IRT', 'BTC', 'ETH']:
                    if display_symbol.endswith(quote):
                        base = display_symbol[:-len(quote)]
                        display_symbol = f"{base}/{quote}"
                        break

            title = f"{emoji} {display_symbol} {pct_str} {price_formatted} {arrow}".replace('  ', ' ')
            exchange_name = get_exchange_display_name(alert.exchange)
            resolved_source = cached_meta.get('source')
            source_badge = f" [via {resolved_source}]" if (resolved_source and alert.exchange.lower() not in resolved_source.lower()) else ""
            body_lines = [f"🏛️ {exchange_name}{source_badge}"]
            if triggered_note and triggered_note.strip():
                clean_note = triggered_note.strip()
                if not clean_note.startswith('📝'):
                    clean_note = f"📝 {clean_note}"
                body_lines.append(clean_note)
            body = "\n".join(body_lines)

            # 1. Durable FCM push
            await enqueue_alert_push(
                alert,
                title,
                body,
                {
                    "alert_id": alert.id,
                    "symbol": display_symbol,
                    "price": str(current_price),
                    "note": alert.note or "",
                    "sound_enabled": "true" if alert.sound_enabled else "false",
                    "vibration_enabled": "true" if alert.vibration_enabled else "false",
                    "tts_enabled": "true" if alert.tts_enabled else "false",
                    "sound": alert.sound or "alarm_siren"
                }
            )

            # 2. Exact Telegram Notification
            effective_chat_id = (alert.telegram_chat_id or "").strip()
            if not effective_chat_id:
                user_prof = USER_PROFILES_DB.get(alert.user_id.lower(), {})
                effective_chat_id = (user_prof.get('telegram_chat_id') or "").strip()
            if not effective_chat_id and 'user_default' in USER_PROFILES_DB:
                effective_chat_id = (USER_PROFILES_DB['user_default'].get('telegram_chat_id') or "").strip()

            if effective_chat_id:
                tg_lines = [
                    f"{emoji} <b>{html.escape(display_symbol)}</b> {pct_str} {price_formatted} {arrow}".replace('  ', ' '),
                    f"🏛️ {html.escape(exchange_name)}"
                ]
                if triggered_note and triggered_note.strip():
                    clean_n = triggered_note.strip()
                    if clean_n.startswith('📝'):
                        clean_n = clean_n[1:].strip()
                    if clean_n:
                        tg_lines.append(f"📝 {html.escape(clean_n)}")

                tg_msg = "\n".join(tg_lines)
                _spawn(send_telegram_alert(client, effective_chat_id, tg_msg))

            # 3. Optional Webhook with SSRF Protection
            if alert.webhook_url:
                hook_data = {
                    "event": "price_alert_triggered",
                    "alert_id": alert.id,
                    "symbol": display_symbol,
                    "price": current_price,
                    "target_price": alert.target_price,
                    "condition": alert.condition,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                _spawn(send_webhook_alert(client, alert.webhook_url, hook_data))

    for alert in ready_alerts:
        try:
            await _process(alert)
        except Exception as e:
            print(f"❌ [Alert Job] {alert.id} {alert.symbol}: {e}")

    if updated:
        await save_alerts_to_disk_async(ALERTS_DB)


async def check_macro_alerts_job():
    """
    Daily Macro Alerts Evaluation Job (Phase 6 / v2.9.1):
    Runs daily on scheduler (distinct from the 2s price alert job).
    Evaluates alerts where alert_nature == 'macro'.
    Supported conditions:
    1. «مقدار جدید منتشر شد» (NEW_RELEASE, NEW_VALUE, newRelease):
       Triggers when a new macro observation release date or value is published.
    2. «از آستانه رد شد» (THRESHOLD_CROSS, ABOVE, BELOW, thresholdCross):
       Triggers when published macro indicator crosses/meets the threshold.
    """
    client = state.http_client
    if client is None:
        return

    current_time = time.time()
    METRICS["total_macro_checks"] = METRICS.get("total_macro_checks", 0) + 1

    macro_alerts = [
        a for a in ALERTS_DB
        if a.is_active and getattr(a, 'alert_nature', 'price') == 'macro'
        and a.exchange.lower() not in ['timer', 'local', 'clock', 'none']
    ]

    if not macro_alerts:
        return

    for a in macro_alerts:
        a.last_checked_at = current_time

    unique_pairs = list({(a.exchange, a.symbol) for a in macro_alerts})
    macro_data: Dict[str, Tuple[Optional[float], List[Dict[str, Any]]]] = {}

    for ex, sym in unique_pairs:
        try:
            price, traces = await fetch_price_with_trace(client, ex, sym, collect_all_traces=False)
            macro_data[f"{ex.lower()}:{normalize_symbol(sym)}"] = (price, traces)
        except Exception as e:
            print(f"❌ [Macro Job Fetch Error] {ex}:{sym}: {e}")

    updated = False

    async def _process_macro(alert):
        nonlocal updated
        key = f"{alert.exchange.lower()}:{normalize_symbol(alert.symbol)}"
        data_entry = macro_data.get(key)
        if not data_entry:
            return
        price, traces = data_entry
        if price is None:
            return

        meta = traces[0] if (traces and isinstance(traces[0], dict)) else {}
        as_of = meta.get('asOf')
        release_date = meta.get('date') or (str(as_of) if as_of else None)
        source = meta.get('source') or 'Macro Provider'
        currency = meta.get('currency') or '%'

        cond = (alert.condition or 'NEW_RELEASE').strip().upper()
        cond_type = str(getattr(alert, 'condition_type', '') or '').strip()

        is_new_release = (
            cond in ('NEW_RELEASE', 'NEW_VALUE', 'NEW_RELEASE_PUBLISHED', 'RELEASE', 'مقدار جدید منتشر شد')
            or cond_type in ('newRelease', 'macroRelease', 'new_release')
        )

        triggered = False
        trigger_reason = ""

        if is_new_release:
            # Baseline initialization on first run:
            if getattr(alert, 'last_macro_release_date', None) is None and getattr(alert, 'last_macro_value', None) is None:
                alert.last_macro_value = price
                alert.last_macro_release_date = str(release_date) if release_date else None
                alert.last_eval_price = price
                alert.last_eval_asof = as_of
                print(f"🛡️ [Macro Armed] {alert.symbol} initialized with baseline {price} (date: {release_date}).")
                return

            # Check if a new release arrived:
            has_new_date = bool(release_date and alert.last_macro_release_date and str(release_date) != alert.last_macro_release_date)
            has_new_asof = bool(as_of and alert.last_eval_asof and as_of > alert.last_eval_asof)
            has_new_val = bool(alert.last_macro_value is not None and abs(price - alert.last_macro_value) > 1e-6)

            if has_new_date or has_new_asof or has_new_val:
                triggered = True
                trigger_reason = f"مقدار جدید منتشر شد: {price} {currency}"
                if release_date:
                    trigger_reason += f" (تاریخ: {release_date})"
        else:
            # Condition: «از آستانه رد شد» (THRESHOLD_CROSS / ABOVE / BELOW)
            target = alert.target_price
            if getattr(alert, 'last_eval_price', None) is None:
                alert.last_eval_price = price
                alert.last_macro_value = price
                alert.last_macro_release_date = str(release_date) if release_date else None
                alert.last_eval_asof = as_of
                is_initially_at_target = False
                if cond in ('BELOW',) and price <= target:
                    is_initially_at_target = True
                elif price >= target:
                    is_initially_at_target = True

                if is_initially_at_target:
                    alert.waiting_for_cross = True
                    print(f"🛡️ [Macro Edge Guard] {alert.symbol}: initial value {price} already at target {target}. Armed for crossing.")
                    return

            if getattr(alert, 'waiting_for_cross', False):
                if cond in ('BELOW',) and price > target:
                    alert.waiting_for_cross = False
                    print(f"🎯 [Macro Edge Armed] {alert.symbol} rose above target {target} ({price}). Ready to trigger on downward crossing.")
                elif price < target:
                    alert.waiting_for_cross = False
                    print(f"🎯 [Macro Edge Armed] {alert.symbol} dipped below target {target} ({price}). Ready to trigger on upward crossing.")
                alert.last_eval_price = price
                return

            if cond in ('BELOW',) and price <= target:
                triggered = True
                trigger_reason = f"نزول به زیر آستانه {target} (مقدار: {price} {currency})"
            elif price >= target:
                triggered = True
                trigger_reason = f"عبور از آستانه {target} (مقدار: {price} {currency})"

        if triggered:
            async with _db_lock:
                is_one_shot = getattr(alert, 'trigger_mode', 'oneShot') == 'oneShot'
                alert.last_triggered_at = current_time
                alert.last_eval_price = price
                alert.last_macro_value = price
                alert.last_macro_release_date = str(release_date) if release_date else None
                alert.last_eval_asof = as_of
                if is_one_shot:
                    alert.is_active = False
                updated = True

            METRICS["total_macro_triggers"] = METRICS.get("total_macro_triggers", 0) + 1
            print(f"🔔 [MACRO TRIGGER] {alert.symbol}: {trigger_reason}")

            title = f"📊 [هشدار ماکرو] {alert.symbol} {price} {currency}"
            body_lines = [f"🏛️ {source}", f"📢 {trigger_reason}"]
            if alert.note and alert.note.strip():
                clean_n = alert.note.strip()
                if not clean_n.startswith('📝'):
                    clean_n = f"📝 {clean_n}"
                body_lines.append(clean_n)
            body = "\n".join(body_lines)

            # 1. FCM Push
            await enqueue_alert_push(
                alert,
                title,
                body,
                {
                    "alert_id": alert.id,
                    "symbol": alert.symbol,
                    "price": str(price),
                    "note": alert.note or "",
                    "sound_enabled": "true" if alert.sound_enabled else "false",
                    "vibration_enabled": "true" if alert.vibration_enabled else "false",
                    "tts_enabled": "true" if alert.tts_enabled else "false",
                    "sound": alert.sound or "alarm_siren",
                    "nature": "macro"
                }
            )

            # 2. Telegram
            effective_chat_id = (alert.telegram_chat_id or "").strip()
            if not effective_chat_id:
                user_prof = USER_PROFILES_DB.get(alert.user_id.lower(), {})
                effective_chat_id = (user_prof.get('telegram_chat_id') or "").strip()
            if not effective_chat_id and 'user_default' in USER_PROFILES_DB:
                effective_chat_id = (USER_PROFILES_DB['user_default'].get('telegram_chat_id') or "").strip()

            if effective_chat_id:
                tg_lines = [
                    f"📊 <b>{html.escape(alert.symbol)}</b> (داده اقتصاد کلان)",
                    f"🏛️ {html.escape(source)}",
                    f"📢 {html.escape(trigger_reason)}"
                ]
                if alert.note and alert.note.strip():
                    tg_lines.append(f"📝 {html.escape(alert.note.strip())}")
                tg_msg = "\n".join(tg_lines)
                _spawn(send_telegram_alert(client, effective_chat_id, tg_msg))

            # 3. Webhook
            if alert.webhook_url:
                hook_data = {
                    "event": "macro_alert_triggered",
                    "alert_id": alert.id,
                    "symbol": alert.symbol,
                    "price": price,
                    "target_price": alert.target_price,
                    "condition": alert.condition,
                    "trigger_reason": trigger_reason,
                    "release_date": release_date,
                    "source": source,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                _spawn(send_webhook_alert(client, alert.webhook_url, hook_data))

    for alert in macro_alerts:
        try:
            await _process_macro(alert)
        except Exception as e:
            print(f"❌ [Macro Alert Job] {alert.id} {alert.symbol}: {e}")

    if updated:
        await save_alerts_to_disk_async(ALERTS_DB)

