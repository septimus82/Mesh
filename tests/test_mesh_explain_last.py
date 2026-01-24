import json
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import mesh_cli


class TestMeshExplainLast(unittest.TestCase):
    def test_explain_last_json(self):
        """Test that mesh explain --last --json produces expected structure."""
        # First, ensure we have a failure artifact.
        # We can manually create one or run doctor on a bad world.
        
        report = {
            "version": 1,
            "target": "worlds/bad.json",
            "summary": {"errors": 1, "warnings": 0, "checks": 1},
            "runs": [],
            "errors": [
                {
                    "source": "validate-all",
                    "message": "Scene scenes/bad.json: not found",
                    "file": "scenes/bad.json",
                    "hint": "Check file existence"
                }
            ],
            "warnings": [],
            "suggested_next_commands": ["mesh validate-all"]
        }
        
        report_path = Path(".mesh/reports/doctor_last_failure.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report))

        with patch("sys.stdout", new=StringIO()) as fake_out:
            try:
                mesh_cli.main(["explain", "--last", "--json"])
            except SystemExit:
                pass
            
            output = fake_out.getvalue()

        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            self.fail(f"Output is not valid JSON: {output}")

        self.assertIn("summary", data)
        self.assertIn("action_hints", data)
        
        hints = data["action_hints"]
        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0]["category"], "missing_scene")
        self.assertEqual(hints[0]["suggested_action"], "create_scene")
        self.assertEqual(hints[0]["target"], "scenes/bad.json")
        self.assertEqual(hints[0]["confidence"], 1.0)
        self.assertIn("root_causes", data)
        self.assertIn("files", data)
        self.assertIn("suggested_fixes", data)
        
        self.assertIsInstance(data["root_causes"], list)
        self.assertIsInstance(data["files"], list)
        self.assertIsInstance(data["suggested_fixes"], list)
        
        # Check content based on our mock report
        self.assertIn("scenes/bad.json", data["files"])
