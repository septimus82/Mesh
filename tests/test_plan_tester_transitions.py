import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.tooling.plan_tester import PlanTester
from engine.tooling.plan_types import Action, Plan


class TestPlanTesterTransitions(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = Path(tempfile.mkdtemp())
        self.tester = PlanTester(self.test_dir)

        # Create dummy source scene
        self.source_scene_path = self.test_dir / "source.json"
        with open(self.source_scene_path, "w") as f:
            json.dump({"entities": []}, f)

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir)

    def test_infer_transition_test(self) -> None:
        """Test that PlanTester infers a transition test from add_transition action."""
        plan = Plan(
            wizard="edit-scene",
            version=1,
            inputs={"path": "source.json"},
            actions=[
                Action(
                    type="add_transition",
                    args={
                        "scene_path": "source.json",
                        "target_scene": "target.json"
                    },
                    description="Add transition"
                )
            ]
        )

        tests = self.tester.infer_tests(plan)
        self.assertEqual(len(tests), 1)
        self.assertEqual(tests[0].type, "transition")
        self.assertEqual(tests[0].name, "Transition: source.json -> target.json")

        assertions = tests[0].assertions
        self.assertEqual(len(assertions), 2)
        self.assertEqual(assertions[0]["type"], "scene_loadable")
        self.assertEqual(assertions[0]["path"], "source.json")
        self.assertEqual(assertions[1]["type"], "transition_valid")
        self.assertEqual(assertions[1]["target"], "target.json")

    def test_run_transition_test_path_success(self) -> None:
        """Test that transition test passes when target is a valid file path."""
        # Create target scene
        target_path = self.test_dir / "target.json"
        with open(target_path, "w") as f:
            json.dump({"entities": []}, f)

        test_spec = self.tester.infer_tests(Plan(
            wizard="edit-scene",
            version=1,
            inputs={},
            actions=[Action(type="add_transition", args={"scene_path": "source.json", "target_scene": "target.json"}, description="")]
        ))[0]

        with patch("engine.paths.resolve_path", side_effect=lambda p: self.test_dir / p):
            report = self.tester.run_tests([test_spec])
            self.assertTrue(report.passed)
            self.assertTrue(report.tests[0]["passed"])

    def test_run_transition_test_id_success(self) -> None:
        """Test that transition test passes when target is a valid scene ID."""
        # Create target scene
        target_path = self.test_dir / "target.json"
        with open(target_path, "w") as f:
            json.dump({"entities": []}, f)

        # Create world definition
        worlds_dir = self.test_dir / "worlds"
        worlds_dir.mkdir()
        with open(worlds_dir / "main.json", "w") as f:
            json.dump({
                "scenes": {
                    "target_id": {"path": "target.json"}
                }
            }, f)

        test_spec = self.tester.infer_tests(Plan(
            wizard="edit-scene",
            version=1,
            inputs={},
            actions=[Action(type="add_transition", args={"scene_path": "source.json", "target_scene": "target_id"}, description="")]
        ))[0]

        with patch("engine.paths.resolve_path", side_effect=lambda p: self.test_dir / p):
            report = self.tester.run_tests([test_spec])
            self.assertTrue(report.passed)

    def test_run_transition_test_fail(self) -> None:
        """Test that transition test fails when target is missing."""
        test_spec = self.tester.infer_tests(Plan(
            wizard="edit-scene",
            version=1,
            inputs={},
            actions=[Action(type="add_transition", args={"scene_path": "source.json", "target_scene": "missing.json"}, description="")]
        ))[0]

        with patch("engine.paths.resolve_path", side_effect=lambda p: self.test_dir / p):
            report = self.tester.run_tests([test_spec])
            self.assertFalse(report.passed)
            self.assertIn("Transition target 'missing.json' could not be resolved", report.tests[0]["error"])
