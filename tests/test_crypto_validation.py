#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — Phase 4 Test Suite: Crypto Alert Validation & Resolution Engine.
Tests:
- Rejection of discontinued exchange 'coinex' with 'EXCHANGE_NOT_SUPPORTED'.
- Rejection of unknown/unsupported crypto exchanges with 'EXCHANGE_NOT_SUPPORTED'.
- Rejection of non-USDT crypto quotes with 'INVALID_QUOTE_CURRENCY'.
- Listing verification: listed symbols pass, unlisted symbols return 'SYMBOL_NOT_LISTED'.
- Non-crypto markets (Iranian, global stocks, forex, macro) pass validation untouched.
- Two-way alias resolution using base_currency + counter_currency + market_symbol.
- API validation enforcement under config.CRYPTO_VALIDATE_ALERTS ('enforce' vs 'false').
"""

import os
import json
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock

import app.config as config
from app.markets.crypto_validation import (
    validate_crypto_alert,
    is_crypto_exchange_candidate,
)
from app.markets.crypto_catalog import (
    resolve_pair,
    save_exchange_catalog_atomic,
)
from app.models import AlertCreate
from app.storage import ALERTS_DB
from app.routes.alerts import create_alert, sync_user_alerts
from fastapi import HTTPException


class TestCryptoValidationEngine(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_val_catalog_")
        self._orig_catalog_dir = getattr(config, "CRYPTO_CATALOG_DIR", None)
        config.CRYPTO_CATALOG_DIR = self.temp_dir

        self._orig_val_flag = getattr(config, "CRYPTO_VALIDATE_ALERTS", "false")
        self._orig_alerts = list(ALERTS_DB)
        ALERTS_DB.clear()

        # Seed sample catalog for binance and kraken
        binance_catalog = {
            "exchange": "binance",
            "updated_at": 1700000000,
            "total_pairs": 3,
            "is_stale": False,
            "pairs": [
                {
                    "symbol": "BTCUSDT",
                    "base": "BTC",
                    "quote": "USDT",
                    "native_symbol": "BTCUSDT",
                    "aliases": ["BTC-USDT", "BTC_USDT"],
                },
                {
                    "symbol": "ETHUSDT",
                    "base": "ETH",
                    "quote": "USDT",
                    "native_symbol": "ETHUSDT",
                    "aliases": ["ETH-USDT"],
                },
                {
                    "symbol": "PEPEUSDT",
                    "base": "PEPE",
                    "quote": "USDT",
                    "native_symbol": "PEPEUSDT",
                    "aliases": [],
                },
            ],
        }
        kraken_catalog = {
            "exchange": "kraken",
            "updated_at": 1700000000,
            "total_pairs": 2,
            "is_stale": False,
            "pairs": [
                {
                    "symbol": "BTCUSDT",
                    "base": "BTC",
                    "quote": "USDT",
                    "native_symbol": "XBTUSDT",
                    "aliases": ["BTCUSDT", "XBT/USDT"],
                },
                {
                    "symbol": "ETHUSDT",
                    "base": "ETH",
                    "quote": "USDT",
                    "native_symbol": "ETHUSDT",
                    "aliases": [],
                },
            ],
        }
        save_exchange_catalog_atomic("binance", binance_catalog, self.temp_dir)
        save_exchange_catalog_atomic("kraken", kraken_catalog, self.temp_dir)

    def tearDown(self):
        ALERTS_DB.clear()
        ALERTS_DB.extend(self._orig_alerts)
        config.CRYPTO_CATALOG_DIR = self._orig_catalog_dir
        config.CRYPTO_VALIDATE_ALERTS = self._orig_val_flag
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_coinex_discontinued_rejection(self):
        """Owner Decision E1.2: CoinEx is permanently discontinued and rejected with EXCHANGE_NOT_SUPPORTED."""
        is_val, code, msg = validate_crypto_alert("coinex", "BTCUSDT", override_dir=self.temp_dir)
        self.assertFalse(is_val)
        self.assertEqual(code, "EXCHANGE_NOT_SUPPORTED")
        self.assertIn("discontinued", msg.lower())

    def test_02_unknown_exchange_rejection(self):
        """Unrecognized crypto exchange must be rejected with EXCHANGE_NOT_SUPPORTED."""
        is_val, code, msg = validate_crypto_alert("unknown_dex_exchange", "BTCUSDT", override_dir=self.temp_dir)
        self.assertFalse(is_val)
        self.assertEqual(code, "EXCHANGE_NOT_SUPPORTED")

    def test_03_non_crypto_exchanges_pass_untouched(self):
        """Iranian exchanges, global stocks, and macro bypass crypto validation untouched."""
        for ex in ["nobitex", "wallex", "tabdeal", "stocks", "global_stocks", "macro", "forex"]:
            is_val, code, msg = validate_crypto_alert(ex, "USDTIRT", override_dir=self.temp_dir)
            self.assertTrue(is_val, f"Failed for {ex}")
            self.assertIsNone(code)
            self.assertIsNone(msg)

    def test_04_invalid_quote_currency_rejected(self):
        """Spot crypto alerts must use USDT quote currency; non-USDT must be rejected."""
        is_val, code, msg = validate_crypto_alert(
            exchange="binance",
            symbol="BTCEUR",
            counter_currency="EUR",
            override_dir=self.temp_dir,
        )
        self.assertFalse(is_val)
        self.assertEqual(code, "INVALID_QUOTE_CURRENCY")
        self.assertIn("USDT", msg)

    def test_05_listed_symbol_passes(self):
        """Symbol present in the exchange catalog must pass validation."""
        is_val, code, msg = validate_crypto_alert(
            exchange="binance",
            symbol="BTCUSDT",
            override_dir=self.temp_dir,
        )
        self.assertTrue(is_val)
        self.assertIsNone(code)

    def test_06_unlisted_symbol_rejected(self):
        """Symbol absent from the exchange catalog must be rejected with SYMBOL_NOT_LISTED."""
        is_val, code, msg = validate_crypto_alert(
            exchange="binance",
            symbol="FAKECOIN999USDT",
            override_dir=self.temp_dir,
        )
        self.assertFalse(is_val)
        self.assertEqual(code, "SYMBOL_NOT_LISTED")

    def test_07_kraken_alias_resolution(self):
        """Kraken uses native symbol XBTUSDT while canonical symbol is BTCUSDT."""
        # Query using canonical base and market_symbol
        status, pair = resolve_pair(
            exchange_id="kraken",
            symbol_or_base="BTCUSDT",
            market_symbol="XBTUSDT",
            override_dir=self.temp_dir,
        )
        self.assertEqual(status, "OK")
        self.assertIsNotNone(pair)
        self.assertEqual(pair["native_symbol"], "XBTUSDT")
        self.assertEqual(pair["base"], "BTC")

        # Query using only base_currency="BTC"
        status2, pair2 = resolve_pair(
            exchange_id="kraken",
            symbol_or_base="BTC",
            base_currency="BTC",
            override_dir=self.temp_dir,
        )
        self.assertEqual(status2, "OK")
        self.assertEqual(pair2["native_symbol"], "XBTUSDT")

    async def test_08_api_create_alert_enforce_mode(self):
        """create_alert route rejects invalid crypto requests when CRYPTO_VALIDATE_ALERTS=enforce."""
        config.CRYPTO_VALIDATE_ALERTS = "enforce"

        # 1. CoinEx rejection
        bad_alert = AlertCreate(
            user_id="user_test_val",
            exchange="coinex",
            symbol="BTCUSDT",
            target_price=65000.0,
        )
        with self.assertRaises(HTTPException) as ctx:
            await create_alert(bad_alert)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("EXCHANGE_NOT_SUPPORTED", ctx.exception.detail)

        # 2. Non-USDT quote rejection
        bad_quote_alert = AlertCreate(
            user_id="user_test_val",
            exchange="binance",
            symbol="BTCEUR",
            counter_currency="EUR",
            target_price=65000.0,
        )
        with self.assertRaises(HTTPException) as ctx:
            await create_alert(bad_quote_alert)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("INVALID_QUOTE_CURRENCY", ctx.exception.detail)

        # 3. Non-crypto alert (nobitex) passes through cleanly
        nobitex_alert = AlertCreate(
            user_id="user_test_val",
            exchange="nobitex",
            symbol="USDTIRT",
            target_price=90000.0,
        )
        res = await create_alert(nobitex_alert)
        self.assertEqual(res.exchange, "nobitex")
        self.assertEqual(res.symbol, "USDTIRT")

    async def test_09_api_create_alert_disabled_mode(self):
        """When CRYPTO_VALIDATE_ALERTS=false, existing behavior is completely preserved."""
        config.CRYPTO_VALIDATE_ALERTS = "false"

        alert = AlertCreate(
            user_id="user_test_val",
            exchange="coinex",
            symbol="BTCUSDT",
            target_price=65000.0,
        )
        # Should NOT raise HTTPException with EXCHANGE_NOT_SUPPORTED
        res = await create_alert(alert)
        self.assertEqual(res.exchange, "coinex")

    async def test_10_api_sync_alerts_enforce_mode(self):
        """sync_user_alerts route rejects invalid crypto alerts during bulk sync when CRYPTO_VALIDATE_ALERTS=enforce."""
        config.CRYPTO_VALIDATE_ALERTS = "enforce"

        payload = {
            "user_id": "user_sync_test",
            "fcm_token": "token_12345678901",
            "sync_mode": "mirror",
            "alerts": [
                {
                    "exchange": "coinex",
                    "symbol": "BTCUSDT",
                    "target_price": 60000.0,
                }
            ],
        }
        with self.assertRaises(HTTPException) as ctx:
            await sync_user_alerts(payload)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("EXCHANGE_NOT_SUPPORTED", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
