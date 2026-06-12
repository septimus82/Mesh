"""Pure helpers for debug panel lines and layout."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from engine.editor.editor_shell_layout import TAB_HEADER_HEIGHT

from .cutscene_debug_model import CutsceneDebugViewModel, build_cutscene_debug_lines
from .event_monitor_model import EventLogViewModel, EventMonitorLine, build_event_monitor_entries
from .quest_debug_model import QuestDebugViewModel, build_quest_debug_lines

DEBUG_PANEL_PADDING = 8.0
DEBUG_PANEL_LINE_HEIGHT = 16.0


@dataclass(frozen=True, slots=True)
class DebugPanelLine:
    text: str
    kind: str = ""
    source_entity: str | None = None
    filter_field: str | None = None


def build_debug_panel_lines(
    quest_vm: QuestDebugViewModel,
    cutscene_vm: CutsceneDebugViewModel,
    event_vm: EventLogViewModel,
    *,
    active_filter_field: str | None = None,
    max_quests: int = 8,
    max_diagnostics: int = 4,
    max_events: int = 4,
) -> list[DebugPanelLine]:
    lines: list[DebugPanelLine] = []

    quest_lines = build_quest_debug_lines(quest_vm, max_quests=max_quests, max_diagnostics=max_diagnostics)
    lines.extend(_wrap_plain_lines(quest_lines))
    lines.append(DebugPanelLine(""))

    cutscene_lines = build_cutscene_debug_lines(cutscene_vm, max_events=max_events)
    lines.extend(_wrap_plain_lines(cutscene_lines))
    lines.append(DebugPanelLine(""))

    event_entries = build_event_monitor_entries(event_vm, active_filter_field=active_filter_field)
    lines.extend(_wrap_event_entries(event_entries))

    return trim_blank_tail(lines)


def truncate_debug_panel_lines(
    lines: Iterable[DebugPanelLine],
    max_lines: int,
) -> list[DebugPanelLine]:
    if max_lines <= 0:
        return []
    items = list(lines)
    if len(items) <= max_lines:
        return items
    trimmed = list(items[:max_lines])
    if trimmed:
        trimmed[-1] = DebugPanelLine("... (truncated)", kind="dim")
    return trimmed


def trim_blank_tail(lines: Iterable[DebugPanelLine]) -> list[DebugPanelLine]:
    trimmed = list(lines)
    while trimmed and not trimmed[-1].text.strip():
        trimmed.pop()
    return trimmed


def compute_debug_panel_content_bounds(dock_rect: object) -> tuple[float, float, int]:
    top = float(getattr(dock_rect, "top", 0.0))
    bottom = float(getattr(dock_rect, "bottom", 0.0))
    content_top = top - TAB_HEADER_HEIGHT - DEBUG_PANEL_PADDING
    content_bottom = bottom + DEBUG_PANEL_PADDING
    max_lines = int(max(0.0, (content_top - content_bottom) / DEBUG_PANEL_LINE_HEIGHT))
    return (content_top, content_bottom, max_lines)


def resolve_debug_panel_line_index(
    y: float,
    content_top: float,
    content_bottom: float,
    line_count: int,
) -> int | None:
    if y > content_top or y < content_bottom:
        return None
    idx = int((content_top - y) / DEBUG_PANEL_LINE_HEIGHT)
    if idx < 0 or idx >= line_count:
        return None
    return idx


def _wrap_plain_lines(lines: Iterable[str]) -> list[DebugPanelLine]:
    wrapped = []
    for line in lines:
        wrapped.append(DebugPanelLine(text=line, kind=_kind_from_text(line)))
    return wrapped


def _wrap_event_entries(entries: Iterable[EventMonitorLine]) -> list[DebugPanelLine]:
    wrapped = []
    for entry in entries:
        wrapped.append(
            DebugPanelLine(
                text=entry.text,
                kind=entry.kind,
                source_entity=entry.source_entity,
                filter_field=entry.filter_field,
            )
        )
    return wrapped


def _kind_from_text(text: str) -> str:
    if text.endswith("Debug") or text in {"Diagnostics:", "Recent Events:", "Event Monitor"}:
        return "header"
    if _is_quest_diagnostic_line(text):
        return "diagnostic"
    if text.startswith("...") or text.startswith("  ..."):
        return "dim"
    if text.startswith("No ") or text.startswith("  (none)") or text.startswith("No events"):
        return "dim"
    return ""


def _is_quest_diagnostic_line(text: str) -> bool:
    if not text.startswith("  "):
        return False
    if " [match]" not in text and " [no-match]" not in text:
        return False
    return ":" in text
