"""Tests for prefab schema validation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.behaviours import load_builtin_behaviours
from engine.behaviours.registry import get_behaviour_info
from engine.validators.schema_validation import (
    validate_prefab,
    validate_prefab_file,
)

_FIXED_HEALTH_MAX_HP = {
    "plant_minion": 10,
    "slime_blob": 5,
    "fire_imp": 8,
    "magma_cube": 15,
    "shadow_stalker": 12,
    "void_wisp": 4,
    "rat_scurrier": 6,
    "bone_dart": 10,
    "torch_wisp": 8,
    "ember_imp": 7,
    "anvil_guard": 14,
    "glass_spitter": 9,
    "rust_drone": 11,
    "cinder_larva": 6,
    "rift_leech": 7,
}

_ALREADY_CORRECT_HEALTH_CONFIGS = {
    "sentry_archer": {"hp": 10, "max_hp": 10},
    "ep04_sentry": {"hp": 10, "max_hp": 10},
    "ep04_sentry_hard": {"hp": 12, "max_hp": 12},
    "ep06_fight_sentry": {"hp": 12, "max_hp": 12},
    "ep06_puzzle_sentry": {"hp": 8, "max_hp": 8},
}


def _prefab_files() -> list[Path]:
    files = [Path("assets/prefabs.json")]
    packs = Path("packs")
    if packs.exists():
        files.extend(sorted(packs.rglob("prefabs.json")))
    return files


@pytest.mark.fast
def test_prefab_health_configs_use_declared_health_fields() -> None:
    load_builtin_behaviours()
    health_info = get_behaviour_info("Health")
    assert health_info is not None
    allowed = {str(field["name"]) for field in health_info.config_fields}
    assert allowed == {"hp", "max_hp", "invulnerable"}

    seen_fixed: dict[str, int] = {}
    seen_correct: dict[str, dict[str, int]] = {}
    for path in _prefab_files():
        prefabs = json.loads(path.read_text(encoding="utf-8"))
        for prefab in prefabs:
            health_config = prefab.get("entity", {}).get("behaviour_config", {}).get("Health")
            if not isinstance(health_config, dict):
                continue
            assert set(health_config) <= allowed, f"{path}:{prefab.get('id')} has invalid Health keys"
            prefab_id = str(prefab["id"])
            if prefab_id in _FIXED_HEALTH_MAX_HP:
                assert health_config == {"max_hp": _FIXED_HEALTH_MAX_HP[prefab_id]}
                seen_fixed[prefab_id] = health_config["max_hp"]
            if prefab_id in _ALREADY_CORRECT_HEALTH_CONFIGS:
                assert health_config == _ALREADY_CORRECT_HEALTH_CONFIGS[prefab_id]
                seen_correct[prefab_id] = dict(health_config)

    assert seen_fixed == _FIXED_HEALTH_MAX_HP
    assert seen_correct == _ALREADY_CORRECT_HEALTH_CONFIGS


@pytest.mark.fast
def test_validate_prefab_valid_minimal() -> None:
    """Valid minimal prefab passes validation."""
    prefab = {
        "id": "test_prefab",
        "entity": {"sprite": "assets/test.png"},
    }

    errors = validate_prefab(Path("prefabs.json"), prefab)
    assert errors == []


@pytest.mark.fast
def test_validate_prefab_missing_id() -> None:
    """Prefab without id fails validation."""
    prefab = {
        "entity": {"sprite": "assets/test.png"},
    }

    errors = validate_prefab(Path("prefabs.json"), prefab)
    assert len(errors) == 1
    assert errors[0].code == "prefab.id.required"


@pytest.mark.fast
def test_validate_prefab_invalid_id_format() -> None:
    """Prefab with invalid id format fails validation."""
    prefab = {
        "id": "Invalid-ID",  # Uppercase and hyphen not allowed
        "entity": {},
    }

    errors = validate_prefab(Path("prefabs.json"), prefab)
    assert any(e.code == "prefab.id.format" for e in errors)


@pytest.mark.fast
def test_validate_prefab_missing_entity() -> None:
    """Prefab without entity fails validation."""
    prefab = {
        "id": "test_prefab",
    }

    errors = validate_prefab(Path("prefabs.json"), prefab)
    assert len(errors) == 1
    assert errors[0].code == "prefab.entity.required"


@pytest.mark.fast
def test_validate_prefab_invalid_entity_type() -> None:
    """Prefab with non-dict entity fails validation."""
    prefab = {
        "id": "test_prefab",
        "entity": "not a dict",
    }

    errors = validate_prefab(Path("prefabs.json"), prefab)
    assert any(e.code == "prefab.entity.type" for e in errors)


@pytest.mark.fast
def test_validate_prefab_invalid_behaviours_type() -> None:
    """Prefab with non-list behaviours fails validation."""
    prefab = {
        "id": "test_prefab",
        "entity": {
            "behaviours": "not a list",
        },
    }

    errors = validate_prefab(Path("prefabs.json"), prefab)
    assert any(e.code == "prefab.entity.behaviours.type" for e in errors)


@pytest.mark.fast
def test_validate_prefab_invalid_behaviour_entry() -> None:
    """Prefab with invalid behaviour entry fails validation."""
    prefab = {
        "id": "test_prefab",
        "entity": {
            "behaviours": [123],  # Not string or dict
        },
    }

    errors = validate_prefab(Path("prefabs.json"), prefab)
    assert any(e.code == "prefab.entity.behaviours.entry_type" for e in errors)


@pytest.mark.fast
def test_validate_prefab_invalid_behaviour_config_type() -> None:
    """Prefab with non-dict behaviour_config fails validation."""
    prefab = {
        "id": "test_prefab",
        "entity": {
            "behaviour_config": ["list"],
        },
    }

    errors = validate_prefab(Path("prefabs.json"), prefab)
    assert any(e.code == "prefab.entity.behaviour_config.type" for e in errors)


@pytest.mark.fast
def test_validate_prefab_invalid_collision_poly() -> None:
    """Prefab with invalid collision_poly fails validation."""
    prefab = {
        "id": "test_prefab",
        "entity": {
            "collision_poly": [[0, 0], [1, 1]],  # Only 2 points
        },
    }

    errors = validate_prefab(Path("prefabs.json"), prefab)
    assert any(e.code == "prefab.entity.collision_poly.min_points" for e in errors)


@pytest.mark.fast
def test_validate_prefab_invalid_tags() -> None:
    """Prefab with non-list tags fails validation."""
    prefab = {
        "id": "test_prefab",
        "entity": {
            "tags": "not a list",
        },
    }

    errors = validate_prefab(Path("prefabs.json"), prefab)
    assert any(e.code == "prefab.entity.tags.type" for e in errors)


@pytest.mark.fast
def test_validate_prefab_invalid_tag_entry() -> None:
    """Prefab with non-string tag entry fails validation."""
    prefab = {
        "id": "test_prefab",
        "entity": {
            "tags": [123],
        },
    }

    errors = validate_prefab(Path("prefabs.json"), prefab)
    assert any(e.code == "prefab.entity.tags.entry_type" for e in errors)


@pytest.mark.fast
def test_validate_prefab_valid_with_all_fields() -> None:
    """Valid prefab with all fields passes validation."""
    prefab = {
        "id": "test_prefab",
        "base": "base_prefab",
        "display_name": "Test Prefab",
        "category": "enemies",
        "tags": ["enemy", "boss"],
        "metadata": {"author": "test"},
        "entity": {
            "sprite": "assets/test.png",
            "behaviours": ["PlayerController", {"type": "AI"}],
            "behaviour_config": {"AI": {"speed": 100}},
            "solid": True,
            "collision_poly": [[0, 0], [10, 0], [10, 10]],
            "tags": ["targetable"],
        },
    }

    errors = validate_prefab(Path("prefabs.json"), prefab)
    assert errors == []


@pytest.mark.fast
def test_validate_prefab_extension_fields_allowed() -> None:
    """Fields with x_ prefix are allowed as extensions."""
    prefab = {
        "id": "test_prefab",
        "x_custom": "allowed",
        "entity": {
            "x_custom_entity": "also allowed",
        },
    }

    errors = validate_prefab(Path("prefabs.json"), prefab, strict=True)
    # Should not have errors for x_ prefixed fields
    assert not any("x_custom" in e.message for e in errors)


@pytest.mark.fast
def test_validate_prefab_file_valid() -> None:
    """Valid prefab file passes validation."""
    data = [
        {"id": "prefab_a", "entity": {}},
        {"id": "prefab_b", "entity": {"sprite": "test.png"}},
    ]

    errors = validate_prefab_file(Path("prefabs.json"), data)
    assert errors == []


@pytest.mark.fast
def test_validate_prefab_file_not_list() -> None:
    """Prefab file that isn't a list fails validation."""
    data = {"id": "prefab_a", "entity": {}}

    errors = validate_prefab_file(Path("prefabs.json"), data)
    assert len(errors) == 1
    assert errors[0].code == "prefab_file.type"


@pytest.mark.fast
def test_validate_prefab_file_duplicate_ids() -> None:
    """Prefab file with duplicate ids fails validation."""
    data = [
        {"id": "same_id", "entity": {}},
        {"id": "same_id", "entity": {}},
    ]

    errors = validate_prefab_file(Path("prefabs.json"), data)
    assert any(e.code == "prefab_file.duplicate_id" for e in errors)


@pytest.mark.fast
def test_validate_prefab_error_includes_path() -> None:
    """Validation errors include JSON path for actionability."""
    data = [
        {"id": "valid", "entity": {}},
        {"id": "invalid", "entity": {"tags": "not a list"}},
    ]

    errors = validate_prefab_file(Path("prefabs.json"), data)

    # Find the tags error
    tags_error = next((e for e in errors if "tags" in e.path), None)
    assert tags_error is not None
    assert "[1]" in tags_error.path  # Should include array index
    assert "entity" in tags_error.path
    assert "tags" in tags_error.path
