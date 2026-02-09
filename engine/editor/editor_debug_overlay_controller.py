from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade

from engine.ui_overlays.common import draw_panel_bg
from engine.editor.state import TOOL_MODE_PATH, TOOL_MODE_ZONE
from engine.behaviours.utils import describe_zone_behaviour


class EditorDebugOverlayController:
    """Encapsulates editor debug overlay line building + rendering."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def draw_debug_overlay(self, text_obj: Any) -> None:
        editor = self._editor
        dirty_flag = bool(editor.dirty_state.is_dirty)
        scene_name = editor.window.scene_controller.current_scene_path or ""
        if scene_name and len(scene_name) > 30:
            scene_name = "..." + scene_name[-27:]

        lines = [
            "EDITOR MODE (F4)",
            f"Scene: {scene_name or 'Unsaved'}" + (" *" if dirty_flag else ""),
            f"Tool: {editor.tool_mode} (R)",
            "----------------",
            "Click: Select Entity",
            "TAB: Toggle Inspector",
            "H: Toggle Hierarchy",
            "Ctrl+S: Save Scene",
            "Ctrl+Z: Undo | Ctrl+Y: Redo",
            "----------------",
        ]

        if editor.shape_edit_mode:
            lines.append(f"Shape Mode: {editor.shape_edit_mode} (Esc to exit)")
            lines.append(f"Shape Snap: {'on' if editor.shape_snap_enabled else 'off'} (G)")
            lines.append("Shift+A: Apply prefab shapes | Shift+R: Reset prefab shapes | Shift+P: Promote shapes")
            lines.append("----------------")
        elif editor.selected_entity:
            lines.append("Shift+A: Apply prefab shapes | Shift+R: Reset prefab shapes | Shift+P: Promote shapes")
            lines.append("----------------")
        if editor._status_message:
            lines.append(editor._status_message)
            lines.append("----------------")

        if editor.tool_mode == TOOL_MODE_PATH:
            lines.append("PATH TOOL:")
            lines.append("Click Point: Select")
            lines.append("Shift+Click: Add Point")
            lines.append("Arrows: Move Point")
            lines.append("Del: Remove Point")
            lines.append("----------------")
        elif editor.tool_mode == TOOL_MODE_ZONE:
            lines.append("ZONE TOOL:")
            lines.append("Shift+Arrows: Resize")
            zone_behaviours = editor._get_zone_behaviours(editor.selected_entity)
            if zone_behaviours:
                active_zone = editor._get_zone_behaviour(editor.selected_entity)
                description = describe_zone_behaviour(active_zone)
                if len(zone_behaviours) > 1:
                    lines.append(
                        f"Ctrl+R: Cycle Zone ({editor.zone_behaviour_index + 1}/{len(zone_behaviours)})"
                    )
                trigger, hitbox = editor.shape.split_zone_behaviours(editor.selected_entity)
                if trigger and hitbox:
                    lines.append("T: Toggle Trigger/Hitbox")
                lines.append(f"Active Target: {description}")
            else:
                lines.append("Select entity with TriggerZone/Hitbox")
            lines.append("----------------")

        inspector = getattr(editor, "inspector", None)
        if inspector is not None and callable(getattr(inspector, "build_selection_overlay_lines", None)):
            lines.extend(inspector.build_selection_overlay_lines())
        else:
            lines.append("No selection")

        start_y = editor.window.height - 100
        draw_panel_bg(
            0,
            300,
            start_y - len(lines) * 20 - 10,
            start_y + 20,
        )

        full_text = "\n".join(lines)
        text_obj.text = full_text
        text_obj.y = start_y
        text_obj.draw()
