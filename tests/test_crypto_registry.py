from app.markets.crypto_registry import (
    get_crypto_adapter, list_crypto_exchanges, is_supported_crypto_exchange,
)


def test_every_active_exchange_has_adapter():
    for m in list_crypto_exchanges():
        if m.status == 'active':
            a = get_crypto_adapter(m.id)
            assert a is not None, f"{m.id} is active but no adapter"
            assert a.provider_key == m.provider_key


def test_pending_adapter_exchanges_are_not_alert_capable():
    assert is_supported_crypto_exchange('bybit') is False
    assert is_supported_crypto_exchange('bitget') is False
    assert get_crypto_adapter('bybit') is None
    assert get_crypto_adapter('bitget') is None


def test_unknown_exchange_returns_no_adapter():
    assert get_crypto_adapter('coinex') is None
    assert get_crypto_adapter('') is None