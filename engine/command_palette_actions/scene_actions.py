from __future__ import annotations

from importlib import import_module
from typing import Any

from ._shared import _log_swallow, _parse_planes_move_to_args, _parse_planes_select_args, _parse_planes_toggle_repeat_args, _set_selected_plane_id

def _run_editor_action_from_impl(w: Any, action_id: str) -> bool:
    impl = import_module("engine.command_palette_registry_actions_impl")
    runner = getattr(impl, "_run_editor_action", None)
    if not callable(runner):
        return False
    return bool(runner(w, action_id))


def action_scene_reload(w: Any, _arg: str | None) -> None:
    """Reload current scene from disk."""
    reloader = getattr(w, "reload_scene_from_disk", None)
    ok = bool(reloader()) if callable(reloader) else False
    print(f"SCENE_RELOAD {'ok' if ok else 'fail'}")


def action_scene_toggle_persist_armed(w: Any, _arg: str | None) -> None:
    """Toggle scene persist armed state."""
    w.scene_persist_armed = not bool(getattr(w, "scene_persist_armed", False))
    print(f"SCENE_PERSIST_ARMED {'on' if w.scene_persist_armed else 'off'}")


def action_planes_add(w: Any, _arg: str | None) -> None:
    _run_editor_action_from_impl(w, "editor.background_planes.add")


def action_planes_duplicate(w: Any, _arg: str | None) -> None:
    _run_editor_action_from_impl(w, "editor.background_planes.duplicate")


def action_planes_remove(w: Any, _arg: str | None) -> None:
    _run_editor_action_from_impl(w, "editor.background_planes.remove")


def action_planes_move_up(w: Any, _arg: str | None) -> None:
    _run_editor_action_from_impl(w, "editor.background_planes.move_up")


def action_planes_move_down(w: Any, _arg: str | None) -> None:
    _run_editor_action_from_impl(w, "editor.background_planes.move_down")


def action_planes_move_top(w: Any, _arg: str | None) -> None:
    _run_editor_action_from_impl(w, "editor.background_planes.move_top")


def action_planes_move_bottom(w: Any, _arg: str | None) -> None:
    _run_editor_action_from_impl(w, "editor.background_planes.move_bottom")


def action_planes_move_to(w: Any, arg: str | None) -> None:
    parser = _parse_planes_move_to_args(arg)
    if not bool(parser.get("ok")):
        return
    mode = str(parser.get("mode") or "").strip().lower()
    if mode == "top":
        _run_editor_action_from_impl(w, "editor.background_planes.move_top")
        return
    if mode in ("bottom", "last"):
        _run_editor_action_from_impl(w, "editor.background_planes.move_bottom")
        return
    if mode != "index":
        return
    index_raw = parser.get("index")
    if not isinstance(index_raw, int):
        return
    try:
        setattr(w, "command_palette_planes_move_to_index", int(index_raw))
    except Exception:
        _log_swallow(
            "CPRA-007",
            "engine.command_palette_registry_actions_impl.action_planes_move_to: set_command_palette_planes_move_to_index",
        )
        return
    try:
        _run_editor_action_from_impl(w, "editor.background_planes.move_to_index")
    finally:
        try:
            delattr(w, "command_palette_planes_move_to_index")
        except Exception:
            _log_swallow(
                "CPRA-008",
                "engine.command_palette_registry_actions_impl.action_planes_move_to: clear_command_palette_planes_move_to_index",
            )


def action_planes_toggle_repeat_x(w: Any, _arg: str | None) -> None:
    _run_editor_action_from_impl(w, "editor.background_planes.toggle_repeat_x")


def action_planes_toggle_repeat_y(w: Any, _arg: str | None) -> None:
    _run_editor_action_from_impl(w, "editor.background_planes.toggle_repeat_y")


def action_planes_toggle_repeat(w: Any, arg: str | None) -> None:
    parser = _parse_planes_toggle_repeat_args(arg)
    if not bool(parser.get("ok")):
        return
    axes = parser.get("axes")
    if not isinstance(axes, tuple):
        return
    if "x" in axes:
        _run_editor_action_from_impl(w, "editor.background_planes.toggle_repeat_x")
    if "y" in axes:
        _run_editor_action_from_impl(w, "editor.background_planes.toggle_repeat_y")


def action_planes_select_prev(w: Any, _arg: str | None) -> None:
    _run_editor_action_from_impl(w, "editor.background_planes.select_prev")


def action_planes_select_next(w: Any, _arg: str | None) -> None:
    _run_editor_action_from_impl(w, "editor.background_planes.select_next")


def action_planes_select(w: Any, arg: str | None) -> None:
    parser = _parse_planes_select_args(arg)
    if not bool(parser.get("ok")):
        return
    mode = str(parser.get("mode") or "").strip().lower()
    if mode == "prev":
        _run_editor_action_from_impl(w, "editor.background_planes.select_prev")
        return
    if mode == "next":
        _run_editor_action_from_impl(w, "editor.background_planes.select_next")
        return
    plane_id = str(parser.get("plane_id") or "").strip()
    if not plane_id:
        return
    _set_selected_plane_id(w, plane_id)
