"""Unified editor action registry used by menus and find/command palettes."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
import copy
from types import SimpleNamespace
from typing import Any, Callable, Iterable, cast

from engine.editor.editor_actions_registry import ActionDef, DEFAULT_ACTION_DEFS
from engine.editor.editor_dock_query import get_dock_snapshot

from engine.runtime_settings import ensure_runtime_settings

# Shortcut scope constants
SHORTCUT_SCOPE_GLOBAL = "global"
SHORTCUT_SCOPE_INLINE_RENAME = "text_input.inline_rename"
SHORTCUT_SCOPE_PROJECT_EXPLORER = "project_explorer"
SHORTCUT_SCOPE_PROJECT_EXPLORER_CONTEXT_MENU = "project_explorer.context_menu"


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
    undo_ctrl = getattr(controller, "undo", None)
    if undo_ctrl is not None:
        from engine.editor.editor_undo_controller import EditorUndoController  # noqa: PLC0415

        if isinstance(undo_ctrl, EditorUndoController):
            return bool(undo_ctrl.can_undo())
    return False


def _enabled_can_redo(controller: Any, _window: Any) -> bool:
    undo_ctrl = getattr(controller, "undo", None)
    if undo_ctrl is not None:
        from engine.editor.editor_undo_controller import EditorUndoController  # noqa: PLC0415

        if isinstance(undo_ctrl, EditorUndoController):
            return bool(undo_ctrl.can_redo())
    return False


def _enabled_scene_dirty(controller: Any, _window: Any) -> bool:
    return bool(getattr(controller, "scene_dirty", False))


def _enabled_not_web(_controller: Any, _window: Any) -> bool:
    return not _is_web_runtime()


def _enabled_multiselect(controller: Any, _window: Any) -> bool:
    """Return True if 2+ entities are selected."""
    selected_ids = getattr(controller, "_selected_entity_ids", [])
    return len(selected_ids) >= 2


def _enabled_multiselect_3(controller: Any, _window: Any) -> bool:
    """Return True if 3+ entities are selected (for distribute)."""
    selected_ids = getattr(controller, "_selected_entity_ids", [])
    return len(selected_ids) >= 3


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
    snapshot = get_dock_snapshot(controller)
    return bool(snapshot is not None and snapshot.right_tab == "Problems")


def _enabled_problems_can_jump(controller: Any, _window: Any) -> bool:
    """True when Problems panel is active, has issues, and selected issue is jump-supported."""
    snapshot = get_dock_snapshot(controller)
    if snapshot is None or snapshot.right_tab != "Problems":
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


def _action_planes_move_up(window: Any) -> None:
    _action_planes_move(window, "up")


def _action_planes_move_down(window: Any) -> None:
    _action_planes_move(window, "down")


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


def _action_planes_toggle_repeat_x(window: Any) -> None:
    _action_planes_toggle_repeat(window, "x")


def _action_planes_toggle_repeat_y(window: Any) -> None:
    _action_planes_toggle_repeat(window, "y")


# -------------------------------------------------------------------------
# Align / Distribute Actions
# -------------------------------------------------------------------------

def _action_align_left(window: Any) -> None:
    editor = _get_editor(window)
    if editor is not None:
        align = getattr(editor, "align", None)
        if align is not None:
            align.align_left()


def _action_align_right(window: Any) -> None:
    editor = _get_editor(window)
    if editor is not None:
        align = getattr(editor, "align", None)
        if align is not None:
            align.align_right()


def _action_align_top(window: Any) -> None:
    editor = _get_editor(window)
    if editor is not None:
        align = getattr(editor, "align", None)
        if align is not None:
            align.align_top()


def _action_align_bottom(window: Any) -> None:
    editor = _get_editor(window)
    if editor is not None:
        align = getattr(editor, "align", None)
        if align is not None:
            align.align_bottom()


def _action_align_center_horizontal(window: Any) -> None:
    editor = _get_editor(window)
    if editor is not None:
        align = getattr(editor, "align", None)
        if align is not None:
            align.align_center_horizontal()


def _action_align_center_vertical(window: Any) -> None:
    editor = _get_editor(window)
    if editor is not None:
        align = getattr(editor, "align", None)
        if align is not None:
            align.align_center_vertical()


def _action_distribute_horizontal(window: Any) -> None:
    editor = _get_editor(window)
    if editor is not None:
        align = getattr(editor, "align", None)
        if align is not None:
            align.distribute_horizontal()


def _action_distribute_vertical(window: Any) -> None:
    editor = _get_editor(window)
    if editor is not None:
        align = getattr(editor, "align", None)
        if align is not None:
            align.distribute_vertical()


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


def _action_planes_select_prev(window: Any) -> None:
    _action_planes_select(window, "prev")


def _action_planes_select_next(window: Any) -> None:
    _action_planes_select(window, "next")


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


def _action_apply_hd2d_preset_soft(window: Any) -> None:
    _apply_hd2d_preset(window, "soft")


def _action_apply_hd2d_preset_crisp(window: Any) -> None:
    _apply_hd2d_preset(window, "crisp")


def _action_apply_hd2d_preset_noir(window: Any) -> None:
    _apply_hd2d_preset(window, "noir")


def _action_apply_hd2d_preset_dreamy(window: Any) -> None:
    _apply_hd2d_preset(window, "dreamy")


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


def _action_toggle_hd2d_shadows_enabled(window: Any) -> None:
    _toggle_hd2d_setting(window, "shadows_enabled")


def _action_toggle_hd2d_shadows_contact_enabled(window: Any) -> None:
    _toggle_hd2d_setting(window, "shadows_contact_enabled")


def _action_toggle_hd2d_shadows_ao_enabled(window: Any) -> None:
    _toggle_hd2d_setting(window, "shadows_ao_enabled")


def _action_toggle_hd2d_depth_tint_enabled(window: Any) -> None:
    _toggle_hd2d_setting(window, "depth_tint_enabled")


def _action_toggle_hd2d_outline_enabled(window: Any) -> None:
    _toggle_hd2d_setting(window, "outline_enabled")


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


def _action_adjust_hd2d_depth_tint_strength_up(window: Any) -> None:
    _adjust_hd2d_slider(window, "depth_tint_strength", 0.05)


def _action_adjust_hd2d_depth_tint_strength_down(window: Any) -> None:
    _adjust_hd2d_slider(window, "depth_tint_strength", -0.05)


def _action_adjust_hd2d_outline_strength_up(window: Any) -> None:
    _adjust_hd2d_slider(window, "outline_strength", 0.05)


def _action_adjust_hd2d_outline_strength_down(window: Any) -> None:
    _adjust_hd2d_slider(window, "outline_strength", -0.05)


def _action_adjust_hd2d_outline_radius_up(window: Any) -> None:
    _adjust_hd2d_slider(window, "outline_radius_px", 1)


def _action_adjust_hd2d_outline_radius_down(window: Any) -> None:
    _adjust_hd2d_slider(window, "outline_radius_px", -1)


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


def _action_toggle_entity_shadow_enabled(window: Any) -> None:
    _toggle_entity_hd2d_override(window, "shadow_enabled")


def _action_toggle_entity_shadow_contact_enabled(window: Any) -> None:
    _toggle_entity_hd2d_override(window, "shadow_contact_enabled")


def _action_toggle_entity_shadow_ao_enabled(window: Any) -> None:
    _toggle_entity_hd2d_override(window, "shadow_ao_enabled")


def _action_toggle_entity_depth_tint_enabled(window: Any) -> None:
    _toggle_entity_hd2d_override(window, "depth_tint_enabled")


def _action_toggle_entity_outline_enabled(window: Any) -> None:
    _toggle_entity_hd2d_override(window, "outline_enabled")


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


def _action_adjust_entity_depth_tint_strength_up(window: Any) -> None:
    _adjust_entity_hd2d_slider(window, "depth_tint_strength", 0.05)


def _action_adjust_entity_depth_tint_strength_down(window: Any) -> None:
    _adjust_entity_hd2d_slider(window, "depth_tint_strength", -0.05)


def _action_adjust_entity_outline_strength_up(window: Any) -> None:
    _adjust_entity_hd2d_slider(window, "outline_strength", 0.05)


def _action_adjust_entity_outline_strength_down(window: Any) -> None:
    _adjust_entity_hd2d_slider(window, "outline_strength", -0.05)


def _action_adjust_entity_outline_radius_up(window: Any) -> None:
    _adjust_entity_hd2d_slider(window, "outline_radius_px", 1)


def _action_adjust_entity_outline_radius_down(window: Any) -> None:
    _adjust_entity_hd2d_slider(window, "outline_radius_px", -1)


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


def _action_adjust_hd2d_batch_radius_up(window: Any) -> None:
    _adjust_hd2d_batch_radius(window, 16)


def _action_adjust_hd2d_batch_radius_down(window: Any) -> None:
    _adjust_hd2d_batch_radius(window, -16)


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
    editor = _get_editor(window)
    if editor is None:
        return
    workspace = getattr(editor, "workspace", None)
    if workspace is None:
        return
    saver = getattr(workspace, "save_hd2d_batch_radius", None)
    if not callable(saver):
        return
    saver(radius)


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
    dock_ctl = getattr(editor, "dock", None) if editor is not None else None
    setter = getattr(dock_ctl, "apply_tab_change", None) if dock_ctl is not None else None
    if callable(setter):
        setter(editor, dock, tab)


def _toggle_dock_tab(window: Any, dock: str, tab: str) -> None:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    if dock == "left":
        snapshot = get_dock_snapshot(editor)
        dock_ctl = getattr(editor, "dock", None)
        if snapshot is not None and snapshot.left_tab == tab and dock_ctl is not None:
            getter = getattr(dock_ctl, "get_left_collapsed", None)
            toggler = getattr(dock_ctl, "toggle_left_dock", None)
            if callable(getter) and callable(toggler) and not getter():
                toggler(editor)
                return
    elif dock == "right":
        snapshot = get_dock_snapshot(editor)
        dock_ctl = getattr(editor, "dock", None)
        if snapshot is not None and snapshot.right_tab == tab and dock_ctl is not None:
            getter = getattr(dock_ctl, "get_right_collapsed", None)
            toggler = getattr(dock_ctl, "toggle_right_dock", None)
            if callable(getter) and callable(toggler) and not getter():
                toggler(editor)
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


def _toggle_debug_panel(window: Any) -> None:
    _toggle_dock_tab(window, "right", "Debug")


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


def _action_debug_select_event_entity(window: Any) -> None:
    """Select an entity from the debug event monitor (EditorAction handler)."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    debug_panels = getattr(editor, "debug_panels", None)
    if debug_panels is None:
        return
    entity_id = debug_panels.consume_pending_select_entity_id()
    if not entity_id:
        return
    debug_panels.activate_event_entity(entity_id)


