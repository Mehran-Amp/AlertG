# -*- coding: utf-8 -*-
"""
AlertG — Real-Time WebSocket Streaming Producers (Phase 7 Stage C).
Provides sub-50ms live price ingestion for Tier A exchanges (Binance, Bybit, OKX).

Specifications:
1. Writes directly into the in-memory snapshot store (update_symbol_snapshot); readers remain O(1) with zero change.
2. Demand-driven subscriptions: Subscribes only to symbols that have active alerts; unsubscribes when alerts are removed.
3. Supervisor: Heartbeat/ping, reconnect with exponential backoff & jitter, resubscribe after reconnect.
4. Automatic fallback: When stream is unhealthy or disconnected, REST poller takes over seamlessly.
5. Per-exchange flags (CRYPTO_STREAM_<EXCHANGE>), default OFF.
"""

import asyncio
import json
import logging
import random
import time
from typing import Dict, Set, Optional, Any, Callable

try:
    import websockets
except ImportError:
    websockets = None

import app.config as config
from app.markets.crypto_snapshot import update_symbol_snapshot
from app.storage import ALERTS_DB

logger = logging.getLogger("signalalert.crypto_stream")


class ExchangeStreamClient:
    """Abstract/Base stream client for a specific exchange."""

    def __init__(self, exchange_id: str, ws_url: str):
        self.exchange_id = exchange_id.lower().strip()
        self.ws_url = ws_url
        self.is_connected = False
        self.is_healthy = False
        self.last_msg_ts = 0.0
        self.messages_count = 0
        self.subscribed_symbols: Set[str] = set()
        self._ws = None
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def is_stream_active(self) -> bool:
        now = time.time()
        max_age = getattr(config, "CRYPTO_SNAPSHOT_MAX_AGE_SECONDS", 10.0)
        return self.is_connected and self.is_healthy and (now - self.last_msg_ts) <= max_age

    def format_subscribe_msg(self, symbols: Set[str]) -> Optional[str]:
        raise NotImplementedError

    def format_unsubscribe_msg(self, symbols: Set[str]) -> Optional[str]:
        raise NotImplementedError

    def parse_message(self, raw_msg: str) -> None:
        raise NotImplementedError

    async def send_heartbeat(self, ws) -> None:
        pass


class BinanceStreamClient(ExchangeStreamClient):
    """Binance Spot Real-Time WebSocket Client."""

    def __init__(self):
        super().__init__("binance", "wss://stream.binance.com:9443/ws")
        self._req_id = 1

    def format_subscribe_msg(self, symbols: Set[str]) -> Optional[str]:
        if not symbols:
            return None
        self._req_id += 1
        params = [f"{s.lower()}@ticker" for s in symbols]
        return json.dumps({"method": "SUBSCRIBE", "params": params, "id": self._req_id})

    def format_unsubscribe_msg(self, symbols: Set[str]) -> Optional[str]:
        if not symbols:
            return None
        self._req_id += 1
        params = [f"{s.lower()}@ticker" for s in symbols]
        return json.dumps({"method": "UNSUBSCRIBE", "params": params, "id": self._req_id})

    def parse_message(self, raw_msg: str) -> None:
        try:
            data = json.loads(raw_msg)
            # Binance 24hrTicker payload: {"e": "24hrTicker", "s": "BTCUSDT", "c": "65123.45", "E": 16725...}
            if isinstance(data, dict) and data.get("e") == "24hrTicker":
                sym = data.get("s", "").upper()
                c_str = data.get("c")
                event_time = data.get("E")
                as_of = (float(event_time) / 1000.0) if event_time else time.time()
                if sym and c_str:
                    price = float(c_str)
                    if price > 0:
                        update_symbol_snapshot(
                            exchange_id="binance",
                            native_symbol=sym,
                            price=price,
                            as_of=as_of,
                            source="ws",
                            latency_ms=round((time.time() - as_of) * 1000.0, 1)
                        )
                        self.last_msg_ts = time.time()
                        self.messages_count += 1
                        self.is_healthy = True
        except Exception as e:
            logger.debug(f"[Binance WS] Parse error: {e}")


class BybitStreamClient(ExchangeStreamClient):
    """Bybit Spot Real-Time WebSocket Client (V5)."""

    def __init__(self):
        super().__init__("bybit", "wss://stream.bybit.com/v5/public/spot")

    def format_subscribe_msg(self, symbols: Set[str]) -> Optional[str]:
        if not symbols:
            return None
        args = [f"tickers.{s.upper()}" for s in symbols]
        return json.dumps({"op": "subscribe", "args": args})

    def format_unsubscribe_msg(self, symbols: Set[str]) -> Optional[str]:
        if not symbols:
            return None
        args = [f"tickers.{s.upper()}" for s in symbols]
        return json.dumps({"op": "unsubscribe", "args": args})

    async def send_heartbeat(self, ws) -> None:
        # Bybit requires periodic {"op": "ping"}
        try:
            await ws.send(json.dumps({"op": "ping"}))
        except Exception:
            pass

    def parse_message(self, raw_msg: str) -> None:
        try:
            data = json.loads(raw_msg)
            # Bybit ticker payload: {"topic": "tickers.BTCUSDT", "data": {"symbol": "BTCUSDT", "lastPrice": "65123.45"}, "ts": ...}
            if isinstance(data, dict) and data.get("topic", "").startswith("tickers."):
                t_data = data.get("data", {})
                sym = t_data.get("symbol", "").upper()
                lp = t_data.get("lastPrice")
                ts = data.get("ts")
                as_of = (float(ts) / 1000.0) if ts else time.time()
                if sym and lp:
                    price = float(lp)
                    if price > 0:
                        update_symbol_snapshot(
                            exchange_id="bybit",
                            native_symbol=sym,
                            price=price,
                            as_of=as_of,
                            source="ws",
                            latency_ms=round((time.time() - as_of) * 1000.0, 1)
                        )
                        self.last_msg_ts = time.time()
                        self.messages_count += 1
                        self.is_healthy = True
        except Exception as e:
            logger.debug(f"[Bybit WS] Parse error: {e}")


