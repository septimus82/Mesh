import unittest

from engine.tooling.plan_tester import TestReport


class TestPlanTestMinCoverage(unittest.TestCase):
    def test_coverage_ratio(self):
        report = TestReport(
            passed=True,
            tests=[],
            coverage={"actions_total": 10, "actions_covered": 8}
        )
        self.assertEqual(report.coverage_ratio, 0.8)

        report_empty = TestReport(
            passed=True,
            tests=[],
            coverage={"actions_total": 0, "actions_covered": 0}
        )
        self.assertEqual(report_empty.coverage_ratio, 1.0)
