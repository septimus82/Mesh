import unittest
from unittest.mock import MagicMock, patch
from engine.scene_controller import SceneController

class TestEncounterRerollDeterminism(unittest.TestCase):
    def test_resolve_budgeted_spawns_uses_seed(self):
        mock_window = MagicMock()
        # Mock engine_config on window
        mock_window.engine_config = MagicMock()
        mock_window.engine_config.encounter_budget_profiles = {}
        
        # Mock prefab manager before creating SceneController to avoid loading assets
        with patch("engine.scene_controller.get_prefab_manager") as mock_pm:
            controller = SceneController(mock_window)
            
            scene_data = {
                "settings": {
                    "encounter_seed": 12345,
                    "encounter_budget": 100
                },
                "entities": [
                    {"prefab_id": "theme_enemy_placeholder", "encounter_group": "default"}
                ]
            }
            
            mock_es = MagicMock()
            mock_es.enemy_prefab_ids = ["enemy1"]
            mock_theme = MagicMock()
            
            mock_pm_instance = MagicMock()
            mock_pm.return_value = mock_pm_instance
            mock_pm_instance.get_prefab.return_value = MagicMock(cost=10)
            
            # We also need to mock random to verify it's seeded
            with patch("random.Random") as mock_random_cls:
                mock_rng = MagicMock()
                mock_random_cls.return_value = mock_rng
                
                controller._resolve_budgeted_spawns(scene_data, mock_es, mock_theme)
                
                mock_random_cls.assert_called_with(12345)
