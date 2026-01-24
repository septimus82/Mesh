import pytest
from unittest.mock import MagicMock, patch
from engine.editor_controller import EditorModeController
from engine.config import EngineConfig
import arcade

MOCK_PALETTE = [
    {"id": "crate", "display_name": "Crate", "entity": {"name": "Crate"}},
    {"id": "enemy", "display_name": "Enemy", "entity": {"name": "Enemy"}}
]

class MockWindow:
    def __init__(self):
        cfg = EngineConfig()
        self.width = cfg.width
        self.height = cfg.height
        self.scene_controller = MagicMock()
        self.screen_to_world = MagicMock(return_value=(0, 0))

@pytest.fixture(autouse=True)
def mock_prefabs():
    with patch("engine.editor_controller.PREFAB_PALETTE", MOCK_PALETTE), \
         patch("engine.editor_controller.load_prefab_palette", return_value=MOCK_PALETTE):
        yield

def test_palette_toggle():
    window = MockWindow()
    controller = EditorModeController(window)
    controller.active = True
    
    assert not controller.palette_active
    
    controller.toggle_palette()
    assert controller.palette_active
    
    controller.toggle_palette()
    assert not controller.palette_active

def test_palette_navigation():
    window = MockWindow()
    controller = EditorModeController(window)
    controller.active = True
    controller.palette_active = True
    
    assert controller.palette_index == 0
    
    controller.move_palette_selection(1)
    assert controller.palette_index == 1
    
    controller.move_palette_selection(-1)
    assert controller.palette_index == 0
    
    # Wrap around
    controller.move_palette_selection(-1)
    assert controller.palette_index == len(MOCK_PALETTE) - 1

def test_place_entity():
    window = MockWindow()
    controller = EditorModeController(window)
    controller.active = True
    controller.palette_active = True
    controller.palette_index = 0 # Crate
    
    # Mock _create_sprite
    new_sprite = MagicMock(spec=arcade.Sprite)
    window.scene_controller._create_sprite.return_value = new_sprite
    
    controller.place_entity_at_mouse(100, 100)
    
    # Verify create called
    window.scene_controller._create_sprite.assert_called()
    args = window.scene_controller._create_sprite.call_args[0][0]
    assert args["name"].startswith("Crate")
    
    # Verify added to layer
    window.scene_controller.add_sprite_to_layer.assert_called_with(new_sprite, "entities")

def test_duplicate_entity():
    window = MockWindow()
    controller = EditorModeController(window)
    controller.active = True
    
    # Select entity
    sprite = MagicMock(spec=arcade.Sprite)
    sprite.mesh_entity_data = {"name": "Original", "x": 100, "y": 100, "layer": "entities"}
    controller.selected_entity = sprite
    
    # Mock create
    dup_sprite = MagicMock(spec=arcade.Sprite)
    window.scene_controller._create_sprite.return_value = dup_sprite
    
    controller.duplicate_selected()
    
    # Verify create called with offset
    window.scene_controller._create_sprite.assert_called()
    args = window.scene_controller._create_sprite.call_args[0][0]
    assert args["name"] == "Original_copy"
    assert args["x"] == 100 + controller.grid_size
    assert args["y"] == 100 - controller.grid_size
    
    # Verify selection changed
    assert controller.selected_entity == dup_sprite

def test_delete_entity():
    window = MockWindow()
    controller = EditorModeController(window)
    controller.active = True
    
    # Setup scene
    sprite = MagicMock(spec=arcade.Sprite)
    sprite.mesh_name = "ToDelete"
    layer = [sprite]
    window.scene_controller.layers = {"entities": layer}
    window.scene_controller.solid_sprites = [sprite]
    
    controller.selected_entity = sprite
    
    controller.delete_selected()
    
    assert sprite not in layer
    assert sprite not in window.scene_controller.solid_sprites
    assert controller.selected_entity is None
