"""Controller for debug panel input and state."""

from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade

from .debug_panels_model import (
    DebugPanelLine,
    build_debug_panel_lines,
    compute_debug_panel_content_bounds,
    resolve_debug_panel_line_index,
    truncate_debug_panel_lines,
)
from .debug_panels_state import (
    get_cutscene_events,
    get_cutscene_state,
    get_quest_diagnostics,
    get_quest_inspector_state,
)
from .cutscene_debug_model import build_cutscene_debug_view_model, format_cutscene_summary_text
from .event_monitor_model import (
    build_event_log_view_model_from_settings,
    format_event_rows_text,
)
from .quest_debug_model import build_quest_debug_view_model
from engine.editor.editor_dock_query import get_dock_snapshot, get_effective_dock_widths
from engine.editor.editor_shell_layout import compute_editor_shell_layout


_FILTER_FIELDS: tuple[str, ...] = ("event_type", "entity_id", "limit")


class EditorDebugPanelsController:
    """Manages debug panel filter state and click handling."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor
        self._active_filter_field: str = "event_type"
        self._pending_select_entity_id: str | None = None
        self._selected_quest_diagnostic: str | None = None

    def apply_workspace_settings(self, settings: Any) -> None:  # noqa: ARG002
        # Workspace settings already populate workspace_data; no extra sync needed.
        return

    def get_event_type_filter(self) -> str:
        settings = self._get_settings()
        return str(getattr(settings, "debug_event_type_filter", "") or "")

    def set_event_type_filter(self, value: str) -> None:
        settings = self._get_settings()
        if settings is None:
            return
        text = str(value or "")
        if getattr(settings, "debug_event_type_filter", "") == text:
            return
        settings.debug_event_type_filter = text
        self._editor._autosave_workspace()

    def get_event_entity_id_filter(self) -> str:
        settings = self._get_settings()
        return str(getattr(settings, "debug_event_entity_id", "") or "")

    def set_event_entity_id_filter(self, value: str) -> None:
        settings = self._get_settings()
        if settings is None:
            return
        text = str(value or "").strip()
        if getattr(settings, "debug_event_entity_id", "") == text:
            return
        settings.debug_event_entity_id = text
        self._editor._autosave_workspace()

    def get_event_limit(self) -> int:
        settings = self._get_settings()
        raw = getattr(settings, "debug_event_limit", 20) if settings is not None else 20
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return 20

    def set_event_limit(self, value: int) -> None:
        settings = self._get_settings()
        if settings is None:
            return
        limit = max(0, int(value))
        if getattr(settings, "debug_event_limit", 20) == limit:
            return
        settings.debug_event_limit = limit
        self._editor._autosave_workspace()

    def get_active_filter_field(self) -> str | None:
        search = getattr(self._editor, "search", None)
        if search is None or not search.is_panel_search_focused("debug"):
            return None
        return self._active_filter_field

    def set_active_filter_field(self, field: str) -> None:
        if field not in _FILTER_FIELDS:
            return
        self._active_filter_field = field

    def advance_active_filter(self, delta: int = 1) -> str:
        if self._active_filter_field not in _FILTER_FIELDS:
            self._active_filter_field = _FILTER_FIELDS[0]
            return self._active_filter_field
        idx = _FILTER_FIELDS.index(self._active_filter_field)
        new_idx = (idx + int(delta)) % len(_FILTER_FIELDS)
        self._active_filter_field = _FILTER_FIELDS[new_idx]
        return self._active_filter_field

    def get_active_filter_text(self) -> str:
        field = self._active_filter_field
        if field == "event_type":
            return self.get_event_type_filter()
        if field == "entity_id":
            return self.get_event_entity_id_filter()
        if field == "limit":
            return str(self.get_event_limit())
        return ""

    def set_active_filter_text(self, text: str) -> None:
        field = self._active_filter_field
        if field == "event_type":
            self.set_event_type_filter(text)
            return
        if field == "entity_id":
            self.set_event_entity_id_filter(text)
            return
        if field == "limit":
            self.set_event_limit(_parse_limit_text(text))
            return

    def build_visible_lines(self, window_w: int, window_h: int) -> list[DebugPanelLine]:
        editor = self._editor
        window = getattr(editor, "window", None)

        quest_vm = build_quest_debug_view_model(
            get_quest_inspector_state(window),
            get_quest_diagnostics(window),
        )
        cutscene_state, cutscene_commands = get_cutscene_state(window)
        cutscene_vm = build_cutscene_debug_view_model(
            cutscene_state,
            cutscene_commands,
            recent_events=get_cutscene_events(window),
        )
        event_vm = build_event_log_view_model_from_settings(
            getattr(window, "gameplay_event_bus", None),
            self._get_settings(),
        )
        search = getattr(editor, "search", None)
        active_field = self.get_active_filter_field()

        lines = build_debug_panel_lines(
            quest_vm,
            cutscene_vm,
            event_vm,
            active_filter_field=active_field,
            max_quests=8,
            max_diagnostics=4,
            max_events=4,
        )

        left_w, right_w = get_effective_dock_widths(editor, window_w)
        layout = compute_editor_shell_layout(window_w, window_h, left_w, right_w)
        _content_top, _content_bottom, max_lines = compute_debug_panel_content_bounds(layout.right_dock)
        return truncate_debug_panel_lines(lines, max_lines)

    def handle_mouse_click(self, x: float, y: float, button: int) -> bool:
        editor = self._editor
        if not getattr(editor, "active", False):
            return False

        snapshot = get_dock_snapshot(editor)
        if snapshot is None or snapshot.right_tab != "Debug":
            return False

        if self._input_blocked():
            return True

        if button != optional_arcade.arcade.MOUSE_BUTTON_LEFT:
            return True

        window = getattr(editor, "window", None)
        window_w = int(getattr(window, "width", 1280) or 1280)
        window_h = int(getattr(window, "height", 720) or 720)

        left_w, right_w = get_effective_dock_widths(editor, window_w)
        layout = compute_editor_shell_layout(window_w, window_h, left_w, right_w)
        dock = layout.right_dock
        if not dock.contains_point(x, y):
            return False

        content_top, content_bottom, _max_lines = compute_debug_panel_content_bounds(dock)
        lines = self.build_visible_lines(window_w, window_h)
        if not lines:
            return True

        line_index = resolve_debug_panel_line_index(y, content_top, content_bottom, len(lines))
        if line_index is None:
            return True

        line = lines[line_index]
        if line.filter_field:
            self.set_active_filter_field(line.filter_field)
            search = getattr(editor, "search", None)
            if search is not None:
                focus = getattr(search, "focus_search_for_active_panel", None)
                if callable(focus):
                    focus()
            return True

        if line.source_entity:
            self._pending_select_entity_id = line.source_entity
            runner = getattr(editor, "run_editor_action", None)
            if callable(runner):
                runner("editor.debug.event.select_entity")
            return True

        if line.kind == "diagnostic":
            self.select_quest_diagnostic(line.text)
            return True

        return True

    def consume_pending_select_entity_id(self) -> str:
        entity_id = self._pending_select_entity_id or ""
        self._pending_select_entity_id = None
        return entity_id

    def select_quest_diagnostic(self, text: str) -> None:
        cleaned = str(text or "").strip()
        self._selected_quest_diagnostic = cleaned or None

    def get_selected_quest_diagnostic_text(self) -> str:
        return self._selected_quest_diagnostic or ""

    def get_cutscene_summary_text(self) -> str:
        window = getattr(self._editor, "window", None)
        cutscene_state, cutscene_commands = get_cutscene_state(window)
        cutscene_vm = build_cutscene_debug_view_model(
            cutscene_state,
            cutscene_commands,
            recent_events=get_cutscene_events(window),
        )
        return format_cutscene_summary_text(cutscene_vm)

    def get_filtered_event_rows_text(self) -> str:
        window = getattr(self._editor, "window", None)
        event_vm = build_event_log_view_model_from_settings(
            getattr(window, "gameplay_event_bus", None),
            self._get_settings(),
        )
        return format_event_rows_text(event_vm)

    def activate_event_entity(self, entity_id: str) -> bool:
        if not entity_id:
            return False
        finder = getattr(self._editor, "find_actions", None)
        if finder is not None:
            activate = getattr(finder, "activate_find_entity", None)
            if callable(activate):
                return bool(activate(entity_id))
        return False

    def _get_settings(self) -> Any | None:
        return getattr(self._editor, "workspace_data", None)

    def _input_blocked(self) -> bool:
        from engine.editor_tooltips_model import (  # noqa: PLC0415
            _is_modal_open_state,
            _is_text_input_active_state,
        )
        from engine.editor.editor_panels_query import panels_is_open  # noqa: PLC0415

        if panels_is_open(self._editor, "unsaved_confirm"):
            return True
        search = getattr(self._editor, "search", None)
        if search is not None and search.is_panel_search_focused("debug"):
            return _is_modal_open_state(self._editor)
        return _is_text_input_active_state(self._editor) or _is_modal_open_state(self._editor)


def _parse_limit_text(value: str) -> int:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not digits:
        return 0
    try:
        return int(digits)
    except (TypeError, ValueError):
        return 0
