from __future__ import annotations
import os
import json
import asyncio
from typing import Optional, List, Dict, Any
from app.config import DATA_DIR
from app.models import Alert
from app.state import _db_lock, _prof_lock

DB_FILE = os.path.join(DATA_DIR, "alerts_data.json") if DATA_DIR != "." else "alerts_data.json"
PROFILES_FILE = os.path.join(DATA_DIR, "user_profiles.json") if DATA_DIR != "." else "user_profiles.json"

def has_perso_arabic(s: str) -> bool:
    """Checks if a string contains valid Persian or Arabic characters."""
    return any(0x0600 <= ord(c) <= 0x06FF or 0xFB50 <= ord(c) <= 0xFEFF or ord(c) == 0x200C for c in s)

def repair_mojibake(s: Optional[str]) -> Optional[str]:
    """Repairs Mojibake corrupted Persian/Arabic strings (Ã, Ø, Ù, Â) up to 3 passes.
    Guaranteed Anti-False-Positive: Only substitutes if Persian/Arabic characters are recovered."""
    if not s or not isinstance(s, str):
        return s
    current = s
    cp1252_map = {
        0x20AC: 0x80, 0x201A: 0x82, 0x0192: 0x83, 0x201E: 0x84,
        0x2026: 0x85, 0x2020: 0x86, 0x2021: 0x87, 0x02C6: 0x88,
        0x2030: 0x89, 0x0160: 0x8A, 0x2039: 0x8B, 0x0152: 0x8C,
        0x017D: 0x8E, 0x2018: 0x91, 0x2019: 0x92, 0x201C: 0x93,
        0x201D: 0x94, 0x2022: 0x95, 0x2013: 0x96, 0x2014: 0x97,
        0x02DC: 0x98, 0x2122: 0x99, 0x0161: 0x9A, 0x203A: 0x9B,
        0x0153: 0x9C, 0x017E: 0x9E, 0x0178: 0x9F
    }
    for _ in range(3):
        mojibake_count_before = sum(1 for c in current if c in 'ÃØÙÂ')
        if mojibake_count_before == 0:
            break
        bytes_list = []
        possible = True
        for ch in current:
            code = ord(ch)
            if code <= 0xFF:
                bytes_list.append(code)
            elif code in cp1252_map:
                bytes_list.append(cp1252_map[code])
            else:
                possible = False
                break
        if not possible or not bytes_list:
            break
        try:
            decoded = bytes(bytes_list).decode('utf-8')
            mojibake_count_after = sum(1 for c in decoded if c in 'ÃØÙÂ')
            if has_perso_arabic(decoded) and mojibake_count_after < mojibake_count_before:
                current = decoded
            else:
                break
        except UnicodeDecodeError:
            break
    return current

def load_alerts_from_disk() -> List[Alert]:
    targets = [DB_FILE]
    fallback = os.path.join(DATA_DIR, "alerts.json") if DATA_DIR != "." else "alerts.json"
    if fallback not in targets:
        targets.append(fallback)

    for target in targets:
        if os.path.exists(target):
            try:
                with open(target, "r", encoding="utf-8") as f:
                    content_raw = f.read()

                # Check for Mojibake before attempting repairs
                has_mojibake = any(c in content_raw for c in 'ÃØÙÂ')
                if has_mojibake:
                    try:
                        import shutil
                        from datetime import datetime
                        # 1. Permanent initial backup (never overwritten)
                        orig_bak = f"{target}.original_corrupted.bak"
                        if not os.path.exists(orig_bak):
                            shutil.copy2(target, orig_bak)
                            print(f"📦 [Backup] Preserved original pre-repair backup: {orig_bak}")
                        # 2. Timestamped backup
                        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                        time_bak = f"{target}.backup_{ts}.bak"
                        shutil.copy2(target, time_bak)
                        print(f"📦 [Backup] Created timestamped backup: {time_bak}")
                    except Exception as be:
                        print(f"⚠️ [Backup] Warning backing up {target}: {be}")

                data = json.loads(content_raw)
                alerts = []
                repaired_count = 0
                for item in data:
                    if isinstance(item, dict):
                        item_was_repaired = False
                        # Only repair text fields that could contain Persian, NEVER base_currency or symbol
                        for k in ['counter_currency', 'note', 'upper_note', 'lower_note']:
                            if item.get(k):
                                rep = repair_mojibake(item[k])
                                if rep != item[k]:
                                    item[k] = rep
                                    item_was_repaired = True
                        if isinstance(item.get('raw_rule'), dict):
                            for rk in ['counterCurrency', 'customNote', 'upperNote', 'lowerNote']:
                                if item['raw_rule'].get(rk):
                                    rep = repair_mojibake(item['raw_rule'][rk])
                                    if rep != item['raw_rule'][rk]:
                                        item['raw_rule'][rk] = rep
                                        item_was_repaired = True
                        if item_was_repaired:
                            repaired_count += 1
                        alerts.append(Alert(**item))

                if repaired_count > 0:
                    print(f"🛠️ [Startup Repair] Successfully repaired {repaired_count} alert(s) containing Mojibake to clean UTF-8.")
                    try:
                        repaired_json = json.dumps([a.model_dump() if hasattr(a, 'model_dump') else a.dict() for a in alerts], ensure_ascii=False, indent=2)
                        tmp_target = f"{target}.tmp"
                        with open(tmp_target, "w", encoding="utf-8") as f:
                            f.write(repaired_json)
                            f.flush()
                            os.fsync(f.fileno())
                        os.replace(tmp_target, target)
                        print(f"💾 [Startup Repair] Atomically persisted {len(alerts)} clean alert(s) to {target}.")
                    except Exception as pe:
                        print(f"⚠️ [Startup Repair] Warning persisting repaired alerts: {pe}")
                else:
                    print(f"✅ [Startup Check] All {len(alerts)} alert(s) on disk are clean UTF-8 (no Mojibake repairs needed).")

                return alerts
            except Exception as e:
                print(f"⚠️ Error loading alerts disk DB: {e}")
    return []

async def save_alerts_to_disk_async(alerts: List[Alert]):
    """Atomic asynchronous disk writer to prevent file corruption during power/server events"""
    try:
        loop = asyncio.get_running_loop()
        async with _db_lock:
            data = [a.model_dump() if hasattr(a, 'model_dump') else a.dict() for a in alerts]
        json_str = json.dumps(data, ensure_ascii=False, indent=2)

        def _write():
            tmp_file = f"{DB_FILE}.tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                f.write(json_str)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, DB_FILE)

        await loop.run_in_executor(None, _write)
    except Exception as e:
        print(f"⚠️ Error saving alerts disk DB: {e}")

ALERTS_DB: List[Alert] = load_alerts_from_disk()

def load_user_profiles_from_disk() -> Dict[str, Dict[str, Any]]:
    if os.path.exists(PROFILES_FILE):
        try:
            with open(PROFILES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading user profiles disk DB: {e}")
    return {}

async def save_user_profiles_to_disk_async(profiles: Dict[str, Dict[str, Any]]):
    try:
        loop = asyncio.get_running_loop()
        async with _prof_lock:
            prof_copy = dict(profiles)
        json_str = json.dumps(prof_copy, ensure_ascii=False, indent=2)

        def _write():
            tmp_file = f"{PROFILES_FILE}.tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                f.write(json_str)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, PROFILES_FILE)

        await loop.run_in_executor(None, _write)
    except Exception as e:
        print(f"⚠️ Error saving user profiles disk DB: {e}")

USER_PROFILES_DB: Dict[str, Dict[str, Any]] = load_user_profiles_from_disk()
