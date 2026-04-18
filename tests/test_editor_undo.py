import unittest
from unittest.mock import MagicMock, patch
import arcade
from engine.editor_controller import EditorModeController

class MockSprite(MagicMock):
    def __init__(self, name="Entity_1", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mesh_name = name
        self.center_x = 100.0
        self.center_y = 100.0
        self.mesh_behaviours_runtime = []
        self.mesh_entity_data = {"name": name, "x": 100.0, "y": 100.0}

class TestEditorUndo(unittest.TestCase):
    def setUp(self):
        self.patcher = patch("engine.editor_controller.PREFAB_PALETTE", [
            {"id": "crate", "display_name": "Crate", "entity": {"name": "Crate"}},
            {"id": "enemy", "display_name": "Enemy", "entity": {"name": "Enemy"}}
        ])
        self.patcher.start()

        self.window = MagicMock()
        self.window.scene_controller = MagicMock()
        self.window.scene_controller.all_sprites = []
        self.window.scene_controller.layers = {"entities": []}
        self.window.scene_controller.solid_sprites = []
        
        # Mock ensure methods
        self.window.scene_controller._ensure_entity_data_dict = lambda s: s.mesh_entity_data
        self.window.scene_controller._ensure_behaviour_config_root = lambda d: d.setdefault("behaviours", {})
        self.window.scene_controller._get_behaviour_configs_for_sprite = lambda s: []
        
        # Mock mutation
        def apply_mutation(sprite, x=None, y=None):
            if x is not None:
                sprite.center_x = x
            if y is not None:
                sprite.center_y = y
        self.window.scene_controller._apply_entity_mutation = apply_mutation
        
        self.controller = EditorModeController(self.window)
        self.controller.active = True

    def tearDown(self):
        self.patcher.stop()

    def test_undo_move_entity(self):
        sprite = MockSprite()
        self.window.scene_controller.all_sprites = [sprite]
        self.controller.selected_entity = sprite
        
        # Move
        self.controller.nudge_selected(16, 0)
        self.assertEqual(sprite.center_x, 116.0)
        self.assertTrue(self.controller.scene_dirty)
        
        # Undo
        self.controller.undo_last()
        self.assertEqual(sprite.center_x, 100.0)
        
        # Redo
        self.controller.redo_last()
        self.assertEqual(sprite.center_x, 116.0)

    @patch('engine.editor.editor_inspector_controller.get_behaviour_param_defs')
    def test_undo_property_change(self, mock_get_defs):
        # Setup mock defs
        mock_def = MagicMock()
        mock_def.default = 100
        mock_get_defs.return_value = {"hp": mock_def}
        
        sprite = MockSprite()
        self.window.scene_controller.all_sprites = [sprite]
        self.controller.selected_entity = sprite
        
        # Change param
        self.controller._update_param("health", "hp", 50)
        
        # Verify change
        config = sprite.mesh_entity_data["behaviours"]["health"]
        self.assertEqual(config["hp"], 50)
        
        # Undo
        self.controller.undo_last()
        # Should revert to 100 (default)
        self.assertEqual(config["hp"], 100)
        
        # Redo
        self.controller.redo_last()
        self.assertEqual(config["hp"], 50)

    def test_undo_add_entity(self):
        # Mock create
        self.window.scene_controller.all_sprites = []
        
        # Let's manually update all_sprites in the mock side effect
        def create_side_effect(data):
            s = MockSprite(data["name"])
            self.window.scene_controller.all_sprites.append(s)
            return s
        self.window.scene_controller._create_sprite.side_effect = create_side_effect
        
        # Add
        self.controller.palette_active = True
        self.controller.palette_index = 0
        self.window.screen_to_world.return_value = (200, 200)
        
        self.controller.place_entity_at_mouse(200, 200)
        self.assertEqual(len(self.window.scene_controller.all_sprites), 1)
        
        # Undo (should delete)
        # _delete_entity_internal removes from layers but doesn't explicitly remove from all_sprites list in this mock setup
        # But it calls layer.remove.
        # Let's check if layer is empty.
        # But I didn't add to layer in my mock side effect?
        # _create_entity_internal calls add_sprite_to_layer.
        
        self.controller.undo_last()
        # We can verify that _delete_entity_internal was called, or check undo stack
        self.assertEqual(len(self.controller.undo_stack), 0)
        self.assertEqual(len(self.controller.redo_stack), 1)
        
        # Redo
        self.controller.redo_last()
        self.assertEqual(len(self.controller.undo_stack), 1)

    def test_undo_delete_entity(self):
        sprite = MockSprite("Entity_1")
        self.window.scene_controller.all_sprites = [sprite]
        self.controller.selected_entity = sprite
        
        self.controller.delete_selected()
        
        self.assertIsNone(self.controller.selected_entity)
        self.assertEqual(len(self.controller.undo_stack), 1)
        
        # Undo
        # Need to mock _create_sprite to return the sprite again
        self.window.scene_controller._create_sprite.return_value = sprite
        
        self.controller.undo_last()
        # Should have called create
        self.window.scene_controller._create_sprite.assert_called()

if __name__ == '__main__':
    unittest.main()
