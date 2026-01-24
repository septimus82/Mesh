import pytest
from unittest.mock import MagicMock, patch
from engine.validators.encounter_budget_validator import EncounterBudgetValidator
from engine.encounter_report import HeadlessSceneController

def test_encounter_budget_validation():
    validator = EncounterBudgetValidator()
    
    # Valid
    res = validator.validate({"settings": {"encounter_budget": 10}}, "scene.json")
    assert len(res) == 0
    
    # Invalid type
    res = validator.validate({"settings": {"encounter_budget": "ten"}}, "scene.json")
    assert len(res) == 1
    assert res[0].level == "ERROR"
    
    # Negative
    res = validator.validate({"settings": {"encounter_budget": -1}}, "scene.json")
    assert len(res) == 1
    assert res[0].level == "ERROR"
    
    # Unknown profile
    # Note: This test relies on load_config() returning default config which has easy/normal/hard
    res = validator.validate({"settings": {"encounter_budget_profile": "unknown"}}, "scene.json")
    assert len(res) == 1
    assert res[0].level == "WARN"


def test_boss_cost_respected_by_budgeted_spawns() -> None:
    controller = HeadlessSceneController({"easy": 1.0, "normal": 1.0, "hard": 1.0})

    scene_data = {
        "settings": {
            "encounter_budget": 1.5,
            "encounter_seed": 123,
        },
        "entities": [
            {"prefab_id": "theme_enemy_placeholder", "encounter_group": "default"},
        ],
    }

    encounter_set = MagicMock()
    encounter_set.enemy_prefab_ids = ["bossy", "normal"]
    encounter_set.variant_id = None
    encounter_set.drop_table_id = None

    theme = MagicMock()
    theme.default_variant_id = None

    pm = MagicMock()

    def get_prefab(pid: str):
        if pid == "bossy":
            return {"encounter_cost": 1, "is_boss": True}
        return {"encounter_cost": 1}

    pm.get_prefab.side_effect = get_prefab

    with patch("engine.encounter_report.get_prefab_manager", return_value=pm):
        controller._resolve_budgeted_spawns(scene_data, encounter_set, theme)

    assert scene_data["entities"][0]["prefab_id"] == "normal"
