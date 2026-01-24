from __future__ import annotations

import json
from pathlib import Path


def test_encounter_set_uniqueness_validator_repo_passes() -> None:
    from engine.validators.encounter_set_uniqueness_validator import validate_encounter_set_uniqueness

    payload = validate_encounter_set_uniqueness()
    assert payload["ok"] is True
    assert payload["errors"] == []


def test_encounter_set_uniqueness_validator_detects_duplicate_ids(tmp_path) -> None:
    from engine.validators.encounter_set_uniqueness_validator import validate_encounter_set_uniqueness

    a = tmp_path / "encounter_sets_a.json"
    b = tmp_path / "encounter_sets_b.json"

    a.write_text(json.dumps({"encounter_sets": [{"id": "dupe", "enemy_prefab_ids": ["slime_blob"]}]}), encoding="utf-8")
    b.write_text(json.dumps({"encounter_sets": [{"id": "dupe", "enemy_prefab_ids": ["rat_scurrier"]}]}), encoding="utf-8")

    payload = validate_encounter_set_uniqueness(source_paths=(a, b))
    assert payload["ok"] is False

    errors = payload["errors"]
    assert isinstance(errors, list) and len(errors) == 1
    err = errors[0]
    assert err["code"] == "encounter_sets.duplicate_id"
    assert err["encounter_set_id"] == "dupe"

    expected_sources = sorted([str(a).replace("\\", "/"), str(b).replace("\\", "/")])
    assert err["source_paths"] == expected_sources
    assert expected_sources[0] in err["message"]
    assert expected_sources[1] in err["message"]

