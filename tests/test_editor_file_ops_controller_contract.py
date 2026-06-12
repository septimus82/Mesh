"""Contract tests for EditorFileOpsController."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

import pytest

from engine.editor.editor_file_ops_controller import EditorFileOpsController


class MockRow:
    def __init__(self, rel_path, is_dir=False):
        self.entry = SimpleNamespace(rel_path=rel_path, is_dir=is_dir)
        self.recent = None

class MockController:
    def __init__(self, tmp_path):
        self.window = SimpleNamespace()
        self.window.repo_root = tmp_path
        self.window.player_hud = MagicMock()
        self.window.scene_controller = MagicMock()
        self.window.scene_controller._loaded_scene_data = {"entities": [{"id": "e1", "sprite": "assets/old.png"}]}

        self.rows = []
        self._project_selected_index = -1

        self._project_tree_rev = 0
        self._refresh_project_explorer_rows = MagicMock()
        self._push_command = MagicMock()

        # Mock Project Explorer for v1.5 compat
        self.project_explorer = MagicMock()
        self.project_explorer.get_selected_row = self._get_selected_row_mock

    def _get_selected_row_mock(self):
        if 0 <= self._project_selected_index < len(self.rows):
            return self.rows[self._project_selected_index]
        return None

    def _project_explorer_selectable_rows(self):
        return self.rows

@pytest.fixture
def controller(tmp_path):
    return MockController(tmp_path)

def test_rename_web_preview_no_fs_write(controller, tmp_path):
    """Web mode should not touch FS, but update refs and push undo."""
    # Setup
    old_file = tmp_path / "assets" / "old.png"
    old_file.parent.mkdir(parents=True)
    old_file.write_text("content")

    controller.rows = [MockRow("assets/old.png")]
    controller._project_selected_index = 0

    ops = EditorFileOpsController(controller)

    # Mock web environment
    with patch("engine.editor.editor_file_ops_controller.sys.platform", "emscripten"):
        result = ops.rename_selected_asset("new.png")

    assert result is True

    # Verify FS untouched
    assert old_file.exists()
    assert not (tmp_path / "assets" / "new.png").exists()

    # Verify Undo Pushed
    controller._push_command.assert_called_once()
    cmd = controller._push_command.call_args[0][0]
    assert cmd["type"] == "safe_rename"
    assert cmd["old_path"] == "assets/old.png"
    assert cmd["new_path"] == "assets/new.png"
    assert len(cmd["replacements"]) == 1 # 1 ref in mocked scene

    # Verify Scene Updated
    entities = controller.window.scene_controller._loaded_scene_data["entities"]
    assert entities[0]["sprite"] == "assets/new.png"

    # Verify Toast
    controller.window.player_hud.enqueue_toast.assert_called_with(ANY, seconds=ANY)
    assert "Preview" in controller.window.player_hud.enqueue_toast.call_args[0][0]

def test_rename_native_fs_write(controller, tmp_path):
    """Native mode should rename file and update refs."""
    # Setup
    old_file = tmp_path / "assets" / "old.png"
    old_file.parent.mkdir(parents=True)
    old_file.write_text("content")

    controller.rows = [MockRow("assets/old.png")]
    controller._project_selected_index = 0

    ops = EditorFileOpsController(controller)

    # Mock native environment
    with patch("engine.editor.editor_file_ops_controller.sys.platform", "win32"):
         result = ops.rename_selected_asset("new.png")

    assert result is True

    # Verify FS changed
    assert not old_file.exists()
    assert (tmp_path / "assets" / "new.png").exists()

    # Verify Undo Pushed
    assert controller._push_command.call_count == 1

    # Verify Tree Refresh
    controller.project_explorer.refresh_tree.assert_called_once()

def test_no_op_rename(controller):
    """Renaming to same name should be no-op."""
    controller.rows = [MockRow("assets/file.png")]
    controller._project_selected_index = 0

    ops = EditorFileOpsController(controller)
    result = ops.rename_selected_asset("file.png")

    assert result is True
    controller._push_command.assert_not_called()

def test_safe_error_handling_fs_fail(controller, tmp_path):
    """FS failure shouldn't crash, still tries ref update if desired (or handled gracefully)."""
    # Setup
    old_file = tmp_path / "assets" / "old.png"
    old_file.parent.mkdir(parents=True)
    old_file.write_text("content")

    controller.rows = [MockRow("assets/old.png")]
    controller._project_selected_index = 0

    ops = EditorFileOpsController(controller)

    # Force FS rename fail (e.g. permission error or destination exists)
    # Actually mock _perform_fs_rename to return False
    with patch.object(ops, "_perform_fs_rename", return_value=False):
        with patch("engine.editor.editor_file_ops_controller.sys.platform", "win32"):
            # Should still return result (True or False depending on implementation choice,
            # original code continued with ref update so returns True)
            result = ops.rename_selected_asset("new.png")

    assert result is True

    # Ref update still happened
    entities = controller.window.scene_controller._loaded_scene_data["entities"]
    assert entities[0]["sprite"] == "assets/new.png"

