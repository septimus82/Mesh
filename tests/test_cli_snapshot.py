import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from engine.tooling import cli_snapshot_command
from tests.utils.args_factory import update_namespace, get_default_args

class TestCliSnapshot(unittest.TestCase):
    def test_snapshot_generation(self):
        """Test that snapshot generation produces valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "snapshot.json"
            
            args = get_default_args(["cli-snapshot"])
            args = update_namespace(args, out=str(out_path), verify=False)
            
            cli_snapshot_command.cli_snapshot_command(args)
            
            self.assertTrue(out_path.exists())
            data = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertIn("subcommands", data)
            self.assertIn("arguments", data)
            
    def test_snapshot_verification(self):
        """Test that verification works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "snapshot.json"
            
            # Generate first
            args = get_default_args(["cli-snapshot"])
            args = update_namespace(args, out=str(out_path), verify=False)
            cli_snapshot_command.cli_snapshot_command(args)
            
            # Verify
            args.verify = True
            # Should not exit
            cli_snapshot_command.cli_snapshot_command(args)
            
            # Modify file
            out_path.write_text("{}", encoding="utf-8")
            
            # Verify should fail
            with self.assertRaises(SystemExit):
                cli_snapshot_command.cli_snapshot_command(args)
