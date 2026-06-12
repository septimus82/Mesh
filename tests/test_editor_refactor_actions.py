"""Integration/Contract tests for specific Refactor Actions wiring."""
from __future__ import annotations

from unittest.mock import MagicMock, Mock

from engine.editor.editor_actions import get_editor_actions
from tests._dock_stub import make_dock_stub


def test_action_refactor_delete_wiring() -> None:
    # Setup
    editor = MagicMock()
    project = MagicMock()
    file_ops = MagicMock()
    editor.project_explorer = project
    editor.file_ops = file_ops
    editor.active = True
    editor.dock = make_dock_stub(left_tab="Project")
    editor.dock = make_dock_stub(left_tab="Project")
    window = MagicMock()
    window.editor_controller = editor

    # Setup selection state
    project.selectable_rows = ["row1"]
    project.selected_paths.return_value = ["some/file.txt"]
    # For _enabled_project_explorer_selection:
    project.selection_state.selected_indices = [0]
    project.selection_count.return_value = 1

    # We call get_editor_actions to get the bound actions
    actions = get_editor_actions(editor, window)

    # Find action
    action = next((a for a in actions if a.id == "editor.project_explorer.refactor_delete_selected"), None)
    assert action is not None
    assert action.shortcut == "Del"

    # Verify enabled logic
    assert action.enabled(editor, window) is True

    # Run
    action.run(window)

    # Verify call
    project.ensure_rows.assert_called_once()
    project.selected_paths.assert_called_with(["row1"])
    file_ops.request_safe_delete_refactor.assert_called_with(["some/file.txt"])

def test_action_refactor_move_wiring() -> None:
    editor = MagicMock()
    project = MagicMock()
    file_ops = MagicMock()
    editor.project_explorer = project
    editor.file_ops = file_ops
    editor.active = True
    editor.dock = make_dock_stub(left_tab="Project")
    window = MagicMock()
    window.editor_controller = editor

    project.selectable_rows = ["row1"]
    project.selected_paths.return_value = ["some/file.txt"]
    project.selection_state.selected_indices = [0]
    project.selection_count.return_value = 1

    actions = get_editor_actions(editor, window)
    action = next((a for a in actions if a.id == "editor.project_explorer.refactor_move_selected"), None)

    assert action is not None
    assert action.shortcut == "Ctrl+Shift+M"
    assert action.enabled(editor, window) is True

    def _prompt(cb):
        cb("assets")
    editor.prompt_project_explorer_move_destination = _prompt
    action.run(window)

    file_ops.request_safe_move_refactor.assert_called_with("assets")

def test_action_refactor_rename_commit_wiring() -> None:
    editor = MagicMock()
    project = MagicMock()
    file_ops = MagicMock()
    editor.project_explorer = project
    editor.file_ops = file_ops
    editor.active = True
    window = MagicMock()
    window.editor_controller = editor

    # Setup rename state
    project.inline_rename_active = True
    project.get_inline_rename_commit_result.return_value = (True, "new_name.txt", None)

    fake_state = Mock()
    fake_state.original_path = "dir/old_name.txt"
    project.inline_rename_state = fake_state

    actions = get_editor_actions(editor, window)
    action = next((a for a in actions if a.id == "editor.project_explorer.refactor_rename_commit"), None)

    assert action is not None
    assert action.enabled(editor, window) is True

    action.run(window)

    # Verify state cleared
    project.cancel_inline_rename.assert_called_once()

    # Verify refactor call with reconstructed path
    # dir/old_name.txt -> dir/new_name.txt
    file_ops.request_safe_rename_refactor.assert_called_with("dir/old_name.txt", "dir/new_name.txt")
