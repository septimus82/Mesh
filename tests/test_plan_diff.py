import unittest
from engine.tooling.plan_types import Plan, Action
from engine.tooling import plan_diff

class TestPlanDiff(unittest.TestCase):
    def test_diff_identical(self):
        plan = Plan(wizard="test", version=1, inputs={}, actions=[
            Action("create_scene", {"path": "a.json", "template": "empty"}, "desc")
        ])
        diff = plan_diff.diff_plans(plan, plan)
        self.assertEqual(len(diff["actions_added"]), 0)
        self.assertEqual(len(diff["actions_removed"]), 0)
        self.assertEqual(len(diff["actions_changed"]), 0)

    def test_diff_add_remove(self):
        plan_a = Plan(wizard="test", version=1, inputs={}, actions=[
            Action("create_scene", {"path": "a.json", "template": "empty"}, "desc")
        ])
        plan_b = Plan(wizard="test", version=1, inputs={}, actions=[
            Action("create_scene", {"path": "b.json", "template": "empty"}, "desc")
        ])
        
        diff = plan_diff.diff_plans(plan_a, plan_b)
        self.assertEqual(len(diff["actions_changed"]), 1)
        self.assertEqual(diff["actions_changed"][0]["index"], 0)
        
    def test_diff_length_mismatch(self):
        plan_a = Plan(wizard="test", version=1, inputs={}, actions=[])
        plan_b = Plan(wizard="test", version=1, inputs={}, actions=[
            Action("create_scene", {"path": "a.json", "template": "empty"}, "desc")
        ])
        
        diff = plan_diff.diff_plans(plan_a, plan_b)
        self.assertEqual(len(diff["actions_added"]), 1)
        self.assertIn("a.json", diff["estimated_files_touched"])

if __name__ == "__main__":
    unittest.main()
