import unittest
from unittest.mock import MagicMock, patch

from engine.tooling import build_demo_command
from tests.utils.args_factory import make_build_demo_args


class TestBuildDemoCommand(unittest.TestCase):
    @patch("engine.content_lock.compute_content_fingerprint")
    @patch("engine.content_lock.build_lock")
    @patch("engine.content_audit.audit_world")
    @patch("engine.config.load_config")
    @patch("engine.content_lock.write_lock")
    @patch("engine.tooling.check.run_check")
    @patch("engine.tooling.polish.main")
    @patch("shutil.copytree")
    @patch("shutil.copy")
    @patch("shutil.rmtree")
    @patch("pathlib.Path.mkdir")
    @patch("engine.tooling.build_demo_command.json_io.write_json_atomic")
    def test_build_flow(
        self,
        mock_write_json,
        mock_mkdir,
        mock_rmtree,
        mock_copy,
        mock_copytree,
        mock_polish,
        mock_check,
        mock_write_lock,
        mock_load_config,
        mock_audit_world,
        mock_build_lock,
        mock_compute_content_fingerprint,
    ):
        # Setup mocks
        mock_check.return_value = True
        mock_polish.return_value = 0
        mock_load_config.return_value = MagicMock(
            audit_policy={
                "ignore": [],
                "allow_packs": [],
                "max_unused_assets": 0,
                "max_unused_prefabs": 0,
                "max_unused_items": 0,
                "max_unused_quests": 0,
            }
        )
        mock_audit_world.return_value = {
            "stats": {
                "unused_assets_count": 0,
                "unused_prefabs_count": 0,
                "unused_items_count": 0,
                "unused_quests_count": 0,
            }
        }
        mock_build_lock.return_value = {
            "packs": [
                {"id": "core", "version": "1.0.0", "type": "content"},
            ]
        }
        mock_compute_content_fingerprint.return_value = "abc123def4567890"

        # Run
        args = make_build_demo_args(
            strict_audit=False,
            diff_from=None
        )
        ret = build_demo_command.handle_build_demo(args)

        # Verify
        self.assertEqual(ret, 0)
        mock_check.assert_called_once()
        mock_polish.assert_called_once()
        mock_copytree.assert_called() # Should copy assets, scenes, etc.

        # Verify manifest write
        mock_write_json.assert_called()

if __name__ == "__main__":
    unittest.main()
