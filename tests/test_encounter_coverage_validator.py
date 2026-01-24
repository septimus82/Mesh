from __future__ import annotations


def test_encounter_coverage_validator_moss_encounters_passes() -> None:
    from engine.validators.encounter_coverage_validator import validate_encounter_coverage

    payload = validate_encounter_coverage(difficulties=("easy", "hard"), encounter_set_ids={"moss_encounters"})
    assert payload["ok"] is True
    assert payload["errors"] == []


def test_encounter_coverage_validator_flags_unaffordable_candidates() -> None:
    from engine.validators.encounter_coverage_validator import validate_encounter_coverage

    class _StubPrefabManager:
        def get_prefab(self, prefab_id: str):
            if prefab_id == "expensive_enemy":
                return {"id": prefab_id, "tags": ["enemy"], "encounter_cost": 999}
            return None

    encounter_sets = {
        "bad_set": {
            "id": "bad_set",
            "enemy_prefab_ids": ["expensive_enemy"],
        }
    }
    presets = {"easy": {"id": "easy"}, "hard": {"id": "hard"}}
    budget_profiles = {"easy": 0.8, "hard": 1.25}

    payload = validate_encounter_coverage(
        difficulties=("easy", "hard"),
        encounter_sets=encounter_sets,
        presets=presets,
        budget_profiles=budget_profiles,
        default_base_budget=10.0,
        prefab_manager=_StubPrefabManager(),
    )
    assert payload["ok"] is False

    errors = payload["errors"]
    assert [e["difficulty"] for e in errors] == ["easy", "hard"]
    easy = errors[0]
    assert easy["encounter_set_id"] == "bad_set"
    assert easy["difficulty"] == "easy"
    assert easy["budget"] == 8.0
    assert easy["cheapest_candidate_cost"] == 999.0
    assert "encounter_set_id=bad_set" in easy["message"]
    assert "difficulty=easy" in easy["message"]

