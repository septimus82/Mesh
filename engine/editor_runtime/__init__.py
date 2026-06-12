"""Editor runtime helpers extracted from engine.editor_controller (pure refactor)."""

from __future__ import annotations

from .input import (
    handle_input,
    handle_mouse_click,
    handle_mouse_drag,
    handle_mouse_release,
    handle_text_input,
)
from .ops import (
    delete_selected,
    duplicate_selected,
    move_palette_selection,
    nudge_selected,
    place_entity_at_mouse,
    redo_last,
    save_current_scene,
    select_palette_index,
    toggle_lights_tool,
    toggle_occluder_tool,
    toggle_palette,
    undo_last,
)

__all__ = [
    "delete_selected",
    "duplicate_selected",
    "handle_input",
    "handle_mouse_click",
    "handle_mouse_drag",
    "handle_mouse_release",
    "handle_text_input",
    "move_palette_selection",
    "nudge_selected",
    "place_entity_at_mouse",
    "redo_last",
    "save_current_scene",
    "select_palette_index",
    "toggle_occluder_tool",
    "toggle_lights_tool",
    "toggle_palette",
    "undo_last",
]
