import argparse
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.tooling import dist_command


class TestDistCommand(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("tests/temp_dist")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir()

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    @patch("engine.tooling.check.run_check")
    @patch("engine.tooling.release_command.release_check_command")
    @patch("engine.tooling.build_demo_command.handle_build_demo")
    @patch("engine.tooling.cli_snapshot_command.cli_snapshot_command")
    @patch("engine.tooling.plan_schema_command.plan_schema_command")
    def test_dist_success(self, mock_schema, mock_cli, mock_build, mock_release, mock_check):
        mock_check.return_value = True
        mock_build.return_value = 0
        mock_cli.return_value = None
        mock_schema.return_value = None

        # Mock release command to not exit
        mock_release.return_value = None

        # Create dummy content.lock.json
        Path("content.lock.json").write_text("{}")

        # Create dummy demo content
        (Path("dist/demo_content")).mkdir(parents=True, exist_ok=True)
        (Path("dist/demo_content/build_manifest.json")).write_text("{}")

        args = argparse.Namespace(
            profile="dev",
            world="worlds/main.json",
            out=str(self.test_dir)
        )

        ret = dist_command.handle_dist(args)

        self.assertEqual(ret, 0)
        self.assertTrue((self.test_dir / "dist_manifest.json").exists())
        self.assertTrue((self.test_dir / "demo_content").exists())

        # Cleanup
        if Path("content.lock.json").exists():
            Path("content.lock.json").unlink()
        if Path("dist/demo_content").exists():
            shutil.rmtree("dist/demo_content")

    @patch("engine.tooling.check.run_check")
    def test_dist_fail_check(self, mock_check):
        mock_check.return_value = False

        args = argparse.Namespace(
            profile="dev",
            world="worlds/main.json",
            out=str(self.test_dir)
        )

        ret = dist_command.handle_dist(args)
        self.assertEqual(ret, 1)
