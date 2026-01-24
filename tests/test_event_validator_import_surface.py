from __future__ import annotations

import builtins
import importlib
import os
import sys


def test_importing_event_validator_has_no_side_effects(monkeypatch) -> None:
    import arcade  # noqa: F401
    from engine.logging_tools import suppress_stdout

    def guarded_open(*_a, **_k):
        raise AssertionError("builtins.open should not run at import time")

    def guarded_replace(*_a, **_k):
        raise AssertionError("os.replace should not run at import time")

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(os, "replace", guarded_replace)

    module_names = [
        "engine.tooling_runtime.event_validator",
        "engine.tooling.event_validator",
    ]
    saved_modules = {name: sys.modules.get(name) for name in module_names}
    try:
        for name in module_names:
            sys.modules.pop(name, None)

        with suppress_stdout() as buf:
            importlib.import_module("engine.tooling_runtime.event_validator")
            mod = importlib.import_module("engine.tooling.event_validator")
    finally:
        for name in module_names:
            sys.modules.pop(name, None)
        for name, module in saved_modules.items():
            if module is not None:
                sys.modules[name] = module

    assert buf.getvalue() == ""
    assert hasattr(mod, "EventValidator")

