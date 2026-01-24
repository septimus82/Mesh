import unittest
from unittest.mock import MagicMock, patch
from engine.scene_controller import SceneController

class TestBudgetEliteCap(unittest.TestCase):
    def setUp(self):
        self.window = MagicMock()
        self.window.engine_config.encounter_budget_profiles = {"normal": 1.0}
        self.controller = SceneController(self.window)
        self.controller.current_scene_path = "scenes/test.json"

    @patch("engine.scene_controller.get_prefab_manager")
    def test_elite_cap_limits_elites(self, mock_pm):
        # Setup
        scene_data = {
            "settings": {
                "encounter_budget": 20,
                "encounter_budget_profile": "normal",
                "elite_cap": 1,
                "encounter_seed": 12345
            },
            "entities": [
                {"prefab_id": "theme_enemy_placeholder"},
                {"prefab_id": "theme_enemy_placeholder"},
                {"prefab_id": "theme_enemy_placeholder"}
            ]
        }
        
        encounter_set = MagicMock()
        encounter_set.enemy_prefab_ids = ["elite_enemy", "grunt_enemy"]
        encounter_set.variant_id = None
        
        theme = MagicMock()
        theme.default_variant_id = None
        
        # Mock Prefab Manager
        def get_prefab(pid):
            if pid == "elite_enemy":
                return {"encounter_cost": 5.0, "is_elite": True}
            elif pid == "grunt_enemy":
                return {"encounter_cost": 2.0, "is_elite": False}
            return None
            
        mock_pm.return_value.get_prefab.side_effect = get_prefab
        
        # Execute
        self.controller._resolve_budgeted_spawns(scene_data, encounter_set, theme)
        
        # Assert
        entities = scene_data["entities"]
        elites = [e for e in entities if e["prefab_id"] == "elite_enemy"]
        grunts = [e for e in entities if e["prefab_id"] == "grunt_enemy"]
        
        # Should have max 1 elite
        self.assertLessEqual(len(elites), 1)
        # Should fill rest with grunts if budget allows
        # Budget 20. 1 elite (5) + 2 grunts (4) = 9. Plenty of budget.
        self.assertEqual(len(entities), 3)

    @patch("engine.scene_controller.get_prefab_manager")
    def test_allow_elites_false_blocks_elites(self, mock_pm):
        scene_data = {
            "settings": {
                "encounter_budget": 20,
                "allow_elites": False,
                "encounter_seed": 12345
            },
            "entities": [
                {"prefab_id": "theme_enemy_placeholder"}
            ]
        }
        
        encounter_set = MagicMock()
        encounter_set.enemy_prefab_ids = ["elite_enemy"]
        encounter_set.variant_id = None
        theme = MagicMock()
        theme.default_variant_id = None
        
        mock_pm.return_value.get_prefab.return_value = {"encounter_cost": 5.0, "is_elite": True}
        
        self.controller._resolve_budgeted_spawns(scene_data, encounter_set, theme)
        
        # Should spawn nothing because only candidate is elite and allow_elites=False
        # The placeholder should be removed as it cannot be fulfilled.
        self.assertEqual(len(scene_data["entities"]), 0)
