from __future__ import annotations

import importlib

import pytest


pytestmark = [pytest.mark.fast]


def test_command_palette_actions_old_and_impl_modules_import() -> None:
    old_mod = importlib.import_module("engine.command_palette_registry_actions")
    impl_mod = importlib.import_module("engine.command_palette_registry_actions_impl")
    assert old_mod is not None
    assert impl_mod is not None


def test_command_palette_actions_key_symbols_resolve_from_old_path() -> None:
    old_mod = importlib.import_module("engine.command_palette_registry_actions")
    impl_mod = importlib.import_module("engine.command_palette_registry_actions_impl")
    for name in (
        "action_toggle_tile_paint",
        "action_toggle_entity_paint",
        "action_scene_reload",
        "action_palette_clear_recent",
    ):
        old_sym = getattr(old_mod, name, None)
        impl_sym = getattr(impl_mod, name, None)
        assert callable(old_sym), f"old path missing callable {name}"
        assert callable(impl_sym), f"impl path missing callable {name}"


def test_command_palette_actions_split_modules_export_expected_symbols() -> None:
    impl_mod = importlib.import_module("engine.command_palette_registry_actions_impl")
    old_mod = importlib.import_module("engine.command_palette_registry_actions")
    debug_mod = importlib.import_module("engine.command_palette_actions.debug_actions")
    entity_mod = importlib.import_module("engine.command_palette_actions.entity_actions")
    io_mod = importlib.import_module("engine.command_palette_actions.io_actions")
    scene_mod = importlib.import_module("engine.command_palette_actions.scene_actions")
    selection_mod = importlib.import_module("engine.command_palette_actions.selection_actions")

    checks = (
        ("action_macro_objective_zone", debug_mod),
        ("action_props_set_prefab_id", entity_mod),
        ("action_scene_save_as", io_mod),
        ("action_planes_move_up", scene_mod),
        ("action_align_selection", selection_mod),
    )
    for name, bucket_mod in checks:
        bucket_sym = getattr(bucket_mod, name, None)
        impl_sym = getattr(impl_mod, name, None)
        old_sym = getattr(old_mod, name, None)
        assert callable(bucket_sym), f"bucket path missing callable {name}"
        assert callable(impl_sym), f"impl path missing callable {name}"
        assert callable(old_sym), f"old path missing callable {name}"
        assert impl_sym is bucket_sym, f"impl symbol should re-export bucket symbol {name}"
        assert old_sym is impl_sym, f"old path should resolve impl symbol {name}"
