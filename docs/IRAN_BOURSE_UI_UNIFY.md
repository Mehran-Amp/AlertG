# Iranian Bourse UI Unification Audit (Phase 22a)

Date: 2026-11-20
Scope: Read-only audit for **Phase 22 (Option A — single consistent Iranian entry)**. No application code was changed in this step.

---

## 1. Screens & Screenshot Checklist

> **Environment note:** The coding environment does not have a Flutter runtime / Android emulator attached, so live screenshots could not be captured here. Every item below was audited directly from the Flutter and Python source files; the owner can attach screenshots from a phone/emulator before starting `22d`/`22e`.

| # | Screen | Source Entry Point | Screenshot Status |
|---|---|---|---|
| 1 | Market chooser (currently 4 cards) | `lib/features/watchlist/pages/create_alert_flow.dart` (`_buildMarketTypeChooser`, L1064–1197) | Pending (phone/emulator) |
| 2 | Iranian hub (`all` view) | `lib/features/watchlist/pages/create_alert_flow.dart` (`_buildIranMarketPicker`, L2131–2374) | Pending (phone/emulator) |
| 3 | Iranian hub — legacy chip `GoldFunds` | `_buildIranMarketPicker`, L2176 (`iran_cat_gold_funds`) | Pending (phone/emulator) |
| 4 | Iranian hub — legacy chip `LeveragedFunds` | `_buildIranMarketPicker`, L2177 (`iran_cat_leveraged`) | Pending (phone/emulator) |
| 5 | Iranian hub — legacy chip `TopStocks` | `_buildIranMarketPicker`, L2178 (`iran_cat_top_stocks`) | Pending (phone/emulator) |
| 6 | Iranian hub — legacy chip `Bourse` | `_buildIranMarketPicker`, L2179 (`iran_cat_bourse`) | Pending (phone/emulator) |
| 7 | Bourse browse list (new TSETMC flow) | `lib/features/iran_bourse/pages/bourse_browse_page.dart` | Pending (phone/emulator) |
| 8 | Bourse symbol detail | `lib/features/iran_bourse/pages/bourse_symbol_detail_page.dart` | Pending (phone/emulator) |
| 9 | Bourse alert form | `lib/features/iran_bourse/alerts/bourse_alert_form_page.dart` | Pending (phone/emulator) |
| 10 | Crypto pair list | `lib/features/watchlist/pages/create_alert_flow.dart` (`_buildCryptoPairPicker`, L1738–1950) | Pending (phone/emulator) |
| 11 | Crypto / Iran legacy alert form | `lib/features/watchlist/pages/create_alert_flow.dart` (`_buildConditionAndFrequencyStep`, L2395–3560) | Pending (phone/emulator) |

---

## 2. Visual & Structural Differences (Wizard vs. Bourse Screens)

Note: Both `MarketFlowType.iran` (`create_alert_flow.dart` L1050–1060) and all `BourseAlertFlow` pages wrap their body in `Directionality(textDirection: TextDirection.rtl)` with pure Persian copy. Language/RTL is **not** a divergence; the differences are navigation structure, AppBar styling, card/row containers, spacing/radius, accent colors, and form field chrome.

### 2.1 Header & Navigation

| Aspect | Shared Wizard (`create_alert_flow.dart`) | Bourse Flow (`bourse_browse_page.dart`, `bourse_symbol_detail_page.dart`, `bourse_alert_form_page.dart`) |
|---|---|---|
| Navigation model | Single `Scaffold` with internal `_flowType` + `_step` state and `PopScope` (`_handleBackNavigation`) | 3 separate `MaterialPageRoute` pages pushed by `BourseAlertFlow` (`browse` → `detail` → `form`), popped back to `bourseFlowRootRoute` on submit |
| `AppBar` background & elevation | Explicit `backgroundColor: theme.colorScheme.surface`, `elevation: 0` (L1012–1014) | Default Material `AppBar(...)` with no explicit `surface` override or `elevation: 0` |
| Back icon | Explicit `Icons.arrow_back_rounded`, `color: theme.colorScheme.onSurface` (L1016) | Default Material back button |
| Title style | Explicit `fontSize: 16, fontWeight: FontWeight.bold, color: theme.colorScheme.onSurface` (L1031) | Default `AppBar` title `TextStyle` (`titleLarge`, typically 20–22px) |
| Step pill (chooser) | Rounded pill (`borderRadius: 20`, `padding: 10x4`, `primary` 15% alpha, `Icons.auto_awesome_rounded` 14px, 12px bold) above 18px `w800` title (L1068–1095) | None |

