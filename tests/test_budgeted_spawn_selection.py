import pytest
from unittest.mock import MagicMock, patch
from engine.scene_controller import SceneController
from engine.encounter_sets import EncounterSet, RegionTheme

@pytest.fixture
def mock_scene_controller():
    window = MagicMock()
    window.engine_config.encounter_budget_profiles = {"easy": 0.5, "normal": 1.0, "hard": 2.0}
    sc = SceneController(window)
    sc.current_scene_path = "scenes/test.json"
    return sc

def test_budgeted_spawn_selection(mock_scene_controller):
    sc = mock_scene_controller
    
    # Setup data
    scene_data = {
        "settings": {
            "encounter_budget": 10,
            "encounter_budget_profile": "normal",
            "encounter_seed": 12345
        },
        "entities": [
            {"prefab_id": "theme_enemy_placeholder", "name": "P1"},
            {"prefab_id": "theme_enemy_placeholder", "name": "P2"},
            {"prefab_id": "theme_enemy_placeholder", "name": "P3"}
        ]
    }
    
    encounter_set = EncounterSet(
        id="test_set",
        enemy_prefab_ids=["cheap", "expensive"]
    )
    theme = RegionTheme(id="test_theme", description="Test")
    
    # Mock PrefabManager
    with patch("engine.scene_controller.get_prefab_manager") as mock_pm_get:
        pm = MagicMock()
        mock_pm_get.return_value = pm
        
        def get_prefab_side_effect(pid):
            if pid == "cheap": return {"encounter_cost": 2}
            if pid == "expensive": return {"encounter_cost": 5}
            return {}
        
        pm.get_prefab.side_effect = get_prefab_side_effect
        
        # Run
        sc._resolve_budgeted_spawns(scene_data, encounter_set, theme)
        
        # Verify
        entities = scene_data["entities"]
        # Budget is 10.
        # Possible combos: 2 expensive (10), 5 cheap (10), mix.
        # With 3 placeholders, we can fit 3 cheap (6) or 2 expensive (10) or 1 exp + 2 cheap (9).
        # We expect at least 2 to be filled (2 expensive = 10)
        assert len(entities) >= 2
        total_cost = 0
        for e in entities:
            pid = e["prefab_id"]
            assert pid in ["cheap", "expensive"]
            cost = 2 if pid == "cheap" else 5
            total_cost += cost
        
        assert total_cost <= 10

def test_budget_exceeded_fallback(mock_scene_controller):
    sc = mock_scene_controller
    
    # Budget 1, cheapest enemy 2
    scene_data = {
        "settings": {
            "encounter_budget": 1,
            "encounter_budget_profile": "normal",
            "encounter_seed": 12345
        },
        "entities": [
            {"prefab_id": "theme_enemy_placeholder", "name": "P1"},
            {"prefab_id": "theme_enemy_placeholder", "name": "P2"}
        ]
    }
    
    encounter_set = EncounterSet(id="test_set", enemy_prefab_ids=["expensive"])
    theme = RegionTheme(id="test_theme", description="Test")
    
    with patch("engine.scene_controller.get_prefab_manager") as mock_pm_get:
        pm = MagicMock()
        mock_pm_get.return_value = pm
        pm.get_prefab.return_value = {"encounter_cost": 5}
        
        sc._resolve_budgeted_spawns(scene_data, encounter_set, theme)
        
        # Should spawn 1 (fallback) and remove the other
        entities = scene_data["entities"]
        assert len(entities) == 1
        assert entities[0]["prefab_id"] == "expensive"
