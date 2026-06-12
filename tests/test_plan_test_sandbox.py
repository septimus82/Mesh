import json
import tempfile
import unittest
from pathlib import Path

from engine.tooling.plan_tester import PlanTester
from engine.tooling.plan_types import Action, Plan


class TestPlanTestSandbox(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.test_dir.name)
        self.tester = PlanTester(self.root)

        # Setup minimal environment
        (self.root / "config.json").write_text("{}")
        (self.root / "assets").mkdir()
        (self.root / "scenes").mkdir()

        # Create a dummy scene to modify
        (self.root / "scenes/original.json").write_text(json.dumps({"entities": []}))

    def tearDown(self):
        self.test_dir.cleanup()

    def test_sandbox_isolation(self):
        # Plan that modifies a scene
        plan = Plan(wizard="test", version=1, inputs={}, actions=[
            Action(type="create_scene", args={"path": "scenes/new_scene.json", "template": "empty"}, description="Create new scene")
        ])

        # Run in sandbox
        report = self.tester.run_tests_in_sandbox(plan)

        # Check report
        self.assertTrue(report.passed)

        # Check that new_scene.json does NOT exist in original root
        self.assertFalse((self.root / "scenes/new_scene.json").exists())

        # Check that original scene is untouched
        self.assertTrue((self.root / "scenes/original.json").exists())
