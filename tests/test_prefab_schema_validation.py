"""Tests for prefab schema validation."""
from __future__ import annotations

from pathlib import Path

import pytest

from engine.validators.schema_validation import (
    ValidationError,
    validate_prefab,
    validate_prefab_file,
)


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
