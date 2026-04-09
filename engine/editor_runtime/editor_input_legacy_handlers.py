from __future__ import annotations

from typing import Callable, TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade
from engine.editor.editor_modal_state_query import is_scene_browser_active
from engine.editor.state import (
    TRANSFORM_MODE_MOVE,
    TRANSFORM_MODE_ROTATE,
    TRANSFORM_MODE_SCALE,
)

from ..logging_tools import get_logger

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController as EditorController

logger = get_logger(__name__)


def handle_input_legacy(
    controller: EditorController,
    key: int,
    modifiers: int,
    *,
    is_text_input_active: Callable[[EditorController], bool],
    run_action: Callable[[str, EditorController, Any], bool] | None = None,
) -> bool:
    if run_action is None:
        from engine.editor.editor_actions import run_editor_action as _run_editor_action  # noqa: PLC0415

        run_action = _run_editor_action
    if is_scene_browser_active(controller):
        handler = getattr(controller, "_handle_scene_browser_input", None)
        if callable(handler):
            return bool(handler(key, modifiers))
        return True

    if getattr(controller, "asset_browser_active", False):
        handler = getattr(controller, "_handle_asset_browser_input", None)
        if callable(handler):
            return bool(handler(key, modifiers))
        return True

    if getattr(controller, "scene_switcher_active", False):
        handler = getattr(controller, "_handle_scene_switcher_input", None)
        if callable(handler):
            return bool(handler(key, modifiers))
        return True

    if key == optional_arcade.arcade.key.J and (modifiers & optional_arcade.arcade.key.MOD_CTRL):
        if not is_text_input_active(controller):
            return bool(run_action("editor.find_everything.toggle", controller, controller.window))
        return True

    dock = getattr(controller, "dock", None)
    snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
    left_tab = getattr(snapshot, "left_tab", "Outliner") or "Outliner"
    right_tab = getattr(snapshot, "right_tab", "Inspector") or "Inspector"

    if left_tab == "Project":
        handler = getattr(controller, "_handle_project_explorer_input", None)
        if callable(handler) and handler(key, modifiers):
            return True

    if controller.entity_panels_active:
        handler = getattr(controller, "_handle_entity_panels_input", None)
        if callable(handler) and handler(key, modifiers):
            return True

    if right_tab == "History":
        handler = getattr(controller, "_handle_history_input", None)
        if callable(handler) and handler(key, modifiers):
            return True
    if right_tab == "Problems":
        handler = getattr(controller, "_handle_problems_input", None)
        if callable(handler) and handler(key, modifiers):
            return True

    # Component Inspector v1 input (when Inspector tab is active)
    if right_tab == "Inspector":
        # Try v1 handler first
        v1_handler = getattr(controller, "_handle_component_inspector_v1_input", None)
        if callable(v1_handler) and v1_handler(key, modifiers):
            return True
        # Fall back to legacy handler
        inspector_handler = getattr(controller, "_handle_inspector_component_input", None)
        if callable(inspector_handler) and inspector_handler(key, modifiers):
            return True

    if (
        key == optional_arcade.arcade.key.O
        and (modifiers & optional_arcade.arcade.key.MOD_SHIFT)
        and not (modifiers & optional_arcade.arcade.key.MOD_CTRL)
    ):
        return bool(controller.shape.toggle_shape_edit_mode("occluder"))
    if (
        key == optional_arcade.arcade.key.C
        and (modifiers & optional_arcade.arcade.key.MOD_SHIFT)
        and not (modifiers & optional_arcade.arcade.key.MOD_CTRL)
    ):
        return bool(controller.shape.toggle_shape_edit_mode("collision"))
    if key == optional_arcade.arcade.key.O and not modifiers:
        return bool(run_action("editor.occluder_tool.toggle", controller, controller.window))

    if controller.shape_edit_mode:
        if key in (optional_arcade.arcade.key.ESCAPE,):
            controller.shape.cancel_shape_edit()
            return True
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
            controller.shape.commit_shape_edit()
            return True
        if key in (optional_arcade.arcade.key.BACKSPACE, optional_arcade.arcade.key.DELETE):
            return bool(controller.shape.remove_shape_point())
        if key == optional_arcade.arcade.key.G and not modifiers:
            controller.shape_snap_enabled = not controller.shape_snap_enabled
            return True

    if not controller.shape_edit_mode:
        if key == optional_arcade.arcade.key.G and not modifiers:
            controller.snap_enabled = not controller.snap_enabled
            return True
        if key == optional_arcade.arcade.key.G and (modifiers & optional_arcade.arcade.key.MOD_SHIFT):
            modes = ["grid8", "grid16", "tile_center"]
            try:
                idx = modes.index(controller.snap_mode)
            except ValueError:
                idx = 0
            controller.snap_mode = modes[(idx + 1) % len(modes)]
            return True

    # Transform mode hotkeys (W = Move, E = Rotate, Q = Scale)
    # Only when selected entity and no modifiers, not in text input
    if controller.selected_entity and not modifiers and not is_text_input_active(controller):
        if key == optional_arcade.arcade.key.W:
            controller.transform_mode = TRANSFORM_MODE_MOVE
            logger.info("[Editor] Transform Mode: %s", controller.transform_mode)
            return True
        if key == optional_arcade.arcade.key.E:
            controller.transform_mode = TRANSFORM_MODE_ROTATE
            logger.info("[Editor] Transform Mode: %s", controller.transform_mode)
            return True
        if key == optional_arcade.arcade.key.Q:
            controller.transform_mode = TRANSFORM_MODE_SCALE
            logger.info("[Editor] Transform Mode: %s", controller.transform_mode)
            return True

    if controller.selected_entity and (modifiers & optional_arcade.arcade.key.MOD_SHIFT) and not (
        modifiers & optional_arcade.arcade.key.MOD_CTRL
    ):
        if key == optional_arcade.arcade.key.A:
            return controller._apply_prefab_shapes(only_missing=True)
        if key == optional_arcade.arcade.key.R and not controller.hierarchy_active:
            return controller._apply_prefab_shapes(only_missing=False)
        if key == optional_arcade.arcade.key.P:
            return controller._promote_prefab_shapes()

    if key == optional_arcade.arcade.key.L and not modifiers:
        return run_action("editor.light_tool.toggle", controller, controller.window)

    if controller.lights_tool_active and not controller.palette_active:
        if key == optional_arcade.arcade.key.P and not modifiers:
            return controller.capture_lighting_preset("custom_1")
        if key == optional_arcade.arcade.key.P and (modifiers & optional_arcade.arcade.key.MOD_SHIFT):
            return controller.capture_lighting_preset("custom_2")

    if not controller.palette_active and not modifiers:
        if optional_arcade.arcade.key.KEY_1 <= key <= optional_arcade.arcade.key.KEY_4:
            return controller.apply_lighting_preset_hotkey(key - optional_arcade.arcade.key.KEY_1)
        if key == optional_arcade.arcade.key.KEY_5:
            return controller.apply_custom_lighting_preset("custom_1")
        if key == optional_arcade.arcade.key.KEY_6:
            return controller.apply_custom_lighting_preset("custom_2")

    if controller.lights_tool_active and controller.lights_selection is not None:
        if controller._handle_lights_key_input(key, modifiers):
            return True

    if controller.occluder_tool_active:
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
            return bool(controller._commit_occluder_polygon())
        if key in (optional_arcade.arcade.key.BACKSPACE, optional_arcade.arcade.key.DELETE):
            return bool(controller._handle_occluder_key_input(key))
        if key == optional_arcade.arcade.key.I:
            return bool(controller._handle_occluder_key_input(key))
        if key == optional_arcade.arcade.key.ESCAPE:
            controller._toggle_occluder_mode(False)
            return True

    if key == optional_arcade.arcade.key.D and not modifiers and controller._entity_has_dialogue(controller.selected_entity):
        controller.toggle_dialogue_panel()
        return True

    if controller.dialogue_panel_active:
        if controller._handle_dialogue_input(key, modifiers):
            return True

    if key == optional_arcade.arcade.key.A and not modifiers and controller._entity_has_animator(controller.selected_entity):
        controller.toggle_animation_panel()
        return True

    if controller.animation_active:
        if controller._handle_animation_input(key, modifiers):
            return True

    if key == optional_arcade.arcade.key.G and not modifiers and controller._tilemap_available():
        controller.toggle_tile_panel()
        return True

    if controller.tile_panel_active:
        if controller._handle_tile_input(key, modifiers):
            return True

    # Hierarchy rename shortcut (Shift+R)
    if (
        key == optional_arcade.arcade.key.R
        and controller.hierarchy_active
        and (modifiers & optional_arcade.arcade.key.MOD_SHIFT)
        and not (modifiers & optional_arcade.arcade.key.MOD_CTRL)
    ):
        if controller._begin_hierarchy_rename():
            return True

    # Toggle Palette
    if key == optional_arcade.arcade.key.P:
        return run_action("editor.prefab_palette.toggle", controller, controller.window)

    # Palette filter Tab-to-insert should win over global Tab inspector toggle.
    if controller.palette_active and controller.palette_filter_active and key == optional_arcade.arcade.key.TAB:
        return bool(controller._handle_palette_input(key, modifiers))

    # Cycle Zone Target (Ctrl+R)
    if key == optional_arcade.arcade.key.R and (modifiers & optional_arcade.arcade.key.MOD_CTRL):
        if controller.tool_mode == "ZONE":
            return controller._cycle_zone_behaviour()
        return False

    # Toggle between trigger/hitbox when both exist (T)
    if key == optional_arcade.arcade.key.T and not modifiers:
        if controller.tool_mode == "ZONE" and controller._toggle_zone_edit_target():
            return True

    # Cycle Tool Mode (plain R)
    if key == optional_arcade.arcade.key.R and not (
        modifiers & (optional_arcade.arcade.key.MOD_SHIFT | optional_arcade.arcade.key.MOD_CTRL)
    ):
        controller._cycle_tool_mode()
        return True

    # Toggle Inspector Focus
    if key == optional_arcade.arcade.key.TAB:
        inspector = getattr(controller, "inspector", None)
        if inspector is not None:
            inspector.toggle_inspector_focus()
        return True

    # Toggle Hierarchy
    if key == optional_arcade.arcade.key.H:
        controller.toggle_hierarchy()
        return True

    # Copy/Paste (Ctrl+C / Ctrl+V) - skip if in text input mode
    if not is_text_input_active(controller):
        if key == optional_arcade.arcade.key.C and (modifiers & optional_arcade.arcade.key.MOD_CTRL):
            copier = getattr(controller, "copy_selected_entity_to_clipboard", None)
            if callable(copier):
                copier()
            return True

        if key == optional_arcade.arcade.key.V and (modifiers & optional_arcade.arcade.key.MOD_CTRL):
            paster = getattr(controller, "paste_entity_from_clipboard", None)
            if callable(paster):
                paster()
            return True

    if controller.palette_active:
        return bool(controller._handle_palette_input(key, modifiers))

    if controller.hierarchy_active:
        return bool(controller._handle_hierarchy_input(key, modifiers))

    if controller.inspector_active and controller.selected_entity:
        return bool(controller._handle_inspector_input(key, modifiers))

    # Tool-specific input
    if controller.tool_mode == "PATH":
        if controller.shape.handle_path_input(key, modifiers):
            return True
    elif controller.tool_mode == "ZONE":
        if controller.shape.handle_zone_input(key, modifiers):
            return True

    # Default movement (fallback)
    return bool(controller._handle_movement_input(key, modifiers))
