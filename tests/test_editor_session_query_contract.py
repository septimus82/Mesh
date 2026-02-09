from __future__ import annotations

from types import SimpleNamespace

from engine.editor.editor_session_model import EditorSessionSnapshot
from engine.editor.editor_session_query import get_session_snapshot


def test_get_session_snapshot_returns_snapshot() -> None:
    snapshot = EditorSessionSnapshot(
        tile_paint_active=False,
        entity_paint_active=False,
        capture_mode_active=False,
        authoring_selected_active=False,
        project_explorer_focused=False,
        command_palette_focused=False,
        problems_panel_focused=False,
        debug_console_open=False,
        active_tool_id=None,
        rev=1,
    )
    controller = SimpleNamespace(session=SimpleNamespace(get_snapshot=lambda: snapshot))
    assert get_session_snapshot(controller) is snapshot
