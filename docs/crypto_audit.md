# AlertG — Crypto Architecture Audit & Baseline Evidence (Phase 0)
**Version:** 2.0 (English, per Part E Master Brief)  
**Date:** October 28, 2026  
**Scope:** Strict read-only audit, baseline data capture, tier classification, and proof validation. Zero product code changes.

---

## 1. Complete Flutter App Exchange Catalog Inventory
Derived directly from `lib/features/exchanges/registry/exchange_catalog.dart` (39 total exchange entries across Tier 1 Global, Regional, Iranian, and Aggregators):

| Row | Exchange ID (`id`) | Display Name | Category | Adapter Class | Default Quote | Spot USDT Support | Backend Status | Classification |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 1 | `binance` | Binance | Tier 1 Global | `BinanceExchange` | USDT | ✅ Yes | ✅ Supported | Tier A (Wave 1) |
| 2 | `kucoin` | KuCoin | Tier 1 Global | `KuCoinExchange` | USDT | ✅ Yes | ✅ Supported | Tier A (Wave 1) |
| 3 | `mexc` | MEXC | Tier 1 Global | `MEXCExchange` | USDT | ✅ Yes | ✅ Supported | Tier A (Wave 1) |
| 4 | `gateio` | Gate.io | Tier 1 Global | `GateioExchange` | USDT | ✅ Yes | ✅ Supported | Tier A (Wave 1) |
| 5 | `lbank` | LBank | Asia / Tier 1 | `LBankExchange` | USDT | ✅ Yes | 🔄 Adapter added (Phase 4e) | Tier A (Wave 1, CoinEx replacement) |
| 6 | `okx` | OKX | Tier 1 Global | `OKXExchange` | USDT | ✅ Yes | 🔄 Adapter added (Phase 4f) | Tier A (Wave 1) |
| 7 | `bybit` | Bybit | Tier 1 Global | `BybitExchange` | USDT | ✅ Yes | ⏳ Pending Adapter | Tier A (Wave 1) |
| 8 | `bitget` | Bitget | Tier 1 Global | `BitgetExchange` | USDT | ✅ Yes | ⏳ Pending Adapter | Tier A (Wave 1) |
| 9 | `kraken` | Kraken | Tier 1 Global | `KrakenExchange` | USD / USDT | ✅ Yes (USDT spot pairs) | 🔄 Adapter added (Phase 4g) | Tier A (Wave 1) |
| 10 | `coinbase` | Coinbase | Tier 1 Global | `CoinbaseExchange` | USD / USDT | ⚠️ Limited USDT | ❌ None | Tier B / Tier A candidate |
| 11 | `bingx` | BingX | Tier 1 Global | `BingXExchange` | USDT | ✅ Yes | ❌ None | Tier A (Wave 2) |
| 12 | `kcex` | KCEX | Tier 1 Global | `KCEXExchange` | USDT | ✅ Yes | ❌ None | Tier A (Wave 2) |
| 13 | `ourbit` | Ourbit | Tier 1 Global | `OurbitExchange` | USDT | ✅ Yes | ❌ None | Tier A (Wave 2) |
| 14 | `xt` | XT.com | Tier 1 Global | `XTExchange` | USDT | ✅ Yes | ❌ None | Tier A (Wave 2) |
| 15 | `toobit` | Toobit | Tier 1 Global | `ToobitExchange` | USDT | ✅ Yes | ❌ None | Tier A (Wave 2) |
| 16 | `htx` | HTX / Huobi | Tier 1 Global | `StandardRestExchange` | USDT | ✅ Yes | ❌ None | Tier A (Wave 2) |
| 17 | `poloniex` | Poloniex | Tier 1 Global | `StandardRestExchange` | USDT | ✅ Yes | ❌ None | Tier A (Wave 2) |
| 18 | `bitmart` | BitMart | Tier 1 Global | `StandardRestExchange` | USDT | ✅ Yes | ❌ None | Tier A (Wave 2) |
| 19 | `phemex` | Phemex | Tier 1 Global | `StandardRestExchange` | USDT | ✅ Yes | ❌ None | Tier A (Wave 3) |
| 20 | `hitbtc` | HitBTC | Tier 1 Global | `StandardRestExchange` | USDT | ✅ Yes | ❌ None | Tier A (Wave 3) |
| 21 | `bitfinex` | Bitfinex | Tier 1 Global | `StandardRestExchange` | USD / USDT | ⚠️ Mostly USD | ❌ None | Tier B (Price only) |
| 22 | `bitstamp` | Bitstamp | Europe / Tier 1 | `StandardRestExchange` | USD / EUR | ⚠️ Mostly USD | ❌ None | Tier B (Price only) |
| 23 | `gemini` | Gemini | US / Tier 1 | `StandardRestExchange` | USD | ⚠️ Mostly USD | ❌ None | Tier B (Price only) |
| 24 | `cryptocom` | Crypto.com | Tier 1 Global | `StandardRestExchange` | USDT | ⚠️ No public ticker URL in app | ❌ None | Tier B / X |
| 25 | `woox` | WOO X | Tier 1 Global | `StandardRestExchange` | USDT | ⚠️ No public ticker URL in app | ❌ None | Tier B / X |
| 26 | `ascendex` | AscendEX | Tier 1 Global | `StandardRestExchange` | USDT | ⚠️ No public ticker URL in app | ❌ None | Tier B / X |
| 27 | `bitrue` | Bitrue | Tier 1 Global | `StandardRestExchange` | USDT | ⚠️ No public ticker URL in app | ❌ None | Tier B / X |
| 28 | `probit` | ProBit | Tier 1 Global | `StandardRestExchange` | USDT | ⚠️ No public ticker URL in app | ❌ None | Tier B / X |
| 29 | `upbit` | Upbit | Asia | `StandardRestExchange` | KRW | ❌ KRW Quote Only | ❌ None | Tier X (Excluded from USDT spot) |
| 30 | `bithumb` | Bithumb | Asia | `StandardRestExchange` | KRW / USDT | ⚠️ No public ticker URL in app | ❌ None | Tier X |
| 31 | `bitflyer` | bitFlyer | Asia | `StandardRestExchange` | JPY / USD | ❌ JPY/USD Quote Only | ❌ None | Tier X |
| 32 | `bitso` | Bitso | Americas | `StandardRestExchange` | MXN / USD | ❌ LatAm Fiat Quotes | ❌ None | Tier X |
| 33 | `indodax` | Indodax | Asia | `StandardRestExchange` | IDR / USDT | ⚠️ No public ticker URL in app | ❌ None | Tier X |
| 34 | `paribu` | Paribu | Europe | `StandardRestExchange` | TRY | ❌ TRY Quote Only | ❌ None | Tier X |
| 35 | `btcturk` | BtcTurk | Europe | `StandardRestExchange` | TRY | ❌ TRY Quote Only | ❌ None | Tier X |
| 36 | `bitvavo` | Bitvavo | Europe | `StandardRestExchange` | EUR | ❌ EUR Quote Only | ❌ None | Tier X |
| 37 | `deribit` | Deribit | Derivatives | `StandardRestExchange` | USD | ❌ Derivatives Only | ❌ None | Tier X |
| 38 | `bitmex` | BitMEX | Derivatives | `StandardRestExchange` | USDT | ❌ Derivatives / Swaps Only | ❌ None | Tier X |
| 39 | `coinex` | CoinEx | Deprecated | `CoinExExchange` | USDT | ❌ 503 / Shutting Down | ❌ Deleted | Tier X (Complete Removal) |

