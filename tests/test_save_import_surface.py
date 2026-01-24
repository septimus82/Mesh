from __future__ import annotations

import builtins
import importlib
import os
import sys


def test_importing_save_modules_has_no_side_effects_and_exports_surface(monkeypatch) -> None:
    import arcade  # noqa: F401
    from engine.logging_tools import suppress_stdout

    def guarded_open(*_a, **_k):
        raise AssertionError("builtins.open should not run at import time")

    def guarded_replace(*_a, **_k):
        raise AssertionError("os.replace should not run at import time")

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(os, "replace", guarded_replace)

    module_names = [
        "engine.save_runtime.constants",
        "engine.save_runtime.errors",
        "engine.save_runtime.io",
        "engine.save_runtime.payloads",
        "engine.save_runtime",
        "engine.savegame",
        "engine.save_manager",
    ]
    saved_modules = {name: sys.modules.get(name) for name in module_names}
    try:
        for name in module_names:
            sys.modules.pop(name, None)

        with suppress_stdout() as buf:
            savegame = importlib.import_module("engine.savegame")
            savemgr = importlib.import_module("engine.save_manager")
            save_rt = importlib.import_module("engine.save_runtime")
    finally:
        for name in module_names:
            sys.modules.pop(name, None)
        for name, module in saved_modules.items():
            if module is not None:
                sys.modules[name] = module

    assert buf.getvalue() == ""
    assert hasattr(savegame, "save_quick_snapshot")
    assert hasattr(savemgr, "SaveManager")
    assert hasattr(save_rt, "payloads")

