from __future__ import annotations

import importlib
import sys

import pytest


def test_assets_reload_is_import_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    # Import engine.assets_reload as if for the first time, then put every module back. Popping them for
    # good left later tests patching a module object nothing used any more: six tests (the widget-overlay
    # and battle-sprite "baseline failures") failed whenever this ran before them.
    for name in ("engine.assets_reload", "engine.optional_arcade", "arcade"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    importlib.import_module("engine.assets_reload")
    assert "arcade" not in sys.modules
