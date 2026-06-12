"""Tile/layer editing actions (background planes) for editor actions."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any, Callable

from engine.swallowed_exceptions import _log_swallow

GetEditorFn = Callable[[Any], Any | None]


def _get_plane_state(window: Any) -> Any:
    state = getattr(window, "background_plane_editor_state", None) if window is not None else None
    if state is None:
        state = SimpleNamespace(selected_plane_id="")
        try:
            setattr(window, "background_plane_editor_state", state)
        except Exception:
            _log_swallow("EDIT-001", "engine/editor/editor_actions_planes.py pass-only blanket swallow")
            pass
    return state


def _get_selected_plane_id(window: Any, get_plane_state: Callable[[Any], Any]) -> str:
    state = get_plane_state(window)
    selected = getattr(state, "selected_plane_id", "")
    return str(selected or "").strip()


def _enabled_plane_selected(_controller: Any, window: Any, get_selected_plane_id: Callable[[Any], str]) -> bool:
    return bool(get_selected_plane_id(window))


def _get_sorted_plane_ids(scene: dict[str, Any]) -> list[str]:
    from engine.editor.background_planes_edit_model import list_background_planes  # noqa: PLC0415

    return [plane.id for plane in list_background_planes(scene)]


def _enabled_scene_loaded(_controller: Any, window: Any) -> bool:
    sc = getattr(window, "scene_controller", None)
    scene = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
    return isinstance(scene, dict)


def _enabled_planes_exist(_controller: Any, window: Any, get_sorted_plane_ids: Callable[[dict[str, Any]], list[str]]) -> bool:
    sc = getattr(window, "scene_controller", None)
    scene = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
    if not isinstance(scene, dict):
        return False
    return bool(get_sorted_plane_ids(scene))


def _push_plane_command(
    window: Any,
    action_id: str,
    before_planes: list[dict[str, Any]],
    after_planes: list[dict[str, Any]],
    get_editor: GetEditorFn,
    detail: dict[str, Any] | None = None,
) -> None:
    if before_planes == after_planes:
        return
    editor = get_editor(window)
    pusher = getattr(editor, "_push_command", None) if editor is not None else None
    if not callable(pusher):
        return
    cmd: dict[str, Any] = {
        "type": "EditBackgroundPlanes",
        "action_id": action_id,
        "before": copy.deepcopy(before_planes),
        "after": copy.deepcopy(after_planes),
    }
    if isinstance(detail, dict) and detail:
        cmd["detail"] = dict(detail)
    pusher(cmd)


def _apply_plane_update(window: Any, new_scene: dict[str, Any], get_editor: GetEditorFn) -> None:
    sc = getattr(window, "scene_controller", None)
    if sc is None:
        return
    sc._loaded_scene_data = new_scene
    try:
        from engine.parallax_model import parse_background_planes  # noqa: PLC0415

        sc._background_planes = parse_background_planes(new_scene)
        cache = getattr(sc, "_background_plane_texture_cache", None)
        if isinstance(cache, dict):
            cache.clear()
    except Exception:
        _log_swallow("EDIT-002", "engine/editor/editor_actions_planes.py pass-only blanket swallow")
        pass
    editor = get_editor(window)
    marker = getattr(editor, "_mark_dirty", None) if editor is not None else None
    if callable(marker):
        marker()


def _action_planes_add(
    window: Any,
    get_plane_state: Callable[[Any], Any],
    apply_plane_update: Callable[[Any, dict[str, Any]], None],
    push_plane_command: Callable[[Any, str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None], None],
) -> None:
    from engine.editor.background_planes_edit_model import add_background_plane  # noqa: PLC0415

    sc = getattr(window, "scene_controller", None)
    scene = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
    if not isinstance(scene, dict):
        return
    before_planes = copy.deepcopy(scene.get("background_planes", [])) if isinstance(scene.get("background_planes", []), list) else []
    new_scene, new_id = add_background_plane(scene, template=None)
    apply_plane_update(window, new_scene)
    state = get_plane_state(window)
    try:
        state.selected_plane_id = new_id
    except Exception:
        _log_swallow("EDIT-003", "engine/editor/editor_actions_planes.py pass-only blanket swallow")
        pass
    push_plane_command(
        window,
        "editor.background_planes.add",
        before_planes,
        new_scene.get("background_planes", []),
        {"plane_id": new_id},
    )


def _action_planes_duplicate(
    window: Any,
    get_selected_plane_id: Callable[[Any], str],
    get_plane_state: Callable[[Any], Any],
    apply_plane_update: Callable[[Any, dict[str, Any]], None],
    push_plane_command: Callable[[Any, str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None], None],
) -> None:
    from engine.editor.background_planes_edit_model import duplicate_background_plane  # noqa: PLC0415

    plane_id = get_selected_plane_id(window)
    if not plane_id:
        return
    sc = getattr(window, "scene_controller", None)
    scene = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
    if not isinstance(scene, dict):
        return
    before_planes = copy.deepcopy(scene.get("background_planes", [])) if isinstance(scene.get("background_planes", []), list) else []
    new_scene, new_id = duplicate_background_plane(scene, plane_id)
    if not new_id:
        return
    apply_plane_update(window, new_scene)
    state = get_plane_state(window)
    try:
        state.selected_plane_id = new_id
    except Exception:
        _log_swallow("EDIT-004", "engine/editor/editor_actions_planes.py pass-only blanket swallow")
        pass
    push_plane_command(
        window,
        "editor.background_planes.duplicate",
        before_planes,
        new_scene.get("background_planes", []),
        {"plane_id": new_id},
    )


def _action_planes_remove(
    window: Any,
    get_selected_plane_id: Callable[[Any], str],
    get_plane_state: Callable[[Any], Any],
    apply_plane_update: Callable[[Any, dict[str, Any]], None],
    push_plane_command: Callable[[Any, str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None], None],
) -> None:
    from engine.editor.background_planes_edit_model import remove_background_plane  # noqa: PLC0415

    plane_id = get_selected_plane_id(window)
    if not plane_id:
        return
    sc = getattr(window, "scene_controller", None)
    scene = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
    if not isinstance(scene, dict):
        return
    before_planes = copy.deepcopy(scene.get("background_planes", [])) if isinstance(scene.get("background_planes", []), list) else []
    new_scene = remove_background_plane(scene, plane_id)
    apply_plane_update(window, new_scene)
    state = get_plane_state(window)
    try:
        state.selected_plane_id = ""
    except Exception:
        _log_swallow("EDIT-005", "engine/editor/editor_actions_planes.py pass-only blanket swallow")
        pass
    push_plane_command(
        window,
        "editor.background_planes.remove",
        before_planes,
        new_scene.get("background_planes", []),
        {"plane_id": plane_id},
    )


def _action_planes_move(
    window: Any,
    direction: str,
    get_selected_plane_id: Callable[[Any], str],
    apply_plane_update: Callable[[Any, dict[str, Any]], None],
    push_plane_command: Callable[[Any, str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None], None],
) -> None:
    from engine.editor.background_planes_edit_model import move_background_plane  # noqa: PLC0415

    plane_id = get_selected_plane_id(window)
    if not plane_id:
        return
    sc = getattr(window, "scene_controller", None)
    scene = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
    if not isinstance(scene, dict):
        return
    before_planes = copy.deepcopy(scene.get("background_planes", [])) if isinstance(scene.get("background_planes", []), list) else []
    new_scene = move_background_plane(scene, plane_id, direction)
    after_planes = new_scene.get("background_planes", [])
    if before_planes == after_planes:
        return
    apply_plane_update(window, new_scene)
    push_plane_command(
        window,
        "editor.background_planes.move_up" if direction == "up" else "editor.background_planes.move_down",
        before_planes,
        after_planes,
        {"plane_id": plane_id, "direction": direction},
    )


def _int_render_layer(entry: dict[str, Any]) -> int:
    raw = entry.get("render_layer", 0)
    if isinstance(raw, int):
        return int(raw)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _str_plane_id(entry: dict[str, Any]) -> str:
    value = entry.get("id", "")
    if isinstance(value, str):
        return value.strip()
    return str(value or "").strip()


def _reorder_planes_for_target_index(
    planes: list[dict[str, Any]],
    plane_id: str,
    target_index: int,
) -> list[dict[str, Any]]:
    ordered = sorted(planes, key=lambda entry: (_int_render_layer(entry), _str_plane_id(entry)))
    current_index = -1
    for index, entry in enumerate(ordered):
        if _str_plane_id(entry) == plane_id:
            current_index = index
            break
    if current_index < 0:
        return ordered
    clamped = max(0, min(int(target_index), len(ordered) - 1))
    if clamped == current_index:
        return ordered
    moved = ordered.pop(current_index)
    ordered.insert(clamped, moved)
    for index, entry in enumerate(ordered):
        entry["render_layer"] = int(index)
    return ordered


def _action_planes_move_to_index(
    window: Any,
    index: int,
    get_selected_plane_id: Callable[[Any], str],
    apply_plane_update: Callable[[Any, dict[str, Any]], None],
    push_plane_command: Callable[[Any, str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None], None],
    *,
    action_id: str = "editor.background_planes.move_to_index",
) -> None:
    plane_id = get_selected_plane_id(window)
    if not plane_id:
        return
    sc = getattr(window, "scene_controller", None)
    scene = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
    if not isinstance(scene, dict):
        return
    before_planes = copy.deepcopy(scene.get("background_planes", [])) if isinstance(scene.get("background_planes", []), list) else []
    if not before_planes:
        return
    new_scene = copy.deepcopy(scene)
    raw_planes = new_scene.get("background_planes", [])
    if not isinstance(raw_planes, list):
        return
    planes = [entry for entry in raw_planes if isinstance(entry, dict)]
    if not planes:
        return
    _reorder_planes_for_target_index(planes, plane_id, index)
    after_planes = new_scene.get("background_planes", [])
    if before_planes == after_planes:
        return
    apply_plane_update(window, new_scene)
    push_plane_command(
        window,
        action_id,
        before_planes,
        after_planes,
        {"plane_id": plane_id, "index": int(index)},
    )


def _action_planes_move_top(
    window: Any,
    get_selected_plane_id: Callable[[Any], str],
    apply_plane_update: Callable[[Any, dict[str, Any]], None],
    push_plane_command: Callable[[Any, str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None], None],
) -> None:
    _action_planes_move_to_index(
        window,
        0,
        get_selected_plane_id,
        apply_plane_update,
        push_plane_command,
        action_id="editor.background_planes.move_top",
    )


def _action_planes_move_bottom(
    window: Any,
    get_selected_plane_id: Callable[[Any], str],
    apply_plane_update: Callable[[Any, dict[str, Any]], None],
    push_plane_command: Callable[[Any, str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None], None],
) -> None:
    sc = getattr(window, "scene_controller", None)
    scene = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
    if not isinstance(scene, dict):
        return
    planes = scene.get("background_planes", [])
    length = len(planes) if isinstance(planes, list) else 0
    if length <= 0:
        return
    _action_planes_move_to_index(
        window,
        length - 1,
        get_selected_plane_id,
        apply_plane_update,
        push_plane_command,
        action_id="editor.background_planes.move_bottom",
    )


def _action_planes_move_to_index_from_window(
    window: Any,
    get_selected_plane_id: Callable[[Any], str],
    apply_plane_update: Callable[[Any, dict[str, Any]], None],
    push_plane_command: Callable[[Any, str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None], None],
) -> None:
    raw = getattr(window, "command_palette_planes_move_to_index", None)
    if isinstance(raw, int):
        index = int(raw)
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            return
        try:
            index = int(text)
        except ValueError:
            return
    else:
        return
    _action_planes_move_to_index(
        window,
        index,
        get_selected_plane_id,
        apply_plane_update,
        push_plane_command,
    )


def _action_planes_move_up(window: Any, action_planes_move: Callable[[Any, str], None]) -> None:
    action_planes_move(window, "up")


def _action_planes_move_down(window: Any, action_planes_move: Callable[[Any, str], None]) -> None:
    action_planes_move(window, "down")


def _action_planes_toggle_repeat(
    window: Any,
    axis: str,
    get_selected_plane_id: Callable[[Any], str],
    apply_plane_update: Callable[[Any, dict[str, Any]], None],
    push_plane_command: Callable[[Any, str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None], None],
) -> None:
    from engine.editor.background_planes_edit_model import get_plane_by_id, update_background_plane  # noqa: PLC0415

    plane_id = get_selected_plane_id(window)
    if not plane_id:
        return
    sc = getattr(window, "scene_controller", None)
    scene = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
    if not isinstance(scene, dict):
        return
    before_planes = copy.deepcopy(scene.get("background_planes", [])) if isinstance(scene.get("background_planes", []), list) else []
    plane = get_plane_by_id(scene, plane_id)
    if plane is None:
        return
    if axis == "x":
        patch = {"repeat_x": not bool(plane.repeat_x)}
    else:
        patch = {"repeat_y": not bool(plane.repeat_y)}
    new_scene = update_background_plane(scene, plane_id, patch)
    after_planes = new_scene.get("background_planes", [])
    if before_planes == after_planes:
        return
    apply_plane_update(window, new_scene)
    push_plane_command(
        window,
        "editor.background_planes.toggle_repeat_x" if axis == "x" else "editor.background_planes.toggle_repeat_y",
        before_planes,
        after_planes,
        {"plane_id": plane_id, "axis": axis},
    )


def _action_planes_toggle_repeat_x(window: Any, action_planes_toggle_repeat: Callable[[Any, str], None]) -> None:
    action_planes_toggle_repeat(window, "x")


def _action_planes_toggle_repeat_y(window: Any, action_planes_toggle_repeat: Callable[[Any, str], None]) -> None:
    action_planes_toggle_repeat(window, "y")


def _action_planes_select(
    window: Any,
    direction: str,
    get_sorted_plane_ids: Callable[[dict[str, Any]], list[str]],
    get_selected_plane_id: Callable[[Any], str],
    get_plane_state: Callable[[Any], Any],
) -> None:
    sc = getattr(window, "scene_controller", None)
    scene = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
    if not isinstance(scene, dict):
        return
    plane_ids = get_sorted_plane_ids(scene)
    if not plane_ids:
        return
    selected = get_selected_plane_id(window)
    if selected in plane_ids:
        current_index = plane_ids.index(selected)
    else:
        current_index = 0 if direction == "next" else len(plane_ids) - 1
    if direction == "next":
        new_index = (current_index + 1) % len(plane_ids)
    else:
        new_index = (current_index - 1) % len(plane_ids)
    state = get_plane_state(window)
    try:
        state.selected_plane_id = plane_ids[new_index]
    except Exception:
        _log_swallow("EDIT-006", "engine/editor/editor_actions_planes.py pass-only blanket swallow")
        pass


def _action_planes_select_prev(window: Any, action_planes_select: Callable[[Any, str], None]) -> None:
    action_planes_select(window, "prev")


def _action_planes_select_next(window: Any, action_planes_select: Callable[[Any, str], None]) -> None:
    action_planes_select(window, "next")
