from __future__ import annotations

from typing import Any

import pytest


pytestmark = [pytest.mark.fast]


def _make_controller() -> Any:
    from engine.scene_controller import SceneController

    sc = object.__new__(SceneController)
    sc.current_scene_path = None
    sc._loaded_scene_data = {}
    sc._authoring_trace_enabled = False
    sc._authoring_trace_data = {}
    return sc


def test_authoring_facade_methods_are_bound_from_part_module() -> None:
    from engine.scene_controller import SceneController

    for name in (
        "_call_authoring",
        "enable_authoring_trace",
        "get_authoring_trace_snapshot",
        "refresh_tilemap_layers",
        "debug_add_entity_payload",
        "debug_preview_macro_objective_zone",
    ):
        method = getattr(SceneController, name, None)
        assert callable(method), f"SceneController.{name} missing or not callable"
        assert getattr(method, "__module__", None) == "engine.scene_controller_parts.authoring"


def test_refresh_tilemap_layers_false_when_scene_path_missing() -> None:
    sc = _make_controller()

    result = sc.refresh_tilemap_layers()

    assert result is False


def test_refresh_tilemap_layers_rebuilds_layers_for_loaded_tilemap() -> None:
    sc = _make_controller()
    sc.current_scene_path = "scenes/test_scene.json"
    sc._loaded_scene_data = {"tilemap": {"tile_layers": []}}

    calls: list[tuple[str, Any]] = []
    sc._clear_tilemap_layers = lambda: calls.append(("clear", None))
    sc._load_tilemap_layers = lambda scene, scene_dir: calls.append(("load", scene, scene_dir))

    result = sc.refresh_tilemap_layers()

    assert result is True
    assert calls[0] == ("clear", None)
    assert calls[1][0] == "load"
    assert calls[1][1] is sc._loaded_scene_data
    assert str(calls[1][2]).replace("\\", "/").endswith("scenes")