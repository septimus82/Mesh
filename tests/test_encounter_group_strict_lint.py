import pytest
from engine.validators.encounter_budget_validator import EncounterBudgetValidator, ValidationResult

def test_strict_lint_unknown_group():
    validator = EncounterBudgetValidator()
    scene_data = {
        "settings": {
            "encounter_group_budgets": {
                "default": 10
            }
        },
        "entities": [
            {
                "prefab_id": "theme_enemy_placeholder",
                "encounter_group": "typo_group"
            }
        ]
    }
    
    # Strict Mode
    results = validator.validate(scene_data, "test.json", strict=True)
    errors = [r for r in results if r.level == "ERROR"]
    assert len(errors) == 1
    assert "references unknown encounter_group 'typo_group'" in errors[0].message
    
    # Dev Mode (Non-strict)
    results = validator.validate(scene_data, "test.json", strict=False)
    errors = [r for r in results if r.level == "ERROR"]
    warns = [r for r in results if r.level == "WARN"]
    assert len(errors) == 0
    assert len(warns) == 1
    assert "references unknown encounter_group 'typo_group'" in warns[0].message

def test_strict_lint_suggestion():
    validator = EncounterBudgetValidator()
    scene_data = {
        "settings": {
            "encounter_group_budgets": {
                "boss_guard": 10
            }
        },
        "entities": [
            {
                "prefab_id": "theme_enemy_placeholder",
                "encounter_group": "boss_gard" # Typo
            }
        ]
    }
    
    results = validator.validate(scene_data, "test.json", strict=True)
    assert "Did you mean 'boss_guard'?" in results[0].message

def test_no_impact_on_legacy():
    validator = EncounterBudgetValidator()
    scene_data = {
        "settings": {
            "encounter_budget": 10
        },
        "entities": [
            {
                "prefab_id": "theme_enemy_placeholder"
                # No encounter_group, defaults to "default"
            }
        ]
    }
    
    # If no group budgets defined, we skip the check?
    # My implementation: "if group_budgets: ..."
    # So legacy scenes (no group_budgets) should pass.
    
    results = validator.validate(scene_data, "test.json", strict=True)
    assert len(results) == 0