### 2.2 Colors & Accents

| Element | Shared Wizard | Bourse Flow |
|---|---|---|
| Crypto accent | `theme.colorScheme.primary` | — |
| Macro / Global stocks accent | `theme.colorScheme.secondary` | — |
| Iran domestic hub accent | Hard-coded amber `Color(0xFFFFB300)` (Card 3 L1148–1156, hub row avatar/price/CTA L2287/2351/2360, `_buildIranChip` L2386–2390, quick percent chips L2977–2980) | — |
| Bourse accent (Card 4) | Hard-coded teal **`Color(0xFF26A69A)`** at `create_alert_flow.dart` L1175, L1176, L1177, L1183 | Inside `lib/features/iran_bourse/`: **no** `0xFF26A69A`; uses `Theme.of(context).colorScheme` + `BourseText` + `AppTokens` (`positive`/`negative`/`warning`) |
| Text styles | Inline `TextStyle` with `theme.colorScheme.onSurface` (+ `0.55`/`0.65`/`0.7` alpha) | `BourseText` (`body` 13px, `secondary` 13px 65% alpha, `caption` 11px `w500`, `header` 15px `w600`, `price` 24px monospace `w600`) |
| Closed-market banner colors | `Color(0xFFE65100)` 8%/25% + `Colors.red` / `Colors.redAccent` badge (L2199–2220, L2667–2681) | `AppTokens.warningSubtle` + `AppTokens.warning` border (`withAlpha(120)`) + `Icons.info_outline` (L46–54 of `bourse_session_banner.dart`) |

### 2.3 Spacing, Radii & Row Style

| Element | Crypto Pair List (`_buildCryptoPairPicker`) | Iranian Hub (`_buildIranMarketPicker`) | Bourse Browse (`BourseBrowsePage` + `BourseBoardRow`) |
|---|---|---|---|
| Page / list padding | Search `horizontal: 16`; list `EdgeInsets.all(16)` | Search `fromLTRB(16, 12, 16, 8)`; list `EdgeInsets.all(16)` | Search `fromLTRB(16, 8, 16, 4)`; list **no outer horizontal padding** (full-bleed `ListTile`) |
| Search `TextField` | `filled: true`, `fillColor: surface`, `contentPadding: 14x10`, `OutlineInputBorder(radius: 12)` | Same (`filled: true`, `radius: 12`, `14x10`, `fontSize: 13`) | Unfilled default `OutlineInputBorder()` (default radius 4px), `isDense: true` |
| Category chips | None (search + exchange header card) | `FilterChip` in `SingleChildScrollView`, `fontSize: 11`, amber `0xFFFFB300` active border/fill | `ChoiceChip` in `SizedBox(height: 48)` `ListView`, default M3 theme styling |
| Row container | Bordered card (`Container` inside `InkWell`, `radius: 14`, `padding: 14x12`, `surface` bg, `dividerColor` border, `8px` gap via `ListView.separated`) | Same bordered card (`radius: 14`, `padding: 14x12`, `surface` bg, `dividerColor` border, `8px` gap) with 40px circular emoji icon | Plain Material **`ListTile`** (no card container, no border, no rounded corners, no 8px card gap) |
| Row typography | Bold 13px title, 11px muted subtitle, monospace price | Bold 13px title, 11px subtitle, bold 13px monospace price + 10px CTA | Default `ListTile` title/subtitle + trailing plain Rial text + 12px colored `%` + 10px muted tag |
| Detail card | None (tap goes directly to alert form) | None (tap goes directly to alert form) | Intermediate `BourseSymbolDetailPage` with default Material `Card` (`padding: 16`) + `FilledButton` |

### 2.4 Alert Form Fields (`_buildConditionAndFrequencyStep` vs. `BourseAlertFormPage`)

