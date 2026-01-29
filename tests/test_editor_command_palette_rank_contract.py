"""Contract tests for editor command palette ranking with focus."""
from __future__ import annotations

from engine.editor.editor_focus_model import FOCUS_PROJECT_EXPLORER
from engine.editor_commands import Command, filter_commands


def _noop(_w) -> None:
    return None


def test_project_explorer_focus_boosts_project_actions() -> None:
    commands = [
        Command(
            id="editor.copy.generic",
            title="Copy",
            keywords=("copy",),
            run=_noop,
        ),
        Command(
            id="editor.project_explorer.copy_path",
            title="Project Explorer: Copy Selected Paths",
            keywords=("project", "explorer", "copy", "path"),
            run=_noop,
        ),
    ]

    focused = filter_commands(commands, "copy", focus_target=FOCUS_PROJECT_EXPLORER)
    assert focused[0].id == "editor.project_explorer.copy_path"


def test_ranking_unchanged_without_focus_boost() -> None:
    commands = [
        Command(
            id="editor.copy.generic",
            title="Copy",
            keywords=("copy",),
            run=_noop,
        ),
        Command(
            id="editor.project_explorer.copy_path",
            title="Project Explorer: Copy Selected Paths",
            keywords=("project", "explorer", "copy", "path"),
            run=_noop,
        ),
    ]

    unfocused = filter_commands(commands, "copy")
    assert unfocused[0].id == "editor.copy.generic"
