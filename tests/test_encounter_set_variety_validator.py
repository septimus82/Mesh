from __future__ import annotations

import json
from pathlib import Path


def test_encounter_set_variety_validator_repo_passes() -> None:
    from engine.validators.encounter_set_variety_validator import validate_encounter_set_variety

    payload = validate_encounter_set_variety()
    assert payload["ok"] is True
    assert payload["errors"] == []


def test_encounter_set_variety_validator_flags_low_variety(tmp_path: Path) -> None:
    from engine.validators.encounter_set_variety_validator import validate_encounter_set_variety

    bad = {
        "encounter_sets": [
            {
                "id": "bad_set",
                "enemy_tags": ["test"],
                "enemy_prefab_ids": ["slime_blob"] * 8,
            }
        ]
    }
    path = tmp_path / "encounter_sets.json"
    path.write_text(json.dumps(bad, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    payload = validate_encounter_set_variety(source_paths=[path])
    assert payload["ok"] is False
    assert payload["errors"]
    first = payload["errors"][0]
    assert first["code"] == "encounter_sets.low_variety"
    assert first["encounter_set_id"] == "bad_set"
    assert int(first["unique_prefabs"]) == 1
    assert int(first["required"]) == 3