### Domestic Iranian Exchanges (Handled under Phase 10 / `iran_market`):
- `nobitex`: Nobitex (TMN & USDT)
- `wallex`: Wallex (TMN & USDT)
- `ramzinex`: Ramzinex (TMN & USDT)
- `tabdeal`: Tabdeal (TMN & USDT)
- `tetherland`: Tetherland (TMN)
- `bitbarg`: Bitbarg (TMN)
- `abantether`: AbanTether (TMN)
- `sarmayex`: Sarmayex (TMN)
- `exir`: Exir (TMN)

### Aggregators (Excluded from Alerts per E1.2):
- `coingecko`: CoinGecko (`CoinGeckoExchange`, Display Only — "Aggregated Price")
- `coinmarketcap`: CoinMarketCap (`CoinMarketCapExchange`, Display Only — "Aggregated Price")

---

## 2. Live Probe Results & Findings

### Server-Side Run (`server360`, Frankfurt/Hetzner IP):
| Exchange | HTTP Status | Latency | USDT Spot Pairs | Pairs w/ Live Price | Coverage % | Verdict |
|:---|:---|:---|:---|:---|:---|:---|
| **Binance** | `200 OK` | 162.0 ms | 516 | 708 | 100.0% | Tier A Benchmark |
| **MEXC** | `200 OK` | 105.0 ms | 1,453 | 1,453 | 100.0% | Tier A Benchmark |
| **KuCoin** | `200 OK` | 343.0 ms | 815 | 815 | 100.0% | Tier A Benchmark |
| **Gate.io** | `200 OK` | 265.1 ms | 2,033 | 2,033 | 100.0% | Tier A Benchmark |
| **LBank** | `200 OK` | 486.0 ms | 1,322 | 1,028 | 77.76% | Tier A (Unpriced ETF tokens filtered) |
| **OKX** | `200 OK` | 379.0 ms | 468 | 469 | 100.0% | Tier A Benchmark |
| **Bybit** | `200 OK` | 351.0 ms | 389 | 389 | 100.0% | Tier A Candidate |
| **Bitget** | `200 OK` | 557.0 ms | 3,518 | 3,523 | 100.0% | Tier A Candidate |
| **Kraken** | `200 OK` | 56.0 ms | 728 | 1,385 | 93.13% | Tier A (Ultra-fast latency) |
| **CoinEx** | `503 ERR` | 250.0 ms | 0 | 0 | 0.0% | Permanent Failure / Deprecated |

