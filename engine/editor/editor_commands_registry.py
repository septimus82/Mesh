from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from engine.editor.command_palette_rank_model import score_command
from engine.editor.editor_focus_model import (
    FOCUS_COMMAND_PALETTE,
    FOCUS_PROJECT_EXPLORER,
    derive_focus_target_for_controller,
)
from engine.editor.editor_dock_query import get_dock_snapshot
from engine.editor.editor_actions import get_palette_actions


@dataclass(frozen=True, slots=True)
class Command:
    id: str
    title: str
    keywords: tuple[str, ...]
    run: Callable[[Any], None]
    shortcut: str | None = None


_COMMAND_SHORTCUT_BADGE_IDS: frozenset[str] = frozenset(
    {
        "editor.scene.save",
        "editor.scene_browser.open",
        "editor.scene_switcher.toggle",
        "editor.history.undo",
        "editor.history.redo",
        "editor.keybinds.open",
        "editor.light_tool.toggle",
        "editor.occluder_tool.toggle",
        "editor.entity_panels.toggle",
        "editor.panel.project_explorer.toggle",
        "editor.panel.problems.toggle",
        "editor.play.start",
    }
)


def _shortcut_badge_for_action(action: Any) -> str | None:
    action_id = str(getattr(action, "id", "") or "")
    if action_id not in _COMMAND_SHORTCUT_BADGE_IDS:
        return None
    shortcut = str(getattr(action, "shortcut", "") or "").strip()
    return shortcut or None


def build_commands_from_actions(actions: Iterable[Any]) -> list[Command]:
    return [
        Command(
            id=action.id,
            title=action.title,
            keywords=action.keywords,
            run=action.run,
            shortcut=_shortcut_badge_for_action(action),
        )
        for action in actions
    ]


def get_all_commands(_window: Any | None = None) -> list[Command]:
    window = _window
    controller = getattr(window, "editor_controller", None) if window is not None else None
    actions = get_palette_actions(controller, window)
    return build_commands_from_actions(actions)


def get_palette_focus_target(window_or_controller: Any) -> str | None:
    controller = getattr(window_or_controller, "editor_controller", None)
    if controller is None:
        controller = window_or_controller
    if controller is None:
        return None
    focus_target = derive_focus_target_for_controller(controller)
    if focus_target == FOCUS_COMMAND_PALETTE:
        dock_snapshot = get_dock_snapshot(controller)
        left_tab = getattr(dock_snapshot, "left_tab", "") if dock_snapshot is not None else ""
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
