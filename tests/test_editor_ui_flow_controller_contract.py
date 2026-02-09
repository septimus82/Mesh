import pytest
from unittest.mock import MagicMock, patch
import sys
from typing import Any, List, Optional
from types import SimpleNamespace

# Mock optional_arcade if not present
if "engine.optional_arcade" not in sys.modules:
    sys.modules["engine.optional_arcade"] = MagicMock()
    sys.modules["engine.optional_arcade.arcade"] = MagicMock()

# Stub for FindResult/FindItem
class FindResult:
    def __init__(self, kind: str, item_id: str, label: str):
        self.kind = kind
        self.item_id = item_id
        self.label = label
        self.score = 1.0

# Stub EditorController
class StubEditorController:
    def __init__(self):
        self.preview_called_with = None
        self.commit_called_with = None
        self.cancel_preview_called = False
        self.run_action_called_with = None
        
        # Mocks needed for find_everything logic that touches window/repo
        self.window = MagicMock()
        self.window.repo_root = None
        
        # Protocol stubs
        self.scene_switcher_recent = []
        self._find_items_override = None
        self._asset_browser_cached_rows = []
        self.problems = SimpleNamespace(issues=[])

    def toggle_find_everything(self) -> bool: return True
    def open_scene(self, scene_path: str) -> None: pass
    def select_entity(self, entity_id: str) -> None: pass
    def focus_camera_on_selection(self) -> None: pass

    # Activation hooks
    def _activate_find_command(self, item_id: str) -> bool: return False # Default to False to let fallback logic run if any
    def _activate_find_asset(self, item_id: str) -> bool: return True
    def _activate_find_scene(self, item_id: str) -> bool: return True
    def _activate_find_entity(self, item_id: str) -> bool: return True
    def _activate_find_problem(self, item_id: str) -> bool: return True

    # -- Protocol Implementation --
    def ui_activate_command(self, cmd_id: str) -> bool: return self._activate_find_command(cmd_id)
    def ui_activate_asset(self, item_id: str) -> bool: return self._activate_find_asset(item_id)
    def ui_activate_scene(self, item_id: str) -> bool: return self._activate_find_scene(item_id)
    def ui_activate_entity(self, item_id: str) -> bool: return self._activate_find_entity(item_id)
    def ui_activate_problem(self, item_id: str) -> bool: return self._activate_find_problem(item_id)

    def ui_get_palette_items(self) -> List[Any]:
        if self._find_items_override is not None:
            return list(self._find_items_override)
        return []

    def ui_toast(self, msg: str) -> None: pass

    def preview_hd2d_preset(self, preset_id: str) -> None:
        self.preview_called_with = preset_id

    def ui_hd2d_preview(self, preset_id: str) -> None:
        self.preview_hd2d_preset(preset_id)

    def _cancel_hd2d_preview(self) -> None:
        self.cancel_preview_called = True
        
    def ui_hd2d_cancel_preview(self) -> None:
        self._cancel_hd2d_preview()
        
    def commit_hd2d_preset(self, preset_id: str) -> bool:
        self.commit_called_with = preset_id
        return True

    def ui_hd2d_commit(self, preset_id: str) -> bool:
        return self.commit_hd2d_preset(preset_id)


    def commit_hd2d_preset(self, preset_id: str) -> bool:
        self.commit_called_with = preset_id
        return True

    def _cancel_hd2d_preview(self) -> None:
        self.cancel_preview_called = True
        
    def run_action(self, action_id: str) -> bool:
        self.run_action_called_with = action_id
        return True

# Prepare to import the controller (it doesn't exist yet, so we define tests anticipating it)
# We will create the file in the next step.

from engine.editor.editor_ui_flow_controller import EditorUIFlowController

