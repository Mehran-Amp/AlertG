# -*- coding: utf-8 -*-
"""
Phase H1 Test:
Asserts that startup catalog sync in server.py calls sync_all_crypto_catalogs()
without a client (client=None), decoupling it completely from shared state.http_client.
"""

import sys
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

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


class TestServerStartupCatalogSync(unittest.IsolatedAsyncioTestCase):
    async def test_startup_sync_calls_without_client(self):
        """Verifies _run_background_crypto_catalog_sync invokes sync_all_crypto_catalogs with client=None."""
        mock_sync = AsyncMock(return_value={"success_count": 7, "total_exchanges": 7})
        with patch("app.markets.crypto_catalog.sync_all_crypto_catalogs", mock_sync):
            import server
            await server._run_background_crypto_catalog_sync()

            mock_sync.assert_awaited_once()
            call_kwargs = mock_sync.call_args.kwargs
            # Assert client was not passed or was None
            self.assertIsNone(call_kwargs.get("client"))


if __name__ == "__main__":
    unittest.main()
