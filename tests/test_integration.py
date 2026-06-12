from unittest.mock import MagicMock, patch

import arcade
import pytest

from engine.config import EngineConfig
from engine.game import GameWindow
from engine.scene_controller import SceneController


@pytest.fixture
def mock_window():
    # Rebase GameWindow to avoid calling real arcade.Window.__init__
    import engine.game
    original_bases = engine.game.GameWindow.__bases__

    class DummyWindow:
        def __init__(self, *args, **kwargs):
            self.width = 800
            self.height = 600
            self._ctx = MagicMock()

    engine.game.GameWindow.__bases__ = (DummyWindow,)

    # Patch arcade components accessed via optional_arcade for good measure?
    # No need if GameWindow.__init__ is effectively mocked by inheritance change (super() calls mock).
    # But GameWindow code inside __init__ might access engine.optional_arcade.arcade functions.

    import engine.optional_arcade
    with patch('engine.optional_arcade.arcade'): # Mock the whole arcade module
        with patch('engine.camera_controller.ArcadeCamera'):
            cfg = EngineConfig()
            window = GameWindow(cfg.width, cfg.height, cfg.title)
            # Mock internal components that might need it
            window.assets = MagicMock()
            window.audio = MagicMock()
            yield window

    # Cleanup
    engine.game.GameWindow.__bases__ = original_bases

def test_scene_controller_initialization(mock_window):
    assert isinstance(mock_window.scene_controller, SceneController)
    assert mock_window.scene_controller.window == mock_window

def test_load_scene_delegation(mock_window):
    # Mock scene_loader to return a dummy scene
    mock_window.scene_loader.load_scene = MagicMock(return_value={
        "entities": [
            {"sprite": "assets/test.png", "x": 100, "y": 100, "name": "test_entity"}
        ],
        "layers": [{"name": "entities"}]
    })

    # Mock assets.get_texture to return a dummy texture
    import engine.optional_arcade
    if engine.optional_arcade.arcade:
        try:
            import arcade
            class DummyTexture(arcade.Texture):
                def __init__(self):
                    self.name = "test"
                    self._image = MagicMock()
                    self._hit_box_points = [(0,0), (10,0), (10,10), (0,10)]
                    self._size = (10, 10)
                    self.width = 10
                    self.height = 10
            mock_texture = DummyTexture()
        except Exception:
            mock_texture = MagicMock()
    else:
        mock_texture = MagicMock()

    mock_window.assets.get_texture.return_value = mock_texture

    # Patch arcade.Sprite.  Points to engine.optional_arcade.arcade.Sprite
    with patch('engine.optional_arcade.arcade.Sprite') as MockSprite:
        # Configure MockSprite instance
        mock_sprite_instance = MockSprite.return_value
        mock_sprite_instance.center_x = 0
        mock_sprite_instance.center_y = 0

        # Replace layers with simple lists to avoid SpriteList logic
        mock_window.scene_controller.layers = {
            "entities": [],
            "background": [],
            "foreground": []
        }

        # Call load_scene on window
        mock_window.load_scene("scenes/test_scene.json")

        # Verify scene_controller.load_scene was called (implicitly by logic)
        # Verify sprites were created
        layer = mock_window.scene_controller.layers["entities"]
        assert len(layer) == 1
        sprite = layer[0]
        # Since we mocked Sprite, we check if it's the mock instance
        # assert sprite == mock_sprite_instance
        # Check if attributes were set on the mock
        assert sprite.center_x == 100.0
        assert sprite.center_y == 100.0
        assert getattr(sprite, "mesh_name") == "test_entity"

def test_reload_scene_delegation(mock_window):
    mock_window.scene_controller.reload_scene = MagicMock(return_value=True)
    mock_window.reload_scene()
    mock_window.scene_controller.reload_scene.assert_called_once()

def test_find_entity_delegation(mock_window):
    mock_window.scene_controller.find_entity = MagicMock(return_value="found_sprite")
    result = mock_window.find_entity("test")
    assert result == "found_sprite"
    mock_window.scene_controller.find_entity.assert_called_with("test")

def test_input_delegation(mock_window):
    mock_window.input_controller.on_key_press = MagicMock()
    main_menu = getattr(mock_window, "main_menu_overlay", None)
    if main_menu is not None:
        main_menu.visible = False
    mock_window.paused = False
    mock_window.on_key_press(arcade.key.A, 0)
    mock_window.input_controller.on_key_press.assert_called_with(arcade.key.A, 0)

    mock_window.input_controller.on_mouse_motion = MagicMock()
    mock_window.on_mouse_motion(10, 20, 0, 0)
    mock_window.input_controller.on_mouse_motion.assert_called_with(10, 20, 0, 0)
