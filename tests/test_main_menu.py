from unittest.mock import MagicMock

import arcade

from engine.behaviours.main_menu import MainMenuBehaviour, MainMenuUI
from engine.config import EngineConfig


class MockWindow:
    def __init__(self):
        cfg = EngineConfig()
        self.width = cfg.width
        self.height = cfg.height
        self.engine_config = cfg
        self.engine_config.start_scene = "scenes/game.json"
        self.game_state_controller = MagicMock()
        self.save_manager = MagicMock()
        self.ui_controller = MagicMock()
        self.ui_controller.ui_elements = []
        self.request_scene_change = MagicMock()
        self.close = MagicMock()
        self.register_ui_element = MagicMock()

def test_main_menu_navigation():
    window = MockWindow()
    sprite = MagicMock()
    behaviour = MainMenuBehaviour(sprite, window)

    # Initial state
    assert behaviour.selected_index == 0
    assert behaviour.options[0] == "New Game"

    # Navigate down
    behaviour.handle_input(arcade.key.DOWN)
    assert behaviour.selected_index == 1
    assert behaviour.options[1] == "Load Game"

    # Navigate down again
    behaviour.handle_input(arcade.key.DOWN)
    assert behaviour.selected_index == 2
    assert behaviour.options[2] == "Settings"

    # Navigate down again
    behaviour.handle_input(arcade.key.DOWN)
    assert behaviour.selected_index == 3
    assert behaviour.options[3] == "Credits"

    # Navigate down again
    behaviour.handle_input(arcade.key.DOWN)
    assert behaviour.selected_index == 4
    assert behaviour.options[4] == "Quit"

    # Wrap around
    behaviour.handle_input(arcade.key.DOWN)
    assert behaviour.selected_index == 0

    # Navigate up (wrap around)
    behaviour.handle_input(arcade.key.UP)
    assert behaviour.selected_index == 4

def test_main_menu_new_game():
    window = MockWindow()
    sprite = MagicMock()
    behaviour = MainMenuBehaviour(sprite, window)

    # Select "New Game" (index 0)
    behaviour.selected_index = 0
    behaviour.handle_input(arcade.key.ENTER)

    # Verify state reset and scene change
    window.game_state_controller.replace_state.assert_called_once_with({})
    window.request_scene_change.assert_called_once_with("scenes/game.json")

def test_main_menu_quit():
    window = MockWindow()
    sprite = MagicMock()
    behaviour = MainMenuBehaviour(sprite, window)

    # Select "Quit" (index 4)
    behaviour.selected_index = 4
    behaviour.handle_input(arcade.key.ENTER)

    window.close.assert_called_once()

def test_main_menu_load_game_flow():
    window = MockWindow()
    sprite = MagicMock()
    behaviour = MainMenuBehaviour(sprite, window)

    # Mock saves
    window.save_manager.list_saves.return_value = ["save1", "save2"]

    # Select "Load Game" (index 1)
    behaviour.selected_index = 1
    behaviour.handle_input(arcade.key.ENTER)

    # Verify state transition
    assert behaviour.state == "load_game"
    assert behaviour.save_slots == ["save1", "save2"]
    assert behaviour.selected_save_index == 0

    # Navigate saves
    behaviour.handle_input(arcade.key.DOWN)
    assert behaviour.selected_save_index == 1

    # Select save
    behaviour.handle_input(arcade.key.ENTER)
    window.save_manager.load_game.assert_called_once_with("save2")

    # Test cancel
    behaviour.handle_input(arcade.key.ESCAPE)
    assert behaviour.state == "main"

def test_main_menu_ui_key_press():
    window = MockWindow()
    sprite = MagicMock()
    behaviour = MainMenuBehaviour(sprite, window)
    ui = MainMenuUI(window, behaviour)

    # Mock behaviour handle_input
    behaviour.handle_input = MagicMock()

    # Simulate key press on UI
    ui.on_key_press(arcade.key.DOWN, 0)

    # Verify behaviour received input
    behaviour.handle_input.assert_called_once_with(arcade.key.DOWN)
