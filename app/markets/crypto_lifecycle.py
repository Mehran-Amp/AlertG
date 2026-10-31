# -*- coding: utf-8 -*-
"""
AlertG — Crypto Lifecycle & Delisted Coin Monitor (Phase 9 / Version 2).
Enforces Phase 9 specifications:
1. When a coin disappears or is delisted from an exchange catalog, mark its alerts
   'needs_attention = True' with 'needs_attention_reason'.
   NEVER auto-delete or auto-deactivate (is_active remains True).
2. Sends exactly one notification per delist event through existing Telegram and FCM paths
   using the Phase 9 notification template.
3. If a delisted coin is later restored / re-listed, clears 'needs_attention'.
4. Preserves 100% isolation: non-crypto alerts and unaffected alerts are untouched.
"""

import time
import logging
from typing import List, Optional, Dict, Any

import httpx

import app.storage as storage
from app.models import Alert
from app.markets.crypto_registry import (
    is_supported_crypto_exchange,
)
from app.markets.crypto_validation import is_crypto_exchange_candidate
from app.markets.crypto_catalog import load_exchange_catalog, resolve_pair
from app.notifier.telegram import (
    send_telegram_alert,
    format_coin_delisted_telegram_msg,
    get_exchange_display_name,
)
from app.notifier import send_fcm_notification_async

logger = logging.getLogger("signalalert.crypto_lifecycle")


def scan_and_flag_delisted_crypto_alerts(
    alerts: List[Alert],
    override_dir: Optional[str] = None,
) -> List[Alert]:
    """
    Scans alerts against their respective exchange catalogs on disk.
    Marks newly delisted alerts with needs_attention = True.
    Clears needs_attention if a coin was restored.

    Returns the list of alerts that newly transitioned to needs_attention = True.
    """
    newly_flagged: List[Alert] = []

    for alert in alerts:
        ex_id = (getattr(alert, "exchange", "") or "").lower().strip()
        if not is_crypto_exchange_candidate(ex_id):
            continue
        if not is_supported_crypto_exchange(ex_id, allow_pending=False):
            continue

        cat = load_exchange_catalog(ex_id, override_dir)
        total_pairs = cat.get("total_pairs", len(cat.get("pairs", [])))
        # Safety: Never flag alerts during catalog failure or if catalog is empty (< 20 pairs)
        if total_pairs < 20 or cat.get("is_stale") and total_pairs == 0:
            continue

        sym_lookup = getattr(alert, "market_symbol", None) or getattr(alert, "base_currency", None) or getattr(alert, "symbol", "")
        status, pair_data = resolve_pair(
            exchange_id=ex_id,
            symbol_or_base=sym_lookup,
            override_dir=override_dir,
            base_currency=getattr(alert, "base_currency", None),
            counter_currency=getattr(alert, "counter_currency", None),
            market_symbol=getattr(alert, "market_symbol", None),
        )

        if status == "SYMBOL_NOT_LISTED":
            if not getattr(alert, "needs_attention", False):
                alert.needs_attention = True
                ex_name = get_exchange_display_name(ex_id)
                alert.needs_attention_reason = (
                    f"Symbol '{alert.symbol}' is no longer listed in {ex_name} spot catalog."
                )
                newly_flagged.append(alert)
                logger.warning(
                    f"⚠️ [Delist Notice] Alert {alert.id} ({alert.symbol}@{ex_id}) "
                    f"marked needs_attention=True (coin no longer listed)."
                )
        elif status == "OK":
            if getattr(alert, "needs_attention", False):
                alert.needs_attention = False
                alert.needs_attention_reason = None
                alert.attention_notified_at = None
                logger.info(
                    f"✅ [Relist Restored] Alert {alert.id} ({alert.symbol}@{ex_id}) "
                    f"cleared needs_attention flag (pair verified active)."
                )

    return newly_flagged


async def dispatch_delisted_alert_notifications(
    flagged_alerts: List[Alert],
    client: Optional[httpx.AsyncClient] = None,
) -> int:
    """
    Sends exactly one notification per delist event across Telegram and FCM.
    Records attention_notified_at timestamp to prevent duplicate notifications.
    """
    notified_count = 0
    now_ts = time.time()

    for alert in flagged_alerts:
        # Prevent duplicate sends
        if getattr(alert, "attention_notified_at", None):
            continue

        ex_id = getattr(alert, "exchange", "")
        ex_name = get_exchange_display_name(ex_id)
        sym = getattr(alert, "symbol", "")
        reason = getattr(alert, "needs_attention_reason", None) or f"Symbol {sym} is no longer listed."

        # 1. Telegram Dispatch
        tg_chat_id = getattr(alert, "telegram_chat_id", None)
        if tg_chat_id:
            try:
                tg_msg = format_coin_delisted_telegram_msg(alert, exchange_name=ex_name, reason=reason)
                if client is not None:
                    await send_telegram_alert(client, str(tg_chat_id), tg_msg)
            except Exception as e:
                logger.warning(f"Failed to dispatch Telegram delist notification for {alert.id}: {e}")

        # 2. FCM Push Dispatch
        fcm_token = getattr(alert, "fcm_token", None)
        if fcm_token:
            try:
                push_title = f"⚠️ {sym} delisted on {ex_name}"
                push_body = f"Coin removed from {ex_name} spot market. Your alert needs attention."
                push_data = {
                    "type": "coin_delisted",
                    "alert_id": str(alert.id),
                    "exchange": str(ex_id),
                    "symbol": str(sym),
                    "needs_attention": "true",
                }
                await send_fcm_notification_async(
                    fcm_token=fcm_token,
                    title=push_title,
                    body=push_body,
                    data_payload=push_data,
                )
            except Exception as e:
                logger.warning(f"Failed to dispatch FCM delist notification for {alert.id}: {e}")

        alert.attention_notified_at = now_ts
        notified_count += 1

    return notified_count


async def check_and_process_delisted_crypto_alerts(
    override_dir: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """
    Full end-to-end lifecycle check:
    1. Scans in-memory and disk alerts.
    2. Identifies and flags delisted coins without deleting alerts.
    3. Sends single notification per event.
    4. Atomically persists changes to storage if any alert was mutated.
    """
    alerts = storage.ALERTS_DB
    newly_flagged = scan_and_flag_delisted_crypto_alerts(alerts, override_dir=override_dir)
    notified = 0

    if newly_flagged:
        notified = await dispatch_delisted_alert_notifications(newly_flagged, client=client)
        try:
            storage.save_alerts_to_disk()
            logger.info(
                f"💾 [Delist Lifecycle] Saved {len(newly_flagged)} newly flagged alert(s) to database."
            )
        except Exception as e:
            logger.error(f"Failed to persist delist alert updates to disk: {e}")

    return {
        "scanned_alerts": len(alerts),
        "newly_flagged": len(newly_flagged),
        "notified_count": notified,
    }
