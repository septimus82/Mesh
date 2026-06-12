import unittest
from unittest.mock import MagicMock, patch

import mesh_cli


class TestRunPresetArgparse(unittest.TestCase):
    def setUp(self):
        self.mock_config = MagicMock()
        self.mock_config.presets = {}

        self.patcher_config = patch("engine.tooling.preset_commands.load_config", return_value=self.mock_config)
        self.patcher_config.start()

        self.patcher_pipeline = patch("engine.tooling.pipeline_runner.run_pipeline")
        self.mock_run_pipeline = self.patcher_pipeline.start()
        self.mock_run_pipeline.return_value = 0

    def tearDown(self):
        self.patcher_config.stop()
        self.patcher_pipeline.stop()

    def test_run_preset_pipeline_flags(self):
        """Test that run-preset correctly parses flags for pipeline command."""
        # Define a preset that uses flags
        self.mock_config.presets = {
            "test_preset": {
                "description": "Test preset with flags",
                "steps": [
                    {
                        "cmd": "pipeline",
                        "args": [
                            "--plan", "plans/test_plan.json",
                            "--world", "worlds/test_world.json",
                            "--dry-run"
                        ]
                    }
                ]
            }
        }

        # Run the preset via mesh_cli.main
        # We need to mock sys.argv or pass args to main if it supports it.
        # mesh_cli.main takes argv.

        # We also need to prevent mesh_cli.main from exiting or printing too much if possible,
        # but since we are calling it with valid args, it should be fine.
        # However, preset_commands.run_preset_command calls mesh_cli.main recursively.
        # We need to make sure we are testing the parsing logic.

        # When we run `mesh run-preset test_preset`, it calls `preset_commands.run_preset_command`.
        # That function retrieves the preset and calls `mesh_cli.main(["pipeline", ...])`.

        # So we can call `mesh_cli.main(["run-preset", "test_preset"])`.

        ret = mesh_cli.main(["run-preset", "test_preset"])

        self.assertEqual(ret, 0)

        # Verify pipeline_runner.run_pipeline was called with correct args
        self.mock_run_pipeline.assert_called_once()
        call_kwargs = self.mock_run_pipeline.call_args.kwargs

        self.assertEqual(call_kwargs["plan_path"], "plans/test_plan.json")
        self.assertEqual(call_kwargs["path"], "worlds/test_world.json")
        self.assertTrue(call_kwargs["dry_run"])

    def test_run_preset_pipeline_positional(self):
        """Test that run-preset correctly parses positional args for pipeline command (legacy/current behavior)."""
        self.mock_config.presets = {
            "test_preset_pos": {
                "description": "Test preset with positional args",
                "steps": [
                    {
                        "cmd": "pipeline",
                        "args": [
                            "plans/test_plan.json",
                            "worlds/test_world.json",
                            "--dry-run"
                        ]
                    }
                ]
            }
        }

        ret = mesh_cli.main(["run-preset", "test_preset_pos"])

        self.assertEqual(ret, 0)

        self.mock_run_pipeline.assert_called_once()
        call_kwargs = self.mock_run_pipeline.call_args.kwargs

        self.assertEqual(call_kwargs["plan_path"], "plans/test_plan.json")
        self.assertEqual(call_kwargs["path"], "worlds/test_world.json")
        self.assertTrue(call_kwargs["dry_run"])
