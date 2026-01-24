import unittest
from pathlib import Path
from engine.tooling.plan_tester import PlanTester, TestSpec, TestReport

class TestPlanTestCoverage(unittest.TestCase):
    def test_coverage_reporting(self):
        tester = PlanTester(Path("."))
        
        # Mock tests
        tests = [
            TestSpec(name="T1", type="scene", assertions=[{"type": "scene_loadable", "path": "missing.json"}]),
            TestSpec(name="T2", type="npc", assertions=[{"type": "npc_present", "scene_path": "missing.json", "role": "r"}])
        ]
        
        # Run tests with explicit total_actions
        # We expect it to fail execution because we didn't setup files, but we check the report structure
        # Actually run_tests catches exceptions and returns report with passed=False
        
        report = tester.run_tests(tests, total_actions=5)
        
        self.assertEqual(report.coverage["actions_total"], 5)
        self.assertEqual(report.coverage["actions_covered"], 2)
        self.assertFalse(report.passed) # Should fail because files don't exist
        self.assertEqual(len(report.tests), 2)

    def test_empty_coverage(self):
        tester = PlanTester(Path("."))
        report = tester.run_tests([], total_actions=10)
        
        self.assertEqual(report.coverage["actions_total"], 10)
        self.assertEqual(report.coverage["actions_covered"], 0)
        self.assertTrue(report.passed)
