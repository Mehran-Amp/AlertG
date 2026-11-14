# -*- coding: utf-8 -*-
"""
Iranian Bourse — notification text and payloads (IB-10).

Prices stay in Rial and are shown with thousands separators and the unit "ریال" (decision D1, no
Toman conversion). The Persian instrument NAME is shown, never the raw id. Push/webhook payloads
carry exchange=tsetmc, symbol=<id>, ticker, name. Used only for exchange 'tsetmc'.
"""
import html
import time
from typing import Any, Dict, Optional, Tuple

UNIT_FA = "ریال"
UNIT_EN = "IRR"
EXCHANGE_FA = "بورس ایران"


def format_rial(value: Optional[float], lang: str = "fa") -> str:
    """693731 -> '693,731 ریال'. Whole Rials; a fractional value keeps up to 2 decimals."""
    if value is None:
        return "-"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    unit = UNIT_EN if lang == "en" else UNIT_FA
    text = f"{int(round(f)):,}" if abs(f - round(f)) < 1e-9 else f"{f:,.2f}"
    return f"{text} {unit}"


def _alert_id(alert: Any) -> str:
    return str(getattr(alert, "symbol", "") or "")


def _lookup_name(alert: Any) -> Optional[str]:
    """Name from the snapshot or the directory cache, if we already have it (no I/O)."""
    iid = _alert_id(alert)
    try:
        from app.markets.iran_bourse import poller as pmod
        if pmod.BOURSE_POLLER is not None:
            e = pmod.BOURSE_POLLER.store.get(iid)
            if e and e["quote"].get("name"):
                return e["quote"]["name"]
    except Exception:
        pass
    try:
        from app.markets.iran_bourse.directory import DIRECTORY
        info, ok = DIRECTORY.cache.get(("i", iid))
        if ok and info and info.get("name"):
            return info["name"]
    except Exception:
        pass
    return None


def ticker_of(alert: Any, meta: Optional[dict] = None) -> str:
    return str((meta or {}).get("ticker") or getattr(alert, "market_symbol", "") or "")


def name_of(alert: Any, meta: Optional[dict] = None) -> str:
    """Persian name, else ticker, else (last resort) the id."""
    return str((meta or {}).get("name") or _lookup_name(alert) or ticker_of(alert, meta) or _alert_id(alert))


def trigger_display(alert: Any, meta: dict, price: float) -> Tuple[str, str]:
    """(display name, price text) for the push title."""
    return name_of(alert, meta), format_rial(price, getattr(alert, "language", "fa") or "fa")


def trigger_payload(alert: Any, meta: Optional[dict] = None) -> Dict[str, str]:
    """Extra push/webhook fields. symbol is the id; all values are strings (FCM data rule)."""
    return {"exchange": "tsetmc", "symbol": _alert_id(alert), "ticker": ticker_of(alert, meta),
            "name": name_of(alert, meta), "unit": UNIT_EN}


def _lang(alert: Any) -> str:
    return "en" if (getattr(alert, "language", "fa") or "fa").lower().startswith("en") else "fa"


def _kind(alert: Any, meta: Optional[dict] = None) -> str:
    n, t = name_of(alert, meta), ticker_of(alert, meta)
    return f"{n} ({t})" if t and t != n else n


def telegram_registered(alert: Any) -> str:
    lang = _lang(alert)
    cond = (getattr(alert, "condition", "ABOVE") or "ABOVE").upper()
    arrow = "⇅" if cond == "BOTHSIDES" else ("▲" if cond == "ABOVE" else "▼")
    if getattr(alert, "condition_type", "") == "percentChange" and getattr(alert, "percent", None):
        target = f"{alert.percent:g}%"
    elif getattr(alert, "condition_type", "") == "absolutePriceChange" and getattr(alert, "delta_absolute", None):
        target = format_rial(alert.delta_absolute, lang)
    else:
        target = format_rial(getattr(alert, "target_price", 0.0), lang)
    ex = "Iran Bourse" if lang == "en" else EXCHANGE_FA
    lines = [f"✅ <b>{html.escape(_kind(alert))}</b> <code>{html.escape(target)}</code> {arrow}", f"🏛️ {ex}"]
    note = getattr(alert, "note", None)
    if note and str(note).strip():
        lines.append(f"📝 {html.escape(str(note).strip().lstrip('📝').strip())}")
    return f"<blockquote>{chr(10).join(lines)}</blockquote>"


