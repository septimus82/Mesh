from __future__ import annotations

from typing import Any, Iterable

from engine.editor.editor_commands_registry import (
    Command,
    filter_commands,
    get_all_commands,
    get_palette_focus_target,
    run_command,
)

__all__ = [
    "Command",
    "filter_commands",
    "get_all_commands",
    "get_palette_focus_target",
    "run_command",
]


def iter_commands(_window: Any | None = None) -> Iterable[Command]:
    return get_all_commands(_window)
