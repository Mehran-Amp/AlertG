from typing import Optional, Dict, Any
from pydantic import BaseModel

class AlertCreate(BaseModel):
    id: Optional[str] = None
    user_id: str
    exchange: str            # e.g. 'nobitex', 'wallex', 'tabdeal', 'binance', 'stocks'
    symbol: str              # e.g. 'BTCUSDT', 'USDTIRT', 'GOLD', 'DX-Y.NYB'
    target_price: float = 0.0
    condition: str = "ABOVE"  # 'ABOVE' or 'BELOW' or 'BOTHSIDES'
    condition_type: Optional[str] = "priceThreshold" # 'priceThreshold' | 'percentChange' | 'absolutePriceChange' | 'volumeChange'
    direction: Optional[str] = "above" # 'above' | 'below' | 'bothSides'
    both_way_behavior: Optional[str] = "oco" # 'oco' | 'dualActive'
    percent: Optional[float] = None
    upper_target_price: Optional[float] = None
    upper_note: Optional[str] = None
    lower_target_price: Optional[float] = None
    lower_note: Optional[str] = None
    delta_absolute: Optional[float] = None
    volume_percent: Optional[float] = None
    base_price: Optional[float] = None
    base_volume: Optional[float] = None
    base_currency: Optional[str] = None
    counter_currency: Optional[str] = None
    market_symbol: Optional[str] = None
    language: Optional[str] = "fa"
    prefer_server_proxy: bool = False
    raw_rule: Optional[Dict[str, Any]] = None
    fcm_token: str = ""
    check_interval_seconds: int = 180
    note: Optional[str] = None
    trigger_mode: Optional[str] = "oneShot" # 'oneShot' | 'recurring'
    alert_nature: Optional[str] = "price"    # 'price' | 'timer' | 'macro'
    sound_enabled: bool = True
    vibration_enabled: bool = True
    tts_enabled: bool = True
    sound: Optional[str] = "alarm_siren"
    telegram_chat_id: Optional[str] = None
    webhook_url: Optional[str] = None

class Alert(AlertCreate):
    id: str
    is_active: bool = True
    created_at: str
    last_checked_at: float = 0.0
    last_triggered_at: float = 0.0
    last_eval_asof: Optional[int] = None
    last_eval_price: Optional[float] = None
    waiting_for_cross: bool = False
    last_macro_release_date: Optional[str] = None
    last_macro_value: Optional[float] = None

class AlertPublic(BaseModel):
    # Same as Alert but WITHOUT fcm_token (never returned to API clients)
    id: str
    user_id: str
    exchange: str
    symbol: str
    target_price: float = 0.0
    condition: str = "ABOVE"
    condition_type: Optional[str] = "priceThreshold"
    direction: Optional[str] = "above"
    both_way_behavior: Optional[str] = "oco"
    percent: Optional[float] = None
    upper_target_price: Optional[float] = None
    upper_note: Optional[str] = None
    lower_target_price: Optional[float] = None
    lower_note: Optional[str] = None
    delta_absolute: Optional[float] = None
    volume_percent: Optional[float] = None
    base_price: Optional[float] = None
    base_volume: Optional[float] = None
    base_currency: Optional[str] = None
    counter_currency: Optional[str] = None
    market_symbol: Optional[str] = None
    language: Optional[str] = "fa"
    prefer_server_proxy: bool = False
    raw_rule: Optional[Dict[str, Any]] = None
    check_interval_seconds: int = 180
    note: Optional[str] = None
    trigger_mode: Optional[str] = "oneShot"
    alert_nature: Optional[str] = "price"
    sound_enabled: bool = True
    vibration_enabled: bool = True
    tts_enabled: bool = True
    sound: Optional[str] = "alarm_siren"
    telegram_chat_id: Optional[str] = None
    webhook_url: Optional[str] = None
    is_active: bool = True
    created_at: str
    last_checked_at: float = 0.0
    last_triggered_at: float = 0.0
    last_eval_asof: Optional[int] = None
    last_eval_price: Optional[float] = None
    waiting_for_cross: bool = False
    last_macro_release_date: Optional[str] = None
    last_macro_value: Optional[float] = None

class UserTelegramUpdateRequest(BaseModel):
    chat_id: Optional[str] = None
    is_connected: bool = True

class TelegramTestRequest(BaseModel):
    chat_id: str
