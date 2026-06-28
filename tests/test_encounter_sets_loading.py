import unittest
from unittest.mock import MagicMock, patch

from engine.encounter_sets import ThemeManager


class TestEncounterSetsLoading(unittest.TestCase):
    def test_load_data(self):
        themes_json = """
        {
            "moss": {
                "description": "Mossy",
                "encounter_set_id": "moss_encounters"
            }
        }
        """
        sets_json = """
        {
            "encounter_sets": [
                {
                    "id": "moss_encounters",
                    "enemy_tags": ["plant"]
                }
            ]
        }
        """

        themes_path = MagicMock()
        themes_path.exists.return_value = True
        themes_path.read_text.return_value = themes_json
        sets_path = MagicMock()
        sets_path.exists.return_value = True
        sets_path.read_text.return_value = sets_json
        presets_path = MagicMock()
        presets_path.exists.return_value = False

        def _resolve_path(relative: str):
            if relative == "assets/data/themes.json":
                return themes_path
            if relative == "packs/core_regions/data/encounter_sets.json":
                return sets_path
            if relative == "packs/core_regions/data/encounter_presets.json":
                return presets_path
            raise AssertionError(f"unexpected resolve_path arg: {relative}")

        with patch("engine.encounter_sets.resolve_path", side_effect=_resolve_path):
            tm = ThemeManager()
            tm.load_data()

            theme = tm.get_theme("moss")
            self.assertIsNotNone(theme)
            self.assertEqual(theme.encounter_set_id, "moss_encounters")

            es = tm.get_encounter_set("moss_encounters")
            self.assertIsNotNone(es)
            self.assertEqual(es.enemy_tags, ["plant"])

    def test_resolve_encounter_set(self):
        tm = ThemeManager()
        # Manually populate for test
        from engine.encounter_sets import EncounterSet, RegionTheme
        tm.themes["moss"] = RegionTheme(id="moss", description="", encounter_set_id="moss_encounters")
        tm.encounter_sets["moss_encounters"] = EncounterSet(id="moss_encounters", enemy_tags=["plant"])
        tm._loaded = True

        es = tm.resolve_encounter_set_for_theme("moss")
        self.assertIsNotNone(es)
        self.assertEqual(es.id, "moss_encounters")

    def test_resolve_legacy_fallback(self):
        tm = ThemeManager()
        from engine.encounter_sets import RegionTheme
        tm.themes["legacy"] = RegionTheme(id="legacy", description="", default_enemy_tags=["old"])
        tm._loaded = True

        es = tm.resolve_encounter_set_for_theme("legacy")
        self.assertIsNotNone(es)
        self.assertEqual(es.id, "virtual_legacy")
        self.assertEqual(es.enemy_tags, ["old"])
