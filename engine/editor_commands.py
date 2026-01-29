from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from engine.editor.command_palette_rank_model import score_command
from engine.editor.editor_focus_model import (
    FOCUS_COMMAND_PALETTE,
    FOCUS_PROJECT_EXPLORER,
    collect_editor_state,
    derive_focus_target,
)

from .editor.editor_actions import get_palette_actions


@dataclass(frozen=True, slots=True)
class Command:
    id: str
    title: str
    keywords: tuple[str, ...]
    run: Callable[[Any], None]


def get_all_commands(_window: Any | None = None) -> list[Command]:
    window = _window
    controller = getattr(window, "editor_controller", None) if window is not None else None
    actions = get_palette_actions(controller, window)
    return [
        Command(
            id=action.id,
            title=action.title,
            keywords=action.keywords,
            run=action.run,
        )
        for action in actions
    ]


def get_palette_focus_target(window_or_controller: Any) -> str | None:
    controller = getattr(window_or_controller, "editor_controller", None)
    if controller is None:
        controller = window_or_controller
    if controller is None:
        return None
    state = collect_editor_state(controller)
    focus_target = derive_focus_target(state)
    if focus_target == FOCUS_COMMAND_PALETTE:
        left_tab = state.get("_left_dock_tab", "")
        if left_tab == "Project":
            return FOCUS_PROJECT_EXPLORER
    return focus_target


def filter_commands(
    commands: Iterable[Command],
    query: str,
    focus_target: str | None = None,
) -> list[Command]:
    scored: list[tuple[tuple[int, int, int, int, str, str], Command]] = []
    for cmd in commands:
        score = score_command(cmd.id, cmd.title, cmd.keywords, query, focus_target)
        if score is None:
            continue
        scored.append((score, cmd))
    scored.sort(key=lambda pair: pair[0])
    return [cmd for _score, cmd in scored]


def run_command(command_id: str, window: Any) -> bool:
    wanted = str(command_id or "").strip()
    if not wanted:
        return False
    for cmd in get_all_commands(window):
        if cmd.id == wanted:
            cmd.run(window)
            return True
    return False
