from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from engine.editor import editor_actions_planes as planes_actions
from engine.editor.background_planes_edit_model import list_background_planes

pytestmark = pytest.mark.fast


def _plane_ids_in_sort_order(scene: dict[str, Any]) -> list[str]:
    return [plane.id for plane in list_background_planes(scene)]


def _plane(plane_id: str, layer: int) -> dict[str, Any]:
    return {
        "id": plane_id,
        "asset_path": "assets/placeholder.png",
        "parallax": 0.5,
        "render_layer": int(layer),
        "alpha": 1.0,
        "offset_x": 0.0,
        "offset_y": 0.0,
        "repeat_x": False,
        "repeat_y": False,
    }


def _make_window(scene: dict[str, Any]) -> Any:
    return SimpleNamespace(scene_controller=SimpleNamespace(_loaded_scene_data=scene))


def _get_selected_plane_id(_window: Any) -> str:
    return "plane_b"


def test_move_top_reorders_selected_plane_to_first() -> None:
    scene = {
        "background_planes": [
            _plane("plane_a", 0),
            _plane("plane_b", 1),
            _plane("plane_c", 2),
        ]
    }
    window = _make_window(scene)
    pushed: list[str] = []

    def _apply_plane_update(w: Any, new_scene: dict[str, Any]) -> None:
        w.scene_controller._loaded_scene_data = new_scene

    def _push_plane_command(
        _w: Any,
        action_id: str,
        _before: list[dict[str, Any]],
        _after: list[dict[str, Any]],
        _detail: dict[str, Any] | None,
    ) -> None:
        pushed.append(action_id)

    planes_actions._action_planes_move_top(
        window,
        _get_selected_plane_id,
        _apply_plane_update,
        _push_plane_command,
    )

    assert _plane_ids_in_sort_order(window.scene_controller._loaded_scene_data)[0] == "plane_b"
    assert pushed == ["editor.background_planes.move_top"]


def test_move_bottom_reorders_selected_plane_to_last() -> None:
    scene = {
        "background_planes": [
            _plane("plane_a", 0),
            _plane("plane_b", 1),
            _plane("plane_c", 2),
        ]
    }
    window = _make_window(scene)

    def _apply_plane_update(w: Any, new_scene: dict[str, Any]) -> None:
        w.scene_controller._loaded_scene_data = new_scene

    planes_actions._action_planes_move_bottom(
        window,
        _get_selected_plane_id,
        _apply_plane_update,
        lambda *_args, **_kwargs: None,
    )

    assert _plane_ids_in_sort_order(window.scene_controller._loaded_scene_data)[-1] == "plane_b"


def test_move_to_index_clamps_and_moves_selected_plane() -> None:
    scene = {
        "background_planes": [
            _plane("plane_a", 0),
            _plane("plane_b", 1),
            _plane("plane_c", 2),
        ]
    }
    window = _make_window(scene)

    def _apply_plane_update(w: Any, new_scene: dict[str, Any]) -> None:
        w.scene_controller._loaded_scene_data = new_scene

    planes_actions._action_planes_move_to_index(
        window,
        99,
        _get_selected_plane_id,
        _apply_plane_update,
        lambda *_args, **_kwargs: None,
    )

    ordered = _plane_ids_in_sort_order(window.scene_controller._loaded_scene_data)
    assert ordered == ["plane_a", "plane_c", "plane_b"]