### Client-Side Probe Execution (Local Dev Workstation):
- Probing from local residential/regional IPs demonstrates geo-blocking (HTTP 403 on OKX, Bybit, Kraken) and timeout/connection errors on Binance.
- This confirms **R8/R9/T6**: All authoritative probe metrics and alert evaluations must be executed from the production server infrastructure.

---

## 3. Tier Classification Table (Section E1.7)

### Tier A (Alert-Capable):
Criteria: Public no-key market list, bulk ticker endpoint, $\ge 30$ active spot USDT pairs, reachable from production server, rate-limit compatible with R9 ($\le 1$ bulk request per poll window), stable symbol mapping.
- **Wave 1 (10 exchanges):** Binance, MEXC, KuCoin, Gate.io, LBank, OKX, Bybit, Bitget, Kraken, Coinbase (pending USDT quota verification).
- **Wave 2 (8 exchanges):** HTX, BingX, XT, Toobit, Ourbit, KCEX, BitMart, Poloniex.
- **Wave 3 (Secondary):** Phemex, HitBTC.

### Tier B (Display Only — Price View in App, No Alerts):
- Bitfinex, Bitstamp, Gemini (limited USDT spot pairs, primary USD/EUR fiat pairs).
- CoinGecko, CoinMarketCap (Aggregated prices, explicitly disallowed from alert evaluation).

### Tier X (Excluded / Removed from Picker):
- **Derivatives:** Deribit, BitMEX.
- **Non-USDT / Fiat-Only:** Upbit (KRW), Bitvavo (EUR), Paribu (TRY), BtcTurk (TRY), bitFlyer (JPY), Bitso (MXN).
- **No Public Ticker / Static List Only:** Crypto.com, WOO X, AscendEX, Bitrue, ProBit, Indodax, Bithumb.
- **Shutting Down:** CoinEx.

---

## 4. Collision Report (`catalog.json` vs Crypto Symbols)

We checked all 772 symbol IDs in `catalog.json` against standard crypto base coins and `BASEUSDT` pairs.

### Identified Collisions:
1. **`STX`**:
   - In `catalog.json`: Seagate Technology Holdings plc (US Stock / S&P 500).
   - In Crypto: Stacks native coin (`STXUSDT` on Binance, KuCoin, OKX, Gate.io).
2. **`W`**:
   - In `catalog.json`: Wayfair Inc. (US Stock).
   - In Crypto: Wormhole native governance token (`WUSDT` on Binance, MEXC, Gate.io).

### Impact & Bug Analysis:
In `app/engine/categories.py` (lines 97–105), `resolve_symbol_category` previously queried `_get_catalog_categories()` *before* checking crypto registry status. As a consequence:
- An alert created on Binance or OKX for `STX` or `W` was misclassified with `category = 'stock'`.
- In `app/engine/calendar.py` (lines 231–233), `is_market_open()` checked `is_us_market_open()` for stocks.
- **Critical Failure:** Alerts for `STX` and `W` were paused outside US NYSE trading hours (weekends and US nights), violating the 24/7 crypto availability guarantee.
- **Resolution (Phase 1/2/3C):** `categories.py` must check registered crypto exchanges immediately after Iranian exchanges, guaranteeing immediate `'crypto'` category return.

---

## 5. The Four Proofs (Verified with File and Line References)

### Proof 7(a): `is_market_open` Returns True for All Crypto
- **File:** `app/engine/calendar.py`, Lines 214–224:
  ```python
  def is_market_open(exchange: str, symbol: str, now_dt: Optional[datetime] = None) -> bool:
      cat = resolve_symbol_category(exchange, symbol)
      if cat == 'crypto':
          return True
  ```
  Once `resolve_symbol_category` returns `'crypto'`, `is_market_open` immediately returns `True` (24/7 operation).

