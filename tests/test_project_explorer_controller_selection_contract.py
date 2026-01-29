"""Contract tests for ProjectExplorerController selection helpers."""
from __future__ import annotations

from pathlib import Path

from engine.editor.editor_project_explorer_controller import ProjectExplorerController
from engine.editor.project_explorer_model import ProjectExplorerDisplayRow, ProjectRow


def _row(rel_path: str) -> ProjectExplorerDisplayRow:
    entry = ProjectRow(rel_path=rel_path, name=Path(rel_path).name, depth=0, is_dir=False)
    return ProjectExplorerDisplayRow(kind="entry", header=None, entry=entry, recent=None)


def _controller_with_rows(tmp_path: Path, paths: list[str]) -> ProjectExplorerController:
    controller = ProjectExplorerController(tmp_path)
    controller.selectable_rows = [_row(p) for p in paths]
    controller.cached_rows = list(controller.selectable_rows)
    controller.project_rows = [ProjectRow(rel_path=p, name=Path(p).name, depth=0, is_dir=False) for p in paths]
    controller.tree_rev = 1
    return controller


def test_selected_paths_sorted_and_primary_path(tmp_path: Path) -> None:
    controller = _controller_with_rows(tmp_path, ["b.txt", "a.txt", "c.txt"])
    controller.handle_click(0)
    controller.handle_click(2, ctrl=True)

    paths = controller.selected_paths(controller.selectable_rows)
    assert paths == ["b.txt", "c.txt"]
    assert controller.primary_path(controller.selectable_rows) == "c.txt"


def test_inline_rename_blocked_when_multi_selected(tmp_path: Path) -> None:
    controller = _controller_with_rows(tmp_path, ["a.txt", "b.txt"])
    controller.handle_click(0)
    controller.handle_click(1, ctrl=True)

    assert controller.begin_inline_rename("a.txt") is False


def test_batch_move_selection_restores_primary_and_paths(tmp_path: Path) -> None:
    controller = _controller_with_rows(tmp_path, ["a.txt", "b.txt", "c.txt"])
    controller.handle_click(0)
    controller.handle_click(2, ctrl=True)

    old_paths = ["a.txt", "c.txt"]
    new_paths = ["moved/a.txt", "moved/c.txt"]
    controller.project_rows = [
        ProjectRow(rel_path="moved/a.txt", name="a.txt", depth=0, is_dir=False),
        ProjectRow(rel_path="moved/b.txt", name="b.txt", depth=0, is_dir=False),
        ProjectRow(rel_path="moved/c.txt", name="c.txt", depth=0, is_dir=False),
    ]
    controller.tree_rev = 1
    controller.cached_rows = []
    controller.apply_post_move_selection(old_paths, new_paths, "a.txt")

    selected = controller.selected_paths(controller.selectable_rows)
    assert selected == ["moved/a.txt", "moved/c.txt"]
    assert controller.primary_path(controller.selectable_rows) == "moved/a.txt"


def test_select_all_and_clear_selection(tmp_path: Path) -> None:
    controller = _controller_with_rows(tmp_path, ["a.txt", "b.txt", "c.txt"])
    controller.select_all()
    assert controller.selection_count() == 3

    controller.clear_selection()
    assert controller.selection_count() == 0
    assert controller.get_selected_row() is None


def test_invert_selection(tmp_path: Path) -> None:
    controller = _controller_with_rows(tmp_path, ["a.txt", "b.txt", "c.txt"])
    controller.handle_click(0)
    controller.invert_selection()

    selected = controller.selected_paths(controller.selectable_rows)
    assert selected == ["b.txt", "c.txt"]