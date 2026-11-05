# -*- coding: utf-8 -*-
"""
AlertG — Wave 2 Crypto Adapters Acceptance Tests (Phase 6).
Tests BingX, XT.COM, Toobit, Poloniex, Coinbase, and Bitfinex adapters:
1. Specification integrity (Rule R11, provider key, status == 'active').
2. Two-way native symbol formatting.
3. Parsing of market symbols response (spot USDT filter, ETF detection).
4. Parsing of batch prices response.
5. Integration into crypto_registry and get_exchange_adapter factory.
"""
import unittest
import sys
from unittest.mock import MagicMock

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

from app.markets.crypto_registry import get_crypto_exchange, list_crypto_exchanges
from app.markets.crypto_catalog import get_exchange_adapter
from app.markets.adapters import (
    BingXAdapter,
    XTAdapter,
    ToobitAdapter,
    PoloniexAdapter,
    CoinbaseAdapter,
    BitfinexAdapter,
)


class TestWave2CryptoAdapters(unittest.TestCase):
    """Test suite for Wave 2 / Phase 6 crypto exchange adapters."""

    def test_01_registry_registration(self):
        """All 6 new exchanges must be registered in crypto_registry as active."""
        for ex_id in ("bingx", "xt", "toobit", "poloniex", "coinbase", "bitfinex"):
            meta = get_crypto_exchange(ex_id)
            self.assertIsNotNone(meta, f"Exchange {ex_id} must be in registry")
            self.assertEqual(meta.status, "active")
            self.assertIn(ex_id, meta.source_label.lower())
            self.assertEqual(meta.provider_key, f"crypto_{ex_id}")

    def test_02_adapter_factory(self):
        """get_exchange_adapter must return the correct adapter instance for each exchange."""
        self.assertIsInstance(get_exchange_adapter("bingx"), BingXAdapter)
        self.assertIsInstance(get_exchange_adapter("xt"), XTAdapter)
        self.assertIsInstance(get_exchange_adapter("toobit"), ToobitAdapter)
        self.assertIsInstance(get_exchange_adapter("poloniex"), PoloniexAdapter)
        self.assertIsInstance(get_exchange_adapter("coinbase"), CoinbaseAdapter)
        self.assertIsInstance(get_exchange_adapter("bitfinex"), BitfinexAdapter)

    def test_03_bingx_adapter(self):
        """BingX adapter symbol formatting, symbols parsing, and bulk prices."""
        adapter = BingXAdapter()
        self.assertEqual(adapter.to_native_symbol("BTC"), "BTC-USDT")
        self.assertEqual(adapter.to_native_symbol("ETH-USDT"), "ETH-USDT")
        self.assertEqual(adapter.to_canonical_base("BTC-USDT"), "BTC")

        raw_symbols = {
            "code": 0,
            "data": {
                "symbols": [
                    {"symbol": "BTC-USDT", "minQty": 0.001, "status": 1},
                    {"symbol": "ETH-USDT", "minQty": 0.01, "status": 1},
                    {"symbol": "BTC-EUR", "minQty": 0.001, "status": 1},  # Non-USDT ignored
                ]
            }
        }
        symbols = adapter.parse_symbols_response(raw_symbols)
        self.assertEqual(len(symbols), 2)
        self.assertEqual(symbols[0].base, "BTC")
        self.assertEqual(symbols[0].quote, "USDT")
        self.assertEqual(symbols[0].market_symbol, "BTC-USDT")

        raw_tickers = {
            "code": 0,
            "data": [
                {"symbol": "BTC-USDT", "lastPrice": 80100.5},
                {"symbol": "ETH-USDT", "lastPrice": 2420.0},
            ]
        }
        prices = adapter.parse_batch_prices_response(raw_tickers)
        self.assertEqual(prices["BTC-USDT"], 80100.5)
        self.assertEqual(prices["BTCUSDT"], 80100.5)

    def test_04_xt_adapter(self):
        """XT.COM adapter symbol formatting, symbols parsing, and bulk prices."""
        adapter = XTAdapter()
        self.assertEqual(adapter.to_native_symbol("BTC"), "btc_usdt")
        self.assertEqual(adapter.to_canonical_base("btc_usdt"), "BTC")

        raw_symbols = {
            "rc": 0,
            "result": {
                "symbols": [
                    {"symbol": "btc_usdt", "baseCurrency": "btc", "quoteCurrency": "usdt", "state": "ONLINE"},
                    {"symbol": "sol_usdt", "baseCurrency": "sol", "quoteCurrency": "usdt", "state": "ONLINE"},
                    {"symbol": "btc_btc", "baseCurrency": "btc", "quoteCurrency": "btc", "state": "ONLINE"},
                ]
            }
        }
        symbols = adapter.parse_symbols_response(raw_symbols)
        self.assertEqual(len(symbols), 2)
        self.assertEqual(symbols[0].base, "BTC")
        self.assertEqual(symbols[0].quote, "USDT")

        raw_tickers = {
            "rc": 0,
            "result": [
                {"s": "btc_usdt", "p": "80200.0"},
                {"s": "sol_usdt", "p": "135.5"},
            ]
        }
        prices = adapter.parse_batch_prices_response(raw_tickers)
        self.assertEqual(prices["btc_usdt"], 80200.0)
        self.assertEqual(prices["btcusdt"], 80200.0)

    def test_05_toobit_adapter(self):
        """Toobit adapter symbol formatting, symbols parsing, and bulk prices."""
        adapter = ToobitAdapter()
        self.assertEqual(adapter.to_native_symbol("BTC"), "BTCUSDT")
        self.assertEqual(adapter.to_canonical_base("BTCUSDT"), "BTC")

        raw_symbols = {
            "symbols": [
                {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT", "status": "TRADING"},
                {"symbol": "XRPUSDT", "baseAsset": "XRP", "quoteAsset": "USDT", "status": "TRADING"},
            ]
        }
        symbols = adapter.parse_symbols_response(raw_symbols)
        self.assertEqual(len(symbols), 2)
        self.assertEqual(symbols[0].base, "BTC")
        self.assertEqual(symbols[0].quote, "USDT")

        raw_tickers = [
            {"s": "BTCUSDT", "p": "80300.0"},
            {"s": "XRPUSDT", "p": "0.55"},
        ]
        prices = adapter.parse_batch_prices_response(raw_tickers)
        self.assertEqual(prices["BTCUSDT"], 80300.0)

    def test_06_poloniex_adapter(self):
        """Poloniex adapter symbol formatting, symbols parsing, and bulk prices."""
        adapter = PoloniexAdapter()
        self.assertEqual(adapter.to_native_symbol("BTC"), "BTC_USDT")
        self.assertEqual(adapter.to_canonical_base("BTC_USDT"), "BTC")

        raw_symbols = [
            {"symbol": "BTC_USDT", "baseCurrencyName": "BTC", "quoteCurrencyName": "USDT", "state": "NORMAL"},
            {"symbol": "TRX_USDT", "baseCurrencyName": "TRX", "quoteCurrencyName": "USDT", "state": "NORMAL"},
        ]
        symbols = adapter.parse_symbols_response(raw_symbols)
        self.assertEqual(len(symbols), 2)
        self.assertEqual(symbols[0].base, "BTC")

        raw_tickers = [
            {"symbol": "BTC_USDT", "close": "80400.0"},
            {"symbol": "TRX_USDT", "close": "0.15"},
        ]
        prices = adapter.parse_batch_prices_response(raw_tickers)
        self.assertEqual(prices["BTC_USDT"], 80400.0)
        self.assertEqual(prices["btcusdt"], 80400.0)

    def test_07_coinbase_adapter(self):
        """Coinbase adapter symbol formatting, symbols parsing, and bulk prices."""
        adapter = CoinbaseAdapter()
        self.assertEqual(adapter.to_native_symbol("BTC"), "BTC-USDT")
        self.assertEqual(adapter.to_canonical_base("BTC-USDT"), "BTC")

        raw_products = [
            {"id": "BTC-USDT", "base_currency": "BTC", "quote_currency": "USDT", "status": "online"},
            {"id": "ETH-USDT", "base_currency": "ETH", "quote_currency": "USDT", "status": "online"},
        ]
        symbols = adapter.parse_symbols_response(raw_products)
        self.assertEqual(len(symbols), 2)
        self.assertEqual(symbols[0].base, "BTC")

        raw_rates = {
            "data": {
                "rates": {
                    "BTC": "0.0000125",  # 1 / 0.0000125 = 80,000
                    "ETH": "0.0004",     # 1 / 0.0004 = 2,500
                }
            }
        }
        prices = adapter.parse_batch_prices_response(raw_rates)
        self.assertAlmostEqual(prices["BTC-USDT"], 80000.0)
        self.assertAlmostEqual(prices["ETH-USDT"], 2500.0)

    def test_08_bitfinex_adapter(self):
        """Bitfinex adapter symbol formatting, symbols parsing, and bulk prices."""
        adapter = BitfinexAdapter()
        self.assertEqual(adapter.to_native_symbol("BTC"), "tBTCUST")
        self.assertEqual(adapter.to_canonical_base("tBTCUST"), "BTC")

        raw_pairs = [["BTCUST", "ETHUST", "AAVE:UST"]]
        symbols = adapter.parse_symbols_response(raw_pairs)
        self.assertEqual(len(symbols), 3)
        self.assertEqual(symbols[0].base, "BTC")
        self.assertEqual(symbols[0].market_symbol, "tBTCUST")

        raw_tickers = [
            ["tBTCUST", 80500, 1.0, 80510, 1.0, 100, 0.01, 80500.0, 1000, 81000, 79000],
            ["tETHUST", 2430, 1.0, 2435, 1.0, 10, 0.01, 2430.0, 500, 2500, 2400],
        ]
        prices = adapter.parse_batch_prices_response(raw_tickers)
        self.assertEqual(prices["tBTCUST"], 80500.0)
        self.assertEqual(prices["BTCUSDT"], 80500.0)


if __name__ == "__main__":
    unittest.main()
