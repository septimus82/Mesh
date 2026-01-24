from __future__ import annotations

import importlib
import sys


def test_assets_reload_is_import_safe() -> None:
    sys.modules.pop("engine.assets_reload", None)
    sys.modules.pop("engine.optional_arcade", None)
    sys.modules.pop("arcade", None)
    importlib.import_module("engine.assets_reload")
    assert "arcade" not in sys.modules
