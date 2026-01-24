"""Test that dev_sandbox pack is excluded from release profiles."""

import unittest
import argparse
from unittest.mock import MagicMock, patch
from pathlib import Path

from engine.tooling.release_command import PROFILES, release_check_command
from engine.content_packs import Pack

class TestDevSandboxExclusion(unittest.TestCase):
    def test_profiles_config(self):
        """Verify profile configurations for WIP packs."""
        self.assertTrue(PROFILES["dev"]["allow_wip_packs"])
        self.assertTrue(PROFILES["demo"]["allow_wip_packs"])
        self.assertFalse(PROFILES["release"]["allow_wip_packs"])
        self.assertFalse(PROFILES["demo_v0_3"]["allow_wip_packs"])

    @patch("engine.tooling.release_command.load_config")
    @patch("engine.tooling.release_command.get_content_index")
    @patch("engine.tooling.release_command.audit_world")
    @patch("engine.tooling.release_command.ReferenceValidator")
    @patch("engine.tooling.release_command.build_lock")
    @patch("engine.tooling.release_command.read_lock")
    @patch("engine.tooling.release_command.diff_locks")
    def test_release_check_excludes_wip(self, mock_diff, mock_read, mock_build, mock_validator, mock_audit, mock_index, mock_config):
        """Test that release check does not auto-allow WIP packs when profile forbids it."""
        
        # Setup mocks
        mock_config.return_value.audit_policy = {}
        mock_config.return_value.plan_test_policy = {}
        
        mock_validator_instance = MagicMock()
        mock_validator_instance.validate.return_value = True
        mock_validator.return_value = mock_validator_instance
        
        mock_audit.return_value = {
            "stats": {
                "unused_assets_count": 0,
                "unused_prefabs_count": 0,
                "unused_items_count": 0,
                "unused_quests_count": 0,
                "total_assets": 100
            }
        }
        
        # Mock packs
        dev_pack = Pack(id="dev_sandbox", root=Path("packs/dev_sandbox"), wip=True)
        core_pack = Pack(id="core", root=Path("packs/core"), wip=False)
        
        mock_index.return_value.packs = [dev_pack, core_pack]
        
        # Mock args
        args = argparse.Namespace()
        args.profile = "demo_v0_3"
        args.world_path = "worlds/main.json"
        args.ignore = None
        args.allow_packs = None
        args.baseline = None
        # Add other args that might be accessed
        args.max_unused_assets = None
        args.max_unused_prefabs = None
        args.max_unused_items = None
        args.max_unused_quests = None
        args.max_unused_delta = None
        args.require_golden_replays = None
        args.emit_changelog = None
        args.diff_from = None
        
        # Run command (we expect it to run without error, but we check calls)
        # We need to catch SystemExit because release_check_command calls exit(0) or exit(1)
        # But wait, release_check_command doesn't return, it prints and exits or finishes.
        # It calls exit(1) on failure.
        
        # We need to mock print to avoid clutter
        with patch("builtins.print"):
             try:
                 release_check_command(args)
             except SystemExit:
                 pass
        
        # Check that audit_world was called with allow_packs NOT containing dev_sandbox
        # audit_world(args.world_path, ignore_patterns=..., allow_packs=...)
        call_args = mock_audit.call_args
        self.assertIsNotNone(call_args)
        _, kwargs = call_args
        allow_packs = kwargs.get("allow_packs", [])
        
        self.assertNotIn("dev_sandbox", allow_packs)
        
        # Now test with dev profile
        args.profile = "dev"
        with patch("builtins.print"):
             try:
                 release_check_command(args)
             except SystemExit:
                 pass
                 
        call_args = mock_audit.call_args
        _, kwargs = call_args
        allow_packs = kwargs.get("allow_packs", [])
        self.assertIn("dev_sandbox", allow_packs)

if __name__ == "__main__":
    unittest.main()
