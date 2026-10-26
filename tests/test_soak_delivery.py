"""Phase 5A-2: soak_delivery.py must be importable and parse args."""
import importlib.util
from pathlib import Path


def test_soak_script_importable():
    spec = importlib.util.spec_from_file_location(
        "soak_delivery",
        Path(__file__).resolve().parent.parent / "scripts" / "soak_delivery.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # _parse_args should return defaults when called with an empty list
    import sys
    old = sys.argv
    sys.argv = ["soak_delivery.py"]
    try:
        args = mod._parse_args()
        assert args.alerts == 200
        assert args.duration == 600
        assert args.live is False
    finally:
        sys.argv = old