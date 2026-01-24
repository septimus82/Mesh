import json
import unittest
from io import StringIO
from unittest.mock import patch

import mesh_cli


class TestMeshDoctorJson(unittest.TestCase):
    def test_doctor_json_output(self):
        """Test that mesh doctor --json produces the expected JSON structure."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            # Run doctor on a known world (main_world.json should be valid or at least run)
            # We use --dry-run or similar if possible, but doctor runs read-only checks mostly.
            # We expect exit code 0 or 1, but we care about output.
            try:
                mesh_cli.main(["doctor", "--world", "worlds/main_world.json", "--json"])
            except SystemExit:
                pass  # Doctor might exit with non-zero if there are issues, which is fine

            output = fake_out.getvalue()
            
        # Parse JSON
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            self.fail(f"Output is not valid JSON: {output}")

        # Verify schema
        self.assertIn("world", data)
        self.assertIn("checks", data)
        self.assertIn("next", data)
        self.assertIn("artifacts", data)
        
        self.assertIsInstance(data["checks"], list)
        if data["checks"]:
            check = data["checks"][0]
            self.assertIn("id", check)
            self.assertIn("ok", check)
            self.assertIn("message", check)
            self.assertIn("file", check)
            self.assertIn("hint", check)

    def test_doctor_json_failure(self):
        """Test doctor JSON output on a non-existent world."""
        with patch("sys.stdout", new=StringIO()) as fake_out:
            try:
                mesh_cli.main(["doctor", "--world", "worlds/non_existent.json", "--json"])
            except SystemExit:
                pass

            output = fake_out.getvalue()

        data = json.loads(output)
        self.assertIn("checks", data)
        # Should have at least one check failure (doctor itself failing to find world)
        self.assertTrue(any(not c["ok"] for c in data["checks"]))
