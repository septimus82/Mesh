import unittest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from engine.tooling import content_commands
from tests.utils.args_factory import make_audit_args

class TestAuditBaselineAuto(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("tests/temp_audit_auto")
        self.test_dir.mkdir(exist_ok=True)
        self.lock_path = self.test_dir / "content.lock.json"
        
    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    @patch("engine.tooling.content_commands.read_lock")
    @patch("engine.tooling.content_commands.audit_world")
    @patch("engine.tooling.content_commands.load_config")
    def test_auto_baseline_found(self, mock_config, mock_audit, mock_read_lock):
        # Setup
        mock_config.return_value = MagicMock(audit_policy={})
        mock_audit.return_value = {"stats": {"unused_assets_count": 10}}
        mock_read_lock.return_value = {"audit_snapshot": {"unused_assets_count": 5}}
        
        # Mock existence of content.lock.json
        with patch("pathlib.Path.exists") as mock_exists:
            # We need to handle multiple calls to exists.
            # First call is checking if baseline "auto" (content.lock.json) exists.
            # Subsequent calls might be for other things.
            # Let's just mock it to return True for content.lock.json
            
            def side_effect(self):
                if self.name == "content.lock.json":
                    return True
                return True # Default to True for others to avoid breaking things
                
            # Actually, content_commands checks Path("content.lock.json").exists()
            # We can patch Path("content.lock.json").exists specifically if we could, but we can't easily.
            # Instead, let's just rely on the fact that we are patching Path.exists globally for this test context?
            # No, that's dangerous.
            
            # Let's just create the file in the current directory?
            # But the code looks for "content.lock.json" in CWD.
            # We can change CWD or just create the file.
            pass

        # Let's actually create the file
        with open("content.lock.json", "w") as f:
            f.write("{}")
            
        try:
            args = make_audit_args(
                world_path="worlds/main.json",
                baseline="auto",
                json=True,
                output=None,
                ignore=None,
                allow_packs=None,
                fail_on_unused=False,
                max_unused_assets=None,
                max_unused_prefabs=None,
                max_unused_items=None
            )
            args.max_unused_quests = None
            args.max_unused_textures = None
            args.max_unused_audio = None
            args.max_unused_data = None
            args.max_unused_delta = None

            # Capture print output or check calls
            # We want to verify that read_lock was called with content.lock.json
            
            content_commands.audit_content_command(args)
            
            mock_read_lock.assert_called()
            call_arg = mock_read_lock.call_args[0][0]
            self.assertEqual(str(call_arg), "content.lock.json")
            
        finally:
            if Path("content.lock.json").exists():
                Path("content.lock.json").unlink()

    @patch("engine.tooling.content_commands.read_lock")
    @patch("engine.tooling.content_commands.audit_world")
    @patch("engine.tooling.content_commands.load_config")
    def test_auto_baseline_missing(self, mock_config, mock_audit, mock_read_lock):
        mock_config.return_value = MagicMock(audit_policy={})
        mock_audit.return_value = {"stats": {"unused_assets_count": 10}}
        
        # Ensure file does not exist
        if Path("content.lock.json").exists():
            Path("content.lock.json").unlink()
            
        args = make_audit_args(
            world_path="worlds/main.json",
            baseline="auto",
            json=True,
            output=None,
            ignore=None,
            allow_packs=None,
            fail_on_unused=False,
            max_unused_assets=None,
            max_unused_prefabs=None,
            max_unused_items=None,
            max_unused_quests=None,
            max_unused_textures=None,
            max_unused_audio=None,
            max_unused_data=None,
            max_unused_delta=None
        )

        content_commands.audit_content_command(args)
        
        # Should NOT call read_lock
        mock_read_lock.assert_not_called()

if __name__ == '__main__':
    unittest.main()
