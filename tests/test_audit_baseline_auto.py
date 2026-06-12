import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from engine.tooling import content_commands
from tests.utils.args_factory import make_audit_args


class TestAuditBaselineAuto(unittest.TestCase):
    def setUp(self):
        temp_root = Path("artifacts/test_tmp")
        temp_root.mkdir(parents=True, exist_ok=True)
        self._temp_dir = tempfile.TemporaryDirectory(dir=temp_root)
        self._old_cwd = Path.cwd()
        os.chdir(self._temp_dir.name)
        self.lock_path = Path("content.lock.json")

    def tearDown(self):
        os.chdir(self._old_cwd)
        self._temp_dir.cleanup()

    @patch("engine.tooling.content_commands.read_lock")
    @patch("engine.tooling.content_commands.audit_world")
    @patch("engine.tooling.content_commands.load_config")
    def test_auto_baseline_found(self, mock_config, mock_audit, mock_read_lock):
        # Setup
        mock_config.return_value = MagicMock(audit_policy={})
        mock_audit.return_value = {"stats": {"unused_assets_count": 10}}
        mock_read_lock.return_value = {"audit_snapshot": {"unused_assets_count": 5}}
        self.lock_path.write_text("{}", encoding="utf-8")

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
            self.assertEqual(call_arg, self.lock_path)

        finally:
            if self.lock_path.exists():
                self.lock_path.unlink()

    @patch("engine.tooling.content_commands.read_lock")
    @patch("engine.tooling.content_commands.audit_world")
    @patch("engine.tooling.content_commands.load_config")
    def test_auto_baseline_missing(self, mock_config, mock_audit, mock_read_lock):
        mock_config.return_value = MagicMock(audit_policy={})
        mock_audit.return_value = {"stats": {"unused_assets_count": 10}}

        # Ensure file does not exist
        if self.lock_path.exists():
            self.lock_path.unlink()

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
