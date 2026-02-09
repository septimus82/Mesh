from __future__ import annotations

from typing import Any


class EditorOverlayController:
    """Orchestrates editor overlay drawing in screen space."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def draw_overlay(self) -> None:
        editor = self._editor
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
