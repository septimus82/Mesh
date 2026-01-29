"""Unified editor action registry used by menus and find/command palettes."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
import copy
from types import SimpleNamespace
from typing import Any, Callable, Iterable

from engine.runtime_settings import ensure_runtime_settings

# Shortcut scope constants
SHORTCUT_SCOPE_GLOBAL = "global"
SHORTCUT_SCOPE_INLINE_RENAME = "text_input.inline_rename"


@dataclass(frozen=True, slots=True)
class EditorAction:
    id: str
    title: str
    keywords: tuple[str, ...]
    group: str | None
    shortcut: str
    enabled: Callable[[Any, Any], bool]
    run: Callable[[Any], None]
    in_palette: bool = True
    in_menu: bool = True
    menu_label: str | None = None
    shortcut_scope: str = SHORTCUT_SCOPE_GLOBAL


def _is_web_runtime() -> bool:
    return sys.platform == "emscripten" or os.environ.get("PYGBAG") == "1"


def _get_editor(window: Any) -> Any | None:
    return getattr(window, "editor_controller", None) if window is not None else None


def _enabled_always(_controller: Any, _window: Any) -> bool:
    return True


def _enabled_has_selection(controller: Any, _window: Any) -> bool:
    return getattr(controller, "selected_entity", None) is not None


def _enabled_has_selection_or_project_explorer(controller: Any, _window: Any) -> bool:
    if getattr(controller, "selected_entity", None) is not None:
        return True
    project_ctrl = getattr(controller, "project_explorer", None)
    if project_ctrl is None:
        return False
    count = getattr(project_ctrl, "selection_count", None)
    if callable(count):
        value = int(count())
        return value > 0
    return False


def _enabled_can_undo(controller: Any, _window: Any) -> bool:
    return bool(getattr(controller, "undo_stack", []))


def _enabled_can_redo(controller: Any, _window: Any) -> bool:
    return bool(getattr(controller, "redo_stack", []))


def _enabled_scene_dirty(controller: Any, _window: Any) -> bool:
    return bool(getattr(controller, "scene_dirty", False))


def _enabled_not_web(_controller: Any, _window: Any) -> bool:
    return not _is_web_runtime()


def _enabled_right_dock_toggle(controller: Any, _window: Any) -> bool:
    return getattr(controller, "tool_mode", "") != "ZONE"


def _get_plane_state(window: Any) -> Any:
    state = getattr(window, "background_plane_editor_state", None) if window is not None else None
    if state is None:
        state = SimpleNamespace(selected_plane_id="")
        try:
            setattr(window, "background_plane_editor_state", state)
        except Exception:
            pass
    return state


def _get_selected_plane_id(window: Any) -> str:
    state = _get_plane_state(window)
    selected = getattr(state, "selected_plane_id", "")
    return str(selected or "").strip()


def _enabled_plane_selected(_controller: Any, window: Any) -> bool:
    return bool(_get_selected_plane_id(window))


def _get_sorted_plane_ids(scene: dict[str, Any]) -> list[str]:
    from engine.editor.background_planes_edit_model import list_background_planes  # noqa: PLC0415

    return [plane.id for plane in list_background_planes(scene)]


def _enabled_scene_loaded(_controller: Any, window: Any) -> bool:
    sc = getattr(window, "scene_controller", None)
    scene = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
    return isinstance(scene, dict)


def _enabled_planes_exist(_controller: Any, window: Any) -> bool:
    sc = getattr(window, "scene_controller", None)
    scene = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
    if not isinstance(scene, dict):
        return False
    return bool(_get_sorted_plane_ids(scene))


def _enabled_problems_panel_active(controller: Any, _window: Any) -> bool:
    """True when Problems panel is the active right dock tab."""
    return getattr(controller, "_right_dock_tab", "") == "Problems"


def _enabled_problems_can_jump(controller: Any, _window: Any) -> bool:
    """True when Problems panel is active, has issues, and selected issue is jump-supported."""
    if getattr(controller, "_right_dock_tab", "") != "Problems":
        return False
    problems_ctl = getattr(controller, "problems", None)
    if problems_ctl is None:
        return False
    target = getattr(problems_ctl, "get_selected_jump_target", lambda: None)()
    if not target:
        return False
    # Check if jump is supported for this target
    from engine.editor.problems_jump_model import is_jump_supported  # noqa: PLC0415

    return is_jump_supported(target)


def _push_plane_command(
    window: Any,
    action_id: str,
    before_planes: list[dict[str, Any]],
    after_planes: list[dict[str, Any]],
    detail: dict[str, Any] | None = None,
) -> None:
    if before_planes == after_planes:
        return
    editor = _get_editor(window)
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


def _apply_plane_update(window: Any, new_scene: dict[str, Any]) -> None:
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
        pass
    editor = _get_editor(window)
    marker = getattr(editor, "_mark_dirty", None) if editor is not None else None
    if callable(marker):
        marker()


def _action_planes_add(window: Any) -> None:
    from engine.editor.background_planes_edit_model import add_background_plane  # noqa: PLC0415

    sc = getattr(window, "scene_controller", None)
    scene = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
    if not isinstance(scene, dict):
        return
    before_planes = copy.deepcopy(scene.get("background_planes", [])) if isinstance(scene.get("background_planes", []), list) else []
    new_scene, new_id = add_background_plane(scene, template=None)
    _apply_plane_update(window, new_scene)
    state = _get_plane_state(window)
    try:
        state.selected_plane_id = new_id
    except Exception:
        pass
    _push_plane_command(
        window,
        "editor.background_planes.add",
        before_planes,
        new_scene.get("background_planes", []),
        {"plane_id": new_id},
    )


def _action_planes_duplicate(window: Any) -> None:
    from engine.editor.background_planes_edit_model import duplicate_background_plane  # noqa: PLC0415

    plane_id = _get_selected_plane_id(window)
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
    _apply_plane_update(window, new_scene)
    state = _get_plane_state(window)
    try:
        state.selected_plane_id = new_id
    except Exception:
        pass
    _push_plane_command(
        window,
        "editor.background_planes.duplicate",
        before_planes,
        new_scene.get("background_planes", []),
        {"plane_id": new_id},
    )


def _action_planes_remove(window: Any) -> None:
    from engine.editor.background_planes_edit_model import remove_background_plane  # noqa: PLC0415

    plane_id = _get_selected_plane_id(window)
    if not plane_id:
        return
    sc = getattr(window, "scene_controller", None)
    scene = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
    if not isinstance(scene, dict):
        return
    before_planes = copy.deepcopy(scene.get("background_planes", [])) if isinstance(scene.get("background_planes", []), list) else []
    new_scene = remove_background_plane(scene, plane_id)
    _apply_plane_update(window, new_scene)
    state = _get_plane_state(window)
    try:
        state.selected_plane_id = ""
    except Exception:
        pass
    _push_plane_command(
        window,
        "editor.background_planes.remove",
        before_planes,
        new_scene.get("background_planes", []),
        {"plane_id": plane_id},
    )


def _action_planes_move(window: Any, direction: str) -> None:
    from engine.editor.background_planes_edit_model import move_background_plane  # noqa: PLC0415

    plane_id = _get_selected_plane_id(window)
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
    _apply_plane_update(window, new_scene)
    _push_plane_command(
        window,
        "editor.background_planes.move_up" if direction == "up" else "editor.background_planes.move_down",
        before_planes,
        after_planes,
        {"plane_id": plane_id, "direction": direction},
    )


def _action_planes_toggle_repeat(window: Any, axis: str) -> None:
    from engine.editor.background_planes_edit_model import get_plane_by_id, update_background_plane  # noqa: PLC0415

    plane_id = _get_selected_plane_id(window)
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
    _apply_plane_update(window, new_scene)
    _push_plane_command(
        window,
        "editor.background_planes.toggle_repeat_x" if axis == "x" else "editor.background_planes.toggle_repeat_y",
        before_planes,
        after_planes,
        {"plane_id": plane_id, "axis": axis},
    )


def _action_planes_select(window: Any, direction: str) -> None:
    sc = getattr(window, "scene_controller", None)
    scene = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
    if not isinstance(scene, dict):
        return
    plane_ids = _get_sorted_plane_ids(scene)
    if not plane_ids:
        return
    selected = _get_selected_plane_id(window)
    if selected in plane_ids:
        current_index = plane_ids.index(selected)
    else:
        current_index = 0 if direction == "next" else len(plane_ids) - 1
    if direction == "next":
        new_index = (current_index + 1) % len(plane_ids)
    else:
        new_index = (current_index - 1) % len(plane_ids)
    state = _get_plane_state(window)
    try:
        state.selected_plane_id = plane_ids[new_index]
    except Exception:
        pass


def _apply_hd2d_preset(window: Any, preset_id: str) -> None:
    from engine.editor.hd2d_look_presets_model import apply_hd2d_preset, get_hd2d_preset_name  # noqa: PLC0415

    sc = getattr(window, "scene_controller", None)
    if sc is None:
        return
    scene = getattr(sc, "_loaded_scene_data", None)
    if not isinstance(scene, dict):
        return
    preset_name = get_hd2d_preset_name(preset_id)
    if preset_name is None:
        return
    before_settings = copy.deepcopy(scene.get("settings")) if isinstance(scene.get("settings"), dict) else {}
    new_scene = apply_hd2d_preset(scene, preset_id)
    after_settings = new_scene.get("settings") if isinstance(new_scene.get("settings"), dict) else {}
    if before_settings == after_settings:
        return
    sc._loaded_scene_data = new_scene
    editor = _get_editor(window)
    if editor is None:
        return
    marker = getattr(editor, "_mark_dirty", None)
    if callable(marker):
        marker()
    pusher = getattr(editor, "_push_command", None)
    if callable(pusher):
        pusher({
            "type": "ApplyHd2dPreset",
            "label": f"Apply HD2D Preset \u00b7 {preset_name}",
            "preset_id": preset_id,
            "before": before_settings,
            "after": after_settings,
        })


def _upgrade_scene_to_hd2d_defaults(window: Any) -> None:
    """Upgrade scene to HD2D defaults (fills missing keys only)."""
    editor = _get_editor(window)
    upgrader = getattr(editor, "upgrade_scene_to_hd2d_defaults", None) if editor is not None else None
    if callable(upgrader):
        upgrader()


def _toggle_hd2d_setting(window: Any, key: str) -> None:
    """Toggle a boolean HD-2D scene setting with undo support."""
    from engine.editor.hd2d_settings_panel_model import (  # noqa: PLC0415
        apply_hd2d_setting_patch,
        format_hd2d_toggle_label,
        parse_hd2d_scene_settings_dict,
    )

    sc = getattr(window, "scene_controller", None)
    if sc is None:
        return
    scene = getattr(sc, "_loaded_scene_data", None)
    if not isinstance(scene, dict):
        return

    # Get current value and compute new value
    current_settings = parse_hd2d_scene_settings_dict(scene)
    old_value = current_settings.get(key, False)
    new_value = not old_value

    # Apply patch
    before_settings = copy.deepcopy(scene.get("settings")) if isinstance(scene.get("settings"), dict) else {}
    new_scene = apply_hd2d_setting_patch(scene, {key: new_value})
    after_settings = new_scene.get("settings") if isinstance(new_scene.get("settings"), dict) else {}

    if before_settings == after_settings:
        return

    sc._loaded_scene_data = new_scene

    # Mark dirty and push undo command
    editor = _get_editor(window)
    if editor is None:
        return
    marker = getattr(editor, "_mark_dirty", None)
    if callable(marker):
        marker()
    pusher = getattr(editor, "_push_command", None)
    if callable(pusher):
        pusher({
            "type": "ToggleHd2dSetting",
            "label": format_hd2d_toggle_label(key, new_value),
            "key": key,
            "before": before_settings,
            "after": after_settings,
        })


def _adjust_hd2d_slider(window: Any, key: str, delta: float) -> None:
    """Adjust a float/int HD-2D scene setting with undo support."""
    from engine.editor.hd2d_settings_panel_model import (  # noqa: PLC0415
        apply_hd2d_setting_patch,
        format_hd2d_setting_change_label,
        parse_hd2d_scene_settings_dict,
        sanitize_hd2d_setting_value,
    )

    sc = getattr(window, "scene_controller", None)
    if sc is None:
        return
    scene = getattr(sc, "_loaded_scene_data", None)
    if not isinstance(scene, dict):
        return

    # Get current value and compute new value
    current_settings = parse_hd2d_scene_settings_dict(scene)
    old_value = current_settings.get(key, 0.0)
    raw_new = old_value + delta
    new_value = sanitize_hd2d_setting_value(key, raw_new)

    if old_value == new_value:
        return

    # Apply patch
    before_settings = copy.deepcopy(scene.get("settings")) if isinstance(scene.get("settings"), dict) else {}
    new_scene = apply_hd2d_setting_patch(scene, {key: new_value})
    after_settings = new_scene.get("settings") if isinstance(new_scene.get("settings"), dict) else {}

    if before_settings == after_settings:
        return

    sc._loaded_scene_data = new_scene

    # Mark dirty and push undo command
    editor = _get_editor(window)
    if editor is None:
        return
    marker = getattr(editor, "_mark_dirty", None)
    if callable(marker):
        marker()
    pusher = getattr(editor, "_push_command", None)
    if callable(pusher):
        pusher({
            "type": "AdjustHd2dSetting",
            "label": format_hd2d_setting_change_label(key, old_value, new_value),
            "key": key,
            "before": before_settings,
            "after": after_settings,
        })


# =============================================================================
# HD-2D Entity Override Actions
# =============================================================================


def _toggle_entity_hd2d_override(window: Any, key: str) -> None:
    """Cycle an entity HD-2D override: None -> True -> False -> None."""
    from engine.editor.hd2d_entity_overrides_model import (  # noqa: PLC0415
        apply_hd2d_entity_override_patch,
        format_entity_toggle_label,
        get_entity_override_value,
    )

    editor = _get_editor(window)
    if editor is None:
        return
    entity_id = getattr(editor, "_primary_selected_id", None)
    if not entity_id:
        return

    sc = getattr(window, "scene_controller", None)
    if sc is None:
        return
    scene = getattr(sc, "_loaded_scene_data", None)
    if not isinstance(scene, dict):
        return

    # Get current value and compute next value in cycle: None -> True -> False -> None
    current = get_entity_override_value(scene, entity_id, key)
    if current is None:
        new_value: bool | None = True
    elif current is True:
        new_value = False
    else:
        new_value = None

    # Apply patch
    before_scene = copy.deepcopy(scene)
    new_scene = apply_hd2d_entity_override_patch(scene, entity_id, {key: new_value})
    if new_scene == before_scene:
        return

    sc._loaded_scene_data = new_scene

    # Mark dirty and push undo command
    marker = getattr(editor, "_mark_dirty", None)
    if callable(marker):
        marker()
    pusher = getattr(editor, "_push_command", None)
    if callable(pusher):
        pusher({
            "type": "ToggleEntityHd2dOverride",
            "label": format_entity_toggle_label(entity_id, key, new_value),
            "entity_id": entity_id,
            "key": key,
            "before": before_scene,
            "after": new_scene,
        })


def _adjust_entity_hd2d_slider(window: Any, key: str, delta: float) -> None:
    """Adjust an entity HD-2D override slider value. If None, initialize to default."""
    from engine.editor.hd2d_entity_overrides_model import (  # noqa: PLC0415
        ENTITY_INT_KEYS,
        apply_hd2d_entity_override_patch,
        format_entity_override_label,
        get_entity_override_value,
        sanitize_hd2d_entity_override_patch,
    )

    editor = _get_editor(window)
    if editor is None:
        return
    entity_id = getattr(editor, "_primary_selected_id", None)
    if not entity_id:
        return

    sc = getattr(window, "scene_controller", None)
    if sc is None:
        return
    scene = getattr(sc, "_loaded_scene_data", None)
    if not isinstance(scene, dict):
        return

    # Get current value - if None, initialize to sensible default
    old_value = get_entity_override_value(scene, entity_id, key)
    if old_value is None:
        # Default to 0.5 for strength values, 1 for int values
        old_value = 1 if key in ENTITY_INT_KEYS else 0.5

    raw_new = old_value + delta
    sanitized = sanitize_hd2d_entity_override_patch({key: raw_new})
    new_value = sanitized.get(key, raw_new)

    if old_value == new_value:
        return

    # Apply patch
    before_scene = copy.deepcopy(scene)
    new_scene = apply_hd2d_entity_override_patch(scene, entity_id, {key: new_value})
    if new_scene == before_scene:
        return

    sc._loaded_scene_data = new_scene

    # Mark dirty and push undo command
    marker = getattr(editor, "_mark_dirty", None)
    if callable(marker):
        marker()
    pusher = getattr(editor, "_push_command", None)
    if callable(pusher):
        pusher({
            "type": "AdjustEntityHd2dOverride",
            "label": format_entity_override_label(entity_id, key, old_value, new_value),
            "entity_id": entity_id,
            "key": key,
            "before": before_scene,
            "after": new_scene,
        })


def _clear_entity_hd2d_override(window: Any, key: str) -> None:
    """Clear an entity HD-2D override (set to None = inherit)."""
    from engine.editor.hd2d_entity_overrides_model import (  # noqa: PLC0415
        apply_hd2d_entity_override_patch,
        get_entity_override_value,
    )

    editor = _get_editor(window)
    if editor is None:
        return
    entity_id = getattr(editor, "_primary_selected_id", None)
    if not entity_id:
        return

    sc = getattr(window, "scene_controller", None)
    if sc is None:
        return
    scene = getattr(sc, "_loaded_scene_data", None)
    if not isinstance(scene, dict):
        return

    # Only clear if currently has a value
    current = get_entity_override_value(scene, entity_id, key)
    if current is None:
        return

    # Apply patch to set to None
    before_scene = copy.deepcopy(scene)
    new_scene = apply_hd2d_entity_override_patch(scene, entity_id, {key: None})
    if new_scene == before_scene:
        return

    sc._loaded_scene_data = new_scene

    # Mark dirty and push undo command
    marker = getattr(editor, "_mark_dirty", None)
    if callable(marker):
        marker()
    pusher = getattr(editor, "_push_command", None)
    if callable(pusher):
        pusher({
            "type": "ClearEntityHd2dOverride",
            "label": f"Clear {key} override for {entity_id}",
            "entity_id": entity_id,
            "key": key,
            "before": before_scene,
            "after": new_scene,
        })


def _enabled_entity_selected(_controller: Any, window: Any) -> bool:
    """Check if an entity is selected."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return False
    return bool(getattr(editor, "_primary_selected_id", None))


