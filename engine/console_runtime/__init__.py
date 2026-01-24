"""Console runtime helpers extracted from engine.console_controller (pure refactor)."""

from __future__ import annotations

from .commands import ParsedCommand, dispatch_command, parse_command_line
from .errors import single_line_error
from .history import history_next, history_previous, history_push, history_reset_cursor
from .render import (
    get_scroll_state,
    get_visible_lines,
    trim_lines_and_adjust_scroll,
    visible_metrics,
)

__all__ = [
    "ParsedCommand",
    "dispatch_command",
    "get_scroll_state",
    "get_visible_lines",
    "history_next",
    "history_previous",
    "history_push",
    "history_reset_cursor",
    "parse_command_line",
    "single_line_error",
    "trim_lines_and_adjust_scroll",
    "visible_metrics",
]

