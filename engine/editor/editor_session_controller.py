from __future__ import annotations

from typing import Optional

from engine.editor.editor_session_model import EditorSessionSnapshot, SessionInputs, build_session_snapshot


class EditorSessionController:
    def __init__(self) -> None:
        self._tile_paint_active = False
        self._entity_paint_active = False
        self._capture_mode_active = False
        self._authoring_selected_active = False
        self._project_explorer_focused = False
        self._command_palette_focused = False
        self._problems_panel_focused = False
        self._debug_console_open = False
        self._active_tool_id: Optional[str] = None
        self._rev = 0
        self._cached_rev = -1
        self._cached_snapshot: EditorSessionSnapshot | None = None

    def _set_bool(self, attr: str, value: bool) -> None:
        current = getattr(self, attr)
        new_value = bool(value)
        if current == new_value:
            return
        setattr(self, attr, new_value)
        self._rev += 1

    def _set_str(self, attr: str, value: Optional[str]) -> None:
        current = getattr(self, attr)
        if current == value:
            return
        setattr(self, attr, value)
        self._rev += 1

    def set_tile_paint_active(self, value: bool) -> None:
        self._set_bool("_tile_paint_active", value)

    def set_entity_paint_active(self, value: bool) -> None:
        self._set_bool("_entity_paint_active", value)

    def set_capture_mode_active(self, value: bool) -> None:
        self._set_bool("_capture_mode_active", value)

    def set_authoring_selected_active(self, value: bool) -> None:
        self._set_bool("_authoring_selected_active", value)

    def set_project_explorer_focused(self, value: bool) -> None:
        self._set_bool("_project_explorer_focused", value)

    def set_command_palette_focused(self, value: bool) -> None:
        self._set_bool("_command_palette_focused", value)

    def set_problems_panel_focused(self, value: bool) -> None:
        self._set_bool("_problems_panel_focused", value)

    def set_debug_console_open(self, value: bool) -> None:
        self._set_bool("_debug_console_open", value)

    def set_active_tool_id(self, value: Optional[str]) -> None:
        self._set_str("_active_tool_id", value)

    def get_snapshot(self) -> EditorSessionSnapshot:
        if self._cached_snapshot is not None and self._cached_rev == self._rev:
            return self._cached_snapshot
        inputs = SessionInputs(
            tile_paint_active=self._tile_paint_active,
            entity_paint_active=self._entity_paint_active,
            capture_mode_active=self._capture_mode_active,
            authoring_selected_active=self._authoring_selected_active,
            project_explorer_focused=self._project_explorer_focused,
            command_palette_focused=self._command_palette_focused,
            problems_panel_focused=self._problems_panel_focused,
            debug_console_open=self._debug_console_open,
            active_tool_id=self._active_tool_id,
            rev=self._rev,
        )
        snapshot = build_session_snapshot(inputs)
        self._cached_snapshot = snapshot
        self._cached_rev = self._rev
        return snapshot
