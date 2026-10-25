"""Phase 3 audit follow-up: checker.py must import Tuple (used in a local
type annotation inside check_macro_alerts_job). This test locks the import
so a future refactor cannot silently drop it.
"""
import inspect
import re
import pytest


class TestCheckerImports:
    """Audit / test 1: Tuple must be imported from typing in checker.py."""

    def test_tuple_is_imported_from_typing(self):
        import app.engine.checker as checker
        src = inspect.getsource(checker)
        m = re.search(r'from typing import ([^\n]+)', src)
        assert m, "app/engine/checker.py must have a `from typing import ...` line"
        imported_names = [n.strip() for n in m.group(1).split(",")]
        assert "Tuple" in imported_names, (
            f"app/engine/checker.py is missing Tuple in its typing import. "
            f"Found: {imported_names!r}"
        )


class TestMacroJobCallable:
    """Audit / test 2: check_macro_alerts_job must be async and importable."""

    def test_check_macro_alerts_job_is_async(self):
        from app.engine.checker import check_macro_alerts_job
        assert inspect.iscoroutinefunction(check_macro_alerts_job)

    def test_check_macro_alerts_job_annotations_resolve(self):
        """Ensure the function's own annotations do not reference unimported names."""
        from app.engine.checker import check_macro_alerts_job
        from typing import get_type_hints
        try:
            hints = get_type_hints(check_macro_alerts_job)
        except NameError as e:
            pytest.fail(
                f"check_macro_alerts_job annotations reference an unimported name: {e}"
            )
        assert isinstance(hints, dict)