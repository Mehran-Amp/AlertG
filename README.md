# BitcoinChecker

A production-grade, local-first real-time financial market alert app in Flutter.

## Architecture Highlights
- **State Management**: BLoC pattern (`flutter_bloc`) with strict event-driven state transitions.
- **Data Ingestion**: Modular Multi-Exchange Adapter pattern inspired by `aneonex/BitcoinChecker` (Binance, Coinbase, Kraken, OKX, CoinGecko).
- **Rule Evaluator**: Dedicated Dart background isolate using a fixed-size `CircularTickBuffer` (RingBuffer) for sub-35MB RAM footprint across variable time windows.
- **Persistence**: Local-first `Isar` NoSQL database; opened independently per isolate.
- **Alert Cooldown**: Strict 3-minute suppression window preventing notification storms.
- **Background & Notifications**:
  - Android 14+: `flutter_background_service` declared as `FOREGROUND_SERVICE_DATA_SYNC` with `dataSync` foreground service type and Doze mode exemption.
  - iOS: Time-Sensitive notifications (`interruptionLevel: timeSensitive`) bypassing Focus modes without special entitlements.
- **Store Target**: Fully compliant for release on Google Play and Apple App Store.

## Symbol catalog: storage & single source of truth (v3.1.0)
- **Source of truth**: the server catalog (`catalog.json`, served by `/api/symbols/catalog` with delta sync via `catalog_version`).
  The Flutter app keeps only a disk cache (`CatalogSyncService`) and an offline fallback of at most 20 symbols.
- **Storage type**: one JSON file (`catalog.json`) plus versioned backups in `catalog_snapshots/`. Why: a few hundred symbols
  (700 fit comfortably, a few hundred KB), a single weekly writer, atomic `os.replace` writes, human-readable diffs in git,
  and no extra service to run. A database would add operations work without a benefit at this size.
- **Schema**: the file carries `schema_version` (currently 1). A file written by a newer schema is refused instead of being overwritten.
- **Single writer**: every write (weekly sync apply, rollback) holds a non-blocking `flock` on `catalog.json.lock`.
  A second writer fails immediately with `CatalogLockedError`; the sync also aborts if the catalog version changed after it was loaded.
- **Backups**: a snapshot of the previous catalog is written to `catalog_snapshots/` before every apply and every rollback.
- **Atomic write** (`save_catalog`: temp file + `os.replace`) is unchanged.

## Baseline & golden comparison (phase 3 tooling)
```bash
# On the server that runs server.py (API_KEY is read from the environment, never stored):
API_KEY=<key> python3 scripts/make_baseline.py --base-url http://127.0.0.1:8000 --phase phase3
#   -> docs/MD5_MANIFEST.txt                       (md5sum -c compatible)
#   -> snapshots/baseline_phase3_<UTC>.json        (symbols, fixed price samples, markets status)
python3 scripts/compare_golden.py --verify-manifest docs/MD5_MANIFEST.txt   # exit 1 on BREAKING differences
md5sum -c docs/MD5_MANIFEST.txt
```
`snapshots/golden_phase0.json` is never written by these tools.
