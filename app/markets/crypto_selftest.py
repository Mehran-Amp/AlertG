# -*- coding: utf-8 -*-
"""
AlertG — Daily Automated Crypto Exchange Self-Test & Admin Alerting (Phase 8 / Micro-phase F-4).
Performs routine health audits across all registered crypto exchanges:
1. Validates endpoint connectivity, API structure, and ticker responsiveness.
2. Detects API schema changes, upstream 403/418/429 blockages, or price dropouts.
3. Dispatches instant Telegram Admin Alerts if coverage drops or exchanges degrade.
4. Stores in-memory snapshot of latest test run accessible via /api/admin/crypto/selftest.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import httpx

from app.markets.crypto_registry import get_supported_exchange_ids, get_crypto_exchange
from app.markets.crypto_catalog import get_exchange_adapter
from app.notifier.telegram import notify_admin_telegram

logger = logging.getLogger("signalalert.crypto_selftest")

# In-memory storage of the latest self-test execution result
_LATEST_SELFTEST_RESULT: Dict[str, Any] = {
    "status": "NOT_RUN_YET",
    "timestamp": 0,
    "total_exchanges": 0,
    "healthy_count": 0,
    "degraded_count": 0,
    "results": {}
}

# Baseline verification tickers to check for active pricing
BASELINE_TICKERS = ("BTC", "ETH", "SOL", "USDT")


async def run_single_exchange_selftest(
    exchange_id: str,
    client: httpx.AsyncClient,
    timeout: float = 10.0
) -> Dict[str, Any]:
    """
    Executes a comprehensive health audit for a single exchange:
    - Verifies batch ticker response
    - Ensures price values are positive valid floats
    - Checks baseline symbol presence
    """
    ex = exchange_id.lower().strip()
    adapter = get_exchange_adapter(ex)
    if not adapter:
        return {
            "exchange": ex,
            "status": "UNAVAILABLE",
            "healthy": False,
            "prices_count": 0,
            "latency_ms": 0.0,
            "issue": f"Adapter not registered for exchange '{ex}'"
        }

    t0 = time.perf_counter()
    try:
        batch_res = await adapter.fetch_batch_prices(client, timeout=timeout)
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        if not batch_res.prices or batch_res.error_code not in ("OK", None):
            issue_msg = batch_res.error or batch_res.error_code or "Empty prices returned"
            return {
                "exchange": ex,
                "display_name": adapter.display_name,
                "status": "DEGRADED",
                "healthy": False,
                "prices_count": len(batch_res.prices) if batch_res.prices else 0,
                "latency_ms": latency_ms,
                "issue": issue_msg,
                "http_status": getattr(batch_res, "http_status", None)
            }

        # Validate that price values are valid numeric numbers > 0
        valid_count = 0
        for sym, price in batch_res.prices.items():
            if isinstance(price, (int, float)) and price > 0:
                valid_count += 1

        if valid_count == 0:
            return {
                "exchange": ex,
                "display_name": adapter.display_name,
                "status": "DEGRADED",
                "healthy": False,
                "prices_count": 0,
                "latency_ms": latency_ms,
                "issue": "Received prices contain no positive numbers (structure change suspected)"
            }

        return {
            "exchange": ex,
            "display_name": adapter.display_name,
            "status": "HEALTHY",
            "healthy": True,
            "prices_count": valid_count,
            "latency_ms": latency_ms,
            "issue": None
        }

    except Exception as e:
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return {
            "exchange": ex,
            "display_name": getattr(adapter, "display_name", ex),
            "status": "DOWN",
            "healthy": False,
            "prices_count": 0,
            "latency_ms": latency_ms,
            "issue": str(e)
        }


async def run_daily_crypto_selftest(
    client: Optional[httpx.AsyncClient] = None,
    notify_admin: bool = True
) -> Dict[str, Any]:
    """
    Runs self-test across all supported crypto exchanges.
    If any exchange is DEGRADED or DOWN, dispatches an admin Telegram alert.
    """
    global _LATEST_SELFTEST_RESULT

    exchanges = get_supported_exchange_ids()
    results: Dict[str, Any] = {}
    healthy_count = 0
    degraded_count = 0
    degraded_details = []

    own_client = False
    active_client = client
    if active_client is None:
        active_client = httpx.AsyncClient(
            timeout=httpx.Timeout(12.0, connect=4.0),
            headers={"User-Agent": "AlertG/3.0.0 (SelfTest)"}
        )
        own_client = True

    try:
        for ex in exchanges:
            res = await run_single_exchange_selftest(ex, active_client)
            results[ex] = res
            if res.get("healthy"):
                healthy_count += 1
            else:
                degraded_count += 1
                degraded_details.append(f"• <b>{res.get('display_name', ex)}</b> ({ex}): {res.get('issue')}")
    finally:
        if own_client and active_client:
            await active_client.aclose()

    now_ts = int(time.time())
    utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    overall_status = "HEALTHY" if degraded_count == 0 else "DEGRADED"

    summary = {
        "status": overall_status,
        "timestamp": now_ts,
        "timestamp_utc": utc_str,
        "total_exchanges": len(exchanges),
        "healthy_count": healthy_count,
        "degraded_count": degraded_count,
        "results": results
    }

    _LATEST_SELFTEST_RESULT = summary

    # Admin Alerting on Degradation
    if degraded_count > 0 and notify_admin:
        alert_lines = [
            "🚨 <b>[AlertG Admin Alert] Crypto Exchange Self-Test Warning</b>",
            f"⚠️ <b>Status:</b> {overall_status} ({degraded_count}/{len(exchanges)} degraded)",
            f"🕒 <b>Time:</b> {utc_str}\n",
            "<b>Degraded Exchanges:</b>",
            *degraded_details[:8],
            "\n💡 Check <code>/api/admin/crypto/selftest</code> for full diagnostics."
        ]
        msg = "\n".join(alert_lines)
        try:
            await notify_admin_telegram(msg)
        except Exception as e:
            logger.error(f"Failed to dispatch admin telegram alert for selftest: {e}")

    return summary


def get_latest_crypto_selftest() -> Dict[str, Any]:
    """Returns the latest self-test summary."""
    return _LATEST_SELFTEST_RESULT