def _enabled_entity_has_overrides(_controller: Any, window: Any) -> bool:
    """Check if an entity is selected AND has any HD-2D overrides set."""
    from engine.editor.hd2d_entity_overrides_model import has_any_override  # noqa: PLC0415

    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return False
    entity_id = getattr(editor, "_primary_selected_id", None)
    if not entity_id:
        return False
    sc = getattr(window, "scene_controller", None)
    if sc is None:
        return False
    scene = getattr(sc, "_loaded_scene_data", None)
    if not isinstance(scene, dict):
        return False
    # Get entity dict from scene
    entities = scene.get("entities")
    if isinstance(entities, dict):
        entity_dict = entities.get(entity_id)
    elif isinstance(entities, list):
        entity_dict = None
        for ent in entities:
            if isinstance(ent, dict) and (ent.get("id") == entity_id or ent.get("mesh_name") == entity_id):
                entity_dict = ent
                break
    else:
        return False
    if not isinstance(entity_dict, dict):
        return False
    return has_any_override(entity_dict)


def _enabled_hd2d_clipboard_has_data(_controller: Any, window: Any) -> bool:
    """Check if the HD-2D overrides clipboard has data AND an entity is selected."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return False
    if not getattr(editor, "_primary_selected_id", None):
        return False
    clipboard = getattr(editor, "_hd2d_overrides_clipboard", None)
    return isinstance(clipboard, dict) and len(clipboard) > 0


def _copy_entity_hd2d_overrides(window: Any) -> None:
    """Copy HD-2D overrides from selected entity into in-editor clipboard.

    No undo entry, no dirty flag - this is a read-only operation.
    """
    from engine.editor.editor_selection_model import selected_entity_id  # noqa: PLC0415
    from engine.editor.hd2d_controller_helpers_model import (  # noqa: PLC0415
        compute_clipboard_patch_from_entity,
        count_clipboard_patch_fields,
    )

    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    entity_id = selected_entity_id(editor)
    if not entity_id:
        return

    sc = getattr(window, "scene_controller", None)
    if sc is None:
        return
    scene = getattr(sc, "_loaded_scene_data", None)
    if not isinstance(scene, dict):
        return

    # Get entity data from scene
    entities = scene.get("entities")
    if not isinstance(entities, dict):
        return
    entity_data = entities.get(entity_id)
    if not isinstance(entity_data, dict):
        return

    # Extract override patch (only non-None values)
    patch = compute_clipboard_patch_from_entity(entity_data)
    field_count = count_clipboard_patch_fields(patch)

    # Store in clipboard (copy, not reference)
    editor._hd2d_overrides_clipboard = copy.deepcopy(patch)

    # Toast feedback
    hud = getattr(window, "player_hud", None)
    if hud is not None:
        enqueue = getattr(hud, "enqueue_toast", None)
        if callable(enqueue):
            if field_count == 0:
                enqueue(f"Copied HD-2D overrides · {entity_id} (empty)")
            else:
                enqueue(f"Copied HD-2D overrides · {entity_id} ({field_count} field{'s' if field_count != 1 else ''})")


def _paste_entity_hd2d_overrides(window: Any) -> None:
    """Paste HD-2D overrides from clipboard onto selected entity.

    Creates one undo entry, marks scene dirty.
    """
    from engine.editor.editor_selection_model import selected_entity_id  # noqa: PLC0415
    from engine.editor.hd2d_controller_helpers_model import (  # noqa: PLC0415
        count_clipboard_patch_fields,
        validate_clipboard_patch,
    )
    from engine.editor.hd2d_entity_overrides_model import (  # noqa: PLC0415
        apply_hd2d_entity_override_patch,
    )

    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    entity_id = selected_entity_id(editor)
    if not entity_id:
        return

    clipboard = getattr(editor, "_hd2d_overrides_clipboard", None)
    if not validate_clipboard_patch(clipboard):
        hud = getattr(window, "player_hud", None)
        if hud is not None:
            enqueue = getattr(hud, "enqueue_toast", None)
            if callable(enqueue):
                enqueue("Nothing to paste")
        return

    # clipboard is now validated as a non-empty dict
    assert isinstance(clipboard, dict)

    sc = getattr(window, "scene_controller", None)
    if sc is None:
        return
    scene = getattr(sc, "_loaded_scene_data", None)
    if not isinstance(scene, dict):
        return

    # Apply patch
    before_scene = copy.deepcopy(scene)
    new_scene = apply_hd2d_entity_override_patch(scene, entity_id, clipboard)
    if new_scene == before_scene:
        hud = getattr(window, "player_hud", None)
        if hud is not None:
            enqueue = getattr(hud, "enqueue_toast", None)
            if callable(enqueue):
                enqueue("No changes")
        return

    sc._loaded_scene_data = new_scene

    # Mark dirty and push undo
    field_count = count_clipboard_patch_fields(clipboard)
    marker = getattr(editor, "_mark_dirty", None)
    if callable(marker):
        marker()
    pusher = getattr(editor, "_push_command", None)
    if callable(pusher):
        pusher({
            "type": "PasteEntityHd2dOverrides",
            "label": f"Paste HD2D Overrides · {entity_id} ({field_count} field{'s' if field_count != 1 else ''})",
            "entity_id": entity_id,
            "before": before_scene,
            "after": new_scene,
        })

    # Toast feedback
    hud = getattr(window, "player_hud", None)
    if hud is not None:
        enqueue = getattr(hud, "enqueue_toast", None)
        if callable(enqueue):
            enqueue(f"Pasted HD-2D overrides · {entity_id}")


def _paste_replace_entity_hd2d_overrides(window: Any) -> None:
    """Paste HD-2D overrides from clipboard as REPLACE (clear first, then apply).

    Creates one undo entry, marks scene dirty.
    Replace = clear all overrides on target entity, then apply clipboard patch.
    """
    from engine.editor.editor_selection_model import selected_entity_id  # noqa: PLC0415
    from engine.editor.hd2d_controller_helpers_model import (  # noqa: PLC0415
        count_clipboard_patch_fields,
        validate_clipboard_patch,
    )
    from engine.editor.hd2d_entity_overrides_model import (  # noqa: PLC0415
        apply_hd2d_entity_override_patch,
        clear_all_overrides,
    )

    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    entity_id = selected_entity_id(editor)
    if not entity_id:
        return

    clipboard = getattr(editor, "_hd2d_overrides_clipboard", None)
    if not validate_clipboard_patch(clipboard):
        hud = getattr(window, "player_hud", None)
        if hud is not None:
            enqueue = getattr(hud, "enqueue_toast", None)
            if callable(enqueue):
                enqueue("Nothing to paste")
        return

    # clipboard is now validated as a non-empty dict
    assert isinstance(clipboard, dict)

    sc = getattr(window, "scene_controller", None)
    if sc is None:
        return
    scene = getattr(sc, "_loaded_scene_data", None)
    if not isinstance(scene, dict):
        return

    # Snapshot before state
    before_scene = copy.deepcopy(scene)

    # Step 1: Clear all overrides (inherit everything)
    cleared_scene = clear_all_overrides(scene, entity_id)

    # Step 2: Apply clipboard patch
    new_scene = apply_hd2d_entity_override_patch(cleared_scene, entity_id, clipboard)

    if new_scene == before_scene:
        hud = getattr(window, "player_hud", None)
        if hud is not None:
            enqueue = getattr(hud, "enqueue_toast", None)
            if callable(enqueue):
                enqueue("No changes")
        return

    sc._loaded_scene_data = new_scene

    # Mark dirty and push ONE undo entry
    field_count = count_clipboard_patch_fields(clipboard)
    marker = getattr(editor, "_mark_dirty", None)
    if callable(marker):
        marker()
    pusher = getattr(editor, "_push_command", None)
    if callable(pusher):
        pusher({
            "type": "PasteReplaceEntityHd2dOverrides",
            "label": f"Paste HD2D Overrides (Replace) · {entity_id} ({field_count} field{'s' if field_count != 1 else ''})",
            "entity_id": entity_id,
            "before": before_scene,
            "after": new_scene,
        })

    # Toast feedback
    hud = getattr(window, "player_hud", None)
    if hud is not None:
        enqueue = getattr(hud, "enqueue_toast", None)
        if callable(enqueue):
            enqueue(f"Pasted HD-2D overrides (replace) · {entity_id}")


def _clear_all_entity_hd2d_overrides(window: Any) -> None:
    """Clear ALL HD-2D overrides on the selected entity.

    Creates one undo entry, marks scene dirty.
    """
    from engine.editor.editor_selection_model import selected_entity_id  # noqa: PLC0415
    from engine.editor.hd2d_entity_overrides_model import (  # noqa: PLC0415
        clear_all_overrides,
        has_any_override,
    )

    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    entity_id = selected_entity_id(editor)
    if not entity_id:
        return

    sc = getattr(window, "scene_controller", None)
    if sc is None:
        return
    scene = getattr(sc, "_loaded_scene_data", None)
    if not isinstance(scene, dict):
        return

    # Get entity dict from scene
    entities = scene.get("entities")
    entity_dict: dict[str, Any] | None = None
    if isinstance(entities, dict):
        entity_dict = entities.get(entity_id)
    elif isinstance(entities, list):
        for ent in entities:
            if isinstance(ent, dict) and (ent.get("id") == entity_id or ent.get("mesh_name") == entity_id):
                entity_dict = ent
                break

    # Check if entity has any overrides
    if not isinstance(entity_dict, dict) or not has_any_override(entity_dict):
        hud = getattr(window, "player_hud", None)
        if hud is not None:
            enqueue = getattr(hud, "enqueue_toast", None)
            if callable(enqueue):
                enqueue("No overrides to clear")
        return

    # Clear all overrides
    before_scene = copy.deepcopy(scene)
    new_scene = clear_all_overrides(scene, entity_id)
    if new_scene == before_scene:
        return

    sc._loaded_scene_data = new_scene

    # Mark dirty and push undo
    marker = getattr(editor, "_mark_dirty", None)
    if callable(marker):
        marker()
    pusher = getattr(editor, "_push_command", None)
    if callable(pusher):
        pusher({
            "type": "ClearAllEntityHd2dOverrides",
            "label": f"Clear HD2D Overrides · {entity_id}",
            "entity_id": entity_id,
            "before": before_scene,
            "after": new_scene,
        })

    # Toast feedback
    hud = getattr(window, "player_hud", None)
    if hud is not None:
        enqueue = getattr(hud, "enqueue_toast", None)
        if callable(enqueue):
            enqueue(f"Cleared HD-2D overrides · {entity_id}")


def _batch_paste_hd2d_overrides(window: Any, replace: bool = False) -> None:
    """Batch paste HD-2D overrides to entities within radius of selected entity.

    Creates ONE undo entry for the entire batch, marks scene dirty.

    Args:
        window: The game window.
        replace: If True, clear existing overrides before applying (replace mode).
                 If False, merge clipboard fields with existing (merge mode).
    """
    from engine.editor.editor_selection_model import selected_entity_id  # noqa: PLC0415
    from engine.editor.hd2d_controller_helpers_model import (  # noqa: PLC0415
        count_clipboard_patch_fields,
        validate_clipboard_patch,
    )
    from engine.editor.hd2d_entity_overrides_model import (  # noqa: PLC0415
        apply_hd2d_entity_override_patch,
        clear_all_overrides,
    )
    from engine.editor.hd2d_override_batch_apply_model import (  # noqa: PLC0415
        compute_batch_apply_targets,
    )

    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    center_id = selected_entity_id(editor)
    if not center_id:
        return

    clipboard = getattr(editor, "_hd2d_overrides_clipboard", None)
    if not validate_clipboard_patch(clipboard):
        hud = getattr(window, "player_hud", None)
        if hud is not None:
            enqueue = getattr(hud, "enqueue_toast", None)
            if callable(enqueue):
                enqueue("Nothing to paste")
        return

    # clipboard is now validated as a non-empty dict
    assert isinstance(clipboard, dict)

    sc = getattr(window, "scene_controller", None)
    if sc is None:
        return
    scene = getattr(sc, "_loaded_scene_data", None)
    if not isinstance(scene, dict):
        return

    # Compute targets using configured batch radius
    batch_radius = float(getattr(editor, "_hd2d_batch_radius_px", 96))
    targets = compute_batch_apply_targets(
        scene, center_id, mode="radius", radius_px=batch_radius, include_center=True
    )

    if not targets:
        hud = getattr(window, "player_hud", None)
        if hud is not None:
            enqueue = getattr(hud, "enqueue_toast", None)
            if callable(enqueue):
                enqueue("No entities in range")
        return

    # Snapshot before state
    before_scene = copy.deepcopy(scene)

    # Apply to each target in deterministic order
    current_scene = scene
    for entity_id in targets:
        if replace:
            # Replace: clear first, then apply
            current_scene = clear_all_overrides(current_scene, entity_id)
        current_scene = apply_hd2d_entity_override_patch(current_scene, entity_id, clipboard)

    if current_scene == before_scene:
        hud = getattr(window, "player_hud", None)
        if hud is not None:
            enqueue = getattr(hud, "enqueue_toast", None)
            if callable(enqueue):
                enqueue("No changes")
        return

    sc._loaded_scene_data = current_scene

    # Mark dirty and push ONE undo entry
    field_count = count_clipboard_patch_fields(clipboard)
    mode_label = "Replace" if replace else "Merge"
    marker = getattr(editor, "_mark_dirty", None)
    if callable(marker):
        marker()
    pusher = getattr(editor, "_push_command", None)
    if callable(pusher):
        pusher({
            "type": "BatchPasteEntityHd2dOverrides",
            "label": f"Batch Paste HD2D Overrides · {len(targets)} entities ({mode_label})",
            "targets": targets,
            "replace": replace,
            "before": before_scene,
            "after": current_scene,
        })

    # Toast feedback
    hud = getattr(window, "player_hud", None)
    if hud is not None:
        enqueue = getattr(hud, "enqueue_toast", None)
        if callable(enqueue):
            enqueue(f"Batch pasted HD-2D overrides ({mode_label}) · {len(targets)} entities")


def _batch_paste_hd2d_overrides_merge(window: Any) -> None:
    """Batch paste HD-2D overrides (merge mode)."""
    _batch_paste_hd2d_overrides(window, replace=False)


def _batch_paste_hd2d_overrides_replace(window: Any) -> None:
    """Batch paste HD-2D overrides (replace mode)."""
    _batch_paste_hd2d_overrides(window, replace=True)


def _adjust_hd2d_batch_radius(window: Any, delta: int) -> None:
    """Adjust HD-2D batch paste radius by delta.

    Does NOT push undo or mark dirty - this is a workspace setting tweak.
    """
    from engine.editor.hd2d_controller_helpers_model import (  # noqa: PLC0415
        compute_next_batch_radius,
        format_batch_radius_display,
    )

    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    current = getattr(editor, "_hd2d_batch_radius_px", 96)
    new_radius = compute_next_batch_radius(current, delta)

    if new_radius == current:
        return

    editor._hd2d_batch_radius_px = new_radius

    # Save to workspace settings (no undo, no dirty)
    _save_hd2d_batch_radius_to_workspace(window, new_radius)

    # Toast feedback
    hud = getattr(window, "player_hud", None)
    if hud is not None:
        enqueue = getattr(hud, "enqueue_toast", None)
        if callable(enqueue):
            enqueue(format_batch_radius_display(new_radius))


def _reset_hd2d_batch_radius(window: Any) -> None:
    """Reset HD-2D batch paste radius to default (96px).

    Does NOT push undo or mark dirty - this is a workspace setting tweak.
    """
    from engine.editor.hd2d_controller_helpers_model import (  # noqa: PLC0415
        format_batch_radius_display,
        get_batch_radius_default,
    )

    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    default_radius = get_batch_radius_default()
    current = getattr(editor, "_hd2d_batch_radius_px", 96)
    if current == default_radius:
        return

    editor._hd2d_batch_radius_px = default_radius

    # Save to workspace settings (no undo, no dirty)
    _save_hd2d_batch_radius_to_workspace(window, default_radius)

    # Toast feedback
    hud = getattr(window, "player_hud", None)
    if hud is not None:
        enqueue = getattr(hud, "enqueue_toast", None)
        if callable(enqueue):
            enqueue(f"{format_batch_radius_display(default_radius)} (reset)")


def _save_hd2d_batch_radius_to_workspace(window: Any, radius: int) -> None:
    """Helper to save batch radius to workspace settings."""
    from engine.workspace_settings import (  # noqa: PLC0415
        load_workspace,
        save_workspace,
    )
    from dataclasses import replace as dataclass_replace  # noqa: PLC0415

    editor = _get_editor(window)
    if editor is None:
        return

    repo_root_getter = getattr(editor, "_get_repo_root", None)
    if not callable(repo_root_getter):
        return

    try:
        repo_root = repo_root_getter()
        settings = load_workspace(repo_root)
        updated = dataclass_replace(settings, hd2d_batch_radius_px=radius)
        save_workspace(repo_root, updated)
    except Exception:  # noqa: BLE001
        pass  # Silently fail on workspace save errors


def _toggle_lights_tool(window: Any) -> None:
    editor = _get_editor(window)
    toggler = getattr(editor, "toggle_lights_tool", None) if editor is not None else None
    if callable(toggler):
        toggler()


def _toggle_occluder_tool(window: Any) -> None:
    editor = _get_editor(window)
    toggler = getattr(editor, "toggle_occluder_tool", None) if editor is not None else None
    if callable(toggler):
        toggler()


def _toggle_entity_panels(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    toggler = getattr(editor, "toggle_entity_panels", None)
    if callable(toggler):
        toggler()


def _set_dock_tab(window: Any, dock: str, tab: str) -> None:
    editor = _get_editor(window)
    setter = getattr(editor, "set_dock_tab", None) if editor is not None else None
    if callable(setter):
        setter(dock, tab)


def _toggle_dock_tab(window: Any, dock: str, tab: str) -> None:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    if dock == "left":
        if getattr(editor, "_left_dock_tab", None) == tab and not getattr(editor, "get_dock_left_collapsed", lambda: False)():
            toggler = getattr(editor, "toggle_left_dock", None)
            if callable(toggler):
                toggler()
                return
    elif dock == "right":
        if getattr(editor, "_right_dock_tab", None) == tab and not getattr(editor, "get_dock_right_collapsed", lambda: False)():
            toggler = getattr(editor, "toggle_right_dock", None)
            if callable(toggler):
                toggler()
                return
    _set_dock_tab(window, dock, tab)


def _toggle_inspector_panel(window: Any) -> None:
    _toggle_dock_tab(window, "right", "Inspector")


def _toggle_outliner_panel(window: Any) -> None:
    _toggle_dock_tab(window, "left", "Outliner")


def _toggle_history_panel(window: Any) -> None:
    _toggle_dock_tab(window, "right", "History")


def _toggle_problems_panel(window: Any) -> None:
    _toggle_dock_tab(window, "right", "Problems")


def _action_problems_jump(window: Any) -> None:
    """Jump to the currently selected problem (EditorAction handler)."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    jumper = getattr(editor, "problems_jump_to_selected", None)
    if callable(jumper):
        jumper()


