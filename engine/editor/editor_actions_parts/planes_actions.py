"""Plane add/remove/move/select/toggle-repeat action handlers."""

from __future__ import annotations

from typing import Any

from engine.editor import editor_actions_planes as _tile_paint_actions
from engine.editor.editor_actions_parts._shared import _get_editor

__all__ = [
    "_get_plane_state",
    "_get_selected_plane_id",
    "_enabled_plane_selected",
    "_get_sorted_plane_ids",
    "_enabled_scene_loaded",
    "_enabled_planes_exist",
    "_push_plane_command",
    "_apply_plane_update",
    "_action_planes_add",
    "_action_planes_duplicate",
    "_action_planes_remove",
    "_action_planes_move",
    "_action_planes_move_up",
    "_action_planes_move_down",
    "_action_planes_move_top",
    "_action_planes_move_bottom",
    "_action_planes_move_to_index",
    "_action_planes_toggle_repeat",
    "_action_planes_toggle_repeat_x",
    "_action_planes_toggle_repeat_y",
    "_action_planes_select",
    "_action_planes_select_prev",
    "_action_planes_select_next",
]


def _get_plane_state(window: Any) -> Any:
    return _tile_paint_actions._get_plane_state(window)


def _get_selected_plane_id(window: Any) -> str:
    return _tile_paint_actions._get_selected_plane_id(window, _get_plane_state)


def _enabled_plane_selected(_controller: Any, window: Any) -> bool:
    return _tile_paint_actions._enabled_plane_selected(_controller, window, _get_selected_plane_id)


def _get_sorted_plane_ids(scene: dict[str, Any]) -> list[str]:
    return _tile_paint_actions._get_sorted_plane_ids(scene)


def _enabled_scene_loaded(_controller: Any, window: Any) -> bool:
    return _tile_paint_actions._enabled_scene_loaded(_controller, window)


def _enabled_planes_exist(_controller: Any, window: Any) -> bool:
    return _tile_paint_actions._enabled_planes_exist(_controller, window, _get_sorted_plane_ids)


def _push_plane_command(
    window: Any,
    action_id: str,
    before_planes: list[dict[str, Any]],
    after_planes: list[dict[str, Any]],
    detail: dict[str, Any] | None = None,
) -> None:
    _tile_paint_actions._push_plane_command(window, action_id, before_planes, after_planes, _get_editor, detail)


def _apply_plane_update(window: Any, new_scene: dict[str, Any]) -> None:
    _tile_paint_actions._apply_plane_update(window, new_scene, _get_editor)


def _action_planes_add(window: Any) -> None:
    _tile_paint_actions._action_planes_add(window, _get_plane_state, _apply_plane_update, _push_plane_command)


def _action_planes_duplicate(window: Any) -> None:
    _tile_paint_actions._action_planes_duplicate(
        window, _get_selected_plane_id, _get_plane_state, _apply_plane_update, _push_plane_command
    )


def _action_planes_remove(window: Any) -> None:
    _tile_paint_actions._action_planes_remove(
        window, _get_selected_plane_id, _get_plane_state, _apply_plane_update, _push_plane_command
    )


def _action_planes_move(window: Any, direction: str) -> None:
    _tile_paint_actions._action_planes_move(window, direction, _get_selected_plane_id, _apply_plane_update, _push_plane_command)


def _action_planes_move_up(window: Any) -> None:
    _tile_paint_actions._action_planes_move_up(window, _action_planes_move)


def _action_planes_move_down(window: Any) -> None:
    _tile_paint_actions._action_planes_move_down(window, _action_planes_move)


def _action_planes_move_top(window: Any) -> None:
    _tile_paint_actions._action_planes_move_top(window, _get_selected_plane_id, _apply_plane_update, _push_plane_command)


def _action_planes_move_bottom(window: Any) -> None:
    _tile_paint_actions._action_planes_move_bottom(window, _get_selected_plane_id, _apply_plane_update, _push_plane_command)


def _action_planes_move_to_index(window: Any) -> None:
    _tile_paint_actions._action_planes_move_to_index_from_window(
        window, _get_selected_plane_id, _apply_plane_update, _push_plane_command
    )


def _action_planes_toggle_repeat(window: Any, axis: str) -> None:
    _tile_paint_actions._action_planes_toggle_repeat(
        window, axis, _get_selected_plane_id, _apply_plane_update, _push_plane_command
    )


def _action_planes_toggle_repeat_x(window: Any) -> None:
    _tile_paint_actions._action_planes_toggle_repeat_x(window, _action_planes_toggle_repeat)


def _action_planes_toggle_repeat_y(window: Any) -> None:
    _tile_paint_actions._action_planes_toggle_repeat_y(window, _action_planes_toggle_repeat)


def _action_planes_select(window: Any, direction: str) -> None:
    _tile_paint_actions._action_planes_select(window, direction, _get_sorted_plane_ids, _get_selected_plane_id, _get_plane_state)


def _action_planes_select_prev(window: Any) -> None:
    _tile_paint_actions._action_planes_select_prev(window, _action_planes_select)


def _action_planes_select_next(window: Any) -> None:
    _tile_paint_actions._action_planes_select_next(window, _action_planes_select)
