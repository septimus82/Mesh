from __future__ import annotations

import importlib

import pytest


pytestmark = [pytest.mark.fast]


def test_editor_actions_old_and_impl_modules_import() -> None:
    old_mod = importlib.import_module("engine.editor.editor_actions")
    impl_mod = importlib.import_module("engine.editor.editor_actions_impl")
    assert old_mod is not None
    assert impl_mod is not None


def test_editor_actions_core_entrypoints_preserved() -> None:
    old_mod = importlib.import_module("engine.editor.editor_actions")
    impl_mod = importlib.import_module("engine.editor.editor_actions_impl")
    assert callable(getattr(old_mod, "get_editor_actions", None))
    assert callable(getattr(old_mod, "run_editor_action", None))
    assert getattr(old_mod, "get_editor_actions")(None, None) == getattr(impl_mod, "get_editor_actions")(None, None)


def test_editor_actions_registry_symbol_surface_preserved() -> None:
    old_mod = importlib.import_module("engine.editor.editor_actions")
    for name in (
        "_enabled_can_undo",
        "_enabled_can_redo",
        "_undo",
        "_redo",
        "_action_align_left",
        "_action_planes_add",
    ):
        assert callable(getattr(old_mod, name, None)), f"missing callable {name}"
