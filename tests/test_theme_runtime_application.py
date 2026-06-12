import unittest
from unittest.mock import MagicMock, patch

import pytest

from engine.scene_controller import SceneController

pytestmark = [pytest.mark.integration, pytest.mark.slow]

class TestThemeRuntimeApplication(unittest.TestCase):
    def setUp(self):
        self.window = MagicMock()
        self.controller = SceneController(self.window)
        self.controller.current_scene_path = "scenes/test.json"

    @patch("engine.scene_controller.get_theme_manager")
    def test_apply_theme_audio(self, mock_get_tm):
        # Setup Theme Manager
        mock_tm = MagicMock()
        mock_get_tm.return_value = mock_tm

        from engine.encounter_sets import EncounterSet, RegionTheme
        mock_tm.get_theme.return_value = RegionTheme(id="moss", description="")
        mock_tm.resolve_encounter_set_for_theme.return_value = EncounterSet(
            id="moss_encounters",
            ambient_audio_key="forest_ambience"
        )

        scene_data = {
            "settings": {
                "region_theme": "moss"
            }
        }

        self.controller._apply_theme_runtime(scene_data)

        self.assertIn("music", scene_data["settings"])
        self.assertEqual(scene_data["settings"]["music"], "assets/music/forest_ambience.mp3")

    @patch("engine.scene_controller.get_theme_manager")
    def test_apply_theme_lighting(self, mock_get_tm):
        mock_tm = MagicMock()
        mock_get_tm.return_value = mock_tm

        from engine.encounter_sets import EncounterSet, RegionTheme
        mock_tm.get_theme.return_value = RegionTheme(id="moss", description="", lighting_hint="green_dim")
        mock_tm.resolve_encounter_set_for_theme.return_value = EncounterSet(id="moss_encounters")

        scene_data = {
            "settings": {
                "region_theme": "moss"
            }
        }

        self.controller._apply_theme_runtime(scene_data)

        self.assertIn("lights", scene_data)
        self.assertEqual(scene_data["lights"][0]["color"], [50, 100, 50])

    @patch("engine.scene_controller.get_theme_manager")
    def test_apply_theme_spawns(self, mock_get_tm):
        mock_tm = MagicMock()
        mock_get_tm.return_value = mock_tm

        from engine.encounter_sets import EncounterSet, RegionTheme
        mock_tm.get_theme.return_value = RegionTheme(id="moss", description="")
        mock_tm.resolve_encounter_set_for_theme.return_value = EncounterSet(
            id="moss_encounters",
            enemy_prefab_ids=["plant_minion"]
        )

        scene_data = {
            "settings": {
                "region_theme": "moss",
                "use_theme_spawns": True
            },
            "entities": [
                {"prefab_id": "theme_enemy_placeholder"},
                {"prefab_id": "other"}
            ]
        }

        self.controller._apply_theme_runtime(scene_data)

        self.assertEqual(scene_data["entities"][0]["prefab_id"], "plant_minion")
        self.assertEqual(scene_data["entities"][1]["prefab_id"], "other")
