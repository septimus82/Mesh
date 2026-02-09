from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from engine.editor.editor_project_explorer_controller import ProjectExplorerController
from engine.editor.project_explorer_context_menu_model import ContextMenuItem
from engine.editor.project_explorer_model import ProjectRow
from engine.editor.project_explorer_selection_model import SelectionState
from tests._dock_stub import make_dock_stub


def _make_controller() -> ProjectExplorerController:
    ctrl = ProjectExplorerController(repo_root=MagicMock())
    ctrl.project_rows = [
        ProjectRow(rel_path="assets/foo.png", name="foo.png", depth=0, is_dir=False),
        ProjectRow(rel_path="assets/bar.png", name="bar.png", depth=0, is_dir=False),
    ]
    ctrl.tree_rev = 1
    ctrl._filter_rows()
    ctrl.selection_state = SelectionState(primary_index=1, selected_indices=frozenset({1}), anchor_index=1)
    return ctrl


def _make_editor(ctrl: ProjectExplorerController) -> SimpleNamespace:
    ui_layers = MagicMock()
    window = SimpleNamespace(width=1280, height=720, scene_controller=None)
    file_ops = SimpleNamespace(
        can_safe_rename_selected_asset=lambda: True,
        can_safe_move_selected_assets_folder=lambda: True,
        can_safe_move_selected_asset=lambda: True,
        can_delete_selected_assets=lambda paths: True,
    )
    editor = SimpleNamespace(
        active=True,
        window=window,
        ui_layers=ui_layers,
        file_ops=file_ops,
        project_explorer=ctrl,
        _primary_selected_id=None,
        dock=make_dock_stub(left_tab="Project"),
    )
    return editor


def test_open_sets_first_enabled_index() -> None:
    ctrl = _make_controller()
    editor = _make_editor(ctrl)
    ctrl.open_context_menu(10, 10, editor, active_scopes=("project_explorer", "global"))
    assert ctrl.context_menu_open is True
    assert ctrl.context_menu_items
    assert ctrl.context_menu_index == 0


def test_move_selection_skips_separators_and_disabled() -> None:
    ctrl = ProjectExplorerController(repo_root=MagicMock())
    ctrl.context_menu_open = True
    ctrl.context_menu_items = [
        ContextMenuItem(kind="action", action_id="a", title="A", enabled=False),
        ContextMenuItem(kind="separator", action_id=None, title=None, enabled=False),
        ContextMenuItem(kind="action", action_id="b", title="B", enabled=True),
    ]
    ctrl.context_menu_index = 0
    ctrl.move_context_menu_selection(1)
    assert ctrl.context_menu_index == 2


def test_activate_runs_action_and_closes() -> None:
    ctrl = ProjectExplorerController(repo_root=MagicMock())
    ctrl.context_menu_open = True
    ctrl.context_menu_items = [
        ContextMenuItem(kind="action", action_id="test.action", title="Test", enabled=True),
    ]
    ctrl.context_menu_index = 0
    editor = _make_editor(ctrl)
    with patch("engine.editor.editor_actions.run_editor_action") as runner:
        runner.return_value = True
        assert ctrl.activate_context_menu_item(editor) is True
    assert ctrl.context_menu_open is False


def test_close_clears_state() -> None:
    ctrl = _make_controller()
    editor = _make_editor(ctrl)
    ctrl.open_context_menu(10, 10, editor, active_scopes=("project_explorer", "global"))
    assert ctrl.context_menu_open is True
    ctrl.close_context_menu(editor)
    assert ctrl.context_menu_open is False
    assert ctrl.context_menu_items == []


def test_selection_persistence_on_reopen() -> None:
    ctrl = _make_controller()
    editor = _make_editor(ctrl)
    ctrl.open_context_menu(10, 10, editor, active_scopes=("project_explorer", "global"))
    ctrl.move_context_menu_selection(1)
    prior_action = None
    if ctrl.context_menu_index is not None:
        item = ctrl.context_menu_items[ctrl.context_menu_index]
        prior_action = item.action_id
    ctrl.close_context_menu(editor)
    ctrl.open_context_menu(20, 20, editor, active_scopes=("project_explorer", "global"))
    assert ctrl.context_menu_index is not None
    assert ctrl.context_menu_items[ctrl.context_menu_index].action_id == prior_action


def test_selection_change_resets_persistence() -> None:
    ctrl = _make_controller()
    editor = _make_editor(ctrl)
    ctrl.open_context_menu(10, 10, editor, active_scopes=("project_explorer", "global"))
    ctrl.move_context_menu_selection(1)
    ctrl.close_context_menu(editor)
    # Change selection to a different row
    ctrl.selection_state = SelectionState(primary_index=2, selected_indices=frozenset({2}), anchor_index=2)
    ctrl.open_context_menu(10, 10, editor, active_scopes=("project_explorer", "global"))
    assert ctrl.context_menu_index == 0


def test_all_disabled_noop_activate() -> None:
    ctrl = ProjectExplorerController(repo_root=MagicMock())
    ctrl.context_menu_open = True
    ctrl.context_menu_items = [
        ContextMenuItem(kind="action", action_id="a", title="A", enabled=False),
        ContextMenuItem(kind="separator", action_id=None, title=None, enabled=False),
    ]
    ctrl.context_menu_index = None
    editor = _make_editor(ctrl)
    with patch("engine.editor.editor_actions.run_editor_action") as runner:
        assert ctrl.activate_context_menu_item(editor) is False
    assert ctrl.context_menu_open is True


def test_right_click_updates_anchor() -> None:
    ctrl = _make_controller()
    editor = _make_editor(ctrl)
    ctrl.open_context_menu(10, 10, editor, active_scopes=("project_explorer", "global"))
    assert ctrl.context_menu_anchor == (10, 10)
    ctrl.open_context_menu(30, 40, editor, active_scopes=("project_explorer", "global"))
    assert ctrl.context_menu_anchor == (30, 40)