def telegram_history_card(alert: Any, current_price: float, triggered_target: Optional[float],
                          previous_price: Optional[float], meta: Optional[dict], custom_note: Optional[str]) -> str:
    lang = _lang(alert)
    fa = lang == "fa"
    from app.engine.calendar import get_tehran_now
    ref = triggered_target or previous_price or getattr(alert, "target_price", None)
    move = ""
    up = (getattr(alert, "condition", "ABOVE") or "ABOVE").upper() != "BELOW"
    if ref and ref > 0:
        pct = (current_price - ref) / ref * 100.0
        up = pct >= 0
        move = f"{'+' if up else ''}{pct:.2f}%"
    icon = "🟢 ▲" if up else "🔴 ▼"
    lines = [
        f"🏷️ <b>{'نماد' if fa else 'Instrument'}:</b> {html.escape(_kind(alert, meta))}",
        f"🏛️ <b>{'بازار' if fa else 'Market'}:</b> {EXCHANGE_FA if fa else 'Iran Bourse'}",
        "",
    ]
    if ref and ref > 0 and abs(current_price - ref) > 1e-6:
        lines.append(f"🎯 <b>{'هدف / مرجع' if fa else 'Target / Reference'}:</b> <code>{format_rial(ref, lang)}</code>")
    lines.append(f"⚡ <b>{'قیمت لحظه‌ای' if fa else 'Triggered At'}:</b> <b><code>{format_rial(current_price, lang)}</code></b> {icon}")
    if move:
        lines.append(f"📈 <b>{'تغییر' if fa else 'Movement'}:</b> <code>{move}</code>")
    close = (meta or {}).get("prev_close")
    if close:
        lines.append(f"📅 <b>{'قیمت پایانی دیروز' if fa else 'Yesterday close'}:</b> <code>{format_rial(close, lang)}</code>")
    note = custom_note or getattr(alert, "note", None)
    if note and str(note).strip():
        lines.append(f"📝 <i>{html.escape(str(note).strip().lstrip('📝').strip())}</i>")
    stamp = get_tehran_now().strftime("%Y-%m-%d %H:%M")
    title = "🔔 <b>هشدار فعال شد</b>" if fa else "🔔 <b>ALERT TRIGGERED</b>"
    foot = f"🕒 {stamp} ({'تهران' if fa else 'Tehran'})"
    return f"{title}\n\n<blockquote>{chr(10).join(lines)}</blockquote>\n\n<blockquote>{foot}</blockquote>"


def missing_text(alert: Any) -> Tuple[str, str]:
    """(title, body) when an instrument vanishes from the data feed."""
    name = name_of(alert)
    if _lang(alert) == "en":
        return (f"⚠️ {name} is no longer listed",
                "The instrument is missing from the Bourse data feed. Your alert is kept but needs attention.")
    return (f"⚠️ نماد {name} دیگر در دسترس نیست",
            "این نماد از فهرست داده‌های بورس حذف شده است. هشدار شما ذخیره مانده ولی نیاز به بررسی دارد.")


async def dispatch_missing_notifications(alerts, client=None) -> int:
    """One Telegram + one FCM message per vanished instrument (attention_notified_at guards repeats)."""
    from app.notifier.telegram import send_telegram_alert
    from app.notifier import send_fcm_notification_async
    sent = 0
    for a in alerts:
        if not getattr(a, "needs_attention", False) or getattr(a, "attention_notified_at", None):
            continue
        title, body = missing_text(a)
        chat = getattr(a, "telegram_chat_id", None)
        if chat and client is not None:
            try:
                await send_telegram_alert(client, str(chat), f"<blockquote>{html.escape(title)}\n{html.escape(body)}</blockquote>")
            except Exception:
                pass
        tok = getattr(a, "fcm_token", None)
        if tok:
            try:
                await send_fcm_notification_async(
                    fcm_token=tok, title=title, body=body,
                    data_payload={**trigger_payload(a), "type": "instrument_missing",
                                  "alert_id": str(a.id), "needs_attention": "true"})
            except Exception:
                pass
        a.attention_notified_at = time.time()
        sent += 1
    return sent