def _action_debug_export_bundle(window: Any) -> None:
    """Export the current debug bundle snapshot to artifacts/ (EditorAction handler)."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    from pathlib import Path  # noqa: PLC0415

    from engine.editor.debug_bundle import build_debug_bundle  # noqa: PLC0415
    from engine.persistence_io import write_json_atomic  # noqa: PLC0415
    from engine.repo_root import get_repo_root  # noqa: PLC0415

    try:
        repo_root = get_repo_root()
    except Exception:
        repo_root = Path.cwd()

    out_path = repo_root / "artifacts" / "debug_bundle.json"
    try:
        bundle = build_debug_bundle(window, editor, deterministic=False)
        payload = bundle.to_dict(deterministic=False)
        write_json_atomic(out_path, payload, indent=2, sort_keys=True, trailing_newline=True)
        _debug_toast(window, f"Debug bundle exported: {out_path.as_posix()}")
    except Exception:
        _debug_toast(window, "Debug bundle export failed")


def _action_debug_copy_quest_diagnostic(window: Any) -> None:
    """Copy the selected quest diagnostic line to clipboard (EditorAction handler)."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    debug_panels = getattr(editor, "debug_panels", None)
    if debug_panels is None:
        return
    text = str(debug_panels.get_selected_quest_diagnostic_text() or "")
    if not text:
        _debug_toast(window, "No quest diagnostic selected")
        return
    from engine.tooling_runtime.clipboard import try_copy_to_clipboard  # noqa: PLC0415

    if try_copy_to_clipboard(text):
        _debug_toast(window, "Quest diagnostic copied")
    else:
        _debug_toast(window, "Clipboard unavailable (headless/web)")


