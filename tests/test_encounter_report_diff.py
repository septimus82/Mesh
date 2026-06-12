import argparse
import unittest
from unittest.mock import patch

from engine.encounter_report import EncounterReport, EncounterSceneReport
from engine.encounter_report_diff import EncounterReportDiff, EncounterSceneDiff, diff_reports
from mesh_cli import _handle_encounter_report


class TestEncounterReportDiff(unittest.TestCase):
    def test_diff_reports(self):
        old_scene = EncounterSceneReport(
            scene_path="scenes/test.json",
            difficulty="normal",
            encounter_budget=100,
            boss_budget_reserve=0,
            elite_cap=2,
            allow_elites=True,
            encounter_layout="default",
            encounter_seed=123,
            total_spawn_cost=100,
            spawn_count=5,
            elite_count=1,
            boss_guard_heuristic=False,
            groups=[]
        )
        new_scene = EncounterSceneReport(
            scene_path="scenes/test.json",
            difficulty="normal",
            encounter_budget=100,
            boss_budget_reserve=0,
            elite_cap=2,
            allow_elites=True,
            encounter_layout="default",
            encounter_seed=123,
            total_spawn_cost=120,
            spawn_count=7,
            elite_count=2,
            boss_guard_heuristic=False,
            groups=[]
        )

        old_report = EncounterReport(scenes=[old_scene])
        new_report = EncounterReport(scenes=[new_scene])

        diff = diff_reports(old_report, new_report)

        self.assertEqual(len(diff.scene_diffs), 1)
        d = diff.scene_diffs[0]
        self.assertEqual(d.spawn_count_delta, 2)
        self.assertEqual(d.elite_count_delta, 1)
        # cost_over_budget_delta depends on calculation.
        # old: cost 100, budget 100 -> over 0
        # new: cost 120, budget 100 -> over 20
        # delta: 20
        self.assertEqual(d.cost_over_budget_delta, 20)

    @patch("mesh_cli.load_report")
    @patch("mesh_cli.diff_reports")
    def test_cli_diff_thresholds(self, mock_diff, mock_load):
        # Setup mock diff
        scene_diff = EncounterSceneDiff(
            scene_path="scenes/test.json",
            difficulty="normal",
            spawn_count_delta=5, # Exceeds 2
            elite_count_delta=0,
            total_spawn_cost_delta=0,
            cost_over_budget_before=0,
            cost_over_budget_after=0,
            cost_over_budget_delta=0,
            boss_reserve_delta=0
        )
        mock_diff.return_value = EncounterReportDiff(scene_diffs=[scene_diff])

        args = argparse.Namespace(
            path=["diff", "old.json", "new.json"],
            max_spawn_delta=2,
            max_elite_delta=None,
            max_cost_overrun=None,
            fail_on_overrun=False,
            json=False,
            out=None
        )

        ret = _handle_encounter_report(args)
        self.assertEqual(ret, 1) # Should fail

    @patch("mesh_cli.legacy_impl.load_report")
    @patch("mesh_cli.legacy_impl.diff_reports")
    def test_cli_diff_pass(self, mock_diff, mock_load):
        # Setup mock diff
        scene_diff = EncounterSceneDiff(
            scene_path="scenes/test.json",
            difficulty="normal",
            spawn_count_delta=1, # Within 2
            elite_count_delta=0,
            total_spawn_cost_delta=0,
            cost_over_budget_before=0,
            cost_over_budget_after=0,
            cost_over_budget_delta=0,
            boss_reserve_delta=0
        )
        mock_diff.return_value = EncounterReportDiff(scene_diffs=[scene_diff])

        args = argparse.Namespace(
            path=["diff", "old.json", "new.json"],
            max_spawn_delta=2,
            max_elite_delta=None,
            max_cost_overrun=None,
            fail_on_overrun=False,
            json=False,
            out=None
        )

        ret = _handle_encounter_report(args)
        self.assertEqual(ret, 0) # Should pass

    def test_check_thresholds(self):
        from engine.encounter_report_diff import EncounterReportDiff, EncounterSceneDiff, check_thresholds

        diff = EncounterReportDiff(scene_diffs=[
            EncounterSceneDiff(
                scene_path="scenes/test.json",
                difficulty="normal",
                spawn_count_delta=5,
                elite_count_delta=2,
                total_spawn_cost_delta=50,
                cost_over_budget_before=0,
                cost_over_budget_after=20,
                cost_over_budget_delta=20,
                boss_reserve_delta=0,
                groups=[]
            )
        ])

        # Test elite delta
        errors = check_thresholds(diff, max_elite_delta=1)
        self.assertEqual(len(errors), 1)
        self.assertIn("Elite delta 2", errors[0])

        # Test spawn delta
        errors = check_thresholds(diff, max_spawn_delta=2)
        self.assertEqual(len(errors), 1)
        self.assertIn("Spawn delta 5", errors[0])

        # Test cost overrun
        errors = check_thresholds(diff, max_cost_overrun=10)
        self.assertEqual(len(errors), 1)
        self.assertIn("Cost overrun 20.00", errors[0])

        # Test fail on overrun
        errors = check_thresholds(diff, fail_on_overrun=True)
        self.assertEqual(len(errors), 1)
        self.assertIn("Cost overrun 20.00 not allowed", errors[0])

        # Test pass
        errors = check_thresholds(diff, max_elite_delta=5, max_spawn_delta=10, max_cost_overrun=50)
        self.assertEqual(len(errors), 0)
