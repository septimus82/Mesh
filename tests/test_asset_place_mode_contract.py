import pytest
from unittest.mock import MagicMock
from engine.editor_controller import EditorModeController
import engine.editor_runtime.input as editor_input
from engine.asset_index import AssetRow
import engine.optional_arcade as optional_arcade

class MockWindow:
    def __init__(self):
        self.camera = MagicMock()
        self.camera.position = (0, 0)
        self.scene_controller = MagicMock()
        self.scene_controller._loaded_scene_data = {"entities": {}}
        self.player_hud = MagicMock()
        self._mouse_x = 100
        self._mouse_y = 100
        self.width = 800
        self.height = 600

    def screen_to_world(self, x, y):
        # Simple identity for test
        return x, y

    def console_log(self, msg):
        pass

@pytest.fixture
def test_controller(monkeypatch):
    monkeypatch.setattr(EditorModeController, "load_workspace", MagicMock())
    window = MockWindow()
    controller = EditorModeController(window)
    controller.active = True
    # Ensure dependencies are clean
    controller.asset_place_active = False
    controller.asset_place_path = None
    return controller

def test_activation_enters_placement_mode(test_controller):
    # Setup
    test_controller.asset_browser_active = True
    row = AssetRow(rel_path="assets/img.png", kind="image", display_name="img")
    test_controller._asset_browser_filtered_rows = [row]
    test_controller.asset_browser_selection_index = 0
    
    # Act
    test_controller._activate_selected_asset()
    
    # Assert
    assert test_controller.asset_place_active is True
    assert test_controller.asset_place_path == "assets/img.png"
    assert test_controller.asset_browser_active is False
    test_controller.window.player_hud.enqueue_toast.assert_called()

def test_placement_spawns_entity_snapped(test_controller):
    # Setup placement mode
    test_controller.asset_place_active = True
    test_controller.asset_place_path = "assets/img.png"
    test_controller.snap_enabled = True
    test_controller.snap_mode = "grid16"
    test_controller.grid_size = 16
    
    # Place at (18.0, 18.0)
    test_controller.place_asset_at(18.0, 18.0)
    
    scene_data = test_controller.window.scene_controller._loaded_scene_data
    assert len(scene_data["entities"]) == 1
    
    eid = list(scene_data["entities"].keys())[0]
    entity = scene_data["entities"][eid]
    # Check snap to 16
    assert entity["x"] == 16.0
    assert entity["y"] == 16.0

def test_input_place_and_cancel(test_controller):
    test_controller.asset_place_active = True
    test_controller.asset_place_path = "img.png"
    
    # ESC cancels
    editor_input.handle_input(test_controller, optional_arcade.arcade.key.ESCAPE, 0)
    assert test_controller.asset_place_active is False
    
    # Re-enable
    test_controller.asset_place_active = True
    
    # Enter places
    count = len(test_controller.window.scene_controller._loaded_scene_data["entities"])
    editor_input.handle_input(test_controller, optional_arcade.arcade.key.ENTER, 0)
    count_after = len(test_controller.window.scene_controller._loaded_scene_data["entities"])
    assert count_after == count + 1

    # Mouse Click places
    editor_input.handle_mouse_click(test_controller, 50, 50, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0)
    assert len(test_controller.window.scene_controller._loaded_scene_data["entities"]) == count + 2

    # Mouse Right Click cancels
    editor_input.handle_mouse_click(test_controller, 0, 0, optional_arcade.arcade.MOUSE_BUTTON_RIGHT, 0)
    assert test_controller.asset_place_active is False

def test_multiple_placements_increment_ids(test_controller):
    test_controller.asset_place_active = True
    test_controller.asset_place_path = "assets/tree.png"
    
    # Place 1
    test_controller.place_asset_at(0, 0)
    scene_data = test_controller.window.scene_controller._loaded_scene_data
    assert "asset_tree_1" in scene_data["entities"]
    
    # Place 2
    test_controller.place_asset_at(100, 100)
    assert "asset_tree_2" in scene_data["entities"]
