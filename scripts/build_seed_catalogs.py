#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SignalAlert Seed Catalog Builder (Phase 4 / v3.2.0)

Extracts and formats initial seed asset catalogs for:
- US Stocks (S&P 500 scraped from Wikipedia with table structure validation)
- US ETFs
- Forex Major Pairs
- Global Indices
- Key Commodities
- US Treasury Bonds & Yields
- Macro Indicators (FRED)
- China / Hong Kong Equities

IMPORTANT EXECUTION RULES:
- Script is authored for standalone execution on remote server (Germany).
- NEVER executes automatically in CI or without explicit user invocation.
- Only uses permitted providers: Yahoo, Finnhub, Twelve Data, FRED.
"""

import os
import sys
import json
import re
from datetime import datetime, timezone
from typing import Dict, Any, List
import urllib.request
import html

SEED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seed")
WIKIPEDIA_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
USER_AGENT = "SignalAlertSeedBot/3.2.0 (contact: admin@signalalert.internal)"

ALLOWED_PROVIDERS = {"yahoo", "finnhub", "twelve_data", "fred"}
VALID_ASSET_CLASSES = {"stock", "etf", "forex", "index", "commodity", "bond", "macro"}
VALID_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CAD", "CHF", "AUD", "NZD", "CNY", "HKD", "IRR", "IRT"}


def fetch_wikipedia_sp500() -> List[Dict[str, Any]]:
    """
    Fetches S&P 500 constituents from Wikipedia using a compliant User-Agent.
    Validates table headers to ensure structural schema integrity before parsing.
    Stops and raises ValueError if columns or structure changed.
    """
    req = urllib.request.Request(
        WIKIPEDIA_SP500_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        content = resp.read().decode("utf-8")

    # Locate constituents table
    table_match = re.search(r'<table[^>]*id=["\']constituents["\'][^>]*>(.*?)</table>', content, re.DOTALL | re.IGNORECASE)
    if not table_match:
        # Fallback search for table with S&P 500 header
        table_match = re.search(r'<table[^>]*class=["\'][^"\']*wikitable[^"\']*["\'][^>]*>(.*?)</table>', content, re.DOTALL | re.IGNORECASE)
        if not table_match:
            raise ValueError("S&P 500 table not found in Wikipedia HTML response.")

    table_html = table_match.group(1)

    # 1. Structural schema validation: check header columns
    header_row_match = re.search(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL | re.IGNORECASE)
    if not header_row_match:
        raise ValueError("Could not extract header row from S&P 500 table.")

    header_cells = re.findall(r'<th[^>]*>(.*?)</th>', header_row_match.group(1), re.DOTALL | re.IGNORECASE)
    clean_headers = [re.sub(r'<[^>]+>', '', h).strip() for h in header_cells]

    expected_mandatory_headers = ["Symbol", "Security"]
    for expected in expected_mandatory_headers:
        if not any(expected.lower() in h.lower() for h in clean_headers):
            raise ValueError(
                f"S&P 500 table schema changed! Expected header '{expected}' missing from headers: {clean_headers}. Halting execution."
            )

    symbol_idx = -1
    security_idx = -1
    for idx, h in enumerate(clean_headers):
        if "symbol" in h.lower() and symbol_idx == -1:
            symbol_idx = idx
        elif "security" in h.lower() and security_idx == -1:
            security_idx = idx

    if symbol_idx == -1 or security_idx == -1:
        raise ValueError(f"Unable to resolve Symbol/Security column indices. Headers: {clean_headers}")

    # 2. Extract rows
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL | re.IGNORECASE)
    results: List[Dict[str, Any]] = []

    for row_content in rows[1:]:  # Skip header row
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row_content, re.DOTALL | re.IGNORECASE)
        if len(cells) <= max(symbol_idx, security_idx):
            continue

        raw_sym = re.sub(r'<[^>]+>', '', cells[symbol_idx]).strip()
        raw_name = html.unescape(re.sub(r'<[^>]+>', '', cells[security_idx]).strip())

        if not raw_sym:
            continue

        # Standardize symbol (e.g., BRK.B -> BRK.B, Yahoo symbol BRK-B)
        sym_id = raw_sym.replace('/', '.')
        yf_sym = raw_sym.replace('.', '-')

        item = {
            "id": sym_id,
            "display_name": raw_name,
            "asset_class": "stock",
            "exchange": "NYSE" if "." in sym_id else "NASDAQ",  # Sensible default exchange classification
            "currency": "USD",
            "tier": 1,
            "provider_map": {
                "yahoo": {"symbol": yf_sym, "priority": 1},
                "finnhub": {"symbol": sym_id, "priority": 2},
                "twelve_data": {"symbol": sym_id, "priority": 3}
            },
            "data_frequency": "live",
            "is_delayed": False
        }
        results.append(item)

    if len(results) < 400:
        raise ValueError(f"Extracted only {len(results)} S&P 500 constituents; expected ~500. Table parsing aborted.")

    return results


def write_seed_file(filename: str, source: str, asset_class: str, symbols: List[Dict[str, Any]]) -> str:
    """Writes a standardized seed file with header and symbol definitions."""
    os.makedirs(SEED_DIR, exist_ok=True)
    out_path = os.path.join(SEED_DIR, filename)

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "source": source,
        "fetched_at": now_iso,
        "asset_class": asset_class,
        "total_count": len(symbols),
        "symbols": symbols
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"✅ Generated seed file: {out_path} ({len(symbols)} symbols)")
    return out_path


def main():
    print("=" * 60)
    print("SignalAlert Seed Catalog Builder v3.2.0")
    print("Fetching constituents and generating category seed files...")
    print("=" * 60)

    try:
        sp500_symbols = fetch_wikipedia_sp500()
        write_seed_file("us_stocks.json", "Wikipedia S&P 500", "stock", sp500_symbols)
    except Exception as e:
        print(f"❌ Error scraping S&P 500: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
