from __future__ import annotations

import importlib
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast]


MAX_ENTITY_OPS_CORE_LINES = 2050
MAX_ENTITY_OPS_IMPL_SHIM_LINES = 40

ENTITY_OPS_IMPL_PATH = Path("engine/scene_runtime/authoring/entity_ops_impl.py")
ENTITY_OPS_CORE_PATH = Path("engine/scene_runtime/authoring/entity_ops_core.py")


def test_entity_ops_impl_stays_thin_shim() -> None:
    source = ENTITY_OPS_IMPL_PATH.read_text(encoding="utf-8")
    line_count = len(source.splitlines())
    assert line_count <= MAX_ENTITY_OPS_IMPL_SHIM_LINES, (
        f"entity_ops_impl.py grew: {line_count} lines (max {MAX_ENTITY_OPS_IMPL_SHIM_LINES})"
    )
    assert 'import_module("engine.scene_runtime.authoring.entity_ops_core")' in source
    assert "sys.modules[__name__] = _impl" in source


def test_entity_ops_core_line_count_ratcheted() -> None:
    line_count = len(ENTITY_OPS_CORE_PATH.read_text(encoding="utf-8").splitlines())
    assert line_count <= MAX_ENTITY_OPS_CORE_LINES, (
        f"entity_ops_core.py grew: {line_count} lines (max {MAX_ENTITY_OPS_CORE_LINES})"
    )


def test_entity_ops_facade_exports_resolve_from_parts_modules() -> None:
    mod = importlib.import_module("engine.scene_runtime.authoring.entity_ops")
    impl = importlib.import_module("engine.scene_runtime.authoring.entity_ops_impl")
    core = importlib.import_module("engine.scene_runtime.authoring.entity_ops_core")
    assert impl is core
    assert mod is core

    assert mod._entity_bounds.__module__ == "engine.scene_runtime.authoring.entity_ops_parts._shared"
    assert mod._anchor_value.__module__ == "engine.scene_runtime.authoring.entity_ops_parts._shared"
    assert mod._snap_value.__module__ == "engine.scene_runtime.authoring.entity_ops_parts._shared"

    assert mod.debug_align_selection.__module__ == "engine.scene_runtime.authoring.entity_ops_parts.transform_ops"
    assert mod.debug_distribute_selection.__module__ == "engine.scene_runtime.authoring.entity_ops_parts.transform_ops"
    assert mod.debug_snap_to_grid.__module__ == "engine.scene_runtime.authoring.entity_ops_parts.transform_ops"
    assert mod.debug_nudge_selection.__module__ == "engine.scene_runtime.authoring.entity_ops_parts.transform_ops"
    assert mod.debug_rotate_selection.__module__ == "engine.scene_runtime.authoring.entity_ops_parts.transform_ops"
    assert mod.debug_mirror_selection.__module__ == "engine.scene_runtime.authoring.entity_ops_parts.transform_ops"
