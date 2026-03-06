from __future__ import annotations

import importlib

import pytest


pytestmark = [pytest.mark.fast]


def test_entity_ops_module_and_helpers_import() -> None:
    mod = importlib.import_module("engine.scene_runtime.authoring.entity_ops")
    impl = importlib.import_module("engine.scene_runtime.authoring.entity_ops_impl")
    core = importlib.import_module("engine.scene_runtime.authoring.entity_ops_core")
    align = importlib.import_module("engine.scene_runtime.authoring.entity_ops_align")
    geom = importlib.import_module("engine.scene_runtime.authoring.entity_ops_geometry")
    xform = importlib.import_module("engine.scene_runtime.authoring.entity_ops_transform")
    parts = importlib.import_module("engine.scene_runtime.authoring.entity_ops_parts")
    parts_shared = importlib.import_module("engine.scene_runtime.authoring.entity_ops_parts._shared")
    parts_selection = importlib.import_module("engine.scene_runtime.authoring.entity_ops_parts.selection_ops")
    parts_spawn = importlib.import_module("engine.scene_runtime.authoring.entity_ops_parts.spawn_ops")
    parts_property = importlib.import_module("engine.scene_runtime.authoring.entity_ops_parts.property_ops")
    parts_transform = importlib.import_module("engine.scene_runtime.authoring.entity_ops_parts.transform_ops")
    parts_debug = importlib.import_module("engine.scene_runtime.authoring.entity_ops_parts.debug_ops")
    parts_delete = importlib.import_module("engine.scene_runtime.authoring.entity_ops_parts.delete_ops")
    assert mod is not None
    assert impl is not None
    assert core is not None
    assert align is not None
    assert geom is not None
    assert xform is not None
    assert parts is not None
    assert parts_shared is not None
    assert parts_selection is not None
    assert parts_spawn is not None
    assert parts_property is not None
    assert parts_transform is not None
    assert parts_debug is not None
    assert parts_delete is not None
    assert impl is core


def test_entity_ops_public_debug_entrypoints_are_callable() -> None:
    mod = importlib.import_module("engine.scene_runtime.authoring.entity_ops")
    parts_transform = importlib.import_module("engine.scene_runtime.authoring.entity_ops_parts.transform_ops")
    parts_shared = importlib.import_module("engine.scene_runtime.authoring.entity_ops_parts._shared")
    for name in (
        "debug_align_selection",
        "debug_distribute_selection",
        "debug_snap_to_grid",
        "debug_nudge_selection",
        "debug_rotate_selection",
        "debug_mirror_selection",
        "debug_scatter_selection",
    ):
        assert callable(getattr(mod, name, None)), f"missing callable {name}"
    assert mod.debug_align_selection is parts_transform.debug_align_selection
    assert mod._entity_bounds is parts_shared._entity_bounds
