from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EditorSessionSnapshot:
    tile_paint_active: bool
    entity_paint_active: bool
    capture_mode_active: bool
    authoring_selected_active: bool
    project_explorer_focused: bool
    command_palette_focused: bool
    problems_panel_focused: bool
    debug_console_open: bool
    active_tool_id: str | None
    rev: int


@dataclass(frozen=True, slots=True)
class SessionInputs:
    tile_paint_active: bool
    entity_paint_active: bool
    capture_mode_active: bool
    authoring_selected_active: bool
    project_explorer_focused: bool
    command_palette_focused: bool
    problems_panel_focused: bool
    debug_console_open: bool
    active_tool_id: str | None
    rev: int


def build_session_snapshot(inputs: SessionInputs) -> EditorSessionSnapshot:
    return EditorSessionSnapshot(
        tile_paint_active=bool(inputs.tile_paint_active),
        entity_paint_active=bool(inputs.entity_paint_active),
        capture_mode_active=bool(inputs.capture_mode_active),
        authoring_selected_active=bool(inputs.authoring_selected_active),
        project_explorer_focused=bool(inputs.project_explorer_focused),
        command_palette_focused=bool(inputs.command_palette_focused),
        problems_panel_focused=bool(inputs.problems_panel_focused),
        debug_console_open=bool(inputs.debug_console_open),
        active_tool_id=inputs.active_tool_id if inputs.active_tool_id is not None else None,
        rev=int(inputs.rev),
    )
