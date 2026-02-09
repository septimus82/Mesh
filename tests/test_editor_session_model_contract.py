from __future__ import annotations

from engine.editor.editor_session_model import SessionInputs, build_session_snapshot


def test_session_snapshot_determinism() -> None:
    inputs = SessionInputs(
        tile_paint_active=True,
        entity_paint_active=False,
        capture_mode_active=False,
        authoring_selected_active=True,
        project_explorer_focused=False,
        command_palette_focused=False,
        problems_panel_focused=True,
        debug_console_open=False,
        active_tool_id="select",
        rev=3,
    )
    snap_a = build_session_snapshot(inputs)
    snap_b = build_session_snapshot(inputs)
    assert snap_a == snap_b


def test_session_snapshot_rev_passthrough() -> None:
    inputs = SessionInputs(
        tile_paint_active=False,
        entity_paint_active=False,
        capture_mode_active=False,
        authoring_selected_active=False,
        project_explorer_focused=False,
        command_palette_focused=False,
        problems_panel_focused=False,
        debug_console_open=False,
        active_tool_id=None,
        rev=42,
    )
    snap = build_session_snapshot(inputs)
    assert snap.rev == 42
