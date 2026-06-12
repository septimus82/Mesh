import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from engine.tooling import release_command
from tests.utils.args_factory import make_release_args


class TestReleaseCheckPlanPolicy(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.test_dir.name)

        # Mock config
        self.config_patcher = patch('engine.tooling.release_command.load_config')
        self.mock_load_config = self.config_patcher.start()
        self.mock_config = MagicMock()
        self.mock_config.audit_policy = {}
        self.mock_config.plan_test_policy = {
            "require_tests_for_applied_plans": True,
            "min_coverage": 0.5
        }
        self.mock_load_config.return_value = self.mock_config

        # Mock paths
        self.paths_patcher = patch('engine.tooling.release_command.resolve_path')
        self.mock_resolve_path = self.paths_patcher.start()
        self.lock_path = self.root / "content.lock.json"
        self.mock_resolve_path.return_value = self.lock_path

        # Create dummy lock file
        self.lock_path.write_text("{}")
        # Set mtime to 1000
        os.utime(self.lock_path, (1000, 1000))

        # Mock plan history
        self.history_patcher = patch('engine.tooling.plan_history.list_history')
        self.mock_list_history = self.history_patcher.start()

        self.get_history_patcher = patch('engine.tooling.plan_history.get_history')
        self.mock_get_history = self.get_history_patcher.start()

    def tearDown(self):
        self.config_patcher.stop()
        self.paths_patcher.stop()
        self.history_patcher.stop()
        self.get_history_patcher.stop()
        self.test_dir.cleanup()

    def test_policy_pass(self):
        # Plan applied after lock (ts=2000) with good coverage
        self.mock_list_history.return_value = [{"id": "plan1", "timestamp": 2000}]
        self.mock_get_history.return_value = {
            "result": {
                "tests": {
                    "passed": True,
                    "coverage": {"actions_total": 10, "actions_covered": 8}
                }
            }
        }

        # We need to mock build_lock/read_lock/diff_locks to pass step 1
        with patch('engine.tooling.release_command.build_lock') as bl, \
             patch('engine.tooling.release_command.read_lock') as rl, \
             patch('engine.tooling.release_command.diff_locks') as dl, \
             patch('engine.tooling.release_command.ReferenceValidator') as rv, \
             patch('engine.tooling.release_command.audit_world') as aw:

            dl.return_value = {
                "packs": {"added": [], "removed": [], "version_changed": [], "order_changed": []},
                "overrides": {"total_delta": 0},
                "content_files": {"changed": [], "added": [], "removed": []}
            }
            rv_instance = rv.return_value
            rv_instance.validate.return_value = True
            aw.return_value = {
                "unused_assets": [],
                "stats": {
                    "unused_prefabs_count": 0,
                    "unused_items_count": 0,
                    "unused_quests_count": 0,
                    "unused_assets_count": 0
                }
            } # minimal audit result

            # Run command
            args = make_release_args(
                profile="release-ready",
                world_path="world.json",
                ignore=None,
                allow_packs=None,
                baseline=None,
                emit_changelog=False,
                diff_from=None
            )

            # Should not exit
            try:
                release_command.release_check_command(args)
            except SystemExit:
                self.fail("release_check_command raised SystemExit unexpectedly!")

    def test_policy_fail_coverage(self):
        # Plan applied after lock (ts=2000) with bad coverage
        self.mock_list_history.return_value = [{"id": "plan1", "timestamp": 2000}]
        self.mock_get_history.return_value = {
            "result": {
                "tests": {
                    "passed": True,
                    "coverage": {"actions_total": 10, "actions_covered": 2} # 0.2 < 0.5
                }
            }
        }

        with patch('engine.tooling.release_command.build_lock'), \
             patch('engine.tooling.release_command.read_lock'), \
             patch('engine.tooling.release_command.diff_locks') as dl:

            dl.return_value = {
                "packs": {"added": [], "removed": [], "version_changed": [], "order_changed": []},
                "overrides": {"total_delta": 0},
                "content_files": {"changed": [], "added": [], "removed": []}
            }

            args = make_release_args(
                profile="release-ready",
                baseline=None
            )

            with self.assertRaises(SystemExit) as cm:
                release_command.release_check_command(args)
            self.assertEqual(cm.exception.code, 1)
