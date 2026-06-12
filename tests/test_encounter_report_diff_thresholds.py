"""Tests for encounter report diff thresholds."""

import unittest

from engine.encounter_report_diff import EncounterReportDiff, EncounterSceneDiff, check_thresholds


class TestEncounterReportDiffThresholds(unittest.TestCase):
    def setUp(self):
        self.diff = EncounterReportDiff(scene_diffs=[
            EncounterSceneDiff(
                scene_path="scenes/test.json",
                difficulty="normal",
                spawn_count_delta=5,
                elite_count_delta=2,
                total_spawn_cost_delta=10.0,
                cost_over_budget_before=0.0,
                cost_over_budget_after=5.0,
                cost_over_budget_delta=5.0,
                boss_reserve_delta=0.0
            )
        ])

    def test_no_thresholds(self):
        errors = check_thresholds(self.diff)
        self.assertEqual(len(errors), 0)

    def test_spawn_delta_threshold(self):
        errors = check_thresholds(self.diff, max_spawn_delta=4)
        self.assertEqual(len(errors), 1)
        self.assertIn("Spawn delta 5 exceeds limit 4", errors[0])

        errors = check_thresholds(self.diff, max_spawn_delta=6)
        self.assertEqual(len(errors), 0)

    def test_elite_delta_threshold(self):
        errors = check_thresholds(self.diff, max_elite_delta=1)
        self.assertEqual(len(errors), 1)
        self.assertIn("Elite delta 2 exceeds limit 1", errors[0])

    def test_cost_overrun_threshold(self):
        errors = check_thresholds(self.diff, max_cost_overrun=4.0)
        self.assertEqual(len(errors), 1)
        self.assertIn("Cost overrun 5.00 exceeds limit 4.0", errors[0])

    def test_fail_on_overrun(self):
        errors = check_thresholds(self.diff, fail_on_overrun=True)
        self.assertEqual(len(errors), 1)
        self.assertIn("Cost overrun 5.00 not allowed", errors[0])

if __name__ == "__main__":
    unittest.main()
