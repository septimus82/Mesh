import unittest
from unittest.mock import MagicMock

import arcade

from engine.editor_controller import (
    TOOL_MODE_PATH,
    TOOL_MODE_ZONE,
    ZONE_TARGET_HITBOX,
    ZONE_TARGET_TRIGGER,
    EditorModeController,
)


class MockSprite(MagicMock):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.center_x = 100
        self.center_y = 100
        self.width = 32
        self.height = 32
        self.mesh_name = "TestEntity"
        self.mesh_behaviours_runtime = []
        self.mesh_entity_data = {}

class PatrolBehaviour:
    def __init__(self):
        self.points = [(100, 100), (200, 100)]
        self.config = {"points": [(100, 100), (200, 100)]}
        self.entity = MockSprite()
        self.mesh_behaviour_type = "patrol"

class TriggerZoneBehaviour:
    def __init__(self):
        self.radius = 50.0
        self.config = {"trigger_radius": 50.0}
        self.entity = MockSprite()
        self.mesh_behaviour_type = "TriggerZone"

class HitboxBehaviour:
    def __init__(self):
        self.width = 32.0
        self.height = 16.0
        self.config = {"width": 32.0, "height": 16.0}
        self.entity = MockSprite()
        self.mesh_behaviour_type = "Hitbox"

class TestEditorPatrol(unittest.TestCase):
    def setUp(self):
        self.window = MagicMock()
        self.window.width = 800
        self.window.height = 600
        self.window.scene_controller = MagicMock()
        self.window.scene_controller.all_sprites = []

        # Mock ensure methods needed by editor
        self.window.scene_controller._ensure_entity_data_dict = lambda s: s.mesh_entity_data
        self.window.scene_controller._ensure_behaviour_config_root = lambda d: {}
        # Mock config list to match runtime list (assuming 1 behaviour for simplicity in tests)
        self.window.scene_controller._get_behaviour_configs_for_sprite = lambda s: [{"type": b.mesh_behaviour_type} for b in s.mesh_behaviours_runtime]

        self.controller = EditorModeController(self.window)
        self.controller.active = True

    def test_path_tool_selection(self):
        self.controller.tool_mode = TOOL_MODE_PATH

        sprite = MockSprite()
        patrol = PatrolBehaviour()
        sprite.mesh_behaviours_runtime = [patrol]
        self.controller.selected_entity = sprite

        # Test selecting existing waypoint
        # Click near (100, 100)
        self.window.screen_to_world.return_value = (102, 102)

        result = self.controller.handle_mouse_click(102, 102, arcade.MOUSE_BUTTON_LEFT, 0)

        self.assertTrue(result)
        self.assertEqual(self.controller.selected_waypoint_index, 0)

    def test_path_tool_add_point(self):
        self.controller.tool_mode = TOOL_MODE_PATH

        sprite = MockSprite()
        patrol = PatrolBehaviour()
        patrol.entity = sprite # Link back
        sprite.mesh_behaviours_runtime = [patrol]
        self.controller.selected_entity = sprite
        self.window.scene_controller.all_sprites = [sprite] # Needed for lookup

        # Shift+Click at (300, 100)
        self.window.screen_to_world.return_value = (300, 100)

        initial_count = len(patrol.points)
        result = self.controller.handle_mouse_click(300, 100, arcade.MOUSE_BUTTON_LEFT, arcade.key.MOD_SHIFT)

        self.assertTrue(result)
        self.assertEqual(len(patrol.points), initial_count + 1)
        # Check if new point is roughly correct (snapped)
        self.assertEqual(patrol.points[-1], (304.0, 96.0)) # 300/16 = 18.75 -> 19*16 = 304

    def test_zone_tool_resize(self):
        self.controller.tool_mode = TOOL_MODE_ZONE

        sprite = MockSprite()
        zone = TriggerZoneBehaviour()
        zone.entity = sprite # Link back
        sprite.mesh_behaviours_runtime = [zone]
        self.controller.selected_entity = sprite
        self.window.scene_controller.all_sprites = [sprite] # Needed for lookup

        # Shift+Right Arrow
        initial_radius = zone.radius
        self.controller.shape.handle_zone_input(arcade.key.RIGHT, arcade.key.MOD_SHIFT)

        self.assertGreater(zone.radius, initial_radius)
        self.assertEqual(zone.radius, initial_radius + 16.0)

    def test_zone_cycle_switches_between_behaviours(self):
        self.controller.tool_mode = TOOL_MODE_ZONE

        sprite = MockSprite()
        trigger = TriggerZoneBehaviour()
        hitbox = HitboxBehaviour()
        trigger.entity = sprite
        hitbox.entity = sprite
        sprite.mesh_behaviours_runtime = [trigger, hitbox]

        self.controller.selected_entity = sprite
        self.window.scene_controller.all_sprites = [sprite]
        self.controller.shape.reset_zone_selection_state()
        self.controller.shape.sync_zone_selection_state(sprite)

        active = self.controller.shape.get_zone_behaviour(sprite)
        self.assertIs(active, trigger)
        self.assertEqual(self.controller.zone_edit_target, ZONE_TARGET_TRIGGER)

        cycled = self.controller.shape.cycle_zone_behaviour()
        self.assertTrue(cycled)
        active_after = self.controller.shape.get_zone_behaviour(sprite)
        self.assertIs(active_after, hitbox)
        self.assertEqual(self.controller.zone_edit_target, ZONE_TARGET_HITBOX)

    def test_zone_toggle_switches_between_trigger_and_hitbox(self):
        self.controller.tool_mode = TOOL_MODE_ZONE

        sprite = MockSprite()
        trigger = TriggerZoneBehaviour()
        hitbox = HitboxBehaviour()
        trigger.entity = sprite
        hitbox.entity = sprite
        sprite.mesh_behaviours_runtime = [trigger, hitbox]

        self.controller.selected_entity = sprite
        self.window.scene_controller.all_sprites = [sprite]
        self.controller.shape.reset_zone_selection_state()
        self.controller.shape.sync_zone_selection_state(sprite)

        active = self.controller.shape.get_zone_behaviour(sprite)
        self.assertIs(active, trigger)
        self.assertEqual(self.controller.zone_edit_target, ZONE_TARGET_TRIGGER)

        toggled = self.controller.shape.toggle_zone_edit_target()
        self.assertTrue(toggled)
        self.assertEqual(self.controller.zone_edit_target, ZONE_TARGET_HITBOX)
        active_after = self.controller.shape.get_zone_behaviour(sprite)
        self.assertIs(active_after, hitbox)

if __name__ == '__main__':
    unittest.main()