class TestEditorUIFlowController:
    @pytest.fixture
    def ctrl(self):
        self.mock_controller = StubEditorController()
        c = EditorUIFlowController(self.mock_controller)
        # Mock _refresh_results to avoid complex dependencies in unit tests
        # We test _refresh_results logic via integration tests or by mocking deps
        c._refresh_results = MagicMock()
        return c

    def test_open_close(self, ctrl):
        """Test toggling the palette open and close."""
        assert not ctrl.is_open
        
        ctrl.open_palette()
        assert ctrl.is_open
        assert ctrl.query == ""
        assert ctrl.selection_index == 0
        ctrl._refresh_results.assert_called_once()
        
        ctrl.close_palette()
        assert not ctrl.is_open
        # Use controller attribute which is the stub
        assert ctrl.controller.cancel_preview_called

    def test_update_query_resets_selection(self, ctrl):
        """Test that changing query resets selection index."""
        ctrl.open_palette()
        ctrl.selection_index = 5
        
        ctrl.update_query("prop")
        assert ctrl.query == "prop"
        assert ctrl.selection_index == 0
        ctrl._refresh_results.call_count >= 2 # Once for open, once for update

    # For navigation tests, we need cached_results to be set.
    # Since we mocked _refresh_results, we can set cached_results manually.
    
    def test_navigation(self, ctrl):
        """Test selection navigation with clamping."""
        ctrl.open_palette()
        # Mock results list
        ctrl.cached_results = [FindResult("kind", "id", "label")] * 5
        
        # We need to manually invoke maybe_preview since moving selection calls it
        # But wait, move_selection calls maybe_preview_from_selection.
        # We should let that run.
        
        ctrl.move_selection(1)
        assert ctrl.selection_index == 1
        
        ctrl.move_selection(10)
        assert ctrl.selection_index == 4  # Clamped
        
        ctrl.move_selection(-10)
        assert ctrl.selection_index == 0  # Clamped

    def test_hd2d_preview_trigger(self, ctrl):
        """Test that navigating to an HD2D preset command triggers preview."""
        ctrl.open_palette()
        
        # Setup results with one normal item and one HD2D preset item
        ctrl.cached_results = [
            FindResult("command", "regular.cmd", "Regular"),
            FindResult("command", "editor.hd2d.preset.retro.apply", "Apply Retro"),
            FindResult("asset", "some_asset", "Asset")
        ]
        
        # Select regular command
        ctrl.selection_index = 0
        ctrl.maybe_preview_from_selection()
        # Should cancel any existing preview
        assert ctrl.controller.cancel_preview_called
        ctrl.controller.cancel_preview_called = False
        
        # Select HD2D preset
        ctrl.selection_index = 1
        ctrl.maybe_preview_from_selection()
        assert ctrl.controller.preview_called_with == "retro"
        
        # Select asset
        ctrl.selection_index = 2
        ctrl.maybe_preview_from_selection()
        assert ctrl.controller.cancel_preview_called
        
    def test_commit_hd2d_preset(self, ctrl):
        """Test that committing an HD2D preset calls the specific controller hook."""
        ctrl.open_palette()
        ctrl.cached_results = [
            FindResult("command", "editor.hd2d.preset.retro.apply", "Apply Retro")
        ]
        
        ctrl.commit_selection()
        
        assert ctrl.controller.commit_called_with == "retro"
        assert not ctrl.is_open

    @patch("engine.editor.editor_ui_flow_controller.run_editor_action")
    def test_commit_regular_action(self, mock_run_action, ctrl):
        """Test that committing a regular action uses generic runner."""
        ctrl.open_palette()
        ctrl.cached_results = [
            FindResult("command", "editor.action.save", "Save")
        ]
        
        ctrl.commit_selection()
        
        mock_run_action.assert_called_once()
        args = mock_run_action.call_args
        assert args[0][0] == "editor.action.save"
        assert not ctrl.is_open

    def test_escape_cancels_preview(self, ctrl):
        """Test that closing via Escape cancels preview."""
        ctrl.open_palette()
        ctrl.close_palette(cancel_preview=True)
        assert not ctrl.is_open
        assert ctrl.controller.cancel_preview_called

