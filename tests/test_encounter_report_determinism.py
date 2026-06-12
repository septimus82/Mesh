import unittest
from unittest.mock import MagicMock, patch

import pytest

from engine.encounter_report import generate_encounter_report

pytestmark = pytest.mark.builtin_behaviours

class TestEncounterReportDeterminism(unittest.TestCase):
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

    def test_determinism(self):
        # Setup identical inputs
        scene_data = {
            "settings": {
                "region_theme": "forest",
                "use_theme_spawns": True,
                "encounter_budget": 10,
                "encounter_seed": 12345
            },
            "entities": [
                {"prefab_id": "theme_enemy_placeholder", "encounter_group": "default"}
            ]
        }
        self.mock_loader.load_scene.return_value = scene_data

        mock_theme = MagicMock()
        mock_theme.default_variant_id = "default"
        self.mock_tm.get_theme.return_value = mock_theme

        mock_set = MagicMock()
        mock_set.enemy_prefab_ids = ["goblin"]
        self.mock_tm.resolve_encounter_set_for_theme.return_value = mock_set

        mock_prefab = {"encounter_cost": 2, "tags": ["enemy"]}
        self.mock_pm.get_prefab.return_value = mock_prefab

        with patch("engine.scene_controller.get_prefab_manager", return_value=self.mock_pm), \
             patch("engine.scene_controller.get_theme_manager", return_value=self.mock_tm), \
             patch("os.path.exists", return_value=True):

            report1 = generate_encounter_report(["scene1.json"], difficulties=["normal"])
            report2 = generate_encounter_report(["scene1.json"], difficulties=["normal"])

            self.assertEqual(len(report1.scenes), 1)
            self.assertEqual(len(report2.scenes), 1)

            # Check key fields match
            s1 = report1.scenes[0]
            s2 = report2.scenes[0]

            self.assertEqual(s1.encounter_seed, s2.encounter_seed)
            self.assertEqual(s1.spawn_count, s2.spawn_count)
            self.assertEqual(s1.total_spawn_cost, s2.total_spawn_cost)