def _action_debug_copy_filtered_events(window: Any) -> None:
    """Copy the last filtered events from the debug panel (EditorAction handler)."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    debug_panels = getattr(editor, "debug_panels", None)
    if debug_panels is None:
        return
    text = str(debug_panels.get_filtered_event_rows_text() or "")
    if not text:
        _debug_toast(window, "No events to copy")
        return
    from engine.tooling_runtime.clipboard import try_copy_to_clipboard  # noqa: PLC0415

    if try_copy_to_clipboard(text):
        _debug_toast(window, "Filtered events copied")
    else:
        _debug_toast(window, "Clipboard unavailable (headless/web)")


def _action_debug_copy_cutscene_summary(window: Any) -> None:
    """Copy the cutscene summary line(s) from the debug panel (EditorAction handler)."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    debug_panels = getattr(editor, "debug_panels", None)
    if debug_panels is None:
        return
    text = str(debug_panels.get_cutscene_summary_text() or "")
    if not text:
        _debug_toast(window, "No cutscene summary available")
        return
    from engine.tooling_runtime.clipboard import try_copy_to_clipboard  # noqa: PLC0415

    if try_copy_to_clipboard(text):
        _debug_toast(window, "Cutscene summary copied")
    else:
        _debug_toast(window, "Clipboard unavailable (headless/web)")


