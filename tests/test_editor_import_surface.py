from __future__ import annotations

import builtins
import importlib
import os
import sys


def test_importing_editor_controller_has_no_side_effects_and_exports_surface(monkeypatch) -> None:
    import arcade  # noqa: F401
    import engine.editor_palette as editor_palette
    from engine.logging_tools import suppress_stdout

    monkeypatch.setattr(
        editor_palette,
        "load_prefab_palette",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("load_prefab_palette should not run at import time")),
    )

    def guarded_open(*_a, **_k):
        raise AssertionError("builtins.open should not run at import time")

    def guarded_replace(*_a, **_k):
        raise AssertionError("os.replace should not run at import time")

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(os, "replace", guarded_replace)

    module_names = [
        "engine.editor_runtime.state",
        "engine.editor_runtime.input",
        "engine.editor_runtime.ops",
        "engine.editor_runtime.render",
        "engine.editor_runtime",
        "engine.editor_controller",
    ]
    saved_modules = {name: sys.modules.get(name) for name in module_names}
    try:
        for name in module_names:
            sys.modules.pop(name, None)

        with suppress_stdout() as buf:
            mod = importlib.import_module("engine.editor_controller")
    finally:
        for name in module_names:
            sys.modules.pop(name, None)
        for name, module in saved_modules.items():
            if module is not None:
                sys.modules[name] = module

    assert buf.getvalue() == ""
    assert getattr(mod, "PREFAB_PALETTE") is None
    assert hasattr(mod, "EditorModeController")
    assert hasattr(mod, "TOOL_MODE_MOVE")
    assert hasattr(mod, "TOOL_MODE_PATH")
    assert hasattr(mod, "TOOL_MODE_ZONE")
