import unittest
from engine.tooling.plan_types import Plan, Action
from engine.tooling import plan_linter

class TestPlanLint(unittest.TestCase):
    def test_valid_plan(self):
        plan = Plan(
            wizard="test",
            version=1,
            inputs={},
            actions=[
                Action("create_scene", {"path": "scenes/test.json", "template": "empty"}, "desc")
            ]
        )
        issues = plan_linter.lint_plan(plan)
        self.assertEqual(len(issues), 0)

    def test_invalid_version(self):
        plan = Plan(wizard="test", version=2, inputs={}, actions=[])
        issues = plan_linter.lint_plan(plan)
        self.assertTrue(any(i.code == "INVALID_VERSION" for i in issues))

    def test_missing_arg(self):
        plan = Plan(
            wizard="test",
            version=1,
            inputs={},
            actions=[
                Action("create_scene", {"path": "scenes/test.json"}, "desc") # Missing template
            ]
        )
        issues = plan_linter.lint_plan(plan)
        self.assertTrue(any(i.code == "MISSING_ARG" for i in issues))

    def test_unknown_action(self):
        plan = Plan(
            wizard="test",
            version=1,
            inputs={},
            actions=[
                Action("unknown_action", {}, "desc")
            ]
        )
        issues = plan_linter.lint_plan(plan)
        self.assertTrue(any(i.code == "UNKNOWN_ACTION" for i in issues))

    def test_suspicious_path(self):
        plan = Plan(
            wizard="test",
            version=1,
            inputs={},
            actions=[
                Action("create_scene", {"path": "../outside.json", "template": "empty"}, "desc")
            ]
        )
        issues = plan_linter.lint_plan(plan)
        self.assertTrue(any(i.code == "SUSPICIOUS_PATH" for i in issues))

if __name__ == "__main__":
    unittest.main()
