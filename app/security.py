import hmac
import math
from typing import Optional, Any, Dict
from fastapi import Header, HTTPException, Depends
from app.config import (
    API_KEY, ADMIN_KEY, TELEGRAM_BOT_TOKEN,
    SYMBOL_RE, EXCHANGE_RE, CHAT_ID_RE,
    MAX_NOTE_LEN
)

import app.config as config

def _key_matches(provided: Optional[str], expected: str) -> bool:
    return bool(provided) and bool(expected) and hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))

async def require_api_key(x_api_key: Optional[str] = Header(None)):
    api_k = getattr(config, 'API_KEY', '')
    admin_k = getattr(config, 'ADMIN_KEY', '')
    if not api_k:
        raise HTTPException(status_code=503, detail="API key is not configured on the server.")
    if not (_key_matches(x_api_key, api_k) or _key_matches(x_api_key, admin_k)):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")

async def require_admin(x_admin_key: Optional[str] = Header(None)):
    import server
    admin_k = getattr(server, 'ADMIN_KEY', getattr(config, 'ADMIN_KEY', ''))
    if not admin_k:
        raise HTTPException(status_code=503, detail="Admin key is not configured on the server.")
    if not _key_matches(x_admin_key, admin_k):
        raise HTTPException(status_code=401, detail="Invalid or missing admin key.")

API_DEP = [Depends(require_api_key)]
ADMIN_DEP = [Depends(require_admin)]

def _scrub(value: Any) -> str:
    text = str(value)
    return text.replace(TELEGRAM_BOT_TOKEN, "***") if TELEGRAM_BOT_TOKEN else text

def _clamp_interval(value: Any) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = 180
    return max(180, min(86400, v))

def _validate_market_args(exchange: str, symbol: str) -> None:
    if not EXCHANGE_RE.match((exchange or '').lower()) or not SYMBOL_RE.match(symbol or ''):
        raise HTTPException(status_code=400, detail="Invalid exchange or symbol.")

def _normalize_sync_item(item: Any) -> Dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("alert item must be an object")
    out = dict(item)
    out['exchange'] = str(item.get('exchange') or 'nobitex').strip().lower()
    out['symbol'] = str(item.get('symbol') or 'USDTIRT').strip().upper()
    if not EXCHANGE_RE.match(out['exchange']) or not SYMBOL_RE.match(out['symbol']):
        raise ValueError("invalid exchange or symbol")
    tp = float(item.get('target_price', 0.0))
    if not math.isfinite(tp):
        raise ValueError("invalid target_price")
    out['target_price'] = tp
    out['condition'] = str(item.get('condition') or 'ABOVE').strip().upper()
    out['condition_type'] = str(item.get('condition_type') or 'priceThreshold').strip()
    out['direction'] = str(item.get('direction') or ('below' if out['condition'] == 'BELOW' else 'above')).strip()
    out['both_way_behavior'] = str(item.get('both_way_behavior') or 'oco').strip()
    
    for float_k in ('percent', 'upper_target_price', 'lower_target_price', 'delta_absolute', 'volume_percent', 'base_price', 'base_volume', 'last_macro_value'):
        v = item.get(float_k)
        if v is not None:
            try:
                fv = float(v)
                if math.isfinite(fv):
                    out[float_k] = fv
            except (ValueError, TypeError):
                out[float_k] = None
        else:
            out[float_k] = None

    for note_k in ('upper_note', 'lower_note'):
        nv = item.get(note_k)
        out[note_k] = str(nv)[:MAX_NOTE_LEN] if nv is not None else None

    out['check_interval_seconds'] = _clamp_interval(item.get('check_interval_seconds', 180))
    note = item.get('note')
    out['note'] = str(note)[:MAX_NOTE_LEN] if note is not None else None
    
    for k in ('id', 'created_at', 'sound', 'trigger_mode', 'alert_nature', 'base_currency', 'counter_currency', 'market_symbol', 'language', 'last_macro_release_date'):
        if item.get(k) is not None:
            out[k] = str(item[k])[:128]

    out['sound_enabled'] = bool(item.get('sound_enabled', True))
    out['vibration_enabled'] = bool(item.get('vibration_enabled', True))
    out['tts_enabled'] = bool(item.get('tts_enabled', True))
    out['prefer_server_proxy'] = bool(item.get('prefer_server_proxy', False))
    out['is_active'] = bool(item.get('is_active', True))
    
    if isinstance(item.get('raw_rule'), dict):
        out['raw_rule'] = item['raw_rule']

    chat = item.get('telegram_chat_id')
    if chat is not None and str(chat).strip():
        chat = str(chat).strip()
        if not CHAT_ID_RE.match(chat):
            raise ValueError("invalid telegram_chat_id")
        out['telegram_chat_id'] = chat
    else:
        out['telegram_chat_id'] = None
    return out
