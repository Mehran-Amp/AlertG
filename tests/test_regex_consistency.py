"""Phase REGEX-1: config.SYMBOL_RE / EXCHANGE_RE must accept every active
symbol and exchange in catalog.json, and must reject dangerous input.

Manager-mandated test matrix:
  1. All active symbols + exchanges pass.
  2. Dangerous inputs are rejected: <script>, '; DROP, 33-char string, "..", "\n".
  3. "S&P 500" and "Deutsche Börse" are accepted.
"""
import json


class TestCatalogAccepts:
    """REGEX-1 / test 1: every active catalog entry passes the new regexes."""

    def test_all_active_symbols_pass(self):
        from app.config import SYMBOL_RE
        with open("catalog.json", "r", encoding="utf-8") as f:
            cat = json.load(f)
        bad = [
            s.get("symbol")
            for s in cat.get("symbols", [])
            if s.get("is_active", 1) and not SYMBOL_RE.match(s.get("symbol", ""))
        ]
        assert bad == [], f"SYMBOL_RE rejects active catalog symbols: {bad[:10]}"

    def test_all_active_exchanges_pass(self):
        from app.config import EXCHANGE_RE
        with open("catalog.json", "r", encoding="utf-8") as f:
            cat = json.load(f)
        bad = [
            (s.get("symbol"), s.get("marketName"))
            for s in cat.get("symbols", [])
            if s.get("is_active", 1)
            and not EXCHANGE_RE.match(s.get("marketName", ""))
        ]
        assert bad == [], f"EXCHANGE_RE rejects active catalog exchanges: {bad[:10]}"


class TestDangerousInputRejected:
    """REGEX-1 / test 2: dangerous inputs must be rejected (manager requirement)."""

    def test_symbol_rejects_dangerous(self):
        from app.config import SYMBOL_RE
        dangerous = [
            "<script>",
            "'; DROP",
            "A" * 33,           # 33 chars > max 32
            "..",               # manager requirement: reject
            "A\nB",             # \n must be rejected (no \s)
            " A",               # leading space
            "A ",               # trailing space
        ]
        for s in dangerous:
            assert not SYMBOL_RE.match(s), f"SYMBOL_RE should reject {s!r}"

    def test_exchange_rejects_dangerous(self):
        from app.config import EXCHANGE_RE
        dangerous = [
            "<script>",
            "'; DROP",
            "A" * 41,           # 41 chars > max 40
            "..",               # manager requirement: reject
            "\n",               # \n rejected
            " A",               # leading space
            "A ",               # trailing space
            "A",                # 1-char exchange rejected (min 2)
        ]
        for s in dangerous:
            assert not EXCHANGE_RE.match(s), f"EXCHANGE_RE should reject {s!r}"


class TestManagerExamples:
    """REGEX-1 / test 3: the two specific examples from the manager must pass."""

    def test_sp500_and_deutsche_boerse_accepted(self):
        from app.config import SYMBOL_RE, EXCHANGE_RE
        assert SYMBOL_RE.match("S&P 500")
        assert EXCHANGE_RE.match("Deutsche Börse")

class TestSyncUsesConfigRegex:
    """REGEX-2: sync.py must not redefine SYMBOL_RE/EXCHANGE_RE locally."""

    def test_sync_uses_config_regex(self):
        import app.config as config
        import app.engine.sync as sync_module
        assert sync_module.SYMBOL_RE is config.SYMBOL_RE
        assert sync_module.EXCHANGE_RE is config.EXCHANGE_RE        