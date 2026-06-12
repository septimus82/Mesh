from unittest.mock import MagicMock, patch

import pytest

from engine.editor.editor_project_explorer_controller import ProjectExplorerController
from engine.editor.project_explorer_model import ProjectExplorerDisplayRow, ProjectExplorerRecentItem, ProjectRow


@pytest.fixture
def mock_repo_root(tmp_path):
    return tmp_path

@pytest.fixture
def controller(mock_repo_root):
    return ProjectExplorerController(mock_repo_root)

class TestProjectExplorerControllerContract:

    def test_initial_state(self, controller):
        assert controller.tree_rev == 0
        assert controller.project_rows == []
        assert controller.cached_rows == []
        assert controller.selectable_rows == []

    @patch("engine.editor.editor_project_explorer_controller.scan_project_tree")
    def test_refresh_tree(self, mock_scan, controller):
        mock_scan.return_value = [
            ProjectRow(name="foo.txt", rel_path="foo.txt", is_dir=False, depth=0),
            ProjectRow(name="bar/", rel_path="bar", is_dir=True, depth=0),
        ]

        controller.refresh_tree()

        assert controller.tree_rev == 1
        assert len(controller.project_rows) == 2
        assert len(controller.cached_rows) > 0 # Should have rows now (headers etc)

        # Verify filtering happened
        assert controller.filter_cache_key is not None

    @patch("engine.editor.editor_project_explorer_controller.scan_project_tree")
    def test_caching(self, mock_scan, controller):
        mock_scan.return_value = []
        controller.refresh_tree()

        old_key = controller.filter_cache_key
        controller.ensure_rows()
        assert controller.filter_cache_key == old_key # No change

        # Change query
        controller.set_query("foo")
        assert controller.filter_cache_key != old_key

        # Reset query
        controller.set_query("")
        # Key might change back or be new but deterministic

    @patch("engine.editor.editor_project_explorer_controller.scan_project_tree")
    def test_selectable_rows(self, mock_scan, controller):
        # Create a tree
        # Root
        #  - file1
        #  - file2
        mock_scan.return_value = [
             ProjectRow(name="file1.txt", rel_path="file1.txt", is_dir=False, depth=0),
             ProjectRow(name="file2.txt", rel_path="file2.txt", is_dir=False, depth=0),
        ]
        controller.refresh_tree()

        # Selectable rows includes entries
        entries = [r for r in controller.selectable_rows if r.entry is not None]
        assert len(entries) == 2
        assert entries[0].entry.name == "file1.txt"

    def test_selection_movement(self, controller):
        # Manually populate selectable rows for test
        # row 1
        r1 = ProjectExplorerDisplayRow(kind="entry", header=None, entry=MagicMock(), recent=None)
        r2 = ProjectExplorerDisplayRow(kind="entry", header=None, entry=MagicMock(), recent=None)
        r3 = ProjectExplorerDisplayRow(kind="entry", header=None, entry=MagicMock(), recent=None)

        controller.selectable_rows = [r1, r2, r3]
        controller.selected_index = 0

        controller.move_selection(1)
        assert controller.selected_index == 1

        controller.move_selection(1)
        assert controller.selected_index == 2

        controller.move_selection(1)
        assert controller.selected_index == 2 # Clamp

        controller.move_selection(-5)
        assert controller.selected_index == 0 # Clamp

    @patch("engine.editor.editor_project_explorer_controller.scan_project_tree")
    def test_reveal_path(self, mock_scan, controller):
        mock_scan.return_value = [
            ProjectRow(name="target.txt", rel_path="target.txt", is_dir=False, depth=0),
        ]
        controller.refresh_tree()

        # Should correspond to something in selectable_rows
        # "Target" entry should be there.

        found = controller.reveal_path("target.txt", viewport_height=100, row_height=10)
        assert found
        assert controller.selected_index >= 0

        # Test Not Found
        found = controller.reveal_path("missing.txt", viewport_height=100, row_height=10)
        assert not found

    def test_recents_push_and_clear(self, controller):
        item = ProjectExplorerRecentItem(kind="scene", rel_path="s1", label="Scene 1")
        controller.push_recent_item(item)

        assert len(controller.recents) == 1
        assert controller.recents[0].label == "Scene 1"
        assert controller.recents_rev > 0

        controller.clear_recents()
        assert len(controller.recents) == 0
