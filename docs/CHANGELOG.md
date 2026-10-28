# Changelog

## [Unreleased] — Phase 3-5 completion

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