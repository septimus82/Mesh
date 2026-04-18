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

def test_encounter_groups_budget_separation(mock_scene_controller):
    sc = mock_scene_controller
    
    # Setup data
    scene_data = {
        "settings": {
            "encounter_group_budgets": {
                "default": 10,
                "boss_guard": 100
            },
            "encounter_group_allow_elites": {
                "default": True,
                "boss_guard": False
            },
            "encounter_budget_profile": "normal",
            "encounter_seed": 12345
        },
        "entities": [
            {"prefab_id": "theme_enemy_placeholder", "name": "P1", "encounter_group": "default"},
            {"prefab_id": "theme_enemy_placeholder", "name": "P2", "encounter_group": "boss_guard"},
        ]
    }
    
    encounter_set = EncounterSet(
        id="test_set",
        enemy_prefab_ids=["cheap_elite", "expensive_normal"]
    )
    theme = RegionTheme(id="test_theme", description="Test")
    
    # Mock PrefabManager
    with patch("engine.scene_controller.get_prefab_manager") as mock_pm_get:
        pm = MagicMock()
        mock_pm_get.return_value = pm
        
        def get_prefab_side_effect(pid):
            if pid == "cheap_elite":
                return {"encounter_cost": 10, "is_elite": True}
            if pid == "expensive_normal":
                return {"encounter_cost": 100, "is_elite": False}
            return {}
        
        pm.get_prefab.side_effect = get_prefab_side_effect
        
        # Run
        sc._resolve_budgeted_spawns(scene_data, encounter_set, theme)
        
        # Verify
        # P1 (default, budget 10) can only afford cheap_elite (10). expensive_normal (100) is too expensive.
        # P2 (boss_guard, budget 100) disallows elites. cheap_elite is elite. Must pick expensive_normal.
        
        p1 = next(e for e in scene_data["entities"] if e["name"] == "P1")
        p2 = next(e for e in scene_data["entities"] if e["name"] == "P2")
        
        assert p1["prefab_id"] == "cheap_elite"
        assert p2["prefab_id"] == "expensive_normal"

def test_boss_guard_heuristic(mock_scene_controller):
    sc = mock_scene_controller
    
    # Setup data: Normal difficulty (not hard) -> boss_guard should disallow elites
    scene_data = {
        "settings": {
            "encounter_group_budgets": {
                "boss_guard": 100
            },
            "encounter_budget_profile": "normal",
            "encounter_seed": 12345
        },
        "entities": [
            {"prefab_id": "theme_enemy_placeholder", "name": "P1", "encounter_group": "boss_guard"},
        ]
    }
    
    encounter_set = EncounterSet(
        id="test_set",
        enemy_prefab_ids=["elite_mob", "normal_mob"]
    )
    theme = RegionTheme(id="test_theme", description="Test")
    
    with patch("engine.scene_controller.get_prefab_manager") as mock_pm_get:
        pm = MagicMock()
        mock_pm_get.return_value = pm
        
        def get_prefab_side_effect(pid):
            if pid == "elite_mob":
                return {"encounter_cost": 10, "is_elite": True}
            if pid == "normal_mob":
                return {"encounter_cost": 10, "is_elite": False}
            return {}
        
        pm.get_prefab.side_effect = get_prefab_side_effect
        
        sc._resolve_budgeted_spawns(scene_data, encounter_set, theme)
        
        p1 = next(e for e in scene_data["entities"] if e["name"] == "P1")
        # Should pick normal_mob because elite is disallowed by heuristic
        assert p1["prefab_id"] == "normal_mob"

def test_boss_reserve_logic(mock_scene_controller):
    sc = mock_scene_controller
    
    # Setup data: Boss reserve 5. Boss guard budget 10.
    # Effective boss guard budget should be 5.
    scene_data = {
        "settings": {
            "encounter_group_budgets": {
                "boss_guard": 10
            },
            "boss_budget_reserve": 5,
            "encounter_budget_profile": "normal",
            "encounter_seed": 12345
        },
        "entities": [
            {"prefab_id": "theme_enemy_placeholder", "name": "P1", "encounter_group": "boss_guard"},
        ]
    }
    
    encounter_set = EncounterSet(
        id="test_set",
        enemy_prefab_ids=["cost_10", "cost_5"]
    )
    theme = RegionTheme(id="test_theme", description="Test")
    
    with patch("engine.scene_controller.get_prefab_manager") as mock_pm_get:
        pm = MagicMock()
        mock_pm_get.return_value = pm
        
        def get_prefab_side_effect(pid):
            if pid == "cost_10":
                return {"encounter_cost": 10}
            if pid == "cost_5":
                return {"encounter_cost": 5}
            return {}
        
        pm.get_prefab.side_effect = get_prefab_side_effect
        
        sc._resolve_budgeted_spawns(scene_data, encounter_set, theme)
        
        p1 = next(e for e in scene_data["entities"] if e["name"] == "P1")
        # Should pick cost_5 because 10 - 5 = 5
        assert p1["prefab_id"] == "cost_5"
