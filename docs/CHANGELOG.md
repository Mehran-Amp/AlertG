# Changelog

## [Unreleased] — Phase 3-5 completion

### Crypto V2 Flutter Client & Server-First Pricing Gateway (feat/server-price-gateway)

- **Server-First Pricing (Phase F1–F3)**: Added `ServerPriceGateway` (`GET /api/price/{exchange}/{symbol}`, 3s timeout, automatic fallback to direct exchange REST API) across all 18 canonical crypto exchanges (`binance`, `mexc`, `kucoin`, `gateio`, `lbank`, `okx`, `kraken`, `bybit`, `bitget`, `htx`, `bingx`, `xt`, `toobit`, `poloniex`, `coinbase`, `bitfinex`, `tabdeal`, `kifpool`) with master switch `kCryptoServerFirstPricing` and per-exchange `k<Exchange>ServerFirst` rollback switches.
- **Deduplicated Price Fetch**: `SchedulerService._getLiveTicker` and `CreateAlertFlow._fetchLivePriceForSelectedAsset` delegate directly to the registered crypto exchange adapter (server-first then direct fallback) without duplicate server calls on failure.
- **No Static Fallbacks & Spot USDT-Only (Phase 9)**: Removed all static coin list fallbacks (`CryptoCatalogData.buildPairs` / hardcoded lists) across active exchange adapters and `CreateAlertFlow`; enforced Spot `USDT` pairs for global crypto exchanges (`TMN`/`USDT` for `tabdeal` and `kifpool`).
- **Offline Disk Cache & Outdated Banner**: Added `disk_cache` "may be outdated" banner and offline empty-catalog retry UI in `CreateAlertFlow`; synchronous test-cache support in `CryptoCatalogService`.
- **Exact Sub-Satoshi Formatting & Legacy CoinEx Purge**: Fixed `FormatUtils.formatExactDecimal` for values `< 1e-12` (no truncation to `0` or scientific notation); purged legacy local `coinex` rules on load/import with a one-time `SnackBar` notice and excluded `coinex` from server sync.
- **Aggregator Dead-Code Cleanup (Category 1 Only)**: Removed unreferenced `lib/features/exchanges/coingecko/coingecko_exchange.dart` and `lib/features/exchanges/coinmarketcap/coinmarketcap_exchange.dart` (along with their empty directories). Deliberately kept the 5 frozen Iranian exchange adapters (`nobitex`, `wallex`, `ramzinex`, `bitbarg`, `tetherland` + `iranian_exchange_adapter.dart`, `iran_market_gateway.dart`, `crypto_catalog_data.dart`) and the 2 tested non-picker adapters (`kcex`, `ourbit`) untouched.
- **Phase 12 Documentation, Legacy Test Alignment & Manifest Refresh**: Documented Crypto V2 architecture, 18 canonical exchanges, feature flags, verification scripts, and rollback pointers in `README.md`; updated 4 obsolete Crypto V1 assertions (`tests/test_phase4_registry_and_catalog.py`, `tests/test_phase5_official_pairs_and_tickers.py`, `tests/test_phase7_iran_market_separation.py`) to match the approved Crypto V2 `ExchangeCatalog`; regenerated `docs/MD5_MANIFEST.txt` cleanly without deleted `coinex`/`coingecko`/`coinmarketcap` entries.



### NTF — Permanent notification shows the date (feature/ntf-calendar-notification)

- Notification 777 title is now `weekday · date` in the calendar chosen in Settings
  (Jalali / Gregorian / Hijri, independent of the app language; 'auto' = Jalali for
  Persian, Gregorian otherwise until the user chooses). Line 2: `server 24/7 online`,
  or `server offline · local monitoring` when prices are not coming from the server.
- Hijri uses a built-in Umm al-Qura table (AH 1400-1499) with a -1/0/+1 day adjustment.
- New pure helper `persistent_notification_text.dart` (no I/O, safe in the service isolate);
  date refresh rides the existing 10 s service tick (midnight / time-zone safe).
