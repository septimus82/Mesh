"""Basic tests for encounter report diffing."""

import unittest
from engine.encounter_report import EncounterReport, EncounterSceneReport, EncounterGroupReport
from engine.encounter_report_diff import diff_reports

class TestEncounterReportDiffBasic(unittest.TestCase):
    def setUp(self):
        self.old_scene = EncounterSceneReport(
            scene_path="scenes/test.json",
            difficulty="normal",
            encounter_budget=10.0,
            boss_budget_reserve=0.0,
            elite_cap=1,
            allow_elites=True,
            encounter_layout="test",
            encounter_seed=1,
            total_spawn_cost=8.0,
            spawn_count=4,
            elite_count=0,
            boss_guard_heuristic=False,
            groups=[
                EncounterGroupReport("g1", 5.0, 2, 0, 4.0),
                EncounterGroupReport("g2", 5.0, 2, 0, 4.0)
            ]
        )
        self.old_report = EncounterReport(scenes=[self.old_scene])

    def test_no_change(self):
        diff = diff_reports(self.old_report, self.old_report)
        self.assertEqual(len(diff.scene_diffs), 1)
        s = diff.scene_diffs[0]
        self.assertEqual(s.spawn_count_delta, 0)
        self.assertEqual(s.elite_count_delta, 0)
        self.assertEqual(s.total_spawn_cost_delta, 0.0)
        self.assertEqual(s.cost_over_budget_delta, 0.0)

    def test_spawn_increase(self):
        new_scene = EncounterSceneReport(
            scene_path="scenes/test.json",
            difficulty="normal",
            encounter_budget=10.0,
            boss_budget_reserve=0.0,
            elite_cap=1,
            allow_elites=True,
            encounter_layout="test",
            encounter_seed=1,
            total_spawn_cost=12.0, # Increased
            spawn_count=6, # Increased
            elite_count=1, # Increased
            boss_guard_heuristic=False,
            groups=[
                EncounterGroupReport("g1", 5.0, 3, 1, 6.0),
                EncounterGroupReport("g2", 5.0, 3, 0, 6.0)
            ]
        )
        new_report = EncounterReport(scenes=[new_scene])
        
        diff = diff_reports(self.old_report, new_report)
        s = diff.scene_diffs[0]
        
        self.assertEqual(s.spawn_count_delta, 2)
        self.assertEqual(s.elite_count_delta, 1)
        self.assertEqual(s.total_spawn_cost_delta, 4.0)
        
        # Overrun check
        # Old: 8.0 cost, 10.0 budget -> 0 overrun
        # New: 12.0 cost, 10.0 budget -> 2.0 overrun
        self.assertEqual(s.cost_over_budget_before, 0.0)
        self.assertEqual(s.cost_over_budget_after, 2.0)
        self.assertEqual(s.cost_over_budget_delta, 2.0)

if __name__ == "__main__":
    unittest.main()
