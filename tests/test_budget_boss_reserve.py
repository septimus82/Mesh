import unittest
from unittest.mock import MagicMock, patch
from engine.scene_controller import SceneController

class TestBudgetBossReserve(unittest.TestCase):
    def setUp(self):
        self.window = MagicMock()
        self.window.engine_config.encounter_budget_profiles = {"normal": 1.0}
        self.controller = SceneController(self.window)
        self.controller.current_scene_path = "scenes/test.json"

    @patch("engine.scene_controller.get_prefab_manager")
    def test_boss_reserve_reduces_budget(self, mock_pm):
        # Setup
        scene_data = {
            "settings": {
                "encounter_budget": 10,
                "encounter_budget_profile": "normal",
                "boss_budget_reserve": 5,
                "encounter_seed": 12345
            },
            "entities": [
                {"prefab_id": "theme_enemy_placeholder"},
                {"prefab_id": "theme_enemy_placeholder"}
            ]
        }
        
        encounter_set = MagicMock()
        encounter_set.enemy_prefab_ids = ["enemy_cheap"]
        encounter_set.variant_id = None
        
        theme = MagicMock()
        theme.default_variant_id = None
        
        # Mock Prefab Manager
        mock_pm.return_value.get_prefab.side_effect = lambda pid: {
            "encounter_cost": 3.0
        } if pid == "enemy_cheap" else None
        
        # Execute
        self.controller._resolve_budgeted_spawns(scene_data, encounter_set, theme)
        
        # Assert
        # Budget = 10. Reserve = 5. Remaining = 5.
        # Enemy cost = 3.
        # Can afford 1 enemy (3 <= 5).
        # Second enemy (3+3=6 > 5) should not spawn.
        
        entities = scene_data["entities"]
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0]["prefab_id"], "enemy_cheap")

    @patch("engine.scene_controller.get_prefab_manager")
    def test_boss_reserve_zero_allows_more(self, mock_pm):
        # Setup
        scene_data = {
            "settings": {
                "encounter_budget": 10,
                "encounter_budget_profile": "normal",
                "boss_budget_reserve": 0,
                "encounter_seed": 12345
            },
            "entities": [
                {"prefab_id": "theme_enemy_placeholder"},
                {"prefab_id": "theme_enemy_placeholder"},
                {"prefab_id": "theme_enemy_placeholder"}
            ]
        }
        
        encounter_set = MagicMock()
        encounter_set.enemy_prefab_ids = ["enemy_cheap"]
        encounter_set.variant_id = None
        
        theme = MagicMock()
        theme.default_variant_id = None
        
        mock_pm.return_value.get_prefab.side_effect = lambda pid: {
            "encounter_cost": 3.0
        } if pid == "enemy_cheap" else None
        
        self.controller._resolve_budgeted_spawns(scene_data, encounter_set, theme)
        
        # Budget = 10. Reserve = 0. Remaining = 10.
        # Enemy cost = 3.
        # Can afford 3 enemies (9 <= 10).
        
        entities = scene_data["entities"]
        self.assertEqual(len(entities), 3)
