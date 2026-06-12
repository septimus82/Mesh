from __future__ import annotations

import builtins
import importlib
import os
import sys


def test_importing_console_controller_does_not_touch_disk_or_print(monkeypatch) -> None:
    import arcade  # noqa: F401

    from engine.logging_tools import suppress_stdout

    def guarded_open(*_a, **_k):
        raise AssertionError("builtins.open should not run at import time")

    def guarded_replace(*_a, **_k):
        raise AssertionError("os.replace should not run at import time")

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(os, "replace", guarded_replace)

    module_names = [
        "engine.console_runtime.history",
        "engine.console_runtime.errors",
        "engine.console_runtime.render",
        "engine.console_runtime.commands",
        "engine.console_runtime",
        "engine.console_controller",
    ]
    saved_modules = {name: sys.modules.get(name) for name in module_names}
    try:
        for name in module_names:
            sys.modules.pop(name, None)

        with suppress_stdout() as buf:
            for name in module_names:
                importlib.import_module(name)
    finally:
        for name in module_names:
            sys.modules.pop(name, None)
        for name, module in saved_modules.items():
            if module is not None:
                sys.modules[name] = module

    assert buf.getvalue() == ""
