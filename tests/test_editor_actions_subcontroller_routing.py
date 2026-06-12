"""Test that actions route to subcontrollers via Protocols."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from engine.editor.editor_actions import run_editor_action
from tests._dock_stub import make_dock_stub


def test_copy_path_uses_file_ops_protocol() -> None:
    # Setup
    mock_file_ops = MagicMock()
    mock_file_ops.can_copy_selected_path.return_value = True
    mock_file_ops.copy_selected_paths = MagicMock()

    mock_editor = MagicMock()
    mock_editor.active = True
    mock_editor.dock = make_dock_stub(left_tab="Project")
    mock_editor.file_ops = mock_file_ops
    mock_editor.project_explorer = MagicMock()
    mock_editor.project_explorer.selected_paths.return_value = ["assets/a.png", "assets/b.png"]
    mock_editor.project_explorer.selection_count.return_value = 2

    mock_window = SimpleNamespace(editor_controller=mock_editor)

    # Execute
    result = run_editor_action("editor.project_explorer.copy_path", mock_editor, mock_window)

    # Verify
    mock_file_ops.copy_selected_paths.assert_called_once_with(["assets/a.png", "assets/b.png"])
    # Enablement check might be called or logic check inside action?
    # Action doesn't call can_copy, enablement does.
    # But checking enablement manually here isn't done by run_editor_action unless we call enablement function.
    # However, I removed the 'hasattr' logic, so relying on Protocol.


def test_copy_common_parent_uses_file_ops_protocol() -> None:
    mock_file_ops = MagicMock()
    mock_file_ops.can_copy_selected_path.return_value = True

    mock_editor = MagicMock()
    mock_editor.active = True
    mock_editor.dock = make_dock_stub(left_tab="Project")
    mock_editor.file_ops = mock_file_ops
    mock_editor.project_explorer = MagicMock()
    mock_editor.project_explorer.selected_paths.return_value = ["assets/a.png", "assets/b.png"]
    mock_editor.project_explorer.selection_count.return_value = 2

    mock_window = SimpleNamespace(editor_controller=mock_editor)

    run_editor_action("editor.project_explorer.copy_common_parent", mock_editor, mock_window)

    mock_file_ops.copy_common_parent.assert_called_once_with(["assets/a.png", "assets/b.png"])

def test_safe_rename_uses_file_ops_protocol() -> None:
    # Setup
    mock_file_ops = MagicMock()
    mock_file_ops.can_safe_rename_selected_asset.return_value = True

    mock_project_explorer = MagicMock()

    mock_editor = MagicMock()
    mock_editor.active = True
    mock_editor.dock = make_dock_stub(left_tab="Project")

    mock_editor.file_ops = mock_file_ops
    mock_editor.project_explorer = mock_project_explorer

    # Internal state for UI populating
    mock_editor._get_selected_project_entry_path.return_value = "assets/foo.png"

    mock_window = SimpleNamespace(editor_controller=mock_editor)

    # Execute
    run_editor_action("editor.project_explorer.safe_rename_asset", mock_editor, mock_window)

    # Verify - now uses inline rename via project_explorer controller
    mock_file_ops.can_safe_rename_selected_asset.assert_called()
    mock_project_explorer.begin_inline_rename.assert_called_once_with("assets/foo.png")

def test_safe_rename_aborts_if_capability_missing() -> None:
    # Setup
    mock_file_ops = MagicMock()
    mock_file_ops.can_safe_rename_selected_asset.return_value = False

    mock_project_explorer = MagicMock()

    mock_editor = MagicMock()
    mock_editor.active = True
    mock_editor.dock = make_dock_stub(left_tab="Project")
    mock_editor.file_ops = mock_file_ops
    mock_editor.project_explorer = mock_project_explorer

    mock_window = SimpleNamespace(editor_controller=mock_editor)

    run_editor_action("editor.project_explorer.safe_rename_asset", mock_editor, mock_window)

    # Verify - begin_inline_rename should NOT be called
    mock_project_explorer.begin_inline_rename.assert_not_called()


def test_safe_move_routes_to_batch_when_multi_selected() -> None:
    mock_file_ops = MagicMock()
    mock_file_ops.can_safe_move_selected_asset.return_value = True

    mock_project_explorer = MagicMock()
    mock_project_explorer.selection_count.return_value = 2

    mock_editor = MagicMock()
    mock_editor.active = True
    mock_editor.dock = make_dock_stub(left_tab="Project")
    mock_editor.file_ops = mock_file_ops
    mock_editor.project_explorer = mock_project_explorer

    def _prompt(cb):
        cb("assets/dest")
        return True

    mock_editor.prompt_project_explorer_move_destination.side_effect = _prompt

    mock_window = SimpleNamespace(editor_controller=mock_editor)

    run_editor_action("editor.project_explorer.refactor_move_selected", mock_editor, mock_window)

    mock_file_ops.request_safe_move_refactor.assert_called_once_with("assets/dest")
