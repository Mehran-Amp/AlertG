# AlertG — Stage B Design Document: Iranian Exchanges (Tabdeal Wave 1)

## 1. Overview & Objective
This document outlines the architectural plan for Stage B: integrating **Tabdeal** into AlertG's Crypto Engine v2 as the first approved Iranian exchange (Wave 1), in compliance with Hard Rules R1–R19, Part E, and the Phase 11 Handover specifications.

---

## 2. Architecture & File Plan

### 2.1 Zone Breakdown & Guarded Files
- **Allowed Zone (Crypto Modules & Tests):**
  - `app/markets/adapters/tabdeal.py` (New Tabdeal Adapter specification)
  - `app/markets/crypto_registry.py` (Add `tabdeal` to registry with `compliance_status: "approved"`, category: `"iran_crypto"`, quotes: `["USDT", "TMN"]`, alias: `{"IRT": "TMN"}`)
  - `tests/test_crypto_adapter_tabdeal.py` (Unit tests with recorded fixtures)
  - `tests/test_iranian_crypto_binding.py` (Binding isolation test, zero cross-exchange calls)
- **Additive-Only Zone (Separate commit with golden tests):**
  - `app/markets/base.py`: Route registered crypto exchanges to strict/engine path before checking Iranian suffix rules. Legacy unregistered Iranian IDs continue using the existing path.
  - `app/engine/categories.py`: Introduce `iran_crypto` category with `cache_ttl = 5.0s`, `outlier_threshold = 1.00` (with 3 confirmations), price floor `1e-12`. `iran_market` (60s cache, Bonbast/Gold/TSE) remains completely untouched.
  - `app/engine/formatter.py` & `app/engine/checker.py` & `app/notifier/telegram.py`: Format prices based on the **quote currency** rather than the exchange name.
    - `TMN` quote: Formatted with comma thousands separators; retains exact decimals if price < 100 TMN (preventing truncating micro-coins like 0.35 TMN to 0).
    - `USDT` quote: Exact decimal formatter (`format_exact_decimal`), preserving all significant digits for values < 1, never scientific notation, never "$0".
    - Existing alerts on Nobitex with prices >= 100 remain 100% byte-identical.
  - `app/security.py`: Validate `counter_currency` for Iranian crypto exchanges allowing only `USDT` and `TMN` (with `IRT` alias). Reject invalid quotes on a per-item basis with `INVALID_QUOTE_CURRENCY` without failing the entire sync request.
  - `app/routes/crypto_symbols.py`: Expose `compliance_status` in `GET /api/crypto/exchanges`. Only approved exchanges are returned for alert creation.
- **Do Not Touch Zone:**
  - `app/markets/global_stocks.py`
  - `app/engine/sync.py`
  - Catalog seed scripts
  - `outbox.py`, `fcm.py`, `journal.py`, `webhook.py`, `safety.py`
  - Stock/forex/macro screens

---

## 3. Tabdeal Adapter Specification Details

1. **Provider Key:** `crypto_tabdeal`
2. **Endpoints:**
   - **Catalog Discovery:** `GET https://api1.tabdeal.org/r/api/v1/exchangeInfo`
     - Status: `status == "TRADING"` and `isSpotTradingAllowed == true`
     - Symbols: Native symbol (e.g. `BTCIRT`, `BTCUSDT`), base asset, quote asset (`IRT` -> mapped to canonical `TMN`, `USDT` -> `USDT`).
   - **Bulk Price Poller:** `GET https://api1.tabdeal.org/r/plots/market_information/`
     - Single bulk request every 10s on-demand (only while active Tabdeal alerts exist).
     - Maps `symbol` (e.g. `BTC_IRT`, `BTC_USDT`) to last traded price (`price` field).
   - **Rial to Toman Conversion:**
     - Tabdeal `_IRT` quotes are expressed in **Rials** (e.g. USDT_IRT = 271,250 Rials = 27,125 Tomans).
     - Conversion rule: For `IRT` quote pairs, divide raw integer value by 10 to obtain canonical `TMN`.
     - USDT pairs require zero conversion.
3. **Price Semantics:**
   - Last traded price (`price` in `market_information/` or `/r/api/v1/trades`).
   - If Tabdeal has no price, status is strictly `NO_PRICE`. No fallback to another exchange, no synthetic tether estimation.
4. **Source Labeling:**
   - Every trace carries: `source: "Tabdeal (tabdeal) Spot"`, matching Rule R11. Never contains `[via`.

---

## 4. Feature Flags & Rollback Plan

### 4.1 Flags
- `CRYPTO_STRICT_V2`: Default `false`. When enabled, enforces strict exchange isolation.
- `CRYPTO_ENGINE_V2`: Default `false`. Enables real-time in-memory snapshot poller.
- `IRAN_STRICT_EXCHANGE`: Default `false` (New).
  - When `false`: Legacy Iranian fallback order in `fetch_iran` remains for legacy callers.
  - When `true`: An alert on exchange X uses only X's verified endpoints.

### 4.2 Rollback Procedures
- **Step 1 (Immediate):** Set `IRAN_STRICT_EXCHANGE=false` and `CRYPTO_ENGINE_V2=false` in environment / config.
- **Step 2:** Restart uvicorn process.
- **Step 3 (Revert if needed):** `git revert` the Stage B commit. All existing alerts remain untouched; `catalog.json` and `iran_catalog.json` have not been modified.

---

## 5. Verification & Test Strategy
1. **Binding Test (`test_iranian_crypto_binding.py`):**
   - Mock Binance/Nobitex/KuCoin with arbitrary prices.
   - Assert Tabdeal alert returns ONLY Tabdeal's price.
   - Assert with Tabdeal failing, it returns `NO_PRICE` / `STALE_PRICE` with 0 requests to any other exchange.
2. **Rial to Toman Tests:**
   - Test `BTCIRT` (21,095,833,291 Rials -> 2,109,583,329.1 TMN).
   - Test micro prices: `PEPEIRT` (1.35 Rials -> 0.135 TMN).
3. **Category & Formatting Tests:**
   - Assert `resolve_symbol_category("tabdeal", "BTCUSDT") == "iran_crypto"`.
   - Assert `CATEGORY_CACHE_TTL["iran_crypto"] == 5.0`.
   - Assert `CATEGORY_CACHE_TTL["iran_market"] == 60.0` (unchanged).
4. **Static Analysis Guard:**
   - `python3 tests/test_undefined_names_static_analysis.py` returns 0 errors.
5. **Full Regression Suite:**
   - Run complete pytest suite: all 566+ tests passing.
