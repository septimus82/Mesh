
import pytest
from unittest.mock import MagicMock, patch
import arcade
from engine.game import GameWindow
from engine.events import MeshEvent
from engine.config import EngineConfig


pytestmark = pytest.mark.builtin_behaviours

class MockEntity(arcade.Sprite):
    def __init__(self, tag="player"):
        super().__init__()
        self.mesh_tag = tag
        self.mesh_name = "MockEntity"

@pytest.fixture
def game_window():
    def mock_init(self, width, height, *args, **kwargs):
        self._width = width
        self._height = height
        # self.ctx = MagicMock() # Removed

    # Patch arcade.Window.__init__ to avoid opening a real window
    # Patch get_size to avoid using self.scale which we can't set easily
    with patch("arcade.Window.__init__", side_effect=mock_init, autospec=True), \
         patch("arcade.Window.get_size", lambda self: (self._width, self._height)):
        with patch("arcade.set_background_color"):
            with patch("arcade.Text"): # Patch Text to avoid context issues
                # Patch other things that might be called in __init__
                with patch("engine.game.SceneLoader"), \
                     patch("engine.game.AssetManager"), \
                     patch("engine.game.AnimationFactory"), \
                     patch("engine.game.TilemapManager"), \
                     patch("engine.game.AudioManager"), \
                     patch("engine.game.ConsoleController"), \
                     patch("engine.game.CameraController"), \
                     patch("engine.game.SceneController"), \
                     patch("engine.game.InputController"), \
                     patch("engine.game.UIController"), \
                     patch("engine.game.GameStateController"), \
                     patch("engine.game.SaveManager"), \
                     patch("engine.game.QuestManager"), \
                     patch("engine.game.PlayerHUD"), \
                     patch("engine.game.GameOverScreen"), \
                     patch("engine.game.PauseMenu"):
                    
                    cfg = EngineConfig()
                    window = GameWindow(cfg.width, cfg.height, cfg.title)
                    
                    # Configure UIController mock to not consume input by default
                    window.ui_controller.on_key_press.return_value = False
                    
                    # Manually set attributes that might be missing or mocked
                    # window.width/height are properties that read _width/_height which we set in mock_init
                    
                    # We need the real event bus for the test
                    from engine.events import MeshEventBus
                    window.event_bus = MeshEventBus()
                    window.event_bus.subscribe("died", window._on_entity_died)
                    
                    # Mock UI elements
                    window.game_over_screen = MagicMock()
                    window.game_over_screen.on_key_press.return_value = False
                    
                    window.pause_menu = MagicMock()
                    # Important: Mock must return False for on_key_press by default so it doesn't consume input
                    window.pause_menu.on_key_press.return_value = False
                    
                    window.player_hud = MagicMock()
                    window.player_hud.on_key_press.return_value = False
                    
                    # Reset flags
                    window.game_over = False
                    window.paused = False
                    
                    return window

def test_game_over_state(game_window):
    # Simulate player death
    player = MockEntity("player")
    event = MeshEvent("died", {"actor": player, "name": "Player"})
    
    # Call the handler directly
    game_window._on_entity_died(event)
    
    assert game_window.game_over is True
    assert game_window.paused is True
    assert game_window.game_over_screen.visible is True

def test_pause_toggle(game_window):
    # Initial state
    assert game_window.paused is False
    game_window.pause_menu.visible = False

    # Press ESC
    game_window.on_key_press(arcade.key.ESCAPE, 0)

    assert game_window.paused is True
    assert game_window.settings_overlay.visible is True
    assert game_window.pause_menu.toggle.call_count == 0

    # Press ESC again
    game_window.on_key_press(arcade.key.ESCAPE, 0)
    
    assert game_window.paused is False
    assert game_window.settings_overlay.visible is False
