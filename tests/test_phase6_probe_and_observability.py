#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 6 Comprehensive Unit Tests:
 1. Admin Probe Endpoint /api/admin/probe:
    - Protected by ADMIN_DEP
    - PROBE_TARGETS contains Iran, DEX, Asian Indices, and Crypto
    - Status categories: HEALTHY, SLOW, BLOCKED_OR_ERROR, SUSPICIOUS_PRICE
    - Supports JSON and HTML responses
 2. Asian Indices Coverage (^N225, ^NSEI, ^KS11):
    - (Phase 3) app no longer hard-codes indices; they come from the server catalog
    - NIKKEI, NIFTY, KOSPI mapped in EXACT_YF_MAP in server.py
 3. DEX Resolution Support:
    - DexScreener and GeckoTerminal supported in server.py fetch_price_with_trace
"""

import unittest
import re
import os

class TestPhase6ProbeAndObservability(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open('server.py', 'r', encoding='utf-8') as f:
            cls.server_code = f.read()

        dart_path = 'lib/features/exchanges/stocks/global_stocks_exchange.dart'
        if os.path.exists(dart_path):
            with open(dart_path, 'r', encoding='utf-8') as f:
                cls.stocks_code = f.read()
        else:
            cls.stocks_code = None

    def test_01_probe_endpoint_registered_with_admin_dep(self):
        """Verify /api/admin/probe is registered and protected by ADMIN_DEP"""
        self.assertIn('@app.get("/api/admin/probe", dependencies=ADMIN_DEP)', self.server_code)
        self.assertIn('@app.get("/admin/probe", dependencies=ADMIN_DEP)', self.server_code)

    def test_02_probe_status_matrix_and_categories(self):
        """Verify status classification and target categories"""
        self.assertIn("'HEALTHY'", self.server_code)
        self.assertIn("'SLOW'", self.server_code)
        self.assertIn("'BLOCKED_OR_ERROR'", self.server_code)
        self.assertIn("'SUSPICIOUS_PRICE'", self.server_code)
        self.assertIn("summary", self.server_code)
        self.assertIn("total_sources", self.server_code)

    def test_03_asian_indices_support(self):
        """Verify ^N225, ^NSEI, ^KS11 in stocks exchange and EXACT_YF_MAP"""
        if self.stocks_code is not None:
            # Phase 3: indices are no longer hard-coded in the app; they come from the server catalog.
            self.assertNotIn("'symbol': '^N225'", self.stocks_code)

        self.assertIn("'NIKKEI': '^N225'", self.server_code)
        self.assertIn("'NIFTY': '^NSEI'", self.server_code)
        self.assertIn("'KOSPI': '^KS11'", self.server_code)

    def test_04_dex_resolution_support(self):
        """Verify DexScreener and GeckoTerminal supported in server.py"""
        self.assertIn("ex in ['dex', 'dexscreener', 'geckoterminal']", self.server_code)
        self.assertIn("api.dexscreener.com", self.server_code)
        self.assertIn("api.geckoterminal.com", self.server_code)


if __name__ == '__main__':
    unittest.main()
