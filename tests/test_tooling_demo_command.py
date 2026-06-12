import argparse
import unittest
from unittest.mock import MagicMock, patch

import mesh_cli


class TestToolingDemoCommand(unittest.TestCase):
    @patch("engine.tooling.demo_runner.GameWindow")
    @patch("engine.tooling.demo_runner.load_config")
    def test_demo_command(self, mock_load_config, mock_window):
        # Mock config
        mock_config = MagicMock()
        mock_config.start_scene = "default.json"
        mock_load_config.return_value = mock_config

        # Mock args
        args = argparse.Namespace(
            command="demo",
            world=None,
            overlay=True
        )

        # Run handler
        ret = mesh_cli._handle_demo(args)
        self.assertEqual(ret, 0)

        # Verify config update
        self.assertTrue(mock_config.debug_mode)

        # Verify window creation and run
        mock_window.assert_called()
        mock_window.return_value.run.assert_called()

if __name__ == "__main__":
    unittest.main()
