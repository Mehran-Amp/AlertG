# Iranian Bourse — Gateway Field Inventory & Alert Types (Phase 21)

This document records the exact real-world JSON fields emitted by `tsetmc-gateway v0.2.2`
(from the real fixtures captured in `tests/fixtures/iran_bourse/real/changes_reload_trimmed.json`,
`quote_ayar.json`, and `symbols.json` — no secrets or tokens), and defines the exact trigger rules
for Iranian-market alert types (`percentChange`, `queueBuy`, `queueSell`, `volumeAbove`).

## 1. Real Gateway Field Shapes (`tsetmc-gateway v0.2.2`)

- **`queue`**: string `"buy"` | `"sell"` | `null` (NOT a nested object).
- **`best_bid` / `best_ask`**: either `null` or `{"price": int, "volume": int, "orders": int}`.
- **`upper_limit` / `lower_limit`**: daily allowed price band in Rial (`int` > 0 when defined).
- **`volume`**: cumulative traded share count today (`int`, `0` if not traded yet).
- **`traded`**: boolean (`true` only when at least one trade happened today).

## 2. 10-Symbol Real Capture Inventory (Phase 21a)

| # | Ticker | Type | `traded` | `last` | `upper_limit` | `lower_limit` | `volume` | `queue` | `best_bid` (`price / vol / ord`) | `best_ask` (`price / vol / ord`) | Classification |
|---|---|---|---|---:|---:|---:|---:|---|---|---|---|
| 1 | `خگلپا` | سهم | `true` | `6,300` | `6,300` | `5,940` | `22,275,063` | `"buy"` | `6,300 / 34,402,624 / 245` | `6,350 / 1,000 / 9` *(out of band > upper)* | **Buy Queue** (`queueBuy = true`) |
| 2 | `توریل` | سهام | `true` | `4,210` | `4,210` | `3,970` | `37,782,645` | `"buy"` | `4,210 / 3,358,402 / 24` | `null` | **Buy Queue** (`queueBuy = true`) |
| 3 | `ثمسکن` | سهام | `true` | `3,960` | `3,960` | `3,740` | `31,970,664` | `"buy"` | `3,960 / 23,542,832 / 180` | `null` | **Buy Queue** (`queueBuy = true`) |
| 4 | `زبینا` | سهام | `true` | `18,450` | `18,450` | `17,390` | `8,856,711` | `"buy"` | `18,450 / 53,305 / 16` | `18,500 / 2,000 / 1` *(out of band > upper)* | **Buy Queue** (`queueBuy = true`) |
| 5 | `وسپهر` | سهام | `true` | `6,250` | `6,250` | `5,890` | `16,874,202` | `"buy"` | `6,250 / 29,540,337 / 178` | `null` | **Buy Queue** (`queueBuy = true`) |
| 6 | `فجهانح` | حق تقدم | `true` | `2,794` | `2,966` | `2,794` | `122,674` | `"sell"` | `null` | `2,794 / 4,930,693 / 1` | **Sell Queue** (`queueSell = true`) |
| 7 | `ضخود9058` | اختیار خرید | `true` | `1` | `100,000` | `1` | `543,675` | `"sell"` | `null` | `1 / 464,423 / 119` | **Sell Queue** (`queueSell = true`) |
| 8 | `ضسپا8090` | اختیار خرید | `false` | `1` | `100,000` | `1` | `0` | `"sell"` | `null` | `1 / 624,000 / 156` | **Not Traded Today** (`queueSell = false` — `traded = false`) |
| 9 | `معیار` | سهام | `true` | `2,590` | `2,590` | `2,440` | `10,117,971` | `null` | `2,589 / 15,000 / 1` | `2,590 / 1,620,401 / 8` | **NOT a Buy Queue** (`last == upper_limit`, but ask exists at `2,590` and bid < upper) |
| 10 | `عیار` | صندوق کالایی | `false` (off-hours capture) | `671,609` | `735,409` | `601,699` | `0` | `null` | `670,899 / 245 / 1` | `673,673 / 6,000 / 1` | **Normal Book** (no queue) |

### Key Takeaways From Real Captures

