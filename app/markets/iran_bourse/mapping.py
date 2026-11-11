# -*- coding: utf-8 -*-
"""Gateway quote -> AlertG price result (Appendix C and D of the integration plan).

Pure functions, no I/O, no unit conversion: prices stay in Rial (decision D1).
Session-closed detection and `alert_eligible` belong to Phase 7, not here.
"""
from datetime import datetime
from typing import Any, Dict, Optional

# Fields the gateway quote must contain (Appendix C). Anything else is ignored (rule N13).
REQUIRED_QUOTE_FIELDS = (
    "id", "isin", "ticker", "name", "last", "close", "first", "low", "high",
    "yesterday", "last_change_pct", "close_change_pct", "trades", "volume",
    "value", "traded", "upper_limit", "lower_limit", "best_bid", "best_ask",
    "queue", "nav", "update_time", "market_code", "market", "board_code",
    "board", "type_code", "type", "sector_code", "sector", "rev",
)

PASS_THROUGH = (
    "upper_limit", "lower_limit", "queue", "nav", "market_code", "market",
    "board_code", "board", "type_code", "type", "sector_code", "sector",
)

PRICE_FIELDS = ("last", "close")
SOURCE = "tsetmc-gateway"
CURRENCY = "IRR"


class MappingError(ValueError):
    """The quote does not match the gateway contract."""


def validate_quote(quote: Any) -> None:
    if not isinstance(quote, dict):
        raise MappingError("quote is not an object")
    missing = [f for f in REQUIRED_QUOTE_FIELDS if f not in quote]
    if missing:
        raise MappingError("quote is missing fields: " + ", ".join(missing))
    # Rule N6: IDs are strings everywhere (they exceed 2**53).
    if not isinstance(quote["id"], str) or not quote["id"].isdigit():
        raise MappingError("quote id must be a digit-only string")


def meta_as_of(meta: Optional[Dict[str, Any]]) -> Optional[int]:
    """meta.updated_at (UTC ISO) -> epoch seconds of the last successful fetch."""
    raw = (meta or {}).get("updated_at")
    if not raw:
        return None
    try:
        return int(datetime.fromisoformat(str(raw)).timestamp())
    except ValueError:
        return None


def quote_to_price_result(
    quote: Dict[str, Any],
    meta: Optional[Dict[str, Any]],
    price_field: str = "last",
) -> Dict[str, Any]:
    """Map one gateway quote and its envelope meta to the AlertG result shape."""
    if price_field not in PRICE_FIELDS:
        raise MappingError("price_field must be 'last' or 'close'")
    validate_quote(quote)
    meta = meta or {}

    raw_price = quote[price_field]
    price = raw_price if isinstance(raw_price, (int, float)) and raw_price > 0 else None
    is_stale = bool(meta.get("stale"))
    traded = bool(quote["traded"])

    if is_stale:
        state = "STALE"
    elif not traded:
        state = "NO_TRADE_TODAY"
    else:
        state = "LIVE"  # Phase 7 may downgrade to CLOSED using the session rules

    result: Dict[str, Any] = {
        "price": price,
        "currency": CURRENCY,
        "asOf": meta_as_of(meta),
        "state": state,
        "source": SOURCE,
        "price_field": price_field,
        "last_trade_time": quote["update_time"],
        "prev_close": quote["yesterday"],
        "change_pct": quote["last_change_pct" if price_field == "last" else "close_change_pct"],
        "high": quote["high"],
        "low": quote["low"],
        "volume": quote["volume"],
        "ticker": quote["ticker"],
        "name": quote["name"],
        "symbol": quote["id"],
        "traded_today": traded,
        "is_stale": is_stale,
    }
    for key in PASS_THROUGH:
        result[key] = quote[key]
    return result
