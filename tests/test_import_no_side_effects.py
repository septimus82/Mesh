from __future__ import annotations

import importlib
import sys


def test_importing_editor_controller_does_not_load_prefab_palette(monkeypatch):
    import engine.editor_palette as editor_palette

    monkeypatch.setattr(
        editor_palette,
        "load_prefab_palette",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("load_prefab_palette should not run at import time")),
    )

    sys.modules.pop("engine.editor_controller_core", None)
    sys.modules.pop("engine.editor_controller", None)
    mod = importlib.import_module("engine.editor_controller")
    assert getattr(mod, "PREFAB_PALETTE") is None


def test_importing_encounter_sets_does_not_instantiate_theme_manager():
    sys.modules.pop("engine.encounter_sets", None)
    mod = importlib.import_module("engine.encounter_sets")
    assert getattr(mod, "_THEME_MANAGER") is None
