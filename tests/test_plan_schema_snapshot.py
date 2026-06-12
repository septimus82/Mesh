import json
import tempfile
import unittest
from pathlib import Path

from engine.tooling import plan_schema_command
from tests.utils.args_factory import get_default_args, update_namespace


class TestPlanSchemaSnapshot(unittest.TestCase):
    def test_schema_generation(self):
        """Test that schema generation produces valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "schema.json"

            args = get_default_args(["plan", "schema"])
            args = update_namespace(args, out=str(out_path), verify=False)

            plan_schema_command.plan_schema_command(args)

            self.assertTrue(out_path.exists())
            data = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertIn("actions", data)
            self.assertIn("create_scene", data["actions"])

    def test_schema_verification(self):
        """Test that verification works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "schema.json"

            # Generate first
            args = get_default_args(["plan", "schema"])
            args = update_namespace(args, out=str(out_path), verify=False)
            plan_schema_command.plan_schema_command(args)

            # Verify
            args.verify = True
            # Should not exit
            plan_schema_command.plan_schema_command(args)

            # Modify file
            out_path.write_text("{}", encoding="utf-8")

            # Verify should fail
            with self.assertRaises(SystemExit):
                plan_schema_command.plan_schema_command(args)
