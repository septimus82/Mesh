import unittest
from unittest.mock import patch, MagicMock
from engine.tooling import release_command
from tests.utils.args_factory import make_release_args

class TestReleaseCheckProfiles(unittest.TestCase):
    
    @patch("engine.tooling.release_command.get_content_index")
    @patch("engine.tooling.release_command.audit_world")
    @patch("engine.tooling.release_command.build_lock")
    @patch("engine.tooling.release_command.read_lock")
    @patch("engine.tooling.release_command.load_config")
    @patch("engine.tooling.release_command.ReferenceValidator")
    def test_profile_defaults(self, mock_validator, mock_config, mock_read, mock_build, mock_audit, mock_get_index):
        # Setup
        mock_config.return_value = MagicMock(audit_policy={}, plan_test_policy={})
        mock_validator.return_value.validate.return_value = True
        mock_audit.return_value = {
            "stats": {
                "unused_assets_count": 50,
                "unused_prefabs_count": 0,
                "unused_items_count": 0,
                "unused_quests_count": 0
            }
        }
        
        # Mock packs
        mock_pack = MagicMock()
        mock_pack.id = "wip_pack"
        mock_pack.wip = True
        mock_get_index.return_value.packs = [mock_pack]
        
        # Mock args
        args = make_release_args(
            world_path="worlds/main.json",
            profile="dev",
            max_unused_assets=None,
            max_unused_prefabs=None,
            max_unused_items=None,
            max_unused_quests=None,
            max_unused_delta=None,
            ignore=None,
            allow_packs=None,
            baseline=None,
            diff_from=None,
            emit_changelog=None
        )
        
        # Run command - should pass because 50 < 100
        try:
            release_command.release_check_command(args)
        except SystemExit as e:
            self.fail(f"Command failed with {e}")
            
        # Verify audit_world called with wip_pack in allow_packs
        call_args = mock_audit.call_args
        allow_packs = call_args[1].get("allow_packs") or call_args[0][2] if len(call_args[0]) > 2 else []
        # audit_world(world_path, ignore_patterns=..., allow_packs=...)
        # It's passed as kwarg in code: allow_packs=allow_packs
        allow_packs = call_args.kwargs.get("allow_packs")
        self.assertIn("wip_pack", allow_packs)

        # Now try with release profile (limit 0)
        args.profile = "release"
        with self.assertRaises(SystemExit):
            release_command.release_check_command(args)

if __name__ == '__main__':
    unittest.main()