def _debug_toast(window: Any, message: str, *, seconds: float = 2.5) -> None:
    hud = getattr(window, "player_hud", None)
    toaster = getattr(hud, "enqueue_toast", None) if hud is not None else None
    if callable(toaster):
        toaster(message, seconds=seconds)


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


def _project_explorer_context_menu_open(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None:
        return
    opener = getattr(editor, "open_project_explorer_context_menu_at_selection", None)
    if callable(opener):
        opener()


def _project_explorer_context_menu_close(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None:
        return
    project = getattr(editor, "project_explorer", None)
    if project is None:
        return
    closer = getattr(project, "close_context_menu", None)
    if callable(closer):
        closer(editor)


def _project_explorer_context_menu_move(window: Any, delta: int) -> None:
    editor = _get_editor(window)
    if editor is None:
        return
    project = getattr(editor, "project_explorer", None)
    if project is None:
        return
    mover = getattr(project, "move_context_menu_selection", None)
    if callable(mover):
        mover(delta)


def _action_project_explorer_context_menu_up(window: Any) -> None:
    _project_explorer_context_menu_move(window, -1)


def _action_project_explorer_context_menu_down(window: Any) -> None:
    _project_explorer_context_menu_move(window, 1)


def _project_explorer_context_menu_activate(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None:
        return
    project = getattr(editor, "project_explorer", None)
    if project is None:
        return
    activator = getattr(project, "activate_context_menu_item", None)
    if callable(activator):
        activator(editor)


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
        # V2 Refactor Path for multi-select
        prompter(lambda dest: editor.file_ops.request_safe_move_refactor(dest))


def _enabled_safe_move_refactor(controller: Any, window: Any) -> bool:
    """Enabled if we can move file (legacy) or folder/multi (v2)."""
    # Base check for project explorer focus/selection
    editor = _get_editor(window)
    if not editor: return False
    
    from engine.editor.project_explorer_power_tools_model import should_handle_project_explorer_shortcut
    if not should_handle_project_explorer_shortcut(editor):
        return False
        
    ops = editor.file_ops
    return bool(ops.can_safe_move_selected_asset() or ops.can_safe_move_selected_assets_folder())


def _safe_move_refactor_wrapper(window: Any) -> None:
    """Dispatch to Legacy or V2 move depending on selection."""
    editor = _get_editor(window)
    if not editor: return
    
    ops = editor.file_ops
    use_v2 = ops.can_safe_move_selected_assets_folder()
    # Check multi-select too?
    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl and getattr(project_ctrl, "selection_count", lambda: 0)() > 1:
        use_v2 = True
        
    prompter = getattr(editor, "prompt_project_explorer_move_destination", None)
    if not callable(prompter): 
        # Toast fallback?
        return

    if use_v2:
        prompter(lambda dest: ops.request_safe_move_refactor(dest))
    else:
        # Legacy
        prompter(lambda dest: editor.safe_move_selected_asset(dest))

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
    if file_ops is not None:
        if hasattr(file_ops, "request_safe_rename_refactor"):
             file_ops.request_safe_rename_refactor(new_name)
        elif hasattr(file_ops, "rename_selected_asset"):
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
    state = getattr(project_ctrl, "selection_state", None)
    if state is not None:
        selected = getattr(state, "selected_indices", None)
        if selected:
            return True
    return False


def _enabled_project_explorer_active(_controller: Any, window: Any) -> bool:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return False
    from engine.editor.project_explorer_power_tools_model import should_handle_project_explorer_shortcut

    return bool(should_handle_project_explorer_shortcut(editor))


def _enabled_project_explorer_context_menu_open(_controller: Any, window: Any) -> bool:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return False
    from engine.editor.editor_panels_query import panels_is_open  # noqa: PLC0415

    return panels_is_open(editor, "project_context_menu")


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
    dock_ctl = getattr(editor, "dock", None) if editor is not None else None
    toggler = getattr(dock_ctl, "toggle_left_dock", None) if dock_ctl is not None else None
    if callable(toggler):
        toggler(editor)


def _toggle_right_dock(window: Any) -> None:
    editor = _get_editor(window)
    dock_ctl = getattr(editor, "dock", None) if editor is not None else None
    toggler = getattr(dock_ctl, "toggle_right_dock", None) if dock_ctl is not None else None
    if callable(toggler):
        toggler(editor)


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


def _action_apply_lighting_preset_0(window: Any) -> None:
    _apply_lighting_preset(window, 0)


def _action_apply_lighting_preset_1(window: Any) -> None:
    _apply_lighting_preset(window, 1)


def _action_apply_lighting_preset_2(window: Any) -> None:
    _apply_lighting_preset(window, 2)


def _action_apply_lighting_preset_3(window: Any) -> None:
    _apply_lighting_preset(window, 3)


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
    panels = getattr(editor, "panels", None)
    if panels and hasattr(panels, "toggle_command_palette"):
        if panels.toggle_command_palette():
            search = getattr(editor, "search", None)
            if search is not None:
                clear = getattr(search, "clear_command_palette_state", None)
                if callable(clear):
                    clear()
        return


def _open_keybinds(window: Any) -> None:
    editor = _get_editor(window)
    if editor:
        panels = getattr(editor, "panels", None)
        if panels and hasattr(panels, "open_keybinds"):
            panels.open_keybinds()
            return


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
    undo_ctrl = getattr(editor, "undo", None) if editor is not None else None
    if undo_ctrl is not None and hasattr(undo_ctrl, "undo"):
        undo_ctrl.undo()
        return
    undoer = getattr(editor, "undo_last", None) if editor is not None else None
    if callable(undoer):
        undoer()


def _redo(window: Any) -> None:
    editor = _get_editor(window)
    undo_ctrl = getattr(editor, "undo", None) if editor is not None else None
    if undo_ctrl is not None and hasattr(undo_ctrl, "redo"):
        undo_ctrl.redo()
        return
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



def _action_refactor_delete_selected(window: Any) -> None:
    editor = _get_editor(window)
    project = getattr(editor, "project_explorer", None)
    file_ops = getattr(editor, "file_ops", None)
    
    if project and file_ops and hasattr(file_ops, "request_safe_delete_refactor"):
        if hasattr(project, "ensure_rows"):
            project.ensure_rows()
        paths = project.selected_paths(getattr(project, "selectable_rows", []))
        if paths:
            file_ops.request_safe_delete_refactor(paths)


def _action_refactor_move_selected(window: Any) -> None:
    editor = _get_editor(window)
    project = getattr(editor, "project_explorer", None)
    file_ops = getattr(editor, "file_ops", None)
    
    if project and file_ops and hasattr(file_ops, "request_safe_move_refactor"):
        # Ensure V2 capability check?
        can_move = getattr(file_ops, "can_safe_move_selected_assets_folder", lambda: True)()
        if not can_move:
             return

        prompter = getattr(editor, "prompt_project_explorer_move_destination", None)
        if callable(prompter):
            prompter(lambda dest: file_ops.request_safe_move_refactor(dest))
        else:
            file_ops.request_safe_move_refactor("")


def _action_refactor_rename_commit(window: Any) -> None:
    editor = _get_editor(window)
    project = getattr(editor, "project_explorer", None)
    if project is None or not getattr(project, "inline_rename_active", False):
        return

    should_commit, new_name, error = project.get_inline_rename_commit_result()
    
    if should_commit and new_name:
        state = getattr(project, "inline_rename_state", None)
        original_path = getattr(state, "original_path", "")
        
        parent = os.path.dirname(original_path)
        new_path = os.path.join(parent, new_name).replace("\\", "/")
        
        project.cancel_inline_rename()
        
        file_ops = getattr(editor, "file_ops", None)
        if file_ops and hasattr(file_ops, "request_safe_rename_refactor"):
            file_ops.request_safe_rename_refactor(original_path, new_path)
            
    elif error is None:
        project.cancel_inline_rename()
    else:
        hud = getattr(window, "player_hud", None)
        if hud:
            toaster = getattr(hud, "enqueue_toast", None)
            if callable(toaster):
                toaster(f"Rename failed: {error}", seconds=2.5)


def _resolve_action_callable(name: str) -> Callable[..., Any]:
    fn = globals().get(str(name))
    if not callable(fn):
        raise KeyError(f"Unknown action callable: {name}")
    return cast(Callable[..., Any], fn)


def _build_actions_from_defs(defs: Iterable[ActionDef]) -> list[EditorAction]:
    actions: list[EditorAction] = []
    for spec in defs:
        enabled_fn = cast(Callable[[Any, Any], bool], _resolve_action_callable(spec.enabled))
        run_fn = cast(Callable[[Any], None], _resolve_action_callable(spec.run))
        actions.append(
            EditorAction(
                id=spec.id,
                title=spec.title,
                keywords=spec.keywords,
                group=spec.group,
                shortcut=spec.shortcut,
                enabled=enabled_fn,
                run=run_fn,
                in_palette=spec.in_palette,
                in_menu=spec.in_menu,
                menu_label=spec.menu_label,
                shortcut_scope=spec.shortcut_scope,
            )
        )
    return actions


def get_editor_actions(controller: Any | None, _window: Any | None) -> list[EditorAction]:
    actions = _build_actions_from_defs(DEFAULT_ACTION_DEFS)
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