def test_move_selected_asset(controller, tmp_path):
    # Setup
    old_file = tmp_path / "assets" / "old.png"
    old_file.parent.mkdir(parents=True)
    old_file.write_text("content")

    (tmp_path / "assets" / "sub").mkdir()

    controller.rows = [MockRow("assets/old.png")]
    controller._project_selected_index = 0

    ops = EditorFileOpsController(controller)

    with patch("engine.editor.editor_file_ops_controller.sys.platform", "win32"):
         result = ops.move_selected_asset("assets/sub")

    assert result is True
    assert (tmp_path / "assets" / "sub" / "old.png").exists()
    assert not old_file.exists()

    cmd = controller._push_command.call_args[0][0]
    assert cmd["type"] == "safe_move"
    assert cmd["new_path"] == "assets/sub/old.png"


def test_delete_selected_paths_batch_native(controller, tmp_path):
    # Setup
    a_file = tmp_path / "assets" / "a.png"
    b_file = tmp_path / "assets" / "b.png"
    a_file.parent.mkdir(parents=True)
    a_file.write_text("a")
    b_file.write_text("b")

    controller.window.scene_controller._loaded_scene_data = {
        "entities": [{"id": "e1", "sprite": "assets/a.png"}],
    }

    ops = EditorFileOpsController(controller)
    with patch("engine.editor.editor_file_ops_controller.sys.platform", "win32"):
        result = ops.delete_selected_paths(["assets/a.png", "assets/b.png"])

    assert result is True
    assert not a_file.exists()
    assert not b_file.exists()
    assert controller._push_command.call_count >= 1
    entities = controller.window.scene_controller._loaded_scene_data["entities"]
    assert entities[0]["sprite"] == ""


def test_delete_selected_paths_batch_web_preview(controller, tmp_path):
    a_file = tmp_path / "assets" / "a.png"
    a_file.parent.mkdir(parents=True)
    a_file.write_text("a")

    ops = EditorFileOpsController(controller)
    with patch("engine.editor.editor_file_ops_controller.sys.platform", "emscripten"):
        result = ops.delete_selected_paths(["assets/a.png"])

    assert result is True
    assert a_file.exists()


def test_move_selected_paths_batch_native(controller, tmp_path):
    a_file = tmp_path / "assets" / "a.png"
    b_file = tmp_path / "assets" / "b.png"
    a_file.parent.mkdir(parents=True)
    a_file.write_text("a")
    b_file.write_text("b")
    (tmp_path / "assets" / "dest").mkdir()

    ops = EditorFileOpsController(controller)
    with patch("engine.editor.editor_file_ops_controller.sys.platform", "win32"):
        result = ops.move_selected_paths_to_folder(
            ["assets/a.png", "assets/b.png"], "assets/dest"
        )

    assert result is True
    assert (tmp_path / "assets" / "dest" / "a.png").exists()
    assert (tmp_path / "assets" / "dest" / "b.png").exists()
    cmd = controller._push_command.call_args[0][0]
    assert cmd["type"] == "safe_move_batch"
    assert cmd["label"] == "Move Assets · 2 → assets/dest"
