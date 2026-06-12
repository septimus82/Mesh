from unittest.mock import MagicMock, patch

import arcade

from engine.config import EngineConfig
from engine.editor_controller import EditorModeController


class MockWindow:
    def __init__(self):
        cfg = EngineConfig()
        self.width = cfg.width
        self.height = cfg.height
        self.paused = False
        self.scene_controller = MagicMock()
        self.screen_to_world = MagicMock(return_value=(100, 100))

def test_editor_toggle():
    window = MockWindow()
    controller = EditorModeController(window)

    assert not controller.active
    assert not window.paused

    controller.toggle()
    assert controller.active
    assert window.paused

    controller.toggle()
    assert not controller.active
    assert not window.paused

def test_editor_selection():
    window = MockWindow()
    controller = EditorModeController(window)
    controller.active = True

    # Mock sprite
    sprite = MagicMock(spec=arcade.Sprite)
    sprite.collides_with_point.return_value = True
    sprite.center_x = 100
    sprite.center_y = 100
    sprite.mesh_name = "TestEntity"

    window.scene_controller.all_sprites = [sprite]

    # Click at 100, 100
    controller.handle_mouse_click(100, 100, arcade.MOUSE_BUTTON_LEFT, 0)

    assert controller.selected_entity == sprite

def test_editor_nudge():
    window = MockWindow()
    controller = EditorModeController(window)
    controller.active = True

    sprite = MagicMock(spec=arcade.Sprite)
    sprite.center_x = 100
    sprite.center_y = 100
    controller.selected_entity = sprite

    controller.nudge_selected(10, 0)

    window.scene_controller._apply_entity_mutation.assert_called_with(
        sprite, x=110, y=100
    )

def test_editor_save():
    window = MockWindow()
    controller = EditorModeController(window)
    controller.active = True
    window.scene_controller.current_scene_path = "test_scene.json"
    window.scene_controller.build_scene_snapshot.return_value = {"entities": []}

    with patch("engine.editor_runtime.ops.json_io.write_json_atomic") as mock_write:
        controller.save_current_scene()
        mock_write.assert_called_with("test_scene.json", {"entities": []})
