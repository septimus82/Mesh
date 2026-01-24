import pytest
import unittest
import json
import os
from unittest.mock import MagicMock, patch
from engine.encounter_report import generate_encounter_report
from dataclasses import asdict


pytestmark = pytest.mark.builtin_behaviours

class TestEncounterReportGolden(unittest.TestCase):
    def setUp(self):
        self.mock_loader_patch = patch("engine.encounter_report.SceneLoader")
        self.mock_loader_cls = self.mock_loader_patch.start()
        self.mock_loader = self.mock_loader_cls.return_value
        
        self.mock_tm_patch = patch("engine.encounter_report.get_theme_manager")
        self.mock_get_tm = self.mock_tm_patch.start()
        self.mock_tm = MagicMock()
        self.mock_get_tm.return_value = self.mock_tm
        
        self.mock_pm_patch = patch("engine.encounter_report.get_prefab_manager")
        self.mock_get_pm = self.mock_pm_patch.start()
        self.mock_pm = MagicMock()
        self.mock_get_pm.return_value = self.mock_pm

    def tearDown(self):
        self.mock_loader_patch.stop()
        self.mock_tm_patch.stop()
        self.mock_pm_patch.stop()

    def test_golden_schema(self):
        # Load fixture
        fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "encounter_report_scene.json")
        with open(fixture_path, "r") as f:
            scene_data = json.load(f)
            
        self.mock_loader.load_scene.return_value = scene_data
        
        # Setup mocks
        mock_theme = MagicMock()
        mock_theme.default_variant_id = "default"
        self.mock_tm.get_theme.return_value = mock_theme
        
        mock_set = MagicMock()
        mock_set.enemy_prefab_ids = ["goblin"]
        self.mock_tm.resolve_encounter_set_for_theme.return_value = mock_set
        
        mock_prefab = {"encounter_cost": 1, "tags": ["enemy", "mini_boss"]}
        self.mock_pm.get_prefab.return_value = mock_prefab
        
        with patch("engine.scene_controller.get_prefab_manager", return_value=self.mock_pm), \
             patch("engine.scene_controller.get_theme_manager", return_value=self.mock_tm), \
             patch("os.path.exists", return_value=True):
             
            report = generate_encounter_report([fixture_path], difficulties=["normal"])
            output = asdict(report)
            
            # Verify schema structure
            self.assertEqual(output.get("schema_version"), 1)
            self.assertIn("scenes", output)
            self.assertEqual(len(output["scenes"]), 1)
            scene = output["scenes"][0]
            
            expected_keys = {
                "scene_path", "difficulty", "encounter_budget", "boss_budget_reserve",
                "elite_cap", "allow_elites", "encounter_layout", "encounter_seed",
                "total_spawn_cost", "spawn_count", "elite_count", "boss_guard_heuristic",
                "mini_boss_cap", "allow_mini_bosses",
                "mini_boss_count", "mini_boss_cost", "mini_boss_cost_share",
                "groups"
            }
            self.assertTrue(expected_keys.issubset(scene.keys()))
            
            # Verify values (assuming mocks worked)
            # We have 2 placeholders, budget 10.
            # If logic runs, they get replaced by goblins (cost 2).
            # Total cost should be 4.
            # But wait, HeadlessSceneController calls _resolve_budgeted_spawns.
            # Does _resolve_budgeted_spawns actually modify the entities list in the mock setup?
            # It relies on `get_prefab_manager().resolve_with_variant` or similar?
            # No, it picks from `encounter_set.enemy_prefab_ids`.
            # And it modifies `entity["prefab_id"]`.
            # So yes, it should work if the base class method is called.
            
            # However, we need to make sure `_resolve_budgeted_spawns` doesn't crash.
            # It uses `random.Random(seed)`.
            
            # Let's just assert the schema is correct for now, as requested.
            # "Assert the report schema version and key fields exist"
            
            self.assertEqual(scene["difficulty"], "normal")
            self.assertEqual(scene["encounter_seed"], 12345)
            self.assertEqual(scene["elite_count"], 0)
            self.assertEqual(scene["mini_boss_count"], 2)
            self.assertGreater(scene["mini_boss_cost"], 0.0)

            group_keys = {"group_id", "budget", "spawn_count", "elite_count", "cost", "mini_boss_count", "mini_boss_cost", "mini_boss_cost_share"}
            self.assertEqual(len(scene["groups"]), 2)
            for g in scene["groups"]:
                self.assertTrue(group_keys.issubset(g.keys()))
                self.assertEqual(g["elite_count"], 0)
                self.assertEqual(g["mini_boss_count"], 1)
