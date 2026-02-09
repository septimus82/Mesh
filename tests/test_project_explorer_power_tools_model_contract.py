"""Contract tests for project_explorer_power_tools_model."""
from __future__ import annotations

from types import SimpleNamespace

from engine.editor.project_explorer_power_tools_model import (
    invert_selection,
    compute_common_parent,
    format_paths_for_clipboard,
    should_handle_project_explorer_shortcut,
)
from tests._dock_stub import make_dock_stub


def test_invert_selection() -> None:
    all_ids = [0, 1, 2, 3]
    selected = frozenset({1, 3})
    assert invert_selection(all_ids, selected) == frozenset({0, 2})


def test_compute_common_parent() -> None:
    paths = ["assets/a.png", "assets/b.png", "assets/sub/c.png"]
    assert compute_common_parent(paths) == "assets"
    assert compute_common_parent(["a.txt"]) == "."
    assert compute_common_parent([]) is None


def test_format_paths_for_clipboard_sorts_and_normalizes() -> None:
    paths = ["b\\file.txt", "a/file.txt", "b/file.txt"]
    assert format_paths_for_clipboard(paths) == "a/file.txt\nb/file.txt\nb/file.txt"


def test_should_handle_project_explorer_shortcut() -> None:
    editor = SimpleNamespace(
        active=True,
        dock=make_dock_stub(left_tab="Project"),
        project_explorer=SimpleNamespace(inline_rename_active=False),
    )
    assert should_handle_project_explorer_shortcut(editor) is True

    editor.project_explorer.inline_rename_active = True
    assert should_handle_project_explorer_shortcut(editor) is False