- Alarm notifications, channels and notification ID 777 are unchanged.
- Device checklist: title correct; tap opens the app; midnight rollover; time-zone change;
  English UI + Jalali calendar; Hijri adjustment; swipe-away + reboot keep the service;
  alarm sound / flash / banner unchanged.

### Phase 3 — Health & observability

- **3C-1** (`2bc8e89`): pin `firebase-admin==7.7.0` + lock error classes
- **3E-1** (`e2e36ee`): `/health/deep` with 503 on degraded pipeline
- **3E-1 precise** (`c96207b`): `last_fcm_ok_ts` / `last_check_ts` thresholds
- **3E-2** (`fa20eca`): `health_check.py` with auto-restart + admin alert (cron)
- **3D** (`ef51446`): correct notification source variable

### Phase 4 — WebSocket

- **4A-1** (`f52051b`): `/ws` endpoint + ConnectionManager
- **4A-1 auth** (`e9bd446`): websocket authentication
- **4A-2** (`41adeaa`): WS alert delivery + ack
- **4A-2 await** (`fad252d`): await WS delivery
- **4A-2 lock** (`543af1c`): asyncio lock lifecycle
- **4B-1** (`e561d9c`): WebSocket client in background service
- **4C** (`d4acdda`, `825cdea`, `b9b5b49`, `7488953`): chaos + metrics + heartbeat

### Phase 5 — Chaos & release gate

- **5A-1** (`b72fbdf`): chaos delivery + resilience suite
- **5A-2** (`c606ccf`): soak delivery script (mocked FCM)
- **5B** (`089eae3`): release gate device matrix
- **5C** (`ba17f58`): GitHub Actions CI (server + flutter)
- **5D** (`bf28fb0`): release gate script (PASS/FAIL)

### Phase 6 — Production hardening (2026-10-27)

- **STATE-CASE-1** (`fc56697`): normalize Yahoo `marketState` case in `_extract_yf`
- **CAL-FIX-1** (`5ae35ce`): forex hours follow New York time (EDT/EST)
- **FIX-BASELINE-1** (`0f8bf48`): empty merge sync must not write baseline
- **AUTH-OFF-1** (`5b9ac23`): disable mock Google Sign-In, hide UI entry points
- **EDGE-FRESH-1** (`3ece94d`): trigger fresh alerts immediately instead of Edge Guard
- **SYNC-4** (`a126b16`, `5ea6fd5`): restore guest alerts from cloud on startup
- **HEALTH-ALERTS-DB-1** (`3425ce1`): warn on sudden `ALERTS_DB` drop in `/health/deep`
- **Incident doc** (`01b75f3`): record empty-sync alert deletion incident

### Audit fixes

- **REGEX-1** (`efc3b7e`): widen `SYMBOL_RE`/`EXCHANGE_RE` to match catalog
- **REGEX-2** (`971ee14`): `sync.py` imports regex from `config.py`
- **FIX-WS-1** (`652e4e7`): WS via `_spawn` with 3s timeout
- **FIX-WS-2** (`fb4c690`): disconnect stale sockets >90s
- **FIX-WS-3** (`ae171c7`): remove API key from query string
- **FIX-6** (`c643544`): `fgs.lifecycle` after `setAsForegroundService`
- **FIX-7** (`7249d06`): log exceptions in `notification_health_page`
- **FIX-FCM-1** (`9830b08`): log swallowed exceptions + remove unused vars
- **Report-5** (`3eb007d`): explicit display names for catalog exchanges
- **Report-6** (`c037e26`): `normalize_symbol` in `routes/alerts.py`
- **chore** (`971573e`): ignore `market_events_state.json` and health_check artifacts

### Tests

- **353 passed, 1 skipped** on Windows (Python 3.14, pytest 9.1.1)
- **6 CI runs** green on GitHub Actions
- **Soak** (20 alerts, 10s): 20/20 acked, 0 unacked, p95 4ms

### Pending (device required)

- **2A-6**: manual device test (5 scenarios)
- **3C-2**: hybrid FCM payload strategy (needs device log)
- **release_gate.md**: 4 sign-off checkboxes