#!/usr/bin/env python3
"""
Compare a baseline snapshot against snapshots/golden_phase0.json and report differences.

    python3 scripts/compare_golden.py                       # newest snapshots/baseline_*.json vs golden
    python3 scripts/compare_golden.py --candidate snapshots/baseline_phase3_<UTC>.json
    python3 scripts/compare_golden.py --verify-manifest docs/MD5_MANIFEST.txt

Severity:
  BREAKING (exit code 1): a golden symbol/price sample/market disappeared, a symbol's category changed,
                          a price sample lost response keys, changed normalization/cache key, or status != ok.
  INFO     (exit code 0): added symbols, renamed labels, count/category totals, state/price value changes.
Exit code 2 = bad input (missing or unreadable files).
"""
import argparse
import glob
import json
import os
import sys
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

DEFAULT_GOLDEN = os.path.join("snapshots", "golden_phase0.json")
BREAKING_SYMBOL_FIELDS = ("category",)
INFO_SYMBOL_FIELDS = ("symbol", "nameEn", "nameFa", "marketName", "unit")


def compare(golden: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, List[str]]:
    breaking: List[str] = []
    info: List[str] = []
    g_ep = golden.get("endpoints", {})
    c_ep = candidate.get("endpoints", {})

    # ---- symbols
    g_sym = g_ep.get("api_symbols_wallstreet_macro", {})
    c_sym = c_ep.get("api_symbols_wallstreet_macro")
    if c_sym is None:
        breaking.append("symbols: endpoint section missing in candidate")
    else:
        g_items = {s["id"]: s for s in g_sym.get("symbols", []) if "id" in s}
        c_items = {s["id"]: s for s in c_sym.get("symbols", []) if "id" in s}
        for sid in sorted(set(g_items) - set(c_items)):
            breaking.append(f"symbols: REMOVED {sid} ({g_items[sid].get('symbol')})")
        for sid in sorted(set(c_items) - set(g_items)):
            info.append(f"symbols: added {sid} ({c_items[sid].get('symbol')})")
        for sid in sorted(set(g_items) & set(c_items)):
            for field in BREAKING_SYMBOL_FIELDS:
                if g_items[sid].get(field) != c_items[sid].get(field):
                    breaking.append(f"symbols: {sid}.{field} {g_items[sid].get(field)!r} -> {c_items[sid].get(field)!r}")
            for field in INFO_SYMBOL_FIELDS:
                if g_items[sid].get(field) != c_items[sid].get(field):
                    info.append(f"symbols: {sid}.{field} {g_items[sid].get(field)!r} -> {c_items[sid].get(field)!r}")
        if g_sym.get("total_count") != c_sym.get("total_count"):
            info.append(f"symbols: total_count {g_sym.get('total_count')} -> {c_sym.get('total_count')}")
        g_cat, c_cat = g_sym.get("categories", {}), c_sym.get("categories", {})
        for cat in sorted(set(g_cat) | set(c_cat)):
            if g_cat.get(cat) != c_cat.get(cat):
                info.append(f"symbols: categories[{cat}] {g_cat.get(cat)} -> {c_cat.get(cat)}")

    # ---- markets status
    g_mk = g_ep.get("api_markets_status", {})
    c_mk = c_ep.get("api_markets_status")
    if c_mk is None:
        breaking.append("markets: endpoint section missing in candidate")
    else:
        g_m, c_m = g_mk.get("markets", {}), c_mk.get("markets", {})
        for name in sorted(set(g_m) - set(c_m)):
            breaking.append(f"markets: REMOVED market '{name}'")
        for name in sorted(set(c_m) - set(g_m)):
            info.append(f"markets: added market '{name}'")
        for name in sorted(set(g_m) & set(c_m)):
            if g_m[name].get("status") != c_m[name].get("status"):
                info.append(f"markets: {name}.status {g_m[name].get('status')!r} -> {c_m[name].get('status')!r} (time dependent)")
        if c_mk.get("status") != g_mk.get("status"):
            breaking.append(f"markets: status {g_mk.get('status')!r} -> {c_mk.get('status')!r}")

    # ---- price samples
    g_ps = g_ep.get("price_samples", {})
    c_ps = c_ep.get("price_samples", {})
    for key in sorted(g_ps):
        if key not in c_ps:
            breaking.append(f"price: sample {key} missing in candidate")
            continue
        g, c = g_ps[key], c_ps[key]
        for field in ("normalized_symbol", "cache_key"):
            if g.get(field) != c.get(field):
                breaking.append(f"price: {key}.{field} {g.get(field)!r} -> {c.get(field)!r}")
        g_resp = g.get("response_template") or {}
        c_resp = c.get("response_template")
        if c_resp is None:
            breaking.append(f"price: {key} no JSON response (http {c.get('http_status')})")
            continue
        http_code = c.get("http_status")  # absent in golden_phase0.json (captured before this field existed)
        if (http_code is not None and http_code != 200) or "status" not in c_resp:
            detail = c_resp.get("detail") if isinstance(c_resp, dict) else None
            breaking.append(f"price: {key} HTTP {http_code} {detail or ''}".rstrip())
            continue
        lost = sorted(set(g_resp) - set(c_resp))
        if lost:
            breaking.append(f"price: {key} response lost keys {lost}")
        gained = sorted(set(c_resp) - set(g_resp))
        if gained:
            info.append(f"price: {key} response gained keys {gained}")
        if g_resp.get("status") == "ok" and c_resp.get("status") != "ok":
            breaking.append(f"price: {key} status {c_resp.get('status')!r} (golden 'ok')")
        if g_resp.get("price") is None and c_resp.get("price") is not None:
            info.append(f"price: {key} now returns a price ({c_resp.get('price')})")
    for key in sorted(set(c_ps) - set(g_ps)):
        info.append(f"price: new sample {key}")

    return {"breaking": breaking, "info": info}


