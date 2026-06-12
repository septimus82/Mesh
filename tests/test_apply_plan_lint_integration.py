import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mesh_cli
from tests.utils.args_factory import make_apply_plan_args


class TestApplyPlanLintIntegration(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.plan_path = self.test_dir / "plan.json"

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_apply_aborts_on_lint_error(self):
        # Create invalid plan
        plan = {
            "wizard": "test",
            "version": 1,
            "inputs": {},
            "actions": [
                {"type": "create_scene", "args": {"path": "scene.json"}, "description": "Missing template"}
            ]
        }
        with open(self.plan_path, "w") as f:
            json.dump(plan, f)

        args = make_apply_plan_args(
            plan_path=str(self.plan_path),
            no_lint=False,
            dry_run=True
        )

        # Capture stdout to check for error message
        with patch("builtins.print") as mock_print:
            ret = mesh_cli._handle_apply_plan(args)
            self.assertEqual(ret, 1)
            # Verify lint error message
            # We expect "Plan linting failed"
            found = False
            for call in mock_print.call_args_list:
                if "Plan linting failed" in str(call):
                    found = True
                    break
            self.assertTrue(found)

    def test_apply_continues_on_lint_warning(self):
        # Create plan with warning (suspicious path) but no error
        # Wait, suspicious path is a warning in my linter.
        plan = {
            "wizard": "test",
            "version": 1,
            "inputs": {},
            "actions": [
                {"type": "create_scene", "args": {"path": "../scene.json", "template": "empty"}, "description": "Suspicious"}
            ]
        }
        with open(self.plan_path, "w") as f:
            json.dump(plan, f)

        args = make_apply_plan_args(
            plan_path=str(self.plan_path),
            no_lint=False,
            dry_run=True
        )

        with patch("builtins.print") as mock_print:
            # Mock PlanExecutor to avoid actual execution issues
            with patch("mesh_cli.ai.PlanExecutor") as MockExecutor:
                ret = mesh_cli._handle_apply_plan(args)
                self.assertEqual(ret, 0)
                MockExecutor.return_value.execute.assert_called()

if __name__ == "__main__":
    unittest.main()
