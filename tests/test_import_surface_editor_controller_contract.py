from __future__ import annotations

import importlib

import pytest

pytestmark = [pytest.mark.fast]


def test_editor_controller_old_path_resolves_to_core_impl() -> None:
    old_mod = importlib.import_module("engine.editor_controller")
    core_mod = importlib.import_module("engine.editor_controller_core")
    assert old_mod is core_mod


def test_editor_controller_key_symbols_preserve_identity() -> None:
    old_mod = importlib.import_module("engine.editor_controller")
    core_mod = importlib.import_module("engine.editor_controller_core")
    for name in (
        "EditorModeController",
        "load_prefab_palette",
        "get_prefab_palette",
        "TOOL_MODE_MOVE",
        "TOOL_MODE_PATH",
        "TOOL_MODE_ZONE",
    ):
        old_sym = getattr(old_mod, name, None)
        core_sym = getattr(core_mod, name, None)
        assert old_sym is not None, f"old path missing {name}"
        assert core_sym is not None, f"core path missing {name}"
        assert old_sym is core_sym, f"symbol identity changed for {name}"


def test_editor_controller_bootstrap_module_exports_expected_helpers() -> None:
    bootstrap_mod = importlib.import_module("engine.editor.editor_controller_bootstrap")
    for name in (
        "bootstrap_dependencies",
        "bootstrap_browser_state",
        "bootstrap_runtime_state",
        "bootstrap_overlay_state",
    ):
        assert callable(getattr(bootstrap_mod, name, None)), f"bootstrap helper missing {name}"
