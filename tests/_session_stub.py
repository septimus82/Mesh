from __future__ import annotations

from types import SimpleNamespace

from engine.editor.editor_session_model import EditorSessionSnapshot


def make_session_stub(**overrides: object) -> SimpleNamespace:
    values = {
        "tile_paint_active": False,
        "entity_paint_active": False,
        "capture_mode_active": False,
        "authoring_selected_active": False,
        "project_explorer_focused": False,
        "command_palette_focused": False,
        "problems_panel_focused": False,
        "debug_console_open": False,
        "active_tool_id": None,
        "rev": 0,
    }
    values.update(overrides)
    snapshot = EditorSessionSnapshot(**values)
    return SimpleNamespace(get_snapshot=lambda: snapshot)
