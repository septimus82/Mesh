import unittest
from unittest.mock import MagicMock
import arcade
from engine.editor_controller import EditorModeController

class MockSprite(MagicMock):
    def __init__(self, name="Entity", layer="entities", behaviours=None, mesh_tag=None, **kwargs):
        super().__init__(**kwargs)
        self.mesh_name = name
        self.layer = layer
        self.mesh_behaviours_runtime = behaviours or []
        self.mesh_entity_data = {"name": name, "layer": layer}
        self.mesh_tag = mesh_tag
        self.center_x = 0
        self.center_y = 0
        self.width = 10
        self.height = 10
        self.name = name

class MockBehaviour:
    def __init__(self, name):
        self.__class__.__name__ = name

class TestEditorHierarchy(unittest.TestCase):
    def setUp(self):
        self.window = MagicMock()
        self.window.scene_controller = MagicMock()
        self.window.scene_controller.all_sprites = []
        
        # Mock ensure methods needed by editor
        self.window.scene_controller._ensure_entity_data_dict = lambda s: s.mesh_entity_data
        self.window.scene_controller._ensure_behaviour_config_root = lambda d: {}
        
        self.controller = EditorModeController(self.window)
        self.controller.active = True
        
    def test_build_hierarchy(self):
        s1 = MockSprite("Player", "entities")
        s2 = MockSprite("Wall", "solid")
        self.window.scene_controller.all_sprites = [s1, s2]
        
        items = self.controller._build_hierarchy_list()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0], s1)
        self.assertEqual(items[1], s2)
        
    def test_filter_by_name(self):
        s1 = MockSprite("Player", "entities")
        s2 = MockSprite("Wall", "solid")
        self.window.scene_controller.all_sprites = [s1, s2]
        
        self.controller.hierarchy_filter = "Play"
        items = self.controller._build_hierarchy_list()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0], s1)
        
    def test_filter_by_behaviour(self):
        b1 = MockBehaviour("PatrolBehaviour")
        s1 = MockSprite("Enemy", "entities", [b1])
        s2 = MockSprite("Wall", "solid")
        self.window.scene_controller.all_sprites = [s1, s2]
        
        self.controller.hierarchy_filter = "@Patrol"
        items = self.controller._build_hierarchy_list()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0], s1)
        
    def test_selection_sync(self):
        s1 = MockSprite("Player", "entities")
        s2 = MockSprite("Wall", "solid")
        self.window.scene_controller.all_sprites = [s1, s2]
        
        # Select via hierarchy index
        self.controller.hierarchy_active = True
        # We need to ensure the list is built
        self.controller._refresh_hierarchy_list()
        
        # Simulate selecting index 1 (Wall)
        self.controller.hierarchy_selection_index = 1
        self.controller._select_hierarchy_item(1)
        
        self.assertEqual(self.controller.selected_entity, s2)

    def test_selection_index_clamped_after_filter(self):
        sprites = [MockSprite("Player"), MockSprite("Wall"), MockSprite("Crate")]
        self.window.scene_controller.all_sprites = sprites
        self.controller.hierarchy_selection_index = 2
        self.controller.hierarchy_filter = "Player"
        self.controller._refresh_hierarchy_list()

        self.assertEqual(len(self.controller._cached_hierarchy_list), 1)
        self.assertEqual(self.controller.hierarchy_selection_index, 0)

    def test_selection_index_negative_when_filter_empty(self):
        sprites = [MockSprite("Player"), MockSprite("Wall")]
        self.window.scene_controller.all_sprites = sprites
        self.controller.hierarchy_filter = "Missing"
        self.controller._refresh_hierarchy_list()

        self.assertEqual(len(self.controller._cached_hierarchy_list), 0)
        self.assertEqual(self.controller.hierarchy_selection_index, -1)

    def test_fallback_display_name_used_in_filter(self):
        unnamed = MockSprite("")
        unnamed.mesh_entity_data["name"] = ""
        unnamed.mesh_name = ""
        unnamed.name = ""
        self.window.scene_controller.all_sprites = [unnamed]

        self.controller._refresh_hierarchy_list()
        display = self.controller._get_display_name_for_sprite(unnamed)
        self.assertEqual(display, "Entity#1")

        self.controller.hierarchy_filter = "entity#1"
        filtered = self.controller._build_hierarchy_list()
        self.assertEqual(filtered, [unnamed])

    def test_display_name_uses_display_name_field(self):
        sprite = MockSprite("")
        sprite.mesh_entity_data["name"] = ""
        sprite.mesh_entity_data["display_name"] = "PrefabLabel"
        sprite.mesh_name = ""
        sprite.name = ""
        self.window.scene_controller.all_sprites = [sprite]

        self.controller._refresh_hierarchy_list()
        display = self.controller._get_display_name_for_sprite(sprite)
        self.assertEqual(display, "PrefabLabel")

    def test_filter_matches_entity_tags(self):
        sprite = MockSprite("", mesh_tag="exit")
        sprite.mesh_entity_data["name"] = ""
        sprite.mesh_entity_data["tag"] = "exit"
        sprite.mesh_name = ""
        sprite.name = ""
        self.window.scene_controller.all_sprites = [sprite]

        self.controller.hierarchy_filter = "exit"
        filtered = self.controller._build_hierarchy_list()
        self.assertEqual(filtered, [sprite])

    def test_rename_entity_updates_data_and_command_stack(self):
        sprite = MockSprite("Old", "entities")
        self.window.scene_controller.all_sprites = [sprite]
        self.controller.selected_entity = sprite
        self.controller.hierarchy_active = True
        self.controller._refresh_hierarchy_list()

        self.assertTrue(self.controller._begin_hierarchy_rename())
        self.controller.hierarchy_rename_buffer = "NewName"
        self.assertTrue(self.controller._commit_hierarchy_rename())

        self.assertEqual(sprite.mesh_name, "NewName")
        self.assertEqual(sprite.mesh_entity_data["name"], "NewName")
        self.assertEqual(self.controller.undo_stack[-1]["type"], "RenameEntity")

    def test_get_entity_tags_reads_list_entries(self):
        sprite = MockSprite("Door", "entities", mesh_tag="door")
        sprite.mesh_entity_data["tags"] = ["door", "puzzle"]
        tags = self.controller._get_entity_tags(sprite)
        self.assertEqual(tags, ["door", "puzzle"])

if __name__ == '__main__':
    unittest.main()
