"""Contract tests for engine/editor/hd2d_entity_overrides_model.py.

Tests the pure model functions for HD-2D entity overrides:
- Parsing overrides from entity dictionaries
- Sanitizing override patches (None = inherit from scene)
- Applying patches immutably to scene payloads
- Formatting undo labels
- Helper functions for override inspection

NOTE: Override fields are stored directly on entities (not nested under hd2d_overrides).
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from engine.editor.hd2d_entity_overrides_model import (
    ENTITY_BOOL_KEYS,
    ENTITY_INT_KEYS,
    ENTITY_OVERRIDE_DEFAULTS,
    ENTITY_OVERRIDE_FRIENDLY_NAMES,
    ENTITY_OVERRIDE_KEYS,
    ENTITY_STRENGTH_KEYS,
    Hd2dEntityOverrides,
    apply_hd2d_entity_override_patch,
    clear_all_overrides,
    count_overrides,
    count_patch_fields,
    extract_override_patch,
    format_entity_override_label,
    format_entity_toggle_label,
    get_entity_override_value,
    has_any_override,
    parse_hd2d_entity_overrides,
    parse_hd2d_entity_overrides_dict,
    sanitize_hd2d_entity_override_patch,
)


# =============================================================================
# Test Constants
# =============================================================================


class TestEntityOverrideDefaults:
    """Tests for ENTITY_OVERRIDE_DEFAULTS constant."""

    def test_defaults_has_expected_keys(self) -> None:
        """ENTITY_OVERRIDE_DEFAULTS should have all expected keys."""
        expected_keys = {
            "shadow_enabled",
            "shadow_contact_enabled",
            "shadow_ao_enabled",
            "depth_tint_enabled",
            "depth_tint_strength",
            "outline_enabled",
            "outline_strength",
            "outline_radius_px",
        }
        assert set(ENTITY_OVERRIDE_DEFAULTS.keys()) == expected_keys

    def test_all_defaults_are_none(self) -> None:
        """All defaults should be None (inherit from scene)."""
        for key, value in ENTITY_OVERRIDE_DEFAULTS.items():
            assert value is None, f"{key} should default to None"

    def test_bool_keys_are_valid(self) -> None:
        """ENTITY_BOOL_KEYS should be subset of ENTITY_OVERRIDE_KEYS."""
        for key in ENTITY_BOOL_KEYS:
            assert key in ENTITY_OVERRIDE_KEYS

    def test_strength_keys_are_valid(self) -> None:
        """ENTITY_STRENGTH_KEYS should be subset of ENTITY_OVERRIDE_KEYS."""
        for key in ENTITY_STRENGTH_KEYS:
            assert key in ENTITY_OVERRIDE_KEYS

    def test_int_keys_are_valid(self) -> None:
        """ENTITY_INT_KEYS should be subset of ENTITY_OVERRIDE_KEYS."""
        for key in ENTITY_INT_KEYS:
            assert key in ENTITY_OVERRIDE_KEYS

    def test_all_keys_have_friendly_names(self) -> None:
        """All override keys should have friendly names."""
        for key in ENTITY_OVERRIDE_KEYS:
            assert key in ENTITY_OVERRIDE_FRIENDLY_NAMES


# =============================================================================
# Test parse_hd2d_entity_overrides
# =============================================================================


class TestParseHd2dEntityOverrides:
    """Tests for parse_hd2d_entity_overrides function."""

    def test_returns_hd2d_entity_overrides_dataclass(self) -> None:
        """Should return Hd2dEntityOverrides dataclass."""
        result = parse_hd2d_entity_overrides({})
        assert isinstance(result, Hd2dEntityOverrides)

    def test_uses_none_for_empty_entity(self) -> None:
        """Should use None (inherit) when entity has no overrides."""
        result = parse_hd2d_entity_overrides({})
        assert result.shadow_enabled is None
        assert result.shadow_contact_enabled is None
        assert result.shadow_ao_enabled is None
        assert result.depth_tint_enabled is None
        assert result.depth_tint_strength is None
        assert result.outline_enabled is None
        assert result.outline_strength is None
        assert result.outline_radius_px is None

    def test_parses_bool_overrides(self) -> None:
        """Should correctly parse boolean overrides (stored directly on entity)."""
        # Overrides are stored directly on entity, not nested
        entity = {
            "id": "test",
            "shadow_enabled": True,
            "shadow_contact_enabled": False,
        }
        result = parse_hd2d_entity_overrides(entity)
        assert result.shadow_enabled is True
        assert result.shadow_contact_enabled is False
        assert result.shadow_ao_enabled is None  # Not set

    def test_parses_float_overrides_with_clamping(self) -> None:
        """Should clamp float overrides to valid range."""
        entity = {
            "depth_tint_strength": 1.5,  # Over max
            "outline_strength": -0.5,  # Under min
        }
        result = parse_hd2d_entity_overrides(entity)
        assert result.depth_tint_strength == pytest.approx(1.0)
        assert result.outline_strength == pytest.approx(0.0)

    def test_parses_int_overrides(self) -> None:
        """Should parse int overrides correctly."""
        entity = {
            "outline_radius_px": 5,
        }
        result = parse_hd2d_entity_overrides(entity)
        assert result.outline_radius_px == 5

    def test_explicit_none_preserved(self) -> None:
        """Explicit None should be preserved (inherit from scene)."""
        entity = {
            "shadow_enabled": None,
        }
        result = parse_hd2d_entity_overrides(entity)
        assert result.shadow_enabled is None

    def test_handles_missing_keys(self) -> None:
        """Should handle entity with no override keys."""
        entity = {"id": "test_entity", "x": 100, "y": 200}
        result = parse_hd2d_entity_overrides(entity)
        assert result.shadow_enabled is None
        assert result.outline_enabled is None

    def test_handles_non_dict_input(self) -> None:
        """Should handle non-dict input gracefully."""
        result = parse_hd2d_entity_overrides(None)  # type: ignore[arg-type]
        assert isinstance(result, Hd2dEntityOverrides)
        assert result.shadow_enabled is None


# =============================================================================
# Test parse_hd2d_entity_overrides_dict
# =============================================================================


class TestParseHd2dEntityOverridesDict:
    """Tests for parse_hd2d_entity_overrides_dict function."""

    def test_returns_dict(self) -> None:
        """Should return a dictionary."""
        result = parse_hd2d_entity_overrides_dict({})
        assert isinstance(result, dict)

    def test_dict_has_all_keys(self) -> None:
        """Returned dict should have all override keys."""
        result = parse_hd2d_entity_overrides_dict({})
        for key in ENTITY_OVERRIDE_KEYS:
            assert key in result

    def test_empty_entity_returns_all_none(self) -> None:
        """Empty entity should return all None values."""
        result = parse_hd2d_entity_overrides_dict({})
        for key in ENTITY_OVERRIDE_KEYS:
            assert result[key] is None

    def test_parses_set_values(self) -> None:
        """Should parse set values correctly (stored directly on entity)."""
        entity = {
            "shadow_enabled": True,
            "outline_strength": 0.8,
        }
        result = parse_hd2d_entity_overrides_dict(entity)
        assert result["shadow_enabled"] is True
        assert result["outline_strength"] == pytest.approx(0.8)


# =============================================================================
# Test sanitize_hd2d_entity_override_patch
# =============================================================================


class TestSanitizeHd2dEntityOverridePatch:
    """Tests for sanitize_hd2d_entity_override_patch function."""

    def test_returns_dict(self) -> None:
        """Should return a dictionary."""
        result = sanitize_hd2d_entity_override_patch({})
        assert isinstance(result, dict)

    def test_preserves_none_values(self) -> None:
        """None values should be preserved (clear override)."""
        patch = {"shadow_enabled": None}
        result = sanitize_hd2d_entity_override_patch(patch)
        assert result["shadow_enabled"] is None

    def test_coerces_bool_values(self) -> None:
        """Should coerce truthy/falsy to bool."""
        patch = {"shadow_enabled": 1, "outline_enabled": 0}
        result = sanitize_hd2d_entity_override_patch(patch)
        assert result["shadow_enabled"] is True
        assert result["outline_enabled"] is False

    def test_clamps_strength_values(self) -> None:
        """Should clamp strength values to [0.0, 1.0]."""
        patch = {"depth_tint_strength": 2.0, "outline_strength": -1.0}
        result = sanitize_hd2d_entity_override_patch(patch)
        assert result["depth_tint_strength"] == pytest.approx(1.0)
        assert result["outline_strength"] == pytest.approx(0.0)

    def test_allows_large_int_values(self) -> None:
        """Model allows int values without upper bound clamping."""
        # NOTE: The model only clamps min to 0, no upper bound
        patch = {"outline_radius_px": 100}
        result = sanitize_hd2d_entity_override_patch(patch)
        assert result["outline_radius_px"] == 100

    def test_filters_unknown_keys(self) -> None:
        """Should filter out unknown keys."""
        patch = {"unknown_key": 123, "shadow_enabled": True}
        result = sanitize_hd2d_entity_override_patch(patch)
        assert "unknown_key" not in result
        assert result["shadow_enabled"] is True

    def test_converts_to_int(self) -> None:
        """Should convert int keys to int."""
        patch = {"outline_radius_px": 3.7}
        result = sanitize_hd2d_entity_override_patch(patch)
        assert result["outline_radius_px"] == 3
        assert isinstance(result["outline_radius_px"], int)


# =============================================================================
# Test apply_hd2d_entity_override_patch
# =============================================================================


class TestApplyHd2dEntityOverridePatch:
    """Tests for apply_hd2d_entity_override_patch function."""

    def test_returns_new_dict(self) -> None:
        """Should return a new dict, not mutate input."""
        scene = {"entities": [{"id": "test"}]}
        before = copy.deepcopy(scene)
        result = apply_hd2d_entity_override_patch(scene, "test", {"shadow_enabled": True})
        assert scene == before  # Original unchanged
        assert result is not scene

    def test_applies_override_to_entity(self) -> None:
        """Should apply override directly to the entity."""
        scene = {
            "entities": [
                {"id": "entity1"},
                {"id": "entity2"},
            ]
        }
        result = apply_hd2d_entity_override_patch(scene, "entity1", {"shadow_enabled": False})
        entity1 = result["entities"][0]
        # Override is stored directly on entity, not nested
        assert entity1["shadow_enabled"] is False
        # entity2 unchanged
        entity2 = result["entities"][1]
        assert "shadow_enabled" not in entity2

    def test_applies_to_existing_entity(self) -> None:
        """Should apply override to entity that already has other fields."""
        scene = {"entities": [{"id": "test", "x": 100, "y": 200}]}
        result = apply_hd2d_entity_override_patch(scene, "test", {"outline_enabled": True})
        entity = result["entities"][0]
        assert entity["outline_enabled"] is True
        assert entity["x"] == 100  # Preserved

    def test_setting_none_removes_key(self) -> None:
        """Setting None should remove the key (inherit from scene)."""
        scene = {
            "entities": [
                {
                    "id": "test",
                    "shadow_enabled": True,
                }
            ]
        }
        result = apply_hd2d_entity_override_patch(scene, "test", {"shadow_enabled": None})
        # The key should be removed (not present)
        assert "shadow_enabled" not in result["entities"][0]

    def test_returns_unchanged_if_entity_not_found(self) -> None:
        """Should return unchanged scene if entity not found."""
        scene = {"entities": [{"id": "test"}]}
        result = apply_hd2d_entity_override_patch(scene, "nonexistent", {"shadow_enabled": True})
        assert result == scene

    def test_handles_missing_entities_key(self) -> None:
        """Should handle scene with no entities key."""
        scene = {}
        result = apply_hd2d_entity_override_patch(scene, "test", {"shadow_enabled": True})
        assert result == scene

    def test_sanitizes_patch_before_applying(self) -> None:
        """Should sanitize patch values before applying."""
        scene = {"entities": [{"id": "test"}]}
        result = apply_hd2d_entity_override_patch(scene, "test", {"depth_tint_strength": 2.0})
        # Should be clamped to 1.0
        assert result["entities"][0]["depth_tint_strength"] == pytest.approx(1.0)

    def test_finds_entity_by_mesh_name(self) -> None:
        """Should find entity by mesh_name if id not present."""
        scene = {"entities": [{"mesh_name": "my_entity"}]}
        result = apply_hd2d_entity_override_patch(scene, "my_entity", {"shadow_enabled": True})
        assert result["entities"][0]["shadow_enabled"] is True


# =============================================================================
# Test format_entity_toggle_label
# =============================================================================


class TestFormatEntityToggleLabel:
    """Tests for format_entity_toggle_label function."""

    def test_format_true_value(self) -> None:
        """Should format True value correctly (Enable action)."""
        label = format_entity_toggle_label("my_entity", "shadow_enabled", True)
        assert "Shadow" in label
        assert "Enable" in label
        assert "my_entity" in label

    def test_format_false_value(self) -> None:
        """Should format False value correctly (Disable action)."""
        label = format_entity_toggle_label("my_entity", "shadow_enabled", False)
        assert "Shadow" in label
        assert "Disable" in label

    def test_format_none_value(self) -> None:
        """Should format None (inherit) value correctly."""
        label = format_entity_toggle_label("my_entity", "shadow_enabled", None)
        assert "Shadow" in label
        assert "inherit" in label.lower() or "Clear" in label

    def test_uses_friendly_names(self) -> None:
        """Should use friendly names for keys."""
        label = format_entity_toggle_label("e", "shadow_contact_enabled", True)
        assert "Contact" in label  # Friendly name, not raw key


# =============================================================================
# Test format_entity_override_label
# =============================================================================


class TestFormatEntityOverrideLabel:
    """Tests for format_entity_override_label function."""

    def test_format_strength_value(self) -> None:
        """Should format strength value with precision."""
        label = format_entity_override_label("my_entity", "depth_tint_strength", 0.5, 0.75)
        assert "Tint Strength" in label

    def test_format_int_value(self) -> None:
        """Should format int value."""
        label = format_entity_override_label("my_entity", "outline_radius_px", 1, 3)
        assert "Radius" in label

    def test_includes_entity_id(self) -> None:
        """Should include entity id."""
        label = format_entity_override_label("player", "outline_strength", 0.3, 0.5)
        assert "player" in label


# =============================================================================
# Test Helper Functions
# =============================================================================


class TestHasAnyOverride:
    """Tests for has_any_override function."""

    def test_empty_overrides_returns_false(self) -> None:
        """Should return False for empty entity."""
        assert has_any_override({}) is False

    def test_all_none_returns_false(self) -> None:
        """Should return False when all values are None."""
        entity = {
            "shadow_enabled": None,
            "outline_enabled": None,
        }
        assert has_any_override(entity) is False

    def test_any_set_value_returns_true(self) -> None:
        """Should return True when any value is set (stored directly on entity)."""
        entity = {"shadow_enabled": True}
        assert has_any_override(entity) is True


class TestCountOverrides:
    """Tests for count_overrides function."""

    def test_empty_overrides_returns_zero(self) -> None:
        """Should return 0 for empty entity."""
        assert count_overrides({}) == 0

    def test_counts_set_values(self) -> None:
        """Should count only non-None values."""
        entity = {
            "shadow_enabled": True,
            "shadow_contact_enabled": False,
            "outline_enabled": None,  # Not counted
        }
        assert count_overrides(entity) == 2


class TestClearAllOverrides:
    """Tests for clear_all_overrides function."""

    def test_clears_existing_overrides(self) -> None:
        """Should clear all overrides from an entity."""
        scene = {
            "entities": [
                {
                    "id": "test",
                    "shadow_enabled": True,
                    "outline_strength": 0.8,
                }
            ]
        }
        result = clear_all_overrides(scene, "test")
        entity = result["entities"][0]
        # All override keys should be removed
        assert "shadow_enabled" not in entity
        assert "outline_strength" not in entity
        # Non-override fields preserved
        assert entity["id"] == "test"


class TestGetEntityOverrideValue:
    """Tests for get_entity_override_value function."""

    def test_returns_none_for_missing_entity(self) -> None:
        """Should return None if entity not found."""
        scene = {"entities": []}
        result = get_entity_override_value(scene, "test", "shadow_enabled")
        assert result is None

    def test_returns_none_for_missing_override(self) -> None:
        """Should return None if override not set."""
        scene = {"entities": [{"id": "test"}]}
        result = get_entity_override_value(scene, "test", "shadow_enabled")
        assert result is None

    def test_returns_set_value(self) -> None:
        """Should return the set value (stored directly on entity)."""
        scene = {
            "entities": [
                {
                    "id": "test",
                    "shadow_enabled": False,
                }
            ]
        }
        result = get_entity_override_value(scene, "test", "shadow_enabled")
        assert result is False


# =============================================================================
# Test Dataclass Properties
# =============================================================================


class TestHd2dEntityOverridesDataclass:
    """Tests for Hd2dEntityOverrides dataclass."""

    def test_is_frozen(self) -> None:
        """Dataclass should be frozen (immutable)."""
        overrides = Hd2dEntityOverrides(
            shadow_enabled=None,
            shadow_contact_enabled=None,
            shadow_ao_enabled=None,
            depth_tint_enabled=None,
            depth_tint_strength=None,
            outline_enabled=None,
            outline_strength=None,
            outline_radius_px=None,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            overrides.shadow_enabled = True  # type: ignore[misc]

    def test_can_set_values_at_construction(self) -> None:
        """Should be able to set values at construction."""
        overrides = Hd2dEntityOverrides(
            shadow_enabled=True,
            shadow_contact_enabled=False,
            shadow_ao_enabled=None,
            depth_tint_enabled=None,
            depth_tint_strength=None,
            outline_enabled=None,
            outline_strength=0.8,
            outline_radius_px=None,
        )
        assert overrides.shadow_enabled is True
        assert overrides.outline_strength == 0.8


# =============================================================================
# Test Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_multiple_patches_to_same_entity(self) -> None:
        """Should correctly apply multiple patches."""
        scene = {"entities": [{"id": "test"}]}
        scene = apply_hd2d_entity_override_patch(scene, "test", {"shadow_enabled": True})
        scene = apply_hd2d_entity_override_patch(scene, "test", {"outline_enabled": True})
        entity = scene["entities"][0]
        assert entity["shadow_enabled"] is True
        assert entity["outline_enabled"] is True

    def test_empty_patch_returns_same_structure(self) -> None:
        """Empty patch should not modify scene structure."""
        scene = {"entities": [{"id": "test"}]}
        result = apply_hd2d_entity_override_patch(scene, "test", {})
        # Should still have entities
        assert "entities" in result
        assert len(result["entities"]) == 1

    def test_strength_at_boundary_values(self) -> None:
        """Should handle boundary values correctly."""
        entity = {
            "depth_tint_strength": 0.0,
            "outline_strength": 1.0,
        }
        result = parse_hd2d_entity_overrides(entity)
        assert result.depth_tint_strength == pytest.approx(0.0)
        assert result.outline_strength == pytest.approx(1.0)

    def test_int_at_boundary_values(self) -> None:
        """Should handle int boundary values correctly."""
        entity = {
            "outline_radius_px": 0,  # Min value
        }
        result = parse_hd2d_entity_overrides(entity)
        assert result.outline_radius_px == 0

# =============================================================================
# Test extract_override_patch
# =============================================================================


class TestExtractOverridePatch:
    """Tests for extract_override_patch function."""

    def test_empty_dict_returns_empty_patch(self) -> None:
        """Empty entity should return empty patch."""
        result = extract_override_patch({})
        assert result == {}

    def test_non_dict_returns_empty_patch(self) -> None:
        """Non-dict input should return empty patch."""
        assert extract_override_patch(None) == {}  # type: ignore[arg-type]
        assert extract_override_patch([]) == {}  # type: ignore[arg-type]
        assert extract_override_patch("str") == {}  # type: ignore[arg-type]

    def test_extracts_only_override_keys(self) -> None:
        """Should only extract known override keys."""
        entity = {
            "id": "test_entity",
            "shadow_enabled": True,
            "outline_strength": 0.5,
            "random_field": "ignored",
        }
        result = extract_override_patch(entity)
        assert result == {"outline_strength": 0.5, "shadow_enabled": True}
        assert "id" not in result
        assert "random_field" not in result

    def test_excludes_none_values(self) -> None:
        """Should not include None values in patch (inherit state)."""
        entity = {
            "shadow_enabled": True,
            "shadow_contact_enabled": None,
            "outline_enabled": False,
        }
        result = extract_override_patch(entity)
        assert result == {"outline_enabled": False, "shadow_enabled": True}
        assert "shadow_contact_enabled" not in result

    def test_returns_sorted_keys(self) -> None:
        """Should return keys in sorted order for determinism."""
        entity = {
            "outline_strength": 0.8,
            "shadow_enabled": True,
            "depth_tint_enabled": False,
        }
        result = extract_override_patch(entity)
        keys = list(result.keys())
        assert keys == sorted(keys)

    def test_extracts_all_override_types(self) -> None:
        """Should extract bool, strength, and int overrides."""
        entity = {
            "shadow_enabled": True,  # bool
            "depth_tint_strength": 0.7,  # float
            "outline_radius_px": 3,  # int
        }
        result = extract_override_patch(entity)
        assert result["shadow_enabled"] is True
        assert result["depth_tint_strength"] == 0.7
        assert result["outline_radius_px"] == 3


# =============================================================================
# Test count_patch_fields
# =============================================================================


class TestCountPatchFields:
    """Tests for count_patch_fields function."""

    def test_empty_patch_returns_zero(self) -> None:
        """Empty patch should return 0."""
        assert count_patch_fields({}) == 0

    def test_non_dict_returns_zero(self) -> None:
        """Non-dict input should return 0."""
        assert count_patch_fields(None) == 0  # type: ignore[arg-type]
        assert count_patch_fields([]) == 0  # type: ignore[arg-type]
        assert count_patch_fields("str") == 0  # type: ignore[arg-type]

    def test_counts_non_none_fields(self) -> None:
        """Should count non-None fields."""
        patch = {
            "shadow_enabled": True,
            "outline_strength": 0.5,
        }
        assert count_patch_fields(patch) == 2

    def test_excludes_none_from_count(self) -> None:
        """Should not count None values."""
        patch = {
            "shadow_enabled": True,
            "shadow_contact_enabled": None,
            "outline_strength": 0.5,
        }
        assert count_patch_fields(patch) == 2

    def test_counts_false_as_valid(self) -> None:
        """False is a valid override value, should be counted."""
        patch = {
            "shadow_enabled": False,
            "outline_enabled": False,
        }
        assert count_patch_fields(patch) == 2

    def test_counts_zero_as_valid(self) -> None:
        """Zero is a valid override value, should be counted."""
        patch = {
            "depth_tint_strength": 0.0,
            "outline_radius_px": 0,
        }
        assert count_patch_fields(patch) == 2


# =============================================================================
# Test Paste Replace vs Merge Behavior
# =============================================================================


class TestPasteReplaceVsMergeBehavior:
    """Tests verifying the difference between paste merge and paste replace operations."""

    def test_paste_merge_preserves_non_clipboard_overrides(self) -> None:
        """Paste merge should preserve overrides not in the clipboard."""
        # Entity has shadow_enabled=True and outline_enabled=True
        scene = {
            "entities": [{
                "id": "test_entity",
                "shadow_enabled": True,
                "outline_enabled": True,
            }]
        }
        # Clipboard only has depth_tint_enabled
        clipboard = {"depth_tint_enabled": False}

        # Merge: apply only clipboard fields
        merged = apply_hd2d_entity_override_patch(scene, "test_entity", clipboard)
        entity = merged["entities"][0]

        # Original overrides should be preserved
        assert entity["shadow_enabled"] is True
        assert entity["outline_enabled"] is True
        # Clipboard override applied
        assert entity["depth_tint_enabled"] is False

    def test_paste_replace_clears_then_applies_clipboard(self) -> None:
        """Paste replace should clear all overrides first, then apply clipboard."""
        # Entity has shadow_enabled=True and outline_enabled=True
        scene = {
            "entities": [{
                "id": "test_entity",
                "shadow_enabled": True,
                "outline_enabled": True,
            }]
        }
        # Clipboard only has depth_tint_enabled
        clipboard = {"depth_tint_enabled": False}

        # Replace: clear all first, then apply clipboard
        cleared = clear_all_overrides(scene, "test_entity")
        replaced = apply_hd2d_entity_override_patch(cleared, "test_entity", clipboard)
        entity = replaced["entities"][0]

        # Original overrides should be cleared (None or missing)
        assert entity.get("shadow_enabled") is None
        assert entity.get("outline_enabled") is None
        # Clipboard override applied
        assert entity["depth_tint_enabled"] is False

    def test_replace_vs_merge_produces_different_results(self) -> None:
        """Replace and merge should produce different results when entity has existing overrides."""
        base_scene = {
            "entities": [{
                "id": "test_entity",
                "shadow_enabled": True,
                "outline_strength": 0.8,
            }]
        }
        clipboard = {"depth_tint_enabled": True}

        # Merge path
        merged = apply_hd2d_entity_override_patch(
            copy.deepcopy(base_scene), "test_entity", clipboard
        )

        # Replace path
        cleared = clear_all_overrides(copy.deepcopy(base_scene), "test_entity")
        replaced = apply_hd2d_entity_override_patch(cleared, "test_entity", clipboard)

        # Results should differ
        merged_entity = merged["entities"][0]
        replaced_entity = replaced["entities"][0]

        # Merged preserves existing overrides
        assert merged_entity.get("shadow_enabled") is True
        assert merged_entity.get("outline_strength") == 0.8

        # Replaced clears existing overrides
        assert replaced_entity.get("shadow_enabled") is None
        assert replaced_entity.get("outline_strength") is None

        # Both have clipboard override
        assert merged_entity.get("depth_tint_enabled") is True
        assert replaced_entity.get("depth_tint_enabled") is True

    def test_replace_with_full_clipboard_matches_clipboard_exactly(self) -> None:
        """Replace with clipboard containing all fields should result in exact clipboard state."""
        scene = {
            "entities": [{
                "id": "test_entity",
                "shadow_enabled": True,
                "shadow_contact_enabled": True,
                "outline_enabled": False,
            }]
        }
        # Full clipboard with specific values
        clipboard = {
            "shadow_enabled": False,
            "depth_tint_enabled": True,
            "depth_tint_strength": 0.5,
        }

        # Replace
        cleared = clear_all_overrides(scene, "test_entity")
        replaced = apply_hd2d_entity_override_patch(cleared, "test_entity", clipboard)
        entity = replaced["entities"][0]

        # Should match clipboard exactly, old values cleared
        assert entity.get("shadow_enabled") is False  # From clipboard
        assert entity.get("shadow_contact_enabled") is None  # Cleared
        assert entity.get("outline_enabled") is None  # Cleared
        assert entity.get("depth_tint_enabled") is True  # From clipboard
        assert entity.get("depth_tint_strength") == 0.5  # From clipboard