1. **Out-of-band opposite quotes happen in real buy queues**: In `خگلپا` (`upper_limit = 6300`, `best_ask.price = 6350`) and `زبینا` (`upper_limit = 18450`, `best_ask.price = 18500`), TSETMC still lists unfillable offers above `upper_limit`. Therefore a buy queue MUST allow `best_ask is None` **OR** `best_ask.price > upper_limit` (and symmetrically a sell queue allows `best_bid is None` **OR** `best_bid.price < lower_limit`).
2. **`last == upper_limit` is NOT sufficient**: `معیار` traded at `upper_limit` (`2590`) with `best_ask = 2590` and `best_bid = 2589` (`queue = null`). Checking `best_bid.price == upper_limit` AND no fillable ask (`best_ask is None or best_ask.price > upper_limit`) prevents false positives.
3. **Untraded instruments can still carry a stale `queue` flag**: `ضسپا8090` has `traded = false, volume = 0, queue = "sell"`. Both `is_buy_queue` and `is_sell_queue` MUST require `traded_today == True` and a live, alert-eligible quote.

## 3. Supported Iranian Bourse Alert Types

| `condition_type` | Target Field | Optional `raw_rule` Keys | Status |
|---|---|---|---|
| `priceThreshold` | `target_price` (or `upper_target_price` / `lower_target_price` for `BOTHSIDES`) | `price_field`: `"last"` \| `"close"` | Live (v1 + dual-target) |
| `percentChange` | `percent` vs `yesterday` (`prev_close`) | `price_field`: `"last"` \| `"close"` | Verified end-to-end (Phase `21b` — server `test_percent_change_uses_yesterday_vambat` + Flutter form supports Above / Below / Both Sides) |
| `absolutePriceChange` | `delta_absolute` (Rial) vs `yesterday` (`prev_close`) | `price_field`: `"last"` \| `"close"` | Live |
| `queueBuy` | `target_price = 0` | `min_queue_volume` (optional `>= 0` shares) | Phase `21c` + `21d` |
| `queueSell` | `target_price = 0` | `min_queue_volume` (optional `>= 0` shares) | Phase `21c` + `21d` |
| `volumeAbove` | `target_price` = share volume threshold (`> 0`) | — | Phase `21e` + `21d` |

## 4. Exact Evaluation & Edge-Trigger Rules

- **Live-only guard**: `queueBuy`, `queueSell`, and `volumeAbove` NEVER fire when the market is `CLOSED`, `STALE`, `NO_TRADE_TODAY`, `alert_eligible == False`, `traded_today == False`, or required daily limits / order-book fields are missing.
- **Buy Queue (`is_buy_queue`)**:
  - `upper_limit > 0`, `best_bid.price == upper_limit`, `best_bid.volume > 0`,
  - `best_ask` is `null` OR `best_ask.price > upper_limit`,
  - `queue != "sell"`,
  - if `min_queue_volume` is set and `> 0`: `best_bid.volume >= min_queue_volume`.
- **Sell Queue (`is_sell_queue`)**:
  - `lower_limit > 0`, `best_ask.price == lower_limit`, `best_ask.volume > 0`,
  - `best_bid` is `null` OR `best_bid.price < lower_limit`,
  - `queue != "buy"`,
  - if `min_queue_volume` is set and `> 0`: `best_ask.volume >= min_queue_volume`.
- **Volume Above (`is_volume_above`)**:
  - `threshold > 0`, `volume > 0`, `volume >= threshold`.
- **Edge-triggered hysteresis**:
  - Entering the condition fires once and sets `waiting_for_cross = True`.
  - Staying in the queue / above volume on subsequent ticks does NOT fire again.
  - Leaving the queue (or volume resetting below threshold on a new trading day) clears `waiting_for_cross = False` so a `recurring` alert can fire again on the next entry.
  - A `oneShot` alert deactivates (`is_active = False`) after its first trigger, identical to all other AlertG rules.
  - **قرارداد فاز 24c (گزینه الف)**: هشدار تازه روی شرط برقرار فوراً فعال میشود. (در فرم ساخت هشدار صف نیز در صورت برقرار بودن صف، اخطار «این نماد همین الان در صف خرید/فروش است. با ثبت، فوراً اعلان می‌گیرید.» نمایش داده می‌شود.)