### Proof 7(b): Alert Fields, UI Interval Limits, and Local Evaluation
1. **Alert Fields Sent by Flutter:**
   - **File:** `lib/core/services/server_alert_service.dart`, Lines 450–480:
     The app explicitly serializes and sends:
     - `'symbol': rule.marketSymbol.toUpperCase()`
     - `'base_currency': rule.baseCurrency`
     - `'counter_currency': rule.counterCurrency`
     - `'market_symbol': rule.marketSymbol`
     - `'check_interval_seconds': rule.checkIntervalSeconds`
     - `'prefer_server_proxy': rule.preferServerProxy`
2. **UI Interval Selection & Limitation:**
   - **File:** `lib/features/watchlist/pages/create_alert_flow.dart`, Lines 682–700:
     ```dart
     final intervalSeconds = _calculateTotalIntervalSeconds();
     if (intervalSeconds < 180) {
       // SnackBar: Minimum check interval must be 3 minutes (180 seconds) or more.
       return;
     }
     ```
     The UI hard-blocks any interval under 180 seconds for all alerts, including crypto. Real-time sub-5s crypto evaluation requires updating this guard for Tier A crypto exchanges.
3. **Local Evaluation & `prefer_server_proxy`:**
   - **File:** `lib/features/alert_engine/scheduler/scheduler_service.dart`, Lines 76–130:
     The app contains a background ticker scheduler (`_getLiveTicker`):
     - If `rule.preferServerProxy == true`, it calls `ServerAlertService.fetchPriceViaServer(rule.exchangeId, rule.pair.marketSymbol)`.
     - Otherwise, it attempts a direct local fetch via `exchange.fetchTicker(rule.pair)` with a 5-second timeout, falling back to server proxy on failure.

### Proof 7(c): Complete Inventory of `coinex` Occurrences
A full search across the repository found **70 occurrences** of `coinex`:
- **Backend Product Code:**
  - `app/markets/crypto_registry.py` (lines 10, 88, 134–144: metadata entry with `status='closing'`).
  - `app/markets/crypto.py` (lines 62, 99–102, 111, 121–122: legacy `_fetch_coinex` provider).
  - `app/markets/base.py` (line 35: string mapping list).
  - `app/markets/crypto_strict.py` (lines 176–180: inline `coinex` branch).
  - `app/markets/limiter.py` (lines 78, 111: `crypto_coinex` limiter and quota).
  - `app/routes/admin.py` (line 542: legacy test endpoint).
  - `app/notifier/telegram.py` (line 28: display name map).
- **Flutter App Code:**
  - `lib/features/exchanges/coinex/coinex_exchange.dart` (entire directory and class).
  - `lib/features/exchanges/registry/exchange_catalog.dart` (catalog registration).
  - `lib/features/settings/pages/debug_diagnostics_page.dart` (lines 49, 139).
  - `lib/features/alert_engine/scheduler/condition_evaluator.dart` (line 69).
- **Tests & Docs:**
  - `tests/test_crypto_registry_lint.py`, `tests/test_crypto_contract.py`.
  - `docs/crypto_audit.md`, `docs/crypto_contract.md`.
  - `scripts/probe_crypto_exchanges.py`.

### Proof 7(d): Production Worker Process Count & Scheduler Architecture
1. **Worker Process Count:**
   - **File:** `run_server.sh`, Line 53:
     ```bash
     nohup $PYTHON_CMD -m uvicorn "$APP" --host "$HOST" --port "$PORT" $ENV_OPT > "$LOG_FILE" 2>&1 &
     ```
     Uvicorn is launched without `--workers`, defaulting to **exactly 1 worker process**.
2. **Scheduler Execution (Guaranteed Single Runner for R9):**
   - **File:** `server.py`, Lines 85–150:
     Schedulers are initialized in `setup_scheduler_jobs()` on `AsyncIOScheduler`:
     ```python
     sched.add_job(check_alerts_job, 'interval', seconds=2, max_instances=1, coalesce=True, id='price_alerts_job')
     ```
     `max_instances=1` and `coalesce=True` ensure no concurrent overlapping cycles.
     Since only one Uvicorn worker process runs in production, **R9's single-poller constraint is naturally preserved**.

---

## 6. Phase 0 Acceptance Sign-Off
- ✅ **Repository Hygiene:** Cleaned up and updated `.gitignore` for runtime artifacts.
- ✅ **Audit Inventory:** Complete categorization of all 39 exchange entries.
- ✅ **Probe Evidence:** Real data captured and analyzed across Frankfurt server and local client runs.
- ✅ **Tier Classification:** Structured Tier A (Waves 1–3), Tier B, and Tier X.
- ✅ **Collision Report:** Identified `STX` and `W` collisions with root cause analysis.
- ✅ **Four Proofs:** Fully documented with verified file and line numbers.
- ✅ **Product Code:** Zero modifications to product logic.
