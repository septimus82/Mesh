import pytest
from engine.validators.variant_validator import VariantValidator

def test_validate_variant_fields():
    validator = VariantValidator()
    
    # Valid
    validator._validate_variant_fields("v1", {
        "id": "v1",
        "hp_mult": 1.5,
        "tags_add": ["tag"],
        "sprite_override": "path.png"
    })
    assert len(validator.errors) == 0
    
    # Invalid types
    validator._validate_variant_fields("v2", {
        "id": "v2",
        "hp_mult": "string", # Error
        "tags_add": "string", # Error
        "sprite_override": 123 # Error
    })
    assert len(validator.errors) == 3
    assert "must be a number" in validator.errors[0]
    assert "must be a list" in validator.errors[1]
    assert "must be a string" in validator.errors[2]

def test_validate_variant_negative_mult():
    validator = VariantValidator()
    validator._validate_variant_fields("v3", {
        "id": "v3",
        "hp_mult": -1.0
    })
    assert len(validator.errors) == 1
    assert "must be non-negative" in validator.errors[0]