| Field / Section | Shared Wizard Form (`create_alert_flow.dart`, L2395–3560) | Bourse Alert Form (`bourse_alert_form_page.dart`, L165–333) |
|---|---|---|
| Outer padding | `EdgeInsets.all(20)` (`ListView`) | `EdgeInsets.all(AppTokens.space16)` (`SingleChildScrollView`) |
| Selected asset header | Bordered `surface` card (`padding: 16`) with asset name, exchange label, live price + refresh icon + closed-market banner | Single plain `Text` line (`آخرین قیمت: ...`, `BourseText.secondary`) + optional amber `Container` closed-market note (`radius: 8`, `padding: 12`) |
| Check frequency / interval | Number `TextField` + `DropdownButtonFormField` (`minutes`/`hours`) + calculated interval caption (`radius: 12`, `filled: true`) | Not present (Bourse alerts are evaluated server-side by the gateway poller, not client-selected intervals) |
| Condition selector | Two equal-width bordered `InkWell` tiles (`radius: 12`, `padding: vertical 12`, `primary` 15% active fill): `percentChange` / `priceThreshold` | `Wrap` of Material `ChoiceChip`s (`price`, `percentChange`, `absoluteChange`) |
| Direction selector | Row of custom `_buildDirectionChip`s (`above`, `below`, `bothSides`; plus OCO vs. Dual-Active when `bothSides`) | Material `SegmentedButton<AlertDirection>` (`above`, `below` only) |
| Quick presets | Iran flow: horizontal `ActionChip` presets (`1%..20%`); price threshold: `±2.5%` quick-fill pills | None (shows live formatted Rial preview, `≈ triggerPrice`, and `% distance` helper texts below input) |
| Text inputs (amount / note) | `filled: true`, `fillColor: surface` (or `surfaceContainerHighest` 40%), `OutlineInputBorder(radius: 12)` with `dividerColor`, bold `monospace` numbers | Unfilled `OutlineInputBorder()` (default radius 4px), default font weight |
| Notification options | Bordered `Material` card (`radius: 14`, `padding: 14`) containing: Note field, Sound preset picker with play/stop audition, 3 `SwitchListTile`s (Sound, Flash SOS, Vibrate), nested TTS Voice card (`radius: 12`) | Only a single `SwitchListTile` for `recurring` (no sound/vibration/flash/TTS pickers) + `alertOnlyLiveNote` caption |
| Primary CTA button | Full-width `ElevatedButton` (`backgroundColor: primary`, `foregroundColor: white`, `padding: vertical 14`, `radius: 12`, bold 14px) | Material `FilledButton` (default M3 pill shape & height) |

---

## 3. `IranDomesticExchange.predefinedAssets` Count per Category

Source: `lib/features/exchanges/stocks/iran_domestic_exchange.dart` (`predefinedAssets`, total **113** entries across **10** categories).

### 3.1 Categories KEPT in the Iranian Hub (Non-TSE — 48 entries)

| Category (`cat`) | Count | Hub Chip Key (`_buildIranMarketPicker`) | Status in Option A |
|---|---:|---|---|
| `Currencies` | 18 | `iran_cat_currencies` (L2173) | Keep unchanged |
| `Tether` | 14 | `iran_cat_tether` (L2174) | Keep unchanged |
| `DigitalGold` | 6 | `iran_cat_digital_gold` (L2175) | Keep unchanged |
| `Coins` | 5 | `iran_cat_coins` (L2172) | Keep unchanged |
| `Gold` | 5 | `iran_cat_gold` (L2171) | Keep unchanged |
| **Subtotal (Kept)** | **48** | **5 chips + `all`** | **Unchanged** |

### 3.2 Legacy TSE / Bourse Categories (65 entries — overlap with new `BourseAlertFlow`)