def _action_problems_copy_location(window: Any) -> None:
    """Copy the selected problem's location to clipboard (EditorAction handler)."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    copier = getattr(editor, "problems_copy_location", None)
    if callable(copier):
        copier()


def _toggle_project_explorer_panel(window: Any) -> None:
    _toggle_dock_tab(window, "left", "Project")


def _reveal_current_in_project_explorer(window: Any) -> None:
    """Reveal current scene or selected entity asset in Project Explorer."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    revealer = getattr(editor, "reveal_current_in_project_explorer", None)
    if callable(revealer):
        revealer()


def _copy_project_explorer_path(window: Any) -> None:
    """Copy the selected Project Explorer row path to clipboard."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    # Direct delegation (Diet V5)
    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is None:
        return
    paths = project_ctrl.selected_paths()
    if not paths:
        return
    if hasattr(editor.file_ops, "copy_selected_paths"):
        editor.file_ops.copy_selected_paths(paths)
    else:
        editor.file_ops.copy_selected_path()


def _copy_project_explorer_common_parent(window: Any) -> None:
    """Copy common parent folder from Project Explorer selection."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is None:
        return
    paths = project_ctrl.selected_paths()
    if not paths:
        return
    copier = getattr(editor.file_ops, "copy_common_parent", None)
    if callable(copier):
        copier(paths)


