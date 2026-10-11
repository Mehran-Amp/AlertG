# Static symbol lists in the Flutter app (inventory, v3.1.0)

| File | Lines (v3.1.0) | Count | Status |
|---|---|---|---|
| `lib/features/exchanges/stocks/global_stocks_exchange.dart` `predefinedStocks` | was 33-1805 | was 184 | **Replaced** by a getter fed by `CatalogSyncService` (server catalog) |
| same file `cryptoMacroSymbols` | 36-~100 | 7 | Kept: crypto-macro indices (TOTAL*, dominance, Fear & Greed); crypto is out of scope |
| `lib/core/services/catalog_sync_service.dart` `_seedDefaultCatalog` | 170-~192 | 22 -> 18 | **Offline fallback**, hard cap 20 (`maxOfflineFallbackSymbols`); Iran seed items removed |
| `lib/features/exchanges/stocks/iran_domestic_exchange.dart` `predefinedAssets` | 33-1082 | 113 | **Pending decision**: not touched (Iran market out of scope; symbols differ from server catalog ids) |
| `lib/features/exchanges/base/crypto_catalog_data.dart` `topCoins` | 5-55 | ~310 tickers | Crypto, not touched |
| `lib/features/watchlist/widgets/asset_search_field.dart` `_popularCoins` | 43 | 13 | Crypto, not touched |
| `lib/core/services/tts_service.dart` (`_macroAssetDirectory` 21, `_cryptoAssetNames` 125, `_stockAssetNames` 277) | - | 74 / 143 / 64 | Spoken-name metadata, not selectable symbol lists |
| `lib/core/utils/crypto_icons.dart` `_metadata` | 7 | 96 | Icon metadata, not a symbol list |

Old static global symbols without a same-named entry in the server catalog (alias differences such as `^GSPC`/`SP500`
or `GC=F`/`GOLD` included): see the list printed in the phase 3 report; add them server-side
(`WALLSTREET_MACRO_SYMBOLS`) or drop them.

## Old static symbols not found by name in the server catalog (123)

- **Macro** (5): DX-Y.NYB, ^TNX, ^IRX, ^TYX, ^FVX
- **Indices** (2): ^GSPC, ^FCHI
- **China** (15): 000001.SS, 399001.SZ, ^HSI, FXI, KWEB, BYDDY, LI, XPEV, XIACY, NTES, SMICY, BILI, ^KS11, ^NSEI, ^TWII
- **Commodities** (5): GC=F, SI=F, PA=F, BZ=F, CL=F
- **Forex** (7): NZDUSD=X, EURJPY=X, GBPJPY=X, EURGBP=X, USDCNH=X, USDTRY=X, USDT/TMN
- **Aerospace** (3): LUNR, NOC, SPCE
- **Top100** (86): BRK-B, LLY, JPM, WMT, V, NVO, TCEHY, XOM, UNH, ORCL, MA, COST, HD, PG, JNJ, ABBV, BAC, BABA, NFLX, SAP, KO, CVX, CRM, LVMUY, TM, HESAY, AZN, NVS, ADBE, CSCO, QCOM, LIN, WFC, MCD, PEP, ACN, IBM, NOW, GE, TMUS, INTU, TXN, MS, GS, CAT, AMGN, UBER, DIS, PM, AXP, ISRG, VZ, BKNG, BLK, PFE, SNY, SONY, SIEGY, DHR, RTX, HON, UNP, AMAT, TTE, MU, COP, ETN, PANW, NKE, BMY, LMT, SBUX, PDD, LRCX, BSX, KLAC, SBGSY, SYK, ADI, VRTX, ARM, CRWD, SMCI, INTC, BIDU, NIO