| Category (`cat`) | Count | Hub Chip Key (`_buildIranMarketPicker`) | Notes |
|---|---:|---|---|
| `TopStocks` | 37 | `iran_cat_top_stocks` (L2178) | Chip to hide in `22c` |
| `GoldFunds` | 12 | `iran_cat_gold_funds` (L2176) | Chip to hide in `22c` (contains legacy `عیار`, etc.) |
| `IndexFunds` | 7 | **No dedicated chip** | **Important finding:** `IndexFunds` has 7 assets in `predefinedAssets` and is treated as TSE (`isTseAsset`, L2266 & L2619). It currently appears when `_iranCategoryFilter == 'all'`. |
| `LeveragedFunds` | 6 | `iran_cat_leveraged` (L2177) | Chip to hide in `22c` |
| `Bourse` | 3 | `iran_cat_bourse` (L2179) | Chip to hide in `22c` (TEDPIX, Equal-Weighted, IFX) |
| **Subtotal (Legacy TSE)** | **65** | **4 visible chips (+ hidden `IndexFunds`)** | **Keep in `predefinedAssets` for old alerts; exclude from hub list in `22c`?** *(Confirm with owner in `22c` whether the `'all'` filter should also hide these 5 legacy TSE categories so they don't duplicate "بورس تهران".)* |

---

## 4. Where Saved Alerts with `iran_market` / Legacy TSE Categories Are Read

Hard rule for `22c`: **Do not delete `IranDomesticExchange`, `predefinedAssets`, or `'iran_market'` handling.** All existing read/edit paths verified in `lib/`:

1. **Edit saved alert (`_step = 2` path)** — `lib/features/watchlist/pages/create_alert_flow.dart` **L200–214**:
   - When `widget.initialRule!.exchangeId == 'iran_market'`, sets `_flowType = MarketFlowType.iran`, `_step = 2`, `_iranSubTab = 0`, and resolves `_selectedIranDomesticAsset` from `IranDomesticExchange.predefinedAssets` matching `s['symbol'] == rule.baseCurrency` (with a `'cat': 'Custom'` fallback if not found).
   - Because edit mode jumps straight to `_step = 2`, hiding chips in `_buildIranMarketPicker` (`_step = 1`) does **not** break editing old `TopStocks`/`Bourse`/`GoldFunds`/`LeveragedFunds`/`IndexFunds` alerts.
2. **Live price & detail fetch during edit/view** — `lib/features/watchlist/pages/create_alert_flow.dart` **L385, L400, L490, L505**:
   - Calls `widget.registry.fetchSnapshotFrom('iran_market', pair)`, `ServerAlertService.fetchPriceViaServer('iran_market', sym)`, and `ServerAlertService.fetchPriceDetailsViaServer('iran_market', sym)`.
3. **Rule persistence on save** — `lib/features/watchlist/pages/create_alert_flow.dart` **L715**:
   - Saves with `exchangeId = 'iran_market'`.
4. **Step-2 closed-market banner check** — `lib/features/watchlist/pages/create_alert_flow.dart` **L2619**:
   - Checks `cat == 'Bourse' || cat == 'GoldFunds' || cat == 'LeveragedFunds' || cat == 'IndexFunds' || cat == 'TopStocks'`.
5. **Exchange adapter & fallback pricing** — `lib/features/exchanges/stocks/iran_domestic_exchange.dart` **L1086, L1215–1242**:
   - `fetchCurrencyPairs()` maps `predefinedAssets`; `fetchTicker()` looks up `predefinedAssets` by symbol and attributes the 5 TSE categories to `'سامانه بورس تهران (TSETMC)'`.
6. **Exchange registry & catalog** — `lib/features/exchanges/registry/exchange_registry.dart` **L16**, `lib/features/exchanges/registry/exchange_catalog.dart` **L25**:
   - Defines `iranMarketId = 'iran_market'`.
7. **Watchlist display & edit trigger** — `lib/features/watchlist/pages/watchlist_page.dart` **L1409–1411**:
   - Maps `'iran_market'` / `'IRAN_MARKET'` → display label `'IR_M'`.
8. **Local condition evaluator** — `lib/features/alert_engine/scheduler/condition_evaluator.dart` **L81**:
   - Maps `'iran_market'` → `'Iran Market'`.
9. **Catalog sync & default watchlist seed** — `lib/core/services/catalog_sync_service.dart` **L15, L82, L113, L418** and `lib/features/watchlist/services/watchlist_service.dart` **L123**.
10. **Separation from new Bourse rules** — `lib/features/iran_bourse/alerts/bourse_alert_draft.dart` **L7**:
    - New Bourse alerts use `exchangeId = 'tsetmc'`, so there is zero ID collision with legacy `'iran_market'` rules.

---

## 5. Legacy Banner Schedule Check vs. `app/markets/iran_bourse/session.py`

| Source | Schedule / Logic | Exact Location |
|---|---|---|
| **Legacy Flutter banner (hub & step-2)** | Reads `_iranMarketsStatus?['tse']`; fallback string: `'شنبه تا چهارشنبه، ۰۹:۰۰ تا ۱۲:۳۰ (وقت تهران)'` | `create_alert_flow.dart` **L2187–2189** and **L2620, L2659** |
| **Backend legacy `tse` key** | `is_tse_market_open()`: Saturday–Wednesday **`09:00–12:30` IRST** (`schedule_fa`: `'شنبه تا چهارشنبه ۰۹:۰۰ تا ۱۲:۳۰'`) | `app/engine/calendar.py` **L185–199, L368–378** |
| **Real Bourse session (`session.py` + `calendar.py`)** | `classify()` calls `is_iran_bourse_open()`: Saturday–Wednesday **`08:30–19:00` IRST** + `feed_fresh` (`STALE` if false) + `seq_age_seconds <= 180.0` (`CLOSED` if quiet > 180s) + `traded_today` (`NO_TRADE_TODAY` if false). Exposed in `/api/markets/status` under `"iran_bourse"` (`schedule_fa`: `'شنبه تا چهارشنبه ۰۸:۳۰ تا ۱۹:۰۰'`). | `app/markets/iran_bourse/session.py` **L28–40** and `app/engine/calendar.py` **L206–231, L284–308, L379** |
| **New Bourse Flutter banner (`BourseSessionBanner`)** | Does **not** hard-code any hours string; renders state directly from server `/api/iran-bourse/board` `session` (`open`/`closed`/`stale`/`unknown`) and `stale` flag. | `lib/features/iran_bourse/widgets/bourse_session_banner.dart` **L21–35** |

### Discrepancy Summary
1. **Hours mismatch (`09:00–12:30` vs. `08:30–19:00`):** During pre-open (`08:30–09:00`) and afternoon fund/ETF/commodity sessions (`12:30–19:00` Tehran — when gold funds such as عیار actively trade), the legacy `tse` banner reports the market as **closed (`۰۹:۰۰ تا ۱۲:۳۰`)** even though the real Bourse gateway and `session.py` treat it as **open (`LIVE`)**.
2. **Scope mismatch after `22c`:** Once the legacy TSE categories are moved behind the new "بورس تهران" entry (`BourseAlertFlow`), the remaining 48 hub items (gold 18k, coins, free currencies, tether, digital gold) are not TSE stock-exchange sessions; showing a TSE-closed `09:00–12:30` banner over free-market FX/tether in `_buildIranMarketPicker` is misleading (whereas `BourseBrowsePage` already shows the accurate `BourseSessionBanner`).

---

## 6. Readiness Notes for Next Sub-Phases (`22b` → `22f`)

- **`22b` (Safety net tests — tests only, no app code):** Pin current behavior in a new test file under `test/`:
  1. Market chooser renders 4 cards (Crypto, Macro, Iran Domestic, Bourse).
  2. Iranian hub renders the 4 legacy TSE chips (`GoldFunds`, `LeveragedFunds`, `TopStocks`, `Bourse`).
  3. Opening `CreateAlertFlow` in edit mode with a saved `AlertRule` whose `exchangeId == 'iran_market'` and `baseCurrency` belongs to `TopStocks` opens step 2 directly with that asset selected.
- **`22c` (Merge entries — requires explicit `"approve 22c"`):**
  - Remove Card 4 from `_buildMarketTypeChooser`; add prominent first tile `"بورس تهران"` inside `_buildIranMarketPicker` calling `BourseAlertFlow.open(...)`.
  - Hide the 4 legacy TSE chips (`GoldFunds`, `LeveragedFunds`, `TopStocks`, `Bourse`) — and confirm with owner whether the `'all'` list inside `_buildIranMarketPicker` should also filter out the 5 legacy TSE categories (`GoldFunds`, `LeveragedFunds`, `TopStocks`, `Bourse`, `IndexFunds`) and hide the legacy `09:00–12:30` TSE banner on the hub while preserving `IranDomesticExchange.predefinedAssets` untouched for saved-alert editing.
- **`22d` & `22e` (Visual & form polish):** Align `BourseBrowsePage`, `BourseSymbolDetailPage`, `BourseAlertFormPage` headers (`surface` bg, `elevation: 0`, 16px bold title), bordered 14px list cards / 12px filled inputs, and replace the hard-coded `0xFF26A69A` color with a theme token while keeping all existing widget `Key`s intact.
