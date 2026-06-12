import argparse
from unittest.mock import MagicMock, patch

from mesh_cli import _handle_demo


def test_demo_command_launches_game():
    with patch("engine.tooling.demo_runner.load_config") as mock_load_config, patch("engine.tooling.demo_runner.GameWindow") as mock_window:
        config = MagicMock()
        config.width = 800
        config.height = 600
        config.title = "Demo"
        config.fullscreen = False
        config.vsync = True
        config.start_scene = "scenes/demo.json"
        mock_load_config.return_value = config

        instance = mock_window.return_value

        args = argparse.Namespace()
        result = _handle_demo(args)

        assert result == 0
        assert config.debug_mode is True
        mock_window.assert_called_once()
        instance.load_scene.assert_called_once_with(config.start_scene)
        instance.run.assert_called_once()

def test_demo_command_handles_error():
    with patch("engine.tooling.demo_runner.load_config") as mock_load_config, patch("engine.tooling.demo_runner.GameWindow") as mock_window:
        config = MagicMock()
        config.width = 800
        config.height = 600
        config.title = "Demo"
        config.fullscreen = False
        config.vsync = True
        config.start_scene = "scenes/demo.json"
        mock_load_config.return_value = config

        instance = mock_window.return_value
        instance.run.side_effect = Exception("Game crash")

        args = argparse.Namespace()

        with patch("builtins.print") as mock_print:
            result = _handle_demo(args)

        assert result == 1
        mock_print.assert_called_with("Error launching demo: Game crash")