class OKXStreamClient(ExchangeStreamClient):
    """OKX Spot Real-Time WebSocket Client (V5)."""

    def __init__(self):
        super().__init__("okx", "wss://ws.okx.com:8443/ws/v5/public")

    def _normalize_okx_sym(self, s: str) -> str:
        s_up = s.upper()
        if "-" not in s_up:
            if s_up.endswith("USDT"):
                return f"{s_up[:-4]}-USDT"
        return s_up

    def format_subscribe_msg(self, symbols: Set[str]) -> Optional[str]:
        if not symbols:
            return None
        args = [{"channel": "tickers", "instId": self._normalize_okx_sym(s)} for s in symbols]
        return json.dumps({"op": "subscribe", "args": args})

    def format_unsubscribe_msg(self, symbols: Set[str]) -> Optional[str]:
        if not symbols:
            return None
        args = [{"channel": "tickers", "instId": self._normalize_okx_sym(s)} for s in symbols]
        return json.dumps({"op": "unsubscribe", "args": args})

    async def send_heartbeat(self, ws) -> None:
        try:
            await ws.send("ping")
        except Exception:
            pass

    def parse_message(self, raw_msg: str) -> None:
        try:
            if raw_msg == "pong":
                self.last_msg_ts = time.time()
                return

            data = json.loads(raw_msg)
            # OKX ticker payload: {"arg": {"channel": "tickers", "instId": "BTC-USDT"}, "data": [{"instId": "BTC-USDT", "last": "65123.45", "ts": "..."}]}
            if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
                for item in data["data"]:
                    inst_id = item.get("instId", "").upper()
                    last_p = item.get("last")
                    ts = item.get("ts")
                    as_of = (float(ts) / 1000.0) if ts else time.time()
                    if inst_id and last_p:
                        price = float(last_p)
                        if price > 0:
                            # Also register no-dash alias for lookup convenience
                            update_symbol_snapshot(
                                exchange_id="okx",
                                native_symbol=inst_id,
                                price=price,
                                as_of=as_of,
                                source="ws",
                                latency_ms=round((time.time() - as_of) * 1000.0, 1)
                            )
                            if "-" in inst_id:
                                update_symbol_snapshot(
                                    exchange_id="okx",
                                    native_symbol=inst_id.replace("-", ""),
                                    price=price,
                                    as_of=as_of,
                                    source="ws",
                                    latency_ms=round((time.time() - as_of) * 1000.0, 1)
                                )
                            self.last_msg_ts = time.time()
                            self.messages_count += 1
                            self.is_healthy = True
        except Exception as e:
            logger.debug(f"[OKX WS] Parse error: {e}")


