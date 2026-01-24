import unittest
import json
import tempfile
import shutil
from pathlib import Path
from engine.tooling.plan_tester import PlanTester, TestSpec
from engine.tooling.plan_types import Plan, Action

class TestPlanTesterSceneWorld(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.test_dir.name)
        self.tester = PlanTester(self.root)
        
        # Create dummy assets structure
        (self.root / "assets").mkdir()
        (self.root / "scenes").mkdir()
        (self.root / "worlds").mkdir()

    def tearDown(self):
        self.test_dir.cleanup()

    def test_infer_scene_test(self):
        plan = Plan(wizard="test", version=1, inputs={}, actions=[
            Action(type="create_scene", args={"path": "scenes/test_scene.json"}, description="Create scene")
        ])
        tests = self.tester.infer_tests(plan)
        self.assertEqual(len(tests), 1)
        self.assertEqual(tests[0].type, "scene")
        self.assertEqual(tests[0].assertions[0]["type"], "scene_loadable")

    def test_run_scene_test_pass(self):
        # Create the scene file
        scene_path = self.root / "scenes/test_scene.json"
        scene_path.write_text(json.dumps({"entities": []}))
        
        test = TestSpec(name="Scene Test", type="scene", assertions=[
            {"type": "scene_loadable", "path": "scenes/test_scene.json"}
        ])
        
        report = self.tester.run_tests([test])
        self.assertTrue(report.passed)

    def test_run_scene_test_fail(self):
        test = TestSpec(name="Scene Test", type="scene", assertions=[
            {"type": "scene_loadable", "path": "scenes/missing.json"}
        ])
        
        report = self.tester.run_tests([test])
        self.assertFalse(report.passed)

    def test_infer_npc_test(self):
        plan = Plan(wizard="test", version=1, inputs={}, actions=[
            Action(type="place_npc", args={"into": "scenes/test_scene.json", "role": "guard"}, description="Place NPC")
        ])
        tests = self.tester.infer_tests(plan)
        self.assertEqual(len(tests), 1)
        self.assertEqual(tests[0].type, "npc")
        self.assertEqual(tests[0].assertions[0]["role"], "guard")

    def test_run_npc_test_pass(self):
        scene_path = self.root / "scenes/test_scene.json"
        scene_path.write_text(json.dumps({
            "entities": [{"name": "guard", "tags": ["npc"]}]
        }))
        
        test = TestSpec(name="NPC Test", type="npc", assertions=[
            {"type": "npc_present", "scene_path": "scenes/test_scene.json", "role": "guard"}
        ])
        
        report = self.tester.run_tests([test])
        self.assertTrue(report.passed)

    def test_run_npc_test_fail(self):
        scene_path = self.root / "scenes/test_scene.json"
        scene_path.write_text(json.dumps({
            "entities": [{"name": "other", "tags": ["npc"]}]
        }))
        
        test = TestSpec(name="NPC Test", type="npc", assertions=[
            {"type": "npc_present", "scene_path": "scenes/test_scene.json", "role": "guard"}
        ])
        
        report = self.tester.run_tests([test])
        self.assertFalse(report.passed)
