import unittest
import time
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
    import fastapi
except ImportError:
    import types
    fastapi = types.ModuleType('fastapi')
    fastapi.__path__ = []
    class APIRouter:
        def get(self, *a, **kw): return lambda fn: fn
        def post(self, *a, **kw): return lambda fn: fn
        def delete(self, *a, **kw): return lambda fn: fn
    class HTTPException(Exception): pass
    class Response:
        def __init__(self, *a, **kw): pass
    class Request:
        pass
    fastapi.APIRouter = APIRouter
    fastapi.HTTPException = HTTPException
    fastapi.Response = Response
    fastapi.Request = Request

    fastapi.Header = MagicMock()
    fastapi.Depends = MagicMock()
    fastapi.Query = lambda default=None, **kw: default
    sys.modules['fastapi'] = fastapi

    resp_mod = types.ModuleType('fastapi.responses')
    class JSONResponse(Response): pass
    class HTMLResponse(Response): pass
    resp_mod.Response = Response
    resp_mod.JSONResponse = JSONResponse
    resp_mod.HTMLResponse = HTMLResponse
    sys.modules['fastapi.responses'] = resp_mod
    fastapi.responses = resp_mod


from app.markets.crypto_snapshot import (
    update_exchange_snapshot,
    get_snapshot_price,
    get_all_snapshots_status,
    get_exchange_snapshot_detail,
    clear_snapshot_store,
)
from app.routes.crypto_symbols import get_crypto_snapshots_endpoint



class TestCryptoSnapshotsEndpoint(unittest.TestCase):
    def setUp(self):
        clear_snapshot_store()

    def tearDown(self):
        clear_snapshot_store()

    def test_multi_exchange_snapshots_and_filtering(self):
        now = time.time()
        # Seed snapshots for Binance, MEXC, and KuCoin
        update_exchange_snapshot(
            exchange_id="binance",
            prices={"BTCUSDT": 78000.0, "ETHUSDT": 2700.0},
            status="OK",
            latency_ms=120.0,
            as_of=now,
        )
        update_exchange_snapshot(
            exchange_id="mexc",
            prices={"BTCUSDT": 78005.0, "KASUSDT": 0.15},
            status="OK",
            latency_ms=145.0,
            as_of=now,
        )
        update_exchange_snapshot(
            exchange_id="kucoin",
            prices={"BTC-USDT": 77995.0, "ETH-USDT": 2698.0},
            status="OK",
            latency_ms=180.0,
            as_of=now,
        )

        # 1. Overview returns all 3 exchanges
        res_all = get_crypto_snapshots_endpoint()
        self.assertEqual(res_all["status"], "success")
        self.assertIn("binance", res_all["snapshots"])
        self.assertIn("mexc", res_all["snapshots"])
        self.assertIn("kucoin", res_all["snapshots"])
        self.assertEqual(res_all["snapshots"]["binance"]["total_pairs"], 2)
        self.assertEqual(res_all["snapshots"]["mexc"]["total_pairs"], 2)

        # 2. Filter by exchange (mexc)
        res_mexc = get_crypto_snapshots_endpoint(exchange="mexc")
        self.assertEqual(res_mexc["status"], "success")
        self.assertEqual(res_mexc["snapshot"]["exchange"], "mexc")
        self.assertIn("KASUSDT", res_mexc["snapshot"]["sample_prices"])
        self.assertEqual(res_mexc["snapshot"]["sample_prices"]["KASUSDT"], 0.15)

        # 3. Lookup exact symbol price in O(1)
        res_sym = get_crypto_snapshots_endpoint(exchange="kucoin", symbol="BTC-USDT")
        self.assertEqual(res_sym["status"], "success")
        self.assertEqual(res_sym["price"], 77995.0)
        self.assertEqual(res_sym["snapshot_status"], "OK")

        # 4. Inactive exchange returns informative not_active
        res_okx = get_crypto_snapshots_endpoint(exchange="okx")
        self.assertEqual(res_okx["status"], "not_active")
        self.assertIn("No active in-memory snapshot", res_okx["detail"])


if __name__ == "__main__":
    unittest.main()
