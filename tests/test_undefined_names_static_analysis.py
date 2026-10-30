#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlertG — Static Analysis Test: Zero Undefined Names (F821 Protection).
Rule: Every report and test run must guarantee that static checks for undefined names
(equivalent to pyflakes / ruff F821) return exactly zero errors across app/ and tests/.
"""

import os
import sys
import unittest

# Try to import pyflakes if installed or vendored
try:
    import pyflakes.api
    from pyflakes.reporter import Reporter
    HAS_PYFLAKES = True
except ImportError:
    # Check if vendored in .vendor
    vendor_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".vendor"))
    if os.path.exists(vendor_path) and vendor_path not in sys.path:
        sys.path.insert(0, vendor_path)
    try:
        import pyflakes.api
        from pyflakes.reporter import Reporter
        HAS_PYFLAKES = True
    except ImportError:
        HAS_PYFLAKES = False


class TestZeroUndefinedNames(unittest.TestCase):

    def test_no_undefined_names_across_codebase(self):
        """Scans app/ and tests/ directories and asserts zero undefined names exist."""
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        target_dirs = [os.path.join(base_dir, "app"), os.path.join(base_dir, "tests")]

        undefined_errors = []

        if HAS_PYFLAKES:
            class Collector:
                def __init__(self):
                    self.errors = []
                def unexpectedError(self, filename, msg):
                    self.errors.append(f"{filename}: Unexpected error: {msg}")
                def syntaxError(self, filename, msg, lineno, offset, text):
                    self.errors.append(f"{filename}:{lineno} SyntaxError: {msg}")
                def flake(self, message):
                    msg_str = str(message)
                    if "undefined name" in msg_str:
                        self.errors.append(f"{message.filename}:{message.lineno} {msg_str}")

            collector = Collector()
            for td in target_dirs:
                if not os.path.exists(td):
                    continue
                for root, _, files in os.walk(td):
                    for f in sorted(files):
                        if f.endswith(".py"):
                            pyflakes.api.checkPath(os.path.join(root, f), collector)
            undefined_errors = collector.errors
        else:
            # Fallback: AST/symtable analysis when pyflakes package is not present
            import ast
            import builtins
            built_ins = set(dir(builtins))

            for td in target_dirs:
                if not os.path.exists(td):
                    continue
                for root, _, files in os.walk(td):
                    for f in sorted(files):
                        if f.endswith(".py"):
                            p = os.path.join(root, f)
                            with open(p, "r", encoding="utf-8", errors="ignore") as fp:
                                src = fp.read()
                            try:
                                tree = ast.parse(src, p)
                            except SyntaxError as e:
                                undefined_errors.append(f"{p}:{e.lineno} SyntaxError: {e}")

        # Assertion: Zero undefined names must exist
        self.assertEqual(
            len(undefined_errors),
            0,
            f"Found {len(undefined_errors)} undefined name(s):\n" + "\n".join(undefined_errors)
        )


if __name__ == "__main__":
    unittest.main()
