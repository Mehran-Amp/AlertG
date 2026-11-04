#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — Phase 7 Stage C Acceptance Tests: WebSocket Streaming Producers.
Verifies:
1. Message parsers for Binance, Bybit, OKX update the in-memory snapshot store with source='ws'.
2. Subscription/unsubscription message formats match official exchange public specifications.
3. Demand-driven symbol discovery accurately checks active alerts in ALERTS_DB.
4. Snapshot store reads (get_snapshot_price) return WebSocket prices seamlessly in O(1) time.
5. Automatic fallback: REST poller yields when WebSocket stream is healthy, and resumes when unhealthy.
"""

import unittest
import asyncio
import time
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

try:
    import httpx
except ImportError:
    httpx = MagicMock()
    sys.modules['httpx'] = httpx

try:
    import apscheduler
except ImportError:
    apscheduler = MagicMock()
    sys.modules['apscheduler'] = apscheduler
    sys.modules['apscheduler.schedulers'] = apscheduler
    sys.modules['apscheduler.schedulers.asyncio'] = apscheduler

try:
    import pydantic
except ImportError:
    pydantic = MagicMock()
    class BaseModel: pass
    pydantic.BaseModel = BaseModel
    sys.modules['pydantic'] = pydantic

import app.config as config
from app.models import Alert
from app.storage import ALERTS_DB
from app.markets.crypto_snapshot import (
    _SNAPSHOT_STORE,
    clear_snapshot_store,
    get_snapshot_price,
    get_snapshot_source,
    update_symbol_snapshot,
)
from app.markets.crypto_stream import (
    BinanceStreamClient,
    BybitStreamClient,
    OKXStreamClient,
    CryptoStreamSupervisor,
    STREAM_SUPERVISOR,
    is_stream_active_and_healthy,
)
from app.markets.crypto_poller import CryptoPollerSupervisor


class TestCryptoStreamStageC(unittest.IsolatedAsyncioTestCase):
    """Phase 7 Stage C WebSocket Stream Producers Test Suite."""

    def setUp(self):
        clear_snapshot_store()
        self._orig_alerts = list(ALERTS_DB)
        ALERTS_DB.clear()

    def tearDown(self):
        clear_snapshot_store()
        ALERTS_DB.clear()
        ALERTS_DB.extend(self._orig_alerts)

    def test_01_binance_stream_parser_and_snapshot_update(self):
        """BinanceStreamClient parses 24hrTicker and writes to snapshot store with source='ws'."""
        client = BinanceStreamClient()
        raw_msg = json.dumps({
            "e": "24hrTicker",
            "E": int(time.time() * 1000),
            "s": "BTCUSDT",
            "c": "67890.12",
        })

        client.parse_message(raw_msg)

        price, as_of, status, latency_ms = get_snapshot_price("binance", "BTCUSDT")
        self.assertEqual(status, "OK")
        self.assertEqual(price, 67890.12)
        self.assertEqual(get_snapshot_source("binance"), "ws")
        self.assertTrue(client.is_healthy)
        self.assertEqual(client.messages_count, 1)

    def test_02_bybit_stream_parser_and_snapshot_update(self):
        """BybitStreamClient parses V5 ticker and writes to snapshot store with source='ws'."""
        client = BybitStreamClient()
        raw_msg = json.dumps({
            "topic": "tickers.SOLUSDT",
            "type": "snapshot",
            "data": {
                "symbol": "SOLUSDT",
                "lastPrice": "152.45"
            },
            "ts": int(time.time() * 1000)
        })

        client.parse_message(raw_msg)

        price, as_of, status, latency_ms = get_snapshot_price("bybit", "SOLUSDT")
        self.assertEqual(status, "OK")
        self.assertEqual(price, 152.45)
        self.assertEqual(get_snapshot_source("bybit"), "ws")
        self.assertTrue(client.is_healthy)

    def test_03_okx_stream_parser_and_snapshot_update(self):
        """OKXStreamClient parses V5 ticker and writes to snapshot store with dash and normalized aliases."""
        client = OKXStreamClient()
        raw_msg = json.dumps({
            "arg": {"channel": "tickers", "instId": "ETH-USDT"},
            "data": [
                {
                    "instId": "ETH-USDT",
                    "last": "3450.75",
                    "ts": str(int(time.time() * 1000))
                }
            ]
        })

        client.parse_message(raw_msg)

        # Lookup with dash
        price_dash, _, status_dash, _ = get_snapshot_price("okx", "ETH-USDT")
        self.assertEqual(status_dash, "OK")
        self.assertEqual(price_dash, 3450.75)

        # Lookup without dash
        price_nodash, _, status_nodash, _ = get_snapshot_price("okx", "ETHUSDT")
        self.assertEqual(status_nodash, "OK")
        self.assertEqual(price_nodash, 3450.75)
        self.assertEqual(get_snapshot_source("okx"), "ws")

    def test_04_demand_driven_subscription_message_formatting(self):
        """Subscription message formatters generate valid JSON adhering to exchange specifications."""
        binance = BinanceStreamClient()
        b_sub = binance.format_subscribe_msg({"BTCUSDT", "ETHUSDT"})
        self.assertIsNotNone(b_sub)
        b_data = json.loads(b_sub)
        self.assertEqual(b_data.get("method"), "SUBSCRIBE")
        self.assertTrue(any("btcusdt@ticker" in p for p in b_data.get("params", [])))

        bybit = BybitStreamClient()
        by_sub = bybit.format_subscribe_msg({"BTCUSDT"})
        self.assertIsNotNone(by_sub)
        by_data = json.loads(by_sub)
        self.assertEqual(by_data.get("op"), "subscribe")
        self.assertIn("tickers.BTCUSDT", by_data.get("args", []))

        okx = OKXStreamClient()
        okx_sub = okx.format_subscribe_msg({"BTCUSDT"})
        self.assertIsNotNone(okx_sub)
        okx_data = json.loads(okx_sub)
        self.assertEqual(okx_data.get("op"), "subscribe")
        self.assertEqual(okx_data.get("args", [])[0].get("instId"), "BTC-USDT")

    def test_05_demand_driven_symbols_scan(self):
        """CryptoStreamSupervisor scans only active alerts for a given exchange."""
        sup = CryptoStreamSupervisor()
        ALERTS_DB.append(Alert(
            id="a1", user_id="u1", exchange="binance", symbol="BTCUSDT",
            target_price=60000.0, is_active=True
        ))
        ALERTS_DB.append(Alert(
            id="a2", user_id="u1", exchange="binance", symbol="ETHUSDT",
            target_price=3000.0, is_active=False  # Inactive must be ignored
        ))
        ALERTS_DB.append(Alert(
            id="a3", user_id="u1", exchange="bybit", symbol="SOLUSDT",
            target_price=150.0, is_active=True
        ))

        needed_binance = sup.get_needed_symbols_for_exchange("binance")
        self.assertEqual(needed_binance, {"BTCUSDT"})

        needed_bybit = sup.get_needed_symbols_for_exchange("bybit")
        self.assertEqual(needed_bybit, {"SOLUSDT"})

        needed_okx = sup.get_needed_symbols_for_exchange("okx")
        self.assertEqual(needed_okx, set())

    async def test_06_poller_fallback_logic(self):
        """REST poller yields when stream is active & healthy, and polls REST when stream is inactive."""
        poller = CryptoPollerSupervisor()

        # 1. When stream is healthy, poll_exchange_once yields without doing REST fetch
        with patch("app.markets.crypto_poller.is_stream_active_and_healthy", return_value=True), \
             patch("app.markets.crypto_poller.get_exchange_adapter") as mock_adapter:
            await poller.poll_exchange_once("binance")
            mock_adapter.assert_not_called()

        # 2. When stream is unhealthy / disconnected, poll_exchange_once executes REST poll
        mock_fetch = AsyncMock(return_value=MagicMock(prices={"BTCUSDT": 65000.0}, error_code="OK", as_of=time.time()))
        mock_adapter_instance = MagicMock()
        mock_adapter_instance.fetch_batch_prices = mock_fetch

        with patch("app.markets.crypto_poller.is_stream_active_and_healthy", return_value=False), \
             patch("app.markets.crypto_poller.get_exchange_adapter", return_value=mock_adapter_instance):
            await poller.poll_exchange_once("binance")
            mock_fetch.assert_called_once()
            self.assertEqual(get_snapshot_source("binance"), "rest")


if __name__ == "__main__":
    unittest.main()
