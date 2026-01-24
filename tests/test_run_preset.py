import unittest
from unittest.mock import patch, MagicMock
from engine.tooling import preset_commands
from tests.utils.args_factory import make_run_preset_args

class TestRunPreset(unittest.TestCase):
    @patch("engine.tooling.preset_commands.load_config")
    @patch("engine.tooling.release_command.release_check_command")
    def test_run_preset(self, mock_release, mock_config):
        mock_config.return_value = MagicMock(
            presets={
                "ci_check": {
                    "description": "CI check preset",
                    "action": "release-check",
                    "args": {
                        "world_path": "worlds/main.json",
                        "profile": "release"
                    }
                }
            },
            world_file="worlds/main.json"
        )
        
        args = make_run_preset_args(name="ci_check")
        
        preset_commands.run_preset_command(args)
        
        mock_release.assert_called()
        call_args = mock_release.call_args[0][0]
        self.assertEqual(call_args.world_path, "worlds/main.json")
        self.assertEqual(call_args.profile, "release")

if __name__ == '__main__':
    unittest.main()