def _project_explorer_select_all(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.select_all()


def _project_explorer_clear_selection(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.clear_selection()


def _project_explorer_invert_selection(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.invert_selection()


def _project_explorer_delete_selected(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    deleter = getattr(editor, "delete_selected", None)
    if callable(deleter):
        deleter()


def _safe_rename_selected_asset(window: Any) -> None:
    """Initiate inline rename for selected Project Explorer asset.

    Uses the new inline rename UX via ProjectExplorerController.
    Press F2 to start editing, Enter to commit, Esc to cancel.
    """
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    # Check capability via Protocol
    if not editor.file_ops.can_safe_rename_selected_asset():
        return

    # Get selected entry path to populate UI
    path_getter = getattr(editor, "_get_selected_project_entry_path", None)
    old_path: str | None = None
    if callable(path_getter):
        old_path = path_getter()

    if not old_path:
        return

    # Start inline rename via project explorer controller
    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.begin_inline_rename(old_path)


def _safe_move_selected_asset(window: Any) -> None:
    """Initiate safe move for selected Project Explorer asset.
    
    Prompts for destination folder (currently strictly requires UI implementation or test harness).
    
    If no UI available, this action does nothing (safe no-op).
    """
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    # Check capability via Protocol
    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is None:
        return
    selection_count = getattr(project_ctrl, "selection_count", None)
    if callable(selection_count) and selection_count() > 1:
        _safe_move_selected_assets(window)
        return

    if not editor.file_ops.can_safe_move_selected_asset():
        return

    prompter = getattr(editor, "prompt_project_explorer_move_destination", None)
    if callable(prompter):
        prompter(lambda dest: editor.safe_move_selected_asset(dest))
        return

    # Fallback toast if no prompt handler
    hud = getattr(window, "player_hud", None)
    toaster = getattr(hud, "enqueue_toast", None) if hud is not None else None
    if callable(toaster):
        toaster("Safe Move: Select specific folder logic pending UI", seconds=2.5)


def _safe_move_selected_assets(window: Any) -> None:
    """Initiate safe move for multiple selected Project Explorer assets."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is None:
        return

    selection_count = getattr(project_ctrl, "selection_count", None)
    if not callable(selection_count) or selection_count() <= 1:
        return

    prompter = getattr(editor, "prompt_project_explorer_move_destination", None)
    if callable(prompter):
        prompter(lambda dest: editor.safe_move_selected_assets(dest))
        return

    hud = getattr(window, "player_hud", None)
    toaster = getattr(hud, "enqueue_toast", None) if hud is not None else None
    if callable(toaster):
        toaster("Safe Move: Select specific folder logic pending UI", seconds=2.5)


# --- Inline Rename Action Handlers ---


def _enabled_inline_rename_active(_controller: Any, window: Any) -> bool:
    """Check if inline rename is active in Project Explorer."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return False

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is None:
        return False

    return getattr(project_ctrl, "inline_rename_active", False) is True


def _inline_rename_commit(window: Any) -> None:
    """Commit the inline rename and perform the actual file rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is None:
        return

    success, new_name = project_ctrl.commit_inline_rename()
    if not success or not new_name:
        # Either no change or error - if error, state is preserved for retry
        # Show toast if there was an error
        should_commit, _, error = project_ctrl.get_inline_rename_commit_result()
        if error:
            hud = getattr(window, "player_hud", None)
            toaster = getattr(hud, "enqueue_toast", None) if hud else None
            if callable(toaster):
                toaster(f"Rename failed: {error}", seconds=2.5)
        return

    # Perform actual rename via file_ops
    file_ops = getattr(editor, "file_ops", None)
    if file_ops is not None and hasattr(file_ops, "rename_selected_asset"):
        file_ops.rename_selected_asset(new_name)


def _inline_rename_cancel(window: Any) -> None:
    """Cancel the inline rename operation."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.cancel_inline_rename()


def _inline_rename_backspace(window: Any) -> None:
    """Delete character before cursor in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_backspace()


def _inline_rename_delete(window: Any) -> None:
    """Delete character at cursor in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_delete()


def _inline_rename_cursor_left(window: Any) -> None:
    """Move cursor left in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_left(shift=False)


def _inline_rename_cursor_left_extend(window: Any) -> None:
    """Move cursor left and extend selection in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_left(shift=True)


def _inline_rename_cursor_right(window: Any) -> None:
    """Move cursor right in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_right(shift=False)


def _inline_rename_cursor_right_extend(window: Any) -> None:
    """Move cursor right and extend selection in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_right(shift=True)


def _inline_rename_cursor_home(window: Any) -> None:
    """Move cursor to start in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_home(shift=False)


def _inline_rename_cursor_home_extend(window: Any) -> None:
    """Move cursor to start and extend selection in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_home(shift=True)


def _inline_rename_cursor_end(window: Any) -> None:
    """Move cursor to end in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_end(shift=False)


def _inline_rename_cursor_end_extend(window: Any) -> None:
    """Move cursor to end and extend selection in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_end(shift=True)


def _inline_rename_cursor_word_left(window: Any) -> None:
    """Move cursor left by word in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_word_left(shift=False)


def _inline_rename_cursor_word_left_extend(window: Any) -> None:
    """Move cursor left by word and extend selection in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_word_left(shift=True)


def _inline_rename_cursor_word_right(window: Any) -> None:
    """Move cursor right by word in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_word_right(shift=False)


def _inline_rename_cursor_word_right_extend(window: Any) -> None:
    """Move cursor right by word and extend selection in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_word_right(shift=True)


def _inline_rename_delete_prev_word(window: Any) -> None:
    """Delete previous word in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_delete_prev_word()


def _inline_rename_delete_next_word(window: Any) -> None:
    """Delete next word in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_delete_next_word()


def _enabled_project_explorer_file_selection(_controller: Any, window: Any) -> bool:
    """Check if there's a file (not folder) selected in Project Explorer."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return False

    from engine.editor.project_explorer_power_tools_model import should_handle_project_explorer_shortcut

    if not should_handle_project_explorer_shortcut(editor):
        return False

    can_rename = False
    can_move = False
    if hasattr(editor.file_ops, "can_safe_rename_selected_asset"):
        can_rename = bool(editor.file_ops.can_safe_rename_selected_asset())
    if hasattr(editor.file_ops, "can_safe_move_selected_asset"):
        can_move = bool(editor.file_ops.can_safe_move_selected_asset())
    return can_rename or can_move


def _enabled_has_reveal_target(_controller: Any, window: Any) -> bool:
    """Check if there's a valid reveal target (scene or selected entity asset)."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return False

    # Check for scene path
    sc = getattr(window, "scene_controller", None)
    if sc is not None:
        scene_path = getattr(sc, "current_scene_path", None)
        if scene_path:
            return True

    # Check for selected entity with asset
    entity_id = getattr(editor, "_primary_selected_id", None)
    if entity_id:
        return True  # Simplified - assume entity might have asset

    return False


def _enabled_project_explorer_selection(_controller: Any, window: Any) -> bool:
    """Check if there's a selection in Project Explorer."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return False

    from engine.editor.project_explorer_power_tools_model import should_handle_project_explorer_shortcut

    if not should_handle_project_explorer_shortcut(editor):
        return False
    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is None:
        return False
    count = getattr(project_ctrl, "selection_count", None)
    if callable(count):
        return bool(count() > 0)
    return False


def _enabled_project_explorer_active(_controller: Any, window: Any) -> bool:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return False
    from engine.editor.project_explorer_power_tools_model import should_handle_project_explorer_shortcut

    return bool(should_handle_project_explorer_shortcut(editor))


def _toggle_prefab_variant_editor(window: Any) -> None:
    _toggle_dock_tab(window, "right", "Inspector")


def _toggle_scene_switcher(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    toggler = getattr(editor, "toggle_scene_switcher", None)
    if callable(toggler):
        toggler()


def _toggle_find_everything(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    toggler = getattr(editor, "toggle_find_everything", None)
    if callable(toggler):
        toggler()


def _toggle_left_dock(window: Any) -> None:
    editor = _get_editor(window)
    toggler = getattr(editor, "toggle_left_dock", None) if editor is not None else None
    if callable(toggler):
        toggler()


def _toggle_right_dock(window: Any) -> None:
    editor = _get_editor(window)
    toggler = getattr(editor, "toggle_right_dock", None) if editor is not None else None
    if callable(toggler):
        toggler()


def _toggle_viewport_maximized(window: Any) -> None:
    editor = _get_editor(window)
    toggler = getattr(editor, "toggle_viewport_maximized", None) if editor is not None else None
    if callable(toggler):
        toggler()


def _open_scene_browser(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    toggler = getattr(editor, "toggle_scene_browser", None)
    if callable(toggler):
        toggler()


def _save_scene(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    saver = getattr(editor, "save_current_scene", None)
    if callable(saver):
        saver()


def _play_from_here(window: Any) -> None:
    editor = _get_editor(window)
    starter = getattr(editor, "play_from_here", None) if editor is not None else None
    if callable(starter):
        starter()


def _stop_playing(window: Any) -> None:
    editor = _get_editor(window)
    stopper = getattr(editor, "stop_playing", None) if editor is not None else None
    if callable(stopper):
        stopper()


def _apply_lighting_preset(window: Any, index: int) -> None:
    editor = _get_editor(window)
    apply_fn = getattr(editor, "apply_lighting_preset_hotkey", None) if editor is not None else None
    if callable(apply_fn):
        apply_fn(int(index))


def _toggle_fog(window: Any) -> None:
    settings = ensure_runtime_settings(window)
    settings.fog_enabled = not bool(settings.fog_enabled)
    settings.apply(window)


def _toggle_soft_shadows(window: Any) -> None:
    settings = ensure_runtime_settings(window)
    settings.soft_shadows_enabled = not bool(settings.soft_shadows_enabled)
    settings.apply(window)


def _toggle_asset_browser(window: Any) -> None:
    editor = _get_editor(window)
    toggler = getattr(editor, "toggle_asset_browser", None) if editor is not None else None
    if callable(toggler):
        toggler()


def _toggle_command_palette(window: Any) -> None:
    editor = _get_editor(window)
    toggler = getattr(editor, "toggle_command_palette", None) if editor is not None else None
    if callable(toggler):
        toggler()
        return
    if editor is None:
        return
    active = bool(getattr(editor, "command_palette_active", False))
    editor.command_palette_active = not active
    if editor.command_palette_active:
        editor.command_palette_query = ""
        editor.command_palette_index = 0


def _toggle_ghost_originals(window: Any) -> None:
    editor = _get_editor(window)
    toggler = getattr(editor, "toggle_ghost_originals", None) if editor is not None else None
    if callable(toggler):
        toggler()


def _toggle_prefab_palette(window: Any) -> None:
    editor = _get_editor(window)
    toggler = getattr(editor, "toggle_palette", None) if editor is not None else None
    if callable(toggler):
        toggler()


def _undo(window: Any) -> None:
    editor = _get_editor(window)
    undoer = getattr(editor, "undo_last", None) if editor is not None else None
    if callable(undoer):
        undoer()


def _redo(window: Any) -> None:
    editor = _get_editor(window)
    redoer = getattr(editor, "redo_last", None) if editor is not None else None
    if callable(redoer):
        redoer()


def _duplicate(window: Any) -> None:
    editor = _get_editor(window)
    duplicator = getattr(editor, "duplicate_selected", None) if editor is not None else None
    if callable(duplicator):
        duplicator()


def _delete(window: Any) -> None:
    editor = _get_editor(window)
    deleter = getattr(editor, "delete_selected", None) if editor is not None else None
    if callable(deleter):
        deleter()


def _export_web_demo(window: Any) -> None:
    if _is_web_runtime():
        return
    exporter = getattr(window, "export_web_demo", None) if window is not None else None
    if callable(exporter):
        exporter()


def _quit_app(window: Any) -> None:
    if _is_web_runtime():
        return
    closer = getattr(window, "close", None) if window is not None else None
    if callable(closer):
        closer()


def get_editor_actions(controller: Any | None, _window: Any | None) -> list[EditorAction]:
    actions: list[EditorAction] = [
        EditorAction(
            id="editor.light_tool.toggle",
            title="Toggle Light Tool",
            keywords=("light", "lighting", "tool"),
            group="Scene",
            shortcut="L",
            enabled=_enabled_always,
            run=_toggle_lights_tool,
            in_palette=True,
            in_menu=True,
            menu_label="Lights Tool",
        ),
        EditorAction(
            id="editor.occluder_tool.toggle",
            title="Toggle Occluder Tool",
            keywords=("occluder", "shadow", "polygon"),
            group="Scene",
            shortcut="O",
            enabled=_enabled_always,
            run=_toggle_occluder_tool,
            in_palette=True,
            in_menu=True,
            menu_label="Occluders Tool",
        ),
        EditorAction(
            id="editor.entity_panels.toggle",
            title="Toggle Entity Panels",
            keywords=("entity", "outliner", "inspector", "panels"),
            group="View",
            shortcut="Ctrl+E",
            enabled=_enabled_always,
            run=_toggle_entity_panels,
            in_palette=True,
            in_menu=True,
            menu_label="Entity Panels",
        ),
        EditorAction(
            id="editor.panel.project_explorer.toggle",
            title="Toggle Project Explorer",
            keywords=("panel", "project", "explorer", "files"),
            group="View",
            shortcut="Ctrl+Alt+4",
            enabled=_enabled_always,
            run=_toggle_project_explorer_panel,
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.project_explorer.reveal_current",
            title="Reveal in Project Explorer",
            keywords=("reveal", "project", "explorer", "scene", "asset", "show"),
            group="View",
            shortcut="Ctrl+Shift+E",
            enabled=_enabled_has_reveal_target,
            run=_reveal_current_in_project_explorer,
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.project_explorer.copy_path",
            title="Project Explorer: Copy Selected Paths",
            keywords=("project", "explorer", "files", "selection", "copy", "move", "delete", "paths", "path", "copy path", "clipboard"),
            group="Edit",
            shortcut="Ctrl+Shift+C",
            enabled=_enabled_project_explorer_selection,
            run=_copy_project_explorer_path,
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.project_explorer.copy_common_parent",
            title="Project Explorer: Copy Common Parent",
            keywords=("project", "explorer", "files", "selection", "copy", "move", "delete", "path", "parent", "folder", "clipboard"),
            group="Edit",
            shortcut="Ctrl+Shift+Alt+C",
            enabled=_enabled_project_explorer_selection,
            run=_copy_project_explorer_common_parent,
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.project_explorer.select_all",
            title="Project Explorer: Select All",
            keywords=("project", "explorer", "files", "selection", "copy", "move", "delete", "select", "all"),
            group="Edit",
            shortcut="Ctrl+A",
            enabled=_enabled_project_explorer_active,
            run=_project_explorer_select_all,
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.project_explorer.clear_selection",
            title="Project Explorer: Clear Selection",
            keywords=("project", "explorer", "files", "selection", "copy", "move", "delete", "clear"),
            group="Edit",
            shortcut="Escape",
            enabled=_enabled_project_explorer_active,
            run=_project_explorer_clear_selection,
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.project_explorer.invert_selection",
            title="Project Explorer: Invert Selection",
            keywords=("project", "explorer", "files", "selection", "copy", "move", "delete", "invert"),
            group="Edit",
            shortcut="Ctrl+I",
            enabled=_enabled_project_explorer_active,
            run=_project_explorer_invert_selection,
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.project_explorer.delete_selected",
            title="Project Explorer: Delete Selected",
            keywords=("project", "explorer", "files", "selection", "copy", "move", "delete"),
            group="Edit",
            shortcut="",
            enabled=_enabled_project_explorer_selection,
            run=_project_explorer_delete_selected,
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.project_explorer.safe_rename_asset",
            title="Safe Rename Asset",
            keywords=("rename", "asset", "refactor", "references", "project", "explorer"),
            group="Edit",
            shortcut="F2",
            enabled=_enabled_project_explorer_file_selection,
            run=_safe_rename_selected_asset,
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.project_explorer.safe_move_asset",
            title="Project Explorer: Move Selected...",
            keywords=("project", "explorer", "files", "selection", "copy", "move", "delete", "asset", "refactor", "references"),
            group="Edit",
            shortcut="Ctrl+Shift+M",
            enabled=_enabled_project_explorer_file_selection,
            run=_safe_move_selected_asset,
            in_palette=True,
            in_menu=True,
        ),
        # --- Inline Rename Actions (not in palette/menu, scoped to inline rename mode) ---
        EditorAction(
            id="editor.project_explorer.inline_rename.commit",
            title="Commit Inline Rename",
            keywords=(),
            group="Edit",
            shortcut="Enter",
            enabled=_enabled_inline_rename_active,
            run=_inline_rename_commit,
            in_palette=False,
            in_menu=False,
            shortcut_scope=SHORTCUT_SCOPE_INLINE_RENAME,
        ),
        EditorAction(
            id="editor.project_explorer.inline_rename.cancel",
            title="Cancel Inline Rename",
            keywords=(),
            group="Edit",
            shortcut="Escape",
            enabled=_enabled_inline_rename_active,
            run=_inline_rename_cancel,
            in_palette=False,
            in_menu=False,
            shortcut_scope=SHORTCUT_SCOPE_INLINE_RENAME,
        ),
        EditorAction(
            id="editor.project_explorer.inline_rename.backspace",
            title="Inline Rename Backspace",
            keywords=(),
            group="Edit",
            shortcut="Backspace",
            enabled=_enabled_inline_rename_active,
            run=_inline_rename_backspace,
            in_palette=False,
            in_menu=False,
            shortcut_scope=SHORTCUT_SCOPE_INLINE_RENAME,
        ),
        EditorAction(
            id="editor.project_explorer.inline_rename.delete",
            title="Inline Rename Delete",
            keywords=(),
            group="Edit",
            shortcut="Delete",
            enabled=_enabled_inline_rename_active,
            run=_inline_rename_delete,
            in_palette=False,
            in_menu=False,
            shortcut_scope=SHORTCUT_SCOPE_INLINE_RENAME,
        ),
        # --- Inline Rename Cursor Navigation Actions ---
        EditorAction(
            id="editor.project_explorer.inline_rename.cursor_left",
            title="Inline Rename Cursor Left",
            keywords=(),
            group="Edit",
            shortcut="Left",
            enabled=_enabled_inline_rename_active,
            run=_inline_rename_cursor_left,
            in_palette=False,
            in_menu=False,
            shortcut_scope=SHORTCUT_SCOPE_INLINE_RENAME,
        ),
        EditorAction(
            id="editor.project_explorer.inline_rename.cursor_left_extend",
            title="Inline Rename Cursor Left Extend",
            keywords=(),
            group="Edit",
            shortcut="Shift+Left",
            enabled=_enabled_inline_rename_active,
            run=_inline_rename_cursor_left_extend,
            in_palette=False,
            in_menu=False,
            shortcut_scope=SHORTCUT_SCOPE_INLINE_RENAME,
        ),
        EditorAction(
            id="editor.project_explorer.inline_rename.cursor_right",
            title="Inline Rename Cursor Right",
            keywords=(),
            group="Edit",
            shortcut="Right",
            enabled=_enabled_inline_rename_active,
            run=_inline_rename_cursor_right,
            in_palette=False,
            in_menu=False,
            shortcut_scope=SHORTCUT_SCOPE_INLINE_RENAME,
        ),
        EditorAction(
            id="editor.project_explorer.inline_rename.cursor_right_extend",
            title="Inline Rename Cursor Right Extend",
            keywords=(),
            group="Edit",
            shortcut="Shift+Right",
            enabled=_enabled_inline_rename_active,
            run=_inline_rename_cursor_right_extend,
            in_palette=False,
            in_menu=False,
            shortcut_scope=SHORTCUT_SCOPE_INLINE_RENAME,
        ),
        EditorAction(
            id="editor.project_explorer.inline_rename.cursor_home",
            title="Inline Rename Cursor Home",
            keywords=(),
            group="Edit",
            shortcut="Home",
            enabled=_enabled_inline_rename_active,
            run=_inline_rename_cursor_home,
            in_palette=False,
            in_menu=False,
            shortcut_scope=SHORTCUT_SCOPE_INLINE_RENAME,
        ),
        EditorAction(
            id="editor.project_explorer.inline_rename.cursor_home_extend",
            title="Inline Rename Cursor Home Extend",
            keywords=(),
            group="Edit",
            shortcut="Shift+Home",
            enabled=_enabled_inline_rename_active,
            run=_inline_rename_cursor_home_extend,
            in_palette=False,
            in_menu=False,
            shortcut_scope=SHORTCUT_SCOPE_INLINE_RENAME,
        ),
        EditorAction(
            id="editor.project_explorer.inline_rename.cursor_end",
            title="Inline Rename Cursor End",
            keywords=(),
            group="Edit",
            shortcut="End",
            enabled=_enabled_inline_rename_active,
            run=_inline_rename_cursor_end,
            in_palette=False,
            in_menu=False,
            shortcut_scope=SHORTCUT_SCOPE_INLINE_RENAME,
        ),
        EditorAction(
            id="editor.project_explorer.inline_rename.cursor_end_extend",
            title="Inline Rename Cursor End Extend",
            keywords=(),
            group="Edit",
            shortcut="Shift+End",
            enabled=_enabled_inline_rename_active,
            run=_inline_rename_cursor_end_extend,
            in_palette=False,
            in_menu=False,
            shortcut_scope=SHORTCUT_SCOPE_INLINE_RENAME,
        ),
        EditorAction(
            id="editor.project_explorer.inline_rename.cursor_word_left",
            title="Inline Rename Cursor Word Left",
            keywords=(),
            group="Edit",
            shortcut="Ctrl+Left",
            enabled=_enabled_inline_rename_active,
            run=_inline_rename_cursor_word_left,
            in_palette=False,
            in_menu=False,
            shortcut_scope=SHORTCUT_SCOPE_INLINE_RENAME,
        ),
        EditorAction(
            id="editor.project_explorer.inline_rename.cursor_word_left_extend",
            title="Inline Rename Cursor Word Left Extend",
            keywords=(),
            group="Edit",
            shortcut="Ctrl+Shift+Left",
            enabled=_enabled_inline_rename_active,
            run=_inline_rename_cursor_word_left_extend,
            in_palette=False,
            in_menu=False,
            shortcut_scope=SHORTCUT_SCOPE_INLINE_RENAME,
        ),
        EditorAction(
            id="editor.project_explorer.inline_rename.cursor_word_right",
            title="Inline Rename Cursor Word Right",
            keywords=(),
            group="Edit",
            shortcut="Ctrl+Right",
            enabled=_enabled_inline_rename_active,
            run=_inline_rename_cursor_word_right,
            in_palette=False,
            in_menu=False,
            shortcut_scope=SHORTCUT_SCOPE_INLINE_RENAME,
        ),
        EditorAction(
            id="editor.project_explorer.inline_rename.cursor_word_right_extend",
            title="Inline Rename Cursor Word Right Extend",
            keywords=(),
            group="Edit",
            shortcut="Ctrl+Shift+Right",
            enabled=_enabled_inline_rename_active,
            run=_inline_rename_cursor_word_right_extend,
            in_palette=False,
            in_menu=False,
            shortcut_scope=SHORTCUT_SCOPE_INLINE_RENAME,
        ),
        EditorAction(
            id="editor.project_explorer.inline_rename.delete_prev_word",
            title="Inline Rename Delete Prev Word",
            keywords=(),
            group="Edit",
            shortcut="Ctrl+Backspace",
            enabled=_enabled_inline_rename_active,
            run=_inline_rename_delete_prev_word,
            in_palette=False,
            in_menu=False,
            shortcut_scope=SHORTCUT_SCOPE_INLINE_RENAME,
        ),
        EditorAction(
            id="editor.project_explorer.inline_rename.delete_next_word",
            title="Inline Rename Delete Next Word",
            keywords=(),
            group="Edit",
            shortcut="Ctrl+Delete",
            enabled=_enabled_inline_rename_active,
            run=_inline_rename_delete_next_word,
            in_palette=False,
            in_menu=False,
            shortcut_scope=SHORTCUT_SCOPE_INLINE_RENAME,
        ),
        EditorAction(
            id="editor.panel.outliner.toggle",
            title="Toggle Outliner",
            keywords=("panel", "outliner", "entities", "list"),
            group="View",
            shortcut="Ctrl+Alt+2",
            enabled=_enabled_always,
            run=_toggle_outliner_panel,
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.panel.inspector.toggle",
            title="Toggle Inspector",
            keywords=("panel", "inspector", "properties", "details"),
            group="View",
            shortcut="Ctrl+Alt+1",
            enabled=_enabled_always,
            run=_toggle_inspector_panel,
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.panel.history.toggle",
            title="Toggle History",
            keywords=("panel", "history", "undo", "stack"),
            group="View",
            shortcut="Ctrl+Alt+5",
            enabled=_enabled_always,
            run=_toggle_history_panel,
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.panel.problems.toggle",
            title="Toggle Problems",
            keywords=("panel", "problems", "lint", "issues"),
            group="View",
            shortcut="Ctrl+Alt+3",
            enabled=_enabled_always,
            run=_toggle_problems_panel,
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.problems.jump_to_selected",
            title="Jump to Selected Problem",
            keywords=("jump", "problem", "go", "navigate", "location", "line"),
            group="View",
            shortcut="Enter",
            enabled=_enabled_problems_can_jump,
            run=_action_problems_jump,
            in_palette=True,
            in_menu=True,
            menu_label="Jump to Problem",
        ),
        EditorAction(
            id="editor.problems.jump_to_selected_ctrl",
            title="Jump to Selected Problem (Ctrl)",
            keywords=(),
            group="View",
            shortcut="Ctrl+Enter",
            enabled=_enabled_problems_can_jump,
            run=_action_problems_jump,
            in_palette=False,
            in_menu=False,
        ),
        EditorAction(
            id="editor.problems.copy_location",
            title="Copy Problem Location",
            keywords=("copy", "problem", "location", "line", "path", "clipboard"),
            group="View",
            shortcut="Ctrl+Shift+L",
            enabled=_enabled_problems_panel_active,
            run=_action_problems_copy_location,
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.panel.prefab_variant_editor.toggle",
            title="Toggle Prefab Variant Editor",
            keywords=("panel", "prefab", "variant", "overrides"),
            group="View",
            shortcut="Ctrl+Alt+6",
            enabled=_enabled_always,
            run=_toggle_prefab_variant_editor,
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.find_everything.toggle",
            title="Find Everything",
            keywords=("find", "search", "launcher", "everything"),
            group="View",
            shortcut="Ctrl+K",
            enabled=_enabled_always,
            run=_toggle_find_everything,
            in_palette=False,
            in_menu=False,
        ),
        EditorAction(
            id="editor.scene_browser.open",
            title="Open Scene Browser",
            keywords=("scene", "browser", "open"),
            group="File",
            shortcut="Ctrl+Shift+O",
            enabled=_enabled_always,
            run=_open_scene_browser,
            in_palette=True,
            in_menu=True,
            menu_label="Open Scene...",
        ),
        EditorAction(
            id="editor.scene_switcher.toggle",
            title="Open Scene Switcher",
            keywords=("scene", "switcher", "open", "quick"),
            group="File",
            shortcut="Ctrl+O",
            enabled=_enabled_always,
            run=_toggle_scene_switcher,
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.scene.save",
            title="Save Scene",
            keywords=("save", "scene"),
            group="File",
            shortcut="Ctrl+S",
            enabled=_enabled_scene_dirty,
            run=_save_scene,
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.play.start",
            title="Play From Here",
            keywords=("play", "start", "test"),
            group=None,
            shortcut="F6",
            enabled=_enabled_always,
            run=_play_from_here,
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.play.stop",
            title="Stop Playing",
            keywords=("stop", "play", "return"),
            group=None,
            shortcut="F7",
            enabled=_enabled_always,
            run=_stop_playing,
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.lighting_preset.1",
            title="Apply Lighting Preset 1",
            keywords=("lighting", "preset", "1"),
            group=None,
            shortcut="",
            enabled=_enabled_always,
            run=lambda w: _apply_lighting_preset(w, 0),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.lighting_preset.2",
            title="Apply Lighting Preset 2",
            keywords=("lighting", "preset", "2"),
            group=None,
            shortcut="",
            enabled=_enabled_always,
            run=lambda w: _apply_lighting_preset(w, 1),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.lighting_preset.3",
            title="Apply Lighting Preset 3",
            keywords=("lighting", "preset", "3"),
            group=None,
            shortcut="",
            enabled=_enabled_always,
            run=lambda w: _apply_lighting_preset(w, 2),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.lighting_preset.4",
            title="Apply Lighting Preset 4",
            keywords=("lighting", "preset", "4"),
            group=None,
            shortcut="",
            enabled=_enabled_always,
            run=lambda w: _apply_lighting_preset(w, 3),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="runtime.fog.toggle",
            title="Toggle Fog",
            keywords=("fog", "atmosphere"),
            group=None,
            shortcut="",
            enabled=_enabled_always,
            run=_toggle_fog,
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="runtime.soft_shadows.toggle",
            title="Toggle Soft Shadows",
            keywords=("soft", "shadows", "lighting"),
            group=None,
            shortcut="",
            enabled=_enabled_always,
            run=_toggle_soft_shadows,
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.asset_browser.toggle",
            title="Toggle Asset Browser",
            keywords=("asset", "browser", "view"),
            group="View",
            shortcut="Ctrl+Shift+A",
            enabled=_enabled_always,
            run=_toggle_asset_browser,
            in_palette=False,
            in_menu=True,
            menu_label="Asset Browser",
        ),
        EditorAction(
            id="editor.command_palette.toggle",
            title="Toggle Command Palette",
            keywords=("command", "palette"),
            group="View",
            shortcut="Ctrl+P",
            enabled=_enabled_always,
            run=_toggle_command_palette,
            in_palette=False,
            in_menu=True,
            menu_label="Command Palette",
        ),
        EditorAction(
            id="editor.dock_left.toggle",
            title="Toggle Left Dock",
            keywords=("dock", "left", "toggle"),
            group="View",
            shortcut="Ctrl+L",
            enabled=_enabled_always,
            run=_toggle_left_dock,
            in_palette=False,
            in_menu=False,
        ),
        EditorAction(
            id="editor.dock_right.toggle",
            title="Toggle Right Dock",
            keywords=("dock", "right", "toggle"),
            group="View",
            shortcut="Ctrl+R",
            enabled=_enabled_right_dock_toggle,
            run=_toggle_right_dock,
            in_palette=False,
            in_menu=False,
        ),
        EditorAction(
            id="editor.viewport_maximize.toggle",
            title="Toggle Viewport Maximize",
            keywords=("viewport", "maximize", "toggle"),
            group="View",
            shortcut="Ctrl+Space",
            enabled=_enabled_always,
            run=_toggle_viewport_maximized,
            in_palette=False,
            in_menu=False,
        ),
        EditorAction(
            id="editor.scene_browser.toggle",
            title="Scene Browser",
            keywords=("scene", "browser", "view"),
            group="View",
            shortcut="",
            enabled=_enabled_always,
            run=_open_scene_browser,
            in_palette=False,
            in_menu=True,
            menu_label="Scene Browser",
        ),
        EditorAction(
            id="editor.ghost_originals.toggle",
            title="Toggle Ghost Originals",
            keywords=("ghost", "originals", "alt", "dup"),
            group="View",
            shortcut="",
            enabled=_enabled_always,
            run=_toggle_ghost_originals,
            in_palette=False,
            in_menu=True,
            menu_label="Ghost Originals During Alt-Dup",
        ),
        EditorAction(
            id="editor.prefab_palette.toggle",
            title="Prefab Palette",
            keywords=("prefab", "palette"),
            group="Scene",
            shortcut="P",
            enabled=_enabled_always,
            run=_toggle_prefab_palette,
            in_palette=False,
            in_menu=True,
            menu_label="Prefab Palette",
        ),
        EditorAction(
            id="editor.history.undo",
            title="Undo",
            keywords=("undo", "history"),
            group="Edit",
            shortcut="Ctrl+Z",
            enabled=_enabled_can_undo,
            run=_undo,
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.history.redo",
            title="Redo",
            keywords=("redo", "history"),
            group="Edit",
            shortcut="Ctrl+Y",
            enabled=_enabled_can_redo,
            run=_redo,
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.duplicate",
            title="Duplicate",
            keywords=("duplicate",),
            group="Edit",
            shortcut="Ctrl+D",
            enabled=_enabled_has_selection,
            run=_duplicate,
            in_palette=False,
            in_menu=True,
        ),
        EditorAction(
            id="editor.delete",
            title="Delete",
            keywords=("delete",),
            group="Edit",
            shortcut="Del",
            enabled=_enabled_has_selection_or_project_explorer,
            run=_delete,
            in_palette=False,
            in_menu=True,
        ),
        EditorAction(
            id="app.export_web_demo",
            title="Export Web Demo...",
            keywords=("export", "web", "demo"),
            group="File",
            shortcut="",
            enabled=_enabled_not_web,
            run=_export_web_demo,
            in_palette=False,
            in_menu=True,
        ),
        EditorAction(
            id="app.quit",
            title="Quit",
            keywords=("quit", "exit"),
            group="File",
            shortcut="Alt+F4",
            enabled=_enabled_not_web,
            run=_quit_app,
            in_palette=False,
            in_menu=True,
        ),
        EditorAction(
            id="editor.hd2d.preset.soft.apply",
            title="HD-2D Preset: Soft",
            keywords=("hd2d", "preset", "look", "soft", "style"),
            group="View",
            shortcut="",
            enabled=_enabled_scene_loaded,
            run=lambda w: _apply_hd2d_preset(w, "soft"),
            in_palette=True,
            in_menu=True,
            menu_label="Soft",
        ),
        EditorAction(
            id="editor.hd2d.preset.crisp.apply",
            title="HD-2D Preset: Crisp",
            keywords=("hd2d", "preset", "look", "crisp", "style"),
            group="View",
            shortcut="",
            enabled=_enabled_scene_loaded,
            run=lambda w: _apply_hd2d_preset(w, "crisp"),
            in_palette=True,
            in_menu=True,
            menu_label="Crisp",
        ),
        EditorAction(
            id="editor.hd2d.preset.noir.apply",
            title="HD-2D Preset: Noir",
            keywords=("hd2d", "preset", "look", "noir", "style"),
            group="View",
            shortcut="",
            enabled=_enabled_scene_loaded,
            run=lambda w: _apply_hd2d_preset(w, "noir"),
            in_palette=True,
            in_menu=True,
            menu_label="Noir",
        ),
        EditorAction(
            id="editor.hd2d.preset.dreamy.apply",
            title="HD-2D Preset: Dreamy",
            keywords=("hd2d", "preset", "look", "dreamy", "style"),
            group="View",
            shortcut="",
            enabled=_enabled_scene_loaded,
            run=lambda w: _apply_hd2d_preset(w, "dreamy"),
            in_palette=True,
            in_menu=True,
            menu_label="Dreamy",
        ),
        EditorAction(
            id="editor.hd2d.defaults.upgrade_scene",
            title="Upgrade Scene to HD2D Defaults",
            keywords=("hd2d", "defaults", "upgrade", "scene", "style"),
            group="View",
            shortcut="",
            enabled=_enabled_scene_loaded,
            run=_upgrade_scene_to_hd2d_defaults,
            in_palette=True,
            in_menu=False,
        ),
        # HD-2D Settings Panel toggle actions
        EditorAction(
            id="editor.hd2d.toggle.shadows",
            title="HD-2D: Toggle Shadows",
            keywords=("hd2d", "shadows", "toggle", "setting"),
            group="View",
            shortcut="",
            enabled=_enabled_scene_loaded,
            run=lambda w: _toggle_hd2d_setting(w, "shadows_enabled"),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.hd2d.toggle.shadows_contact",
            title="HD-2D: Toggle Contact Shadows",
            keywords=("hd2d", "shadows", "contact", "toggle", "setting"),
            group="View",
            shortcut="",
            enabled=_enabled_scene_loaded,
            run=lambda w: _toggle_hd2d_setting(w, "shadows_contact_enabled"),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.hd2d.toggle.shadows_ao",
            title="HD-2D: Toggle Ambient Occlusion",
            keywords=("hd2d", "shadows", "ao", "ambient", "occlusion", "toggle", "setting"),
            group="View",
            shortcut="",
            enabled=_enabled_scene_loaded,
            run=lambda w: _toggle_hd2d_setting(w, "shadows_ao_enabled"),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.hd2d.toggle.depth_tint",
            title="HD-2D: Toggle Depth Tint",
            keywords=("hd2d", "tint", "depth", "toggle", "setting"),
            group="View",
            shortcut="",
            enabled=_enabled_scene_loaded,
            run=lambda w: _toggle_hd2d_setting(w, "depth_tint_enabled"),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.hd2d.toggle.outline",
            title="HD-2D: Toggle Outline",
            keywords=("hd2d", "outline", "toggle", "setting"),
            group="View",
            shortcut="",
            enabled=_enabled_scene_loaded,
            run=lambda w: _toggle_hd2d_setting(w, "outline_enabled"),
            in_palette=True,
            in_menu=False,
        ),
        # HD-2D Settings Panel slider actions (increase/decrease)
        EditorAction(
            id="editor.hd2d.tint_strength.increase",
            title="HD-2D: Increase Tint Strength",
            keywords=("hd2d", "tint", "strength", "increase"),
            group="View",
            shortcut="",
            enabled=_enabled_scene_loaded,
            run=lambda w: _adjust_hd2d_slider(w, "depth_tint_strength", 0.05),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.hd2d.tint_strength.decrease",
            title="HD-2D: Decrease Tint Strength",
            keywords=("hd2d", "tint", "strength", "decrease"),
            group="View",
            shortcut="",
            enabled=_enabled_scene_loaded,
            run=lambda w: _adjust_hd2d_slider(w, "depth_tint_strength", -0.05),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.hd2d.outline_strength.increase",
            title="HD-2D: Increase Outline Strength",
            keywords=("hd2d", "outline", "strength", "increase"),
            group="View",
            shortcut="",
            enabled=_enabled_scene_loaded,
            run=lambda w: _adjust_hd2d_slider(w, "outline_strength", 0.05),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.hd2d.outline_strength.decrease",
            title="HD-2D: Decrease Outline Strength",
            keywords=("hd2d", "outline", "strength", "decrease"),
            group="View",
            shortcut="",
            enabled=_enabled_scene_loaded,
            run=lambda w: _adjust_hd2d_slider(w, "outline_strength", -0.05),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.hd2d.outline_radius.increase",
            title="HD-2D: Increase Outline Radius",
            keywords=("hd2d", "outline", "radius", "increase"),
            group="View",
            shortcut="",
            enabled=_enabled_scene_loaded,
            run=lambda w: _adjust_hd2d_slider(w, "outline_radius_px", 1),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.hd2d.outline_radius.decrease",
            title="HD-2D: Decrease Outline Radius",
            keywords=("hd2d", "outline", "radius", "decrease"),
            group="View",
            shortcut="",
            enabled=_enabled_scene_loaded,
            run=lambda w: _adjust_hd2d_slider(w, "outline_radius_px", -1),
            in_palette=True,
            in_menu=False,
        ),
        # HD-2D Entity Override toggle actions (when entity is selected)
        EditorAction(
            id="editor.entity.hd2d.toggle.shadow",
            title="Entity HD-2D: Toggle Shadow Override",
            keywords=("entity", "hd2d", "shadow", "toggle", "override"),
            group="Entity",
            shortcut="",
            enabled=_enabled_entity_selected,
            run=lambda w: _toggle_entity_hd2d_override(w, "shadow_enabled"),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.entity.hd2d.toggle.shadow_contact",
            title="Entity HD-2D: Toggle Contact Shadow Override",
            keywords=("entity", "hd2d", "shadow", "contact", "toggle", "override"),
            group="Entity",
            shortcut="",
            enabled=_enabled_entity_selected,
            run=lambda w: _toggle_entity_hd2d_override(w, "shadow_contact_enabled"),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.entity.hd2d.toggle.shadow_ao",
            title="Entity HD-2D: Toggle AO Shadow Override",
            keywords=("entity", "hd2d", "shadow", "ao", "ambient", "occlusion", "toggle", "override"),
            group="Entity",
            shortcut="",
            enabled=_enabled_entity_selected,
            run=lambda w: _toggle_entity_hd2d_override(w, "shadow_ao_enabled"),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.entity.hd2d.toggle.depth_tint",
            title="Entity HD-2D: Toggle Depth Tint Override",
            keywords=("entity", "hd2d", "tint", "depth", "toggle", "override"),
            group="Entity",
            shortcut="",
            enabled=_enabled_entity_selected,
            run=lambda w: _toggle_entity_hd2d_override(w, "depth_tint_enabled"),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.entity.hd2d.toggle.outline",
            title="Entity HD-2D: Toggle Outline Override",
            keywords=("entity", "hd2d", "outline", "toggle", "override"),
            group="Entity",
            shortcut="",
            enabled=_enabled_entity_selected,
            run=lambda w: _toggle_entity_hd2d_override(w, "outline_enabled"),
            in_palette=True,
            in_menu=False,
        ),
        # HD-2D Entity Override slider actions
        EditorAction(
            id="editor.entity.hd2d.tint_strength.increase",
            title="Entity HD-2D: Increase Tint Strength Override",
            keywords=("entity", "hd2d", "tint", "strength", "increase", "override"),
            group="Entity",
            shortcut="",
            enabled=_enabled_entity_selected,
            run=lambda w: _adjust_entity_hd2d_slider(w, "depth_tint_strength", 0.05),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.entity.hd2d.tint_strength.decrease",
            title="Entity HD-2D: Decrease Tint Strength Override",
            keywords=("entity", "hd2d", "tint", "strength", "decrease", "override"),
            group="Entity",
            shortcut="",
            enabled=_enabled_entity_selected,
            run=lambda w: _adjust_entity_hd2d_slider(w, "depth_tint_strength", -0.05),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.entity.hd2d.outline_strength.increase",
            title="Entity HD-2D: Increase Outline Strength Override",
            keywords=("entity", "hd2d", "outline", "strength", "increase", "override"),
            group="Entity",
            shortcut="",
            enabled=_enabled_entity_selected,
            run=lambda w: _adjust_entity_hd2d_slider(w, "outline_strength", 0.05),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.entity.hd2d.outline_strength.decrease",
            title="Entity HD-2D: Decrease Outline Strength Override",
            keywords=("entity", "hd2d", "outline", "strength", "decrease", "override"),
            group="Entity",
            shortcut="",
            enabled=_enabled_entity_selected,
            run=lambda w: _adjust_entity_hd2d_slider(w, "outline_strength", -0.05),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.entity.hd2d.outline_radius.increase",
            title="Entity HD-2D: Increase Outline Radius Override",
            keywords=("entity", "hd2d", "outline", "radius", "increase", "override"),
            group="Entity",
            shortcut="",
            enabled=_enabled_entity_selected,
            run=lambda w: _adjust_entity_hd2d_slider(w, "outline_radius_px", 1),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.entity.hd2d.outline_radius.decrease",
            title="Entity HD-2D: Decrease Outline Radius Override",
            keywords=("entity", "hd2d", "outline", "radius", "decrease", "override"),
            group="Entity",
            shortcut="",
            enabled=_enabled_entity_selected,
            run=lambda w: _adjust_entity_hd2d_slider(w, "outline_radius_px", -1),
            in_palette=True,
            in_menu=False,
        ),
        # HD-2D Entity Override clipboard actions (copy/paste/clear)
        EditorAction(
            id="editor.hd2d.entity_overrides.copy",
            title="Entity HD-2D: Copy Overrides",
            keywords=("entity", "hd2d", "override", "copy", "clipboard"),
            group="Entity",
            shortcut="Ctrl+Alt+C",
            enabled=_enabled_entity_selected,
            run=_copy_entity_hd2d_overrides,
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.hd2d.entity_overrides.paste",
            title="Entity HD-2D: Paste Overrides (Merge)",
            keywords=("entity", "hd2d", "override", "paste", "clipboard", "merge"),
            group="Entity",
            shortcut="Ctrl+Alt+V",
            enabled=_enabled_hd2d_clipboard_has_data,
            run=_paste_entity_hd2d_overrides,
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.hd2d.entity_overrides.paste_replace",
            title="Entity HD-2D: Paste Overrides (Replace)",
            keywords=("entity", "hd2d", "override", "paste", "clipboard", "replace"),
            group="Entity",
            shortcut="Ctrl+Shift+Alt+V",
            enabled=_enabled_hd2d_clipboard_has_data,
            run=_paste_replace_entity_hd2d_overrides,
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.hd2d.entity_overrides.clear_all",
            title="Entity HD-2D: Clear All Overrides",
            keywords=("entity", "hd2d", "override", "clear", "all", "reset"),
            group="Entity",
            shortcut="Ctrl+Shift+Backspace",
            enabled=_enabled_entity_has_overrides,
            run=_clear_all_entity_hd2d_overrides,
            in_palette=True,
            in_menu=False,
        ),
        # HD-2D Entity Override batch actions
        EditorAction(
            id="editor.hd2d.entity_overrides.batch_paste_radius_merge",
            title="Entity HD-2D: Batch Paste Overrides (Radius, Merge)",
            keywords=("entity", "hd2d", "override", "batch", "paste", "radius", "merge", "nearby"),
            group="Entity",
            shortcut="Ctrl+Shift+B",
            enabled=_enabled_hd2d_clipboard_has_data,
            run=_batch_paste_hd2d_overrides_merge,
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.hd2d.entity_overrides.batch_paste_radius_replace",
            title="Entity HD-2D: Batch Paste Overrides (Radius, Replace)",
            keywords=("entity", "hd2d", "override", "batch", "paste", "radius", "replace", "nearby"),
            group="Entity",
            shortcut="Ctrl+Shift+Alt+B",
            enabled=_enabled_hd2d_clipboard_has_data,
            run=_batch_paste_hd2d_overrides_replace,
            in_palette=True,
            in_menu=False,
        ),
        # HD-2D batch radius adjustment actions
        EditorAction(
            id="editor.hd2d.entity_overrides.batch_radius.increase",
            title="Entity HD-2D: Increase Batch Radius (+16px)",
            keywords=("entity", "hd2d", "batch", "radius", "increase", "expand"),
            group="Entity",
            shortcut="Ctrl+Alt+]",
            enabled=_enabled_always,
            run=lambda w: _adjust_hd2d_batch_radius(w, 16),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.hd2d.entity_overrides.batch_radius.decrease",
            title="Entity HD-2D: Decrease Batch Radius (-16px)",
            keywords=("entity", "hd2d", "batch", "radius", "decrease", "shrink"),
            group="Entity",
            shortcut="Ctrl+Alt+[",
            enabled=_enabled_always,
            run=lambda w: _adjust_hd2d_batch_radius(w, -16),
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.hd2d.entity_overrides.batch_radius.reset",
            title="Entity HD-2D: Reset Batch Radius (96px)",
            keywords=("entity", "hd2d", "batch", "radius", "reset", "default"),
            group="Entity",
            shortcut="Ctrl+Alt+\\\\",
            enabled=_enabled_always,
            run=_reset_hd2d_batch_radius,
            in_palette=True,
            in_menu=False,
        ),
        EditorAction(
            id="editor.background_planes.add",
            title="Background Planes: Add",
            keywords=("background", "plane", "planes", "parallax", "add"),
            group="Scene",
            shortcut="Ctrl+Alt+B",
            enabled=_enabled_always,
            run=_action_planes_add,
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.background_planes.duplicate",
            title="Background Planes: Duplicate Selected",
            keywords=("background", "plane", "planes", "parallax", "duplicate", "copy"),
            group="Scene",
            shortcut="Ctrl+Alt+D",
            enabled=_enabled_plane_selected,
            run=_action_planes_duplicate,
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.background_planes.remove",
            title="Background Planes: Remove Selected",
            keywords=("background", "plane", "planes", "parallax", "remove", "delete"),
            group="Scene",
            shortcut="Ctrl+Alt+Backspace",
            enabled=_enabled_plane_selected,
            run=_action_planes_remove,
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.background_planes.move_up",
            title="Background Planes: Move Up",
            keywords=("background", "plane", "planes", "parallax", "move", "up", "layer"),
            group="Scene",
            shortcut="Alt+PageUp",
            enabled=_enabled_plane_selected,
            run=lambda w: _action_planes_move(w, "up"),
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.background_planes.move_down",
            title="Background Planes: Move Down",
            keywords=("background", "plane", "planes", "parallax", "move", "down", "layer"),
            group="Scene",
            shortcut="Alt+PageDown",
            enabled=_enabled_plane_selected,
            run=lambda w: _action_planes_move(w, "down"),
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.background_planes.select_prev",
            title="Background Planes: Select Previous",
            keywords=("background", "plane", "planes", "parallax", "select", "previous", "cycle"),
            group="Scene",
            shortcut="Ctrl+Alt+PageUp",
            enabled=_enabled_planes_exist,
            run=lambda w: _action_planes_select(w, "prev"),
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.background_planes.select_next",
            title="Background Planes: Select Next",
            keywords=("background", "plane", "planes", "parallax", "select", "next", "cycle"),
            group="Scene",
            shortcut="Ctrl+Alt+PageDown",
            enabled=_enabled_planes_exist,
            run=lambda w: _action_planes_select(w, "next"),
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.background_planes.toggle_repeat_x",
            title="Background Planes: Toggle Tiling X",
            keywords=("background", "plane", "planes", "parallax", "tiling", "tile", "repeat", "x"),
            group="Scene",
            shortcut="Ctrl+Alt+X",
            enabled=_enabled_plane_selected,
            run=lambda w: _action_planes_toggle_repeat(w, "x"),
            in_palette=True,
            in_menu=True,
        ),
        EditorAction(
            id="editor.background_planes.toggle_repeat_y",
            title="Background Planes: Toggle Tiling Y",
            keywords=("background", "plane", "planes", "parallax", "tiling", "tile", "repeat", "y"),
            group="Scene",
            shortcut="Ctrl+Alt+Y",
            enabled=_enabled_plane_selected,
            run=lambda w: _action_planes_toggle_repeat(w, "y"),
            in_palette=True,
            in_menu=True,
        ),
    ]
    overrides = getattr(controller, "_keymap_overrides", None) if controller is not None else None
    if isinstance(overrides, dict) and overrides:
        from engine.editor.keymap_override_model import apply_keymap_overrides  # noqa: PLC0415

        updated, _, _ = apply_keymap_overrides(actions, overrides)
        return [action for action in updated if isinstance(action, EditorAction)]
    return actions


def get_palette_actions(controller: Any | None, window: Any | None) -> list[EditorAction]:
    return [action for action in get_editor_actions(controller, window) if action.in_palette]


def get_menu_actions(controller: Any | None, window: Any | None) -> list[EditorAction]:
    return [action for action in get_editor_actions(controller, window) if action.in_menu and action.group]


def find_action(actions: Iterable[EditorAction], action_id: str) -> EditorAction | None:
    wanted = str(action_id or "").strip()
    if not wanted:
        return None
    for action in actions:
        if action.id == wanted:
            return action
    return None


def run_editor_action(action_id: str, controller: Any, window: Any) -> bool:
    actions = get_editor_actions(controller, window)
    action = find_action(actions, action_id)
    if action is None:
        return False
    if not action.enabled(controller, window):
        return False
    action.run(window)
    return True
