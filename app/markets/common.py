def normalize_symbol(symbol: str) -> str:
    return (symbol or '').upper().replace('/', '').replace(' ', '').replace('-', '').replace('_', '')