class CryptoStreamSupervisor:
    """
    Supervisor managing demand-driven WebSocket streaming producers.
    - Observes active alerts in ALERTS_DB
    - Subscribes/unsubscribes dynamically
    - Recovers with exponential backoff and jitter
    - Exposes stream health status for poller fallback
    """

    def __init__(self):
        self._running = False
        self._clients: Dict[str, ExchangeStreamClient] = {
            "binance": BinanceStreamClient(),
            "bybit": BybitStreamClient(),
            "okx": OKXStreamClient(),
        }
        self._supervisor_task: Optional[asyncio.Task] = None

    def is_stream_enabled_for_exchange(self, exchange_id: str) -> bool:
        ex = exchange_id.lower().strip()
        global_enabled = getattr(config, "CRYPTO_STREAM_ENABLED", False)
        if not global_enabled:
            return False

        if ex == "binance":
            return getattr(config, "CRYPTO_STREAM_BINANCE", False)
        elif ex == "bybit":
            return getattr(config, "CRYPTO_STREAM_BYBIT", False)
        elif ex == "okx":
            return getattr(config, "CRYPTO_STREAM_OKX", False)
        return False

    def is_exchange_stream_healthy(self, exchange_id: str) -> bool:
        ex = exchange_id.lower().strip()
        client = self._clients.get(ex)
        if not client:
            return False
        return client.is_stream_active()

    def get_needed_symbols_for_exchange(self, exchange_id: str) -> Set[str]:
        ex = exchange_id.lower().strip()
        symbols = set()
        for alert in ALERTS_DB:
            if getattr(alert, "is_active", False):
                if getattr(alert, "alert_nature", "price") == "price":
                    a_ex = (getattr(alert, "exchange", "") or "").lower().strip()
                    if a_ex == ex:
                        sym = (getattr(alert, "symbol", "") or "").strip().upper()
                        if sym:
                            symbols.add(sym)
        return symbols

    async def _run_exchange_stream(self, client: ExchangeStreamClient) -> None:
        """Main loop for a single exchange stream with reconnect and backoff."""
        if websockets is None:
            logger.info(f"ℹ️ [Stream:{client.exchange_id}] websockets module not installed; stream disabled.")
            return

        backoff = 1.0
        while self._running:
            if not self.is_stream_enabled_for_exchange(client.exchange_id):
                await asyncio.sleep(2.0)
                continue

            needed_symbols = self.get_needed_symbols_for_exchange(client.exchange_id)
            if not needed_symbols:
                # No active alerts for this exchange; sleep without holding open connection
                client.is_connected = False
                client.is_healthy = False
                await asyncio.sleep(2.0)
                continue

            try:
                logger.info(f"🔌 [Stream:{client.exchange_id}] Connecting to {client.ws_url}...")
                async with websockets.connect(
                    client.ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    client._ws = ws
                    client.is_connected = True
                    client.is_healthy = True
                    backoff = 1.0  # Reset backoff on successful connect

                    # Initial subscribe
                    sub_msg = client.format_subscribe_msg(needed_symbols)
                    if sub_msg:
                        await ws.send(sub_msg)
                        client.subscribed_symbols = set(needed_symbols)
                        logger.info(f"📡 [Stream:{client.exchange_id}] Subscribed to {len(needed_symbols)} symbols: {list(needed_symbols)[:5]}")

                    # Heartbeat & message loop
                    last_hb = time.time()
                    while self._running:
                        try:
                            # Periodic demand synchronization
                            current_needed = self.get_needed_symbols_for_exchange(client.exchange_id)
                            to_add = current_needed - client.subscribed_symbols
                            to_remove = client.subscribed_symbols - current_needed

                            if to_add:
                                add_msg = client.format_subscribe_msg(to_add)
                                if add_msg:
                                    await ws.send(add_msg)
                                    client.subscribed_symbols.update(to_add)
                            if to_remove:
                                rem_msg = client.format_unsubscribe_msg(to_remove)
                                if rem_msg:
                                    await ws.send(rem_msg)
                                    client.subscribed_symbols.difference_update(to_remove)

                            # Heartbeat check
                            now = time.time()
                            if now - last_hb >= 15.0:
                                await client.send_heartbeat(ws)
                                last_hb = now

                            # Receive message with 1.0s timeout to allow demand sync
                            try:
                                msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                                if msg:
                                    client.parse_message(msg)
                            except asyncio.TimeoutError:
                                pass

                        except Exception as e:
                            logger.warning(f"⚠️ [Stream:{client.exchange_id}] Stream communication error: {e}")
                            break

            except Exception as e:
                logger.warning(f"⚠️ [Stream:{client.exchange_id}] Connection error: {e}")

            client.is_connected = False
            client.is_healthy = False
            client._ws = None

            # Exponential backoff with jitter
            jitter = random.uniform(0.1, 0.5)
            sleep_sec = min(30.0, backoff + jitter)
            backoff = min(30.0, backoff * 2.0)
            logger.info(f"⏱️ [Stream:{client.exchange_id}] Reconnecting in {sleep_sec:.1f}s...")
            await asyncio.sleep(sleep_sec)

    async def start(self) -> None:
        """Starts the stream supervisor and all exchange client loops."""
        if self._running:
            return
        self._running = True
        logger.info("🚀 [StreamSupervisor] Starting crypto WebSocket streaming supervisor...")
        for ex_id, client in self._clients.items():
            task = asyncio.create_task(self._run_exchange_stream(client))
            client._task = task

    async def stop(self) -> None:
        """Stops all streams cleanly."""
        self._running = False
        for client in self._clients.values():
            if client._task and not client._task.done():
                client._task.cancel()
            client.is_connected = False
            client.is_healthy = False

    def get_status(self) -> Dict[str, Any]:
        """Returns health and metrics dictionary for all streams."""
        res = {}
        now = time.time()
        for ex_id, client in self._clients.items():
            res[ex_id] = {
                "enabled": self.is_stream_enabled_for_exchange(ex_id),
                "connected": client.is_connected,
                "healthy": client.is_stream_active(),
                "messages_received": client.messages_count,
                "last_message_age_seconds": round(now - client.last_msg_ts, 1) if client.last_msg_ts > 0 else None,
                "subscribed_symbols": list(client.subscribed_symbols),
            }
        return res


# Global singleton supervisor instance
STREAM_SUPERVISOR = CryptoStreamSupervisor()


def is_stream_active_and_healthy(exchange_id: str) -> bool:
    """Returns whether the WebSocket stream is actively providing live data for an exchange."""
    return STREAM_SUPERVISOR.is_exchange_stream_healthy(exchange_id)
