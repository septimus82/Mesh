from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade
from engine.ui_overlays.common import _draw_rectangle_filled


class EditorOverlayController:
    """Orchestrates editor overlay drawing in screen space."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def draw_overlay(self) -> None:
        editor = self._editor
        build = getattr(editor, "build", None)
        if build is not None and callable(getattr(build, "tick", None)):
            build.tick()

        if getattr(getattr(editor, "build_session", None), "is_running", False):
            self._draw_building_overlay()
            return

        if getattr(getattr(editor, "play_session", None), "is_playing", False):
            self._draw_playtesting_overlay()
            return

        if not editor.active:
            return

        editor._tick_workspace_autosave()
        editor._update_status()

        editor.debug_overlay.draw_debug_overlay(editor._overlay_text_obj)

        if editor.palette_active:
            editor.palette.draw_palette(editor._palette_text_obj)

        editor.hierarchy.draw_hierarchy_panel()

        if editor.dialogue_panel_active:
            editor.dialogue.draw_dialogue_panel()
            editor.dialogue.draw_quest_context_panel()

        editor.animation.draw_animation_panel_if_active()
        editor.tile.draw_tile_panel_if_active()

        confirm = getattr(editor, "unsaved_confirm", None)
        if confirm is not None and confirm.is_open:
            confirm.draw()

        panels = getattr(editor, "panels", None)
        if panels is not None and callable(getattr(panels, "draw_panels", None)):
            panels.draw_panels()
        elif hasattr(editor, "ui_layers"):
            editor.ui_layers.draw_all()

    def _draw_playtesting_overlay(self) -> None:
        window = getattr(self._editor, "window", None)
        if window is None:
            return

        center_x = float(getattr(window, "width", 1280)) / 2.0
        center_y = float(getattr(window, "height", 720)) / 2.0
        _draw_rectangle_filled(center_x, center_y, 360.0, 72.0, (0, 0, 0, 180))
        optional_arcade.arcade.draw_text(
            "Playtesting...",
            center_x,
            center_y + 8.0,
            optional_arcade.arcade.color.WHITE,
            22,
            anchor_x="center",
            anchor_y="center",
            font_name=("Consolas", "Courier New", "Courier"),
        )
        optional_arcade.arcade.draw_text(
            "Press Esc to return to editor",
            center_x,
            center_y - 20.0,
            optional_arcade.arcade.color.LIGHT_GRAY,
            12,
            anchor_x="center",
            anchor_y="center",
            font_name=("Consolas", "Courier New", "Courier"),
        )

    def _draw_building_overlay(self) -> None:
        window = getattr(self._editor, "window", None)
        if window is None:
            return

        center_x = float(getattr(window, "width", 1280)) / 2.0
        center_y = float(getattr(window, "height", 720)) / 2.0
        _draw_rectangle_filled(center_x, center_y, 460.0, 72.0, (0, 0, 0, 180))
        optional_arcade.arcade.draw_text(
            "Building...",
            center_x,
            center_y + 8.0,
            optional_arcade.arcade.color.WHITE,
            22,
            anchor_x="center",
            anchor_y="center",
            font_name=("Consolas", "Courier New", "Courier"),
        )
        optional_arcade.arcade.draw_text(
            "This may take about 30 seconds",
            center_x,
            center_y - 20.0,
            optional_arcade.arcade.color.LIGHT_GRAY,
            12,
            anchor_x="center",
            anchor_y="center",
            font_name=("Consolas", "Courier New", "Courier"),
        )