def _load(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _newest_baseline(root: str = ROOT) -> Optional[str]:
    files = sorted(glob.glob(os.path.join(root, "snapshots", "baseline_*.json")))
    return files[-1] if files else None


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Diff a baseline snapshot against the golden snapshot.")
    ap.add_argument("--golden", default=os.path.join(ROOT, DEFAULT_GOLDEN))
    ap.add_argument("--candidate", help="Baseline snapshot (default: newest snapshots/baseline_*.json).")
    ap.add_argument("--verify-manifest", metavar="MANIFEST", help="Also verify MD5 of main files against this manifest.")
    ap.add_argument("--json", action="store_true", help="Print the report as JSON.")
    args = ap.parse_args(argv)

    candidate_path = args.candidate or _newest_baseline()
    if not candidate_path:
        print("No candidate snapshot given and none found in snapshots/baseline_*.json", file=sys.stderr)
        return 2
    try:
        golden, candidate = _load(args.golden), _load(candidate_path)
    except (OSError, ValueError) as e:
        print(f"Cannot read snapshot: {e}", file=sys.stderr)
        return 2

    report = compare(golden, candidate)
    manifest_problems: List[str] = []
    if args.verify_manifest:
        import make_baseline
        try:
            manifest_problems = make_baseline.verify_manifest(ROOT, args.verify_manifest)
        except OSError as e:
            print(f"Cannot read manifest: {e}", file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps({**report, "manifest": manifest_problems}, ensure_ascii=False, indent=2))
    else:
        print(f"golden:    {args.golden}")
        print(f"candidate: {candidate_path}")
        for label, lines in (("BREAKING", report["breaking"]), ("INFO", report["info"]), ("MANIFEST", manifest_problems)):
            print(f"\n== {label} ({len(lines)})")
            for line in lines:
                print(f"  - {line}")
        print("\nRESULT:", "FAIL" if report["breaking"] or manifest_problems else "OK")
    return 1 if (report["breaking"] or manifest_problems) else 0


if __name__ == "__main__":
    sys.exit(main())
