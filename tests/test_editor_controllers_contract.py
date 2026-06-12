"""Contract tests for extracted editor controllers.

Verifies:
- EditorWorkspaceController behavior
- EditorSelectionController behavior
- EditorSceneOpsController behavior
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock


class MockWindow:
    def __init__(self) -> None:
        self.repo_root = Path("/tmp/mock_repo")
        self.width = 800
        self.height = 600

class MockController:
    def __init__(self) -> None:
        self.window = MockWindow()
        self.scene_dirty = False
        self.dirty_state = MagicMock()
        self.dirty_state.is_dirty = False
        self.selection_group = MagicMock()

class TestEditorWorkspaceController:
    def test_add_recent_project(self) -> None:
        from engine.editor.editor_workspace_controller import EditorWorkspaceController

        ctrl = MockController()
        ws_ctrl = EditorWorkspaceController(ctrl)

        # Test adding
        ws_ctrl.add_recent_project("proj1")
        assert "proj1" in ws_ctrl.recent_projects
        assert len(ws_ctrl.recent_projects) == 1

        # Test dedupe
        ws_ctrl.add_recent_project("proj1")
        assert len(ws_ctrl.recent_projects) == 1

        # Test limit
        for i in range(15):
            ws_ctrl.add_recent_project(f"proj{i}")
        assert len(ws_ctrl.recent_projects) == 10
        assert ws_ctrl.recent_projects[0] == "proj14"

class TestEditorSelectionController:
    def test_selection_basics(self) -> None:
        from engine.editor.editor_selection_controller import EditorSelectionController

        ctrl = MockController()
        sel_ctrl = EditorSelectionController(ctrl)

        # Select
        sel_ctrl.select_entity("ent1")
        assert sel_ctrl.primary_selected_id == "ent1"
        assert "ent1" in sel_ctrl.selected_ids

        # Additive
        sel_ctrl.select_entity("ent2", additive=True)
        assert len(sel_ctrl.selected_ids) == 2
        assert sel_ctrl.primary_selected_id == "ent2"  # Usually updates primary

        # Deselect
        sel_ctrl.deselect_entity("ent1")
        assert "ent1" not in sel_ctrl.selected_ids

        # Clear
        sel_ctrl.clear_selection()
        assert len(sel_ctrl.selected_ids) == 0
        assert sel_ctrl.primary_selected_id is None

class TestEditorSceneOpsController:
    def test_dirty_state(self) -> None:
        from engine.editor.editor_scene_ops import EditorSceneOpsController

        ctrl = MockController()
        ops_ctrl = EditorSceneOpsController(ctrl)
        assert ops_ctrl.scene_dirty is False
        assert ops_ctrl.dirty_state.is_dirty is False

        ops_ctrl.mark_dirty()
        assert ops_ctrl.scene_dirty is True
        assert ops_ctrl.dirty_state.is_dirty is True

        ops_ctrl.mark_clean()
        assert ops_ctrl.scene_dirty is False
        assert ops_ctrl.dirty_state.is_dirty is False
