# -*- coding: utf-8 -*-
"""
AlertG — Exact Price Formatter (Phase 5 / Hard Rule R3).
Ensures all prices are formatted exactly without rounding artifacts,
scientific notation, or truncation to '$0' for micro-priced coins.
"""
from decimal import Decimal
from typing import Union, Optional


def format_exact_decimal(val: Union[float, int, str, Decimal, None]) -> str:
    """
    Takes any numeric representation and converts it into a plain fixed-point decimal string.
    - Strips scientific notation (e.g. 1e-08 -> '0.00000001').
    - Keeps all significant digits for values < 1.
    - Strips only trailing zeros after the decimal point.
    - Never rounds to 4 decimals, never outputs '$0' or scientific notation.
    """
    if val is None:
        return ""
    try:
        if isinstance(val, float):
            d_str = repr(val)
        else:
            d_str = str(val).strip()

        d = Decimal(d_str)
        fixed = f"{d:f}"
        if "." in fixed:
            fixed = fixed.rstrip("0").rstrip(".")
        return fixed if fixed else "0"
    except Exception:
        return str(val)


def format_display_price(
    val: Optional[Union[float, int, Decimal]],
    currency_prefix: str = "$",
    is_tmn: bool = False,
    tmn_label: str = "تومان",
) -> str:
    """
    Standard presentation formatter for AlertG:
    - Value >= 1.0: standard thousands-separated with 2 decimals (e.g. $67,000.50, $1.23)
    - 0.0 < Value < 1.0: exact decimal representation with prefix (e.g. $0.5678, $0.00000085)
    - Value == 0.0: '$0'
    - None: '-'
    - is_tmn: integer tomans with Persian or English label
    """
    if val is None:
        return "-"
    try:
        fval = float(val)
    except (ValueError, TypeError):
        return str(val)

    if is_tmn:
        return f"{int(fval):,} {tmn_label}"

    if fval == 0.0:
        return f"{currency_prefix}0"
    elif fval >= 1.0:
        return f"{currency_prefix}{fval:,.2f}"
    else:
        dec_str = format_exact_decimal(fval)
        return f"{currency_prefix}{dec_str}"
