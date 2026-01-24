from engine.tooling.plan_tester import TestReport, TestSpec


def test_plan_tester_dataclasses_not_collected_as_tests():
    assert TestSpec.__test__ is False
    assert TestReport.__test__ is False

