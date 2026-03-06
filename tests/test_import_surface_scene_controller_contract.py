from __future__ import annotations

import importlib

import pytest

pytestmark = [pytest.mark.fast]


def test_scene_controller_import_surface_smoke() -> None:
    mod = importlib.import_module("engine.scene_controller")
    impl = importlib.import_module("engine.scene_controller_impl")
    assert impl is not None
    cls = getattr(mod, "SceneController", None)
    assert cls is not None
    for name in (
        "load_scene",
        "reload_scene",
        "update",
        "draw",
        "request_scene_change",
        "queue_scene_change",
        "get_all_entities",
    ):
        assert callable(getattr(cls, name, None)), f"missing SceneController.{name}"


def test_scene_controller_runtime_helpers_are_importable() -> None:
    mod = importlib.import_module("engine.scene_controller")
    for name in (
        "_reload_scene_runtime",
        "_perform_scene_change_runtime",
        "_build_scene_snapshot_runtime",
        "_apply_scene_state_runtime",
    ):
        assert hasattr(mod, name), f"missing runtime helper {name}"


def test_scene_controller_parts_modules_importable() -> None:
    for name in (
        "engine.scene_controller_parts",
        "engine.scene_controller_parts.loading",
        "engine.scene_controller_parts.transitions",
        "engine.scene_controller_parts.runtime_hooks",
        "engine.scene_controller_parts.persistence",
        "engine.scene_controller_parts.quests_flags",
    ):
        module = importlib.import_module(name)
        assert module is not None
