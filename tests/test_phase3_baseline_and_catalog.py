"""
Phase 3 (v3.1.0): baseline tooling + catalog integrity.

- scripts/make_baseline.py: MD5 manifest (md5sum -c compatible), fixed price-sample set, never overwrites golden.
- scripts/compare_golden.py: reports BREAKING vs INFO differences against snapshots/golden_phase0.json.
- app/engine/sync.py: schema_version, single-writer lock, backup (snapshot) before every apply.
All tests run offline.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "scripts", f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


make_baseline = _load_script("make_baseline")
compare_golden = _load_script("compare_golden")

GOLDEN_PATH = os.path.join(ROOT, "snapshots", "golden_phase0.json")


def _golden():
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class TestManifest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "app", "__pycache__"))
        with open(os.path.join(self.tmp, "server.py"), "w") as f:
            f.write("print('x')\n")
        with open(os.path.join(self.tmp, "app", "mod.py"), "w") as f:
            f.write("A = 1\n")
        with open(os.path.join(self.tmp, "app", "__pycache__", "mod.cpython-311.pyc"), "wb") as f:
            f.write(b"\x00")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_manifest_format_is_md5sum_compatible_and_skips_pycache(self):
        n = make_baseline.write_manifest(self.tmp, "docs/MD5_MANIFEST.txt")
        self.assertEqual(n, 2)
        with open(os.path.join(self.tmp, "docs", "MD5_MANIFEST.txt"), encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertEqual([l.split("  ", 1)[1] for l in lines], ["app/mod.py", "server.py"])
        expected = hashlib.md5(b"print('x')\n").hexdigest()
        self.assertIn(f"{expected}  server.py", lines)

    def test_verify_detects_changed_missing_and_unlisted(self):
        make_baseline.write_manifest(self.tmp, "docs/MD5_MANIFEST.txt")
        self.assertEqual(make_baseline.verify_manifest(self.tmp, "docs/MD5_MANIFEST.txt"), [])
        with open(os.path.join(self.tmp, "server.py"), "a") as f:
            f.write("# edit\n")
        os.remove(os.path.join(self.tmp, "app", "mod.py"))
        with open(os.path.join(self.tmp, "app", "new.py"), "w") as f:
            f.write("B = 2\n")
        problems = make_baseline.verify_manifest(self.tmp, "docs/MD5_MANIFEST.txt")
        self.assertIn("CHANGED  server.py", problems)
        self.assertIn("MISSING  app/mod.py", problems)
        self.assertIn("UNLISTED app/new.py", problems)

    def test_repo_manifest_if_present_matches_tree(self):
        path = os.path.join(ROOT, "docs", "MD5_MANIFEST.txt")
        if not os.path.exists(path):
            self.skipTest("docs/MD5_MANIFEST.txt is generated on the server by make_baseline.py")
        self.assertEqual(make_baseline.verify_manifest(ROOT, "docs/MD5_MANIFEST.txt"), [])


class TestCapture(unittest.TestCase):
    @staticmethod
    def _fake_fetch(base_url, path, api_key, timeout=15.0):
        if path == "/":
            return 200, {"status": "online", "engine": "SignalAlert Enterprise Engine v9.9.9"}
        if path == "/api/symbols/wallstreet-macro":
            return 200, {"status": "success", "market": "X", "total_count": 1, "categories": {"stock": 1},
                         "symbols": [{"id": "AAPL", "symbol": "AAPL", "nameEn": "Apple", "nameFa": "a",
                                      "category": "stock", "marketName": "US", "unit": "$", "added_at": "volatile"}]}
        if path == "/api/markets/status":
            return 200, {"status": "ok", "markets": {"crypto": {"status": "open"}}}
        if path.startswith("/api/price/"):
            return 200, {"status": "ok", "price": 1.0}
        return 404, None

    def test_capture_uses_fixed_samples_and_stable_symbol_keys(self):
        snap = make_baseline.capture_snapshot("http://x", "k", "t", fetch=self._fake_fetch, root=ROOT)
        samples = snap["endpoints"]["price_samples"]
        golden_keys = set(_golden()["endpoints"]["price_samples"])
        self.assertEqual(set(samples), golden_keys)
        self.assertEqual(samples["bonbast/USD/TMN"]["normalized_symbol"], "USDTMN")
        self.assertEqual(samples["bonbast/USD/TMN"]["cache_key"], "bonbast:USDTMN")
        sym = snap["endpoints"]["api_symbols_wallstreet_macro"]["symbols"][0]
        self.assertNotIn("added_at", sym)
        self.assertEqual(snap["metadata"]["server_version"], "SignalAlert Enterprise Engine v9.9.9")

    def test_yahoo_samples_are_requested_through_global_stocks(self):
        paths = []

        def spy(base_url, path, api_key, timeout=15.0):
            paths.append(path)
            return self._fake_fetch(base_url, path, api_key, timeout)

        snap = make_baseline.capture_snapshot("http://x", "k", "t", fetch=spy, root=ROOT)
        self.assertFalse([p for p in paths if p.startswith("/api/price/yahoo/")])
        self.assertIn("/api/price/global_stocks/AAPL", paths)
        self.assertIn("/api/price/global_stocks/^TNX", paths)
        self.assertEqual(snap["endpoints"]["price_samples"]["yahoo/AAPL"]["request_exchange"], "global_stocks")
        self.assertEqual(snap["endpoints"]["price_samples"]["yahoo/AAPL"]["cache_key"], "yahoo:AAPL")

    def test_no_api_key_value_is_stored(self):
        snap = make_baseline.capture_snapshot("http://x", "SECRET-KEY-VALUE", "t", fetch=self._fake_fetch, root=ROOT)
        self.assertNotIn("SECRET-KEY-VALUE", json.dumps(snap))

    def test_write_snapshot_never_overwrites(self):
        tmp = tempfile.mkdtemp()
        try:
            p1 = make_baseline.write_snapshot({"a": 1}, tmp, "t", root=ROOT)
            with self.assertRaises(FileExistsError):
                with open(p1, "x"):
                    pass
            self.assertTrue(os.path.basename(p1).startswith("baseline_"))
            self.assertFalse(os.path.basename(p1).startswith("golden"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_golden_file_is_preserved(self):
        self.assertTrue(os.path.exists(GOLDEN_PATH))
        self.assertEqual(_golden()["metadata"]["phase"], "Phase 0 Baseline")


class TestCompare(unittest.TestCase):
    def test_golden_vs_itself_is_clean(self):
        rep = compare_golden.compare(_golden(), _golden())
        self.assertEqual(rep, {"breaking": [], "info": []})

    def test_removed_symbol_and_category_change_are_breaking(self):
        cand = json.loads(json.dumps(_golden()))
        syms = cand["endpoints"]["api_symbols_wallstreet_macro"]["symbols"]
        removed = syms.pop(0)
        syms[0]["category"] = "changed_category"
        rep = compare_golden.compare(_golden(), cand)
        self.assertTrue(any(f"REMOVED {removed['id']}" in b for b in rep["breaking"]))
        self.assertTrue(any(".category" in b for b in rep["breaking"]))

    def test_added_symbol_and_label_change_are_info_only(self):
        cand = json.loads(json.dumps(_golden()))
        syms = cand["endpoints"]["api_symbols_wallstreet_macro"]["symbols"]
        syms[0]["nameFa"] = "new label"
        syms.append({"id": "NEW1", "symbol": "NEW1", "nameEn": "n", "nameFa": "n", "category": "stock",
                     "marketName": "m", "unit": "$"})
        rep = compare_golden.compare(_golden(), cand)
        self.assertEqual(rep["breaking"], [])
        self.assertTrue(any("added NEW1" in i for i in rep["info"]))
        self.assertTrue(any(".nameFa" in i for i in rep["info"]))

    def test_price_sample_lost_keys_and_http_error_are_breaking(self):
        cand = json.loads(json.dumps(_golden()))
        ps = cand["endpoints"]["price_samples"]
        del ps["yahoo/AAPL"]["response_template"]["currency"]
        ps["yahoo/TSLA"]["http_status"] = 502
        ps["yahoo/TSLA"]["response_template"] = {"detail": "Unable to fetch live price"}
        del ps["binance/BTCUSDT"]
        rep = compare_golden.compare(_golden(), cand)
        text = "\n".join(rep["breaking"])
        self.assertIn("yahoo/AAPL response lost keys ['currency']", text)
        self.assertIn("yahoo/TSLA HTTP 502", text)
        self.assertIn("binance/BTCUSDT missing", text)

    def test_cli_exit_codes(self):
        tmp = tempfile.mkdtemp()
        try:
            ok = os.path.join(tmp, "ok.json")
            bad = os.path.join(tmp, "bad.json")
            with open(ok, "w", encoding="utf-8") as f:
                json.dump(_golden(), f, ensure_ascii=False)
            cand = _golden()
            cand["endpoints"]["api_symbols_wallstreet_macro"]["symbols"].pop(0)
            with open(bad, "w", encoding="utf-8") as f:
                json.dump(cand, f, ensure_ascii=False)
            self.assertEqual(compare_golden.main(["--candidate", ok]), 0)
            self.assertEqual(compare_golden.main(["--candidate", bad]), 1)
            self.assertEqual(compare_golden.main(["--candidate", os.path.join(tmp, "missing.json")]), 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestCatalogIntegrity(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import app.engine.sync as sync_module
        self.sync = sync_module
        self.tmp = tempfile.mkdtemp()
        self.orig = (sync_module.CATALOG_FILE, sync_module.CATALOG_SNAPSHOTS_DIR)
        sync_module.CATALOG_FILE = os.path.join(self.tmp, "catalog.json")
        sync_module.CATALOG_SNAPSHOTS_DIR = os.path.join(self.tmp, "catalog_snapshots")

    def tearDown(self):
        self.sync.CATALOG_FILE, self.sync.CATALOG_SNAPSHOTS_DIR = self.orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _seed(self, **extra):
        symbols = [{"id": f"S{i}", "symbol": f"S{i}", "nameEn": f"S{i}", "nameFa": f"S{i}", "category": "stock",
                    "marketName": "m", "unit": "$", "is_active": 1, "delisted_at": None, "added_at": "x"}
                   for i in range(100)]
        cat = {"catalog_version": 1, "app_version": "t", "last_sync_at": "x", "total_active": 100,
               "total_symbols": 100, "symbols": symbols}
        cat.update(extra)
        self.sync.save_catalog(cat)
        return cat

    def test_initial_catalog_has_schema_version(self):
        from app.config import CATALOG_SCHEMA_VERSION
        self.assertEqual(self.sync.get_initial_catalog_data()["schema_version"], CATALOG_SCHEMA_VERSION)
        self.assertEqual(self.sync.load_catalog()["schema_version"], CATALOG_SCHEMA_VERSION)

    def test_legacy_file_without_schema_version_is_accepted(self):
        self._seed()
        self.assertEqual(self.sync.load_catalog()["schema_version"], 1)

    def test_newer_schema_is_refused_and_not_overwritten(self):
        self._seed(schema_version=999)
        with self.assertRaises(self.sync.CatalogSchemaError):
            self.sync.load_catalog()
        with open(self.sync.CATALOG_FILE, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["schema_version"], 999)

    async def test_apply_writes_schema_version_and_backup_before_apply(self):
        self._seed()
        candidates = [{"id": f"S{i}", "symbol": f"S{i}", "nameEn": f"S{i}", "nameFa": f"S{i}",
                       "category": "stock", "marketName": "m", "unit": "$"} for i in range(100)]
        candidates.append({"id": "S100", "symbol": "S100", "nameEn": "n", "nameFa": "n",
                           "category": "stock", "marketName": "m", "unit": "$"})
        report = await self.sync.run_weekly_catalog_sync(candidate_items=candidates, dry_run=False, ignore_safety=True)
        self.assertEqual(report["status"], "applied_success")
        self.assertTrue(os.path.exists(report["snapshot_path"]))
        with open(report["snapshot_path"], encoding="utf-8") as f:
            self.assertEqual(json.load(f)["catalog_version"], 1)  # backup holds the pre-apply version
        with open(self.sync.CATALOG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["catalog_version"], 2)
        self.assertEqual(data["schema_version"], 1)

    @unittest.skipIf(sys.platform.startswith("win"), "flock is POSIX only")
    async def test_second_writer_is_rejected_while_lock_is_held(self):
        self._seed()
        candidates = [{"id": "S1", "symbol": "S1", "nameEn": "n", "nameFa": "n", "category": "stock",
                       "marketName": "m", "unit": "$"}]
        with self.sync.catalog_write_lock():
            with self.assertRaises(self.sync.CatalogLockedError):
                with self.sync.catalog_write_lock():
                    pass
            with self.assertRaises(self.sync.CatalogLockedError):
                await self.sync.run_weekly_catalog_sync(candidate_items=candidates, dry_run=False, ignore_safety=True)
        with self.sync.catalog_write_lock():  # released afterwards
            pass

    async def test_apply_aborts_if_catalog_changed_after_load(self):
        cat = self._seed()
        candidates = [{"id": f"S{i}", "symbol": f"S{i}", "nameEn": f"S{i}", "nameFa": f"S{i}",
                       "category": "stock", "marketName": "m", "unit": "$"} for i in range(100)]
        diff = self.sync.compute_catalog_diff(cat, candidates)
        stale = dict(cat)
        bumped = dict(cat)
        bumped["catalog_version"] = 5
        self.sync.save_catalog(bumped)
        with self.sync.catalog_write_lock():
            with self.assertRaises(self.sync.CatalogLockedError):
                await self.sync._apply_catalog_sync(stale, diff, diff["stats"], {})


if __name__ == "__main__":
    unittest.main()
