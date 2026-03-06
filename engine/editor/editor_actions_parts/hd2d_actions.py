"""HD-2D preset, toggle, slider, entity override, clipboard, and batch action handlers."""

from __future__ import annotations

import copy
from typing import Any

from engine.editor.editor_actions_parts._shared import _get_editor

__all__ = [
    "_apply_hd2d_preset",
    "_action_apply_hd2d_preset_soft",
    "_action_apply_hd2d_preset_crisp",
    "_action_apply_hd2d_preset_noir",
    "_action_apply_hd2d_preset_dreamy",
    "_upgrade_scene_to_hd2d_defaults",
    "_toggle_hd2d_setting",
    "_action_toggle_hd2d_shadows_enabled",
    "_action_toggle_hd2d_shadows_contact_enabled",
    "_action_toggle_hd2d_shadows_ao_enabled",
    "_action_toggle_hd2d_depth_tint_enabled",
    "_action_toggle_hd2d_outline_enabled",
    "_adjust_hd2d_slider",
    "_action_adjust_hd2d_depth_tint_strength_up",
    "_action_adjust_hd2d_depth_tint_strength_down",
    "_action_adjust_hd2d_outline_strength_up",
    "_action_adjust_hd2d_outline_strength_down",
    "_action_adjust_hd2d_outline_radius_up",
    "_action_adjust_hd2d_outline_radius_down",
    "_toggle_entity_hd2d_override",
    "_action_toggle_entity_shadow_enabled",
    "_action_toggle_entity_shadow_contact_enabled",
    "_action_toggle_entity_shadow_ao_enabled",
    "_action_toggle_entity_depth_tint_enabled",
    "_action_toggle_entity_outline_enabled",
    "_adjust_entity_hd2d_slider",
    "_action_adjust_entity_depth_tint_strength_up",
    "_action_adjust_entity_depth_tint_strength_down",
    "_action_adjust_entity_outline_strength_up",
    "_action_adjust_entity_outline_strength_down",
    "_action_adjust_entity_outline_radius_up",
    "_action_adjust_entity_outline_radius_down",
    "_clear_entity_hd2d_override",
    "_enabled_entity_has_overrides",
    "_enabled_hd2d_clipboard_has_data",
    "_copy_entity_hd2d_overrides",
    "_paste_entity_hd2d_overrides",
    "_paste_replace_entity_hd2d_overrides",
    "_clear_all_entity_hd2d_overrides",
    "_batch_paste_hd2d_overrides",
    "_batch_paste_hd2d_overrides_merge",
    "_batch_paste_hd2d_overrides_replace",
    "_adjust_hd2d_batch_radius",
    "_action_adjust_hd2d_batch_radius_up",
    "_action_adjust_hd2d_batch_radius_down",
    "_reset_hd2d_batch_radius",
    "_save_hd2d_batch_radius_to_workspace",
]


# -------------------------------------------------------------------------
# HD-2D Scene Presets
# -------------------------------------------------------------------------


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


# -------------------------------------------------------------------------
# HD-2D Scene Toggle / Slider
# -------------------------------------------------------------------------


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


# -------------------------------------------------------------------------
# HD-2D Entity Override: Enabled Guards
# -------------------------------------------------------------------------


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


# -------------------------------------------------------------------------
# HD-2D Clipboard: Copy / Paste / Replace / Clear / Batch
# -------------------------------------------------------------------------


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


# -------------------------------------------------------------------------
# HD-2D Batch Operations
# -------------------------------------------------------------------------


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


# -------------------------------------------------------------------------
# HD-2D Batch Radius
# -------------------------------------------------------------------------


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
