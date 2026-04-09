"""
Tests for save schema validation and migration.

Covers:
- Current version validation
- Old version migration
- Future version rejection
- Corrupt payload rejection
- Field type validation
"""
from __future__ import annotations

import pytest

from engine.save_runtime.schema import (
    SAVE_SCHEMA_VERSION,
    SaveValidationError,
    load_and_validate,
    migrate_save,
    validate_save,
)
from tests._typing import as_any


class TestMigrateSave:
    """Tests for migrate_save()."""
    
    def test_current_version_unchanged(self) -> None:
        """Current version payloads pass through unchanged (except normalization)."""
        payload = {
            "save_schema_version": SAVE_SCHEMA_VERSION,
            "scene_id": "scenes/test.json",
            "flags": {"found_key": True},
            "gold": 100,
        }
        result = migrate_save(dict(payload))
        
        assert result["save_schema_version"] == SAVE_SCHEMA_VERSION
        assert result["scene_id"] == "scenes/test.json"
        assert result["flags"] == {"found_key": True}
        assert result["gold"] == 100
    
    def test_v0_migrates_to_current(self) -> None:
        """v0 payloads (no version) get version field added."""
        payload = {
            "scene_id": "scenes/old.json",
            "flags": ["flag_a", "flag_b"],  # Old list format
        }
        result = migrate_save(dict(payload))
        
        assert result["save_schema_version"] == SAVE_SCHEMA_VERSION
        # Flags should be converted to dict
        assert result["flags"] == {"flag_a": True, "flag_b": True}
    
    def test_save_format_version_used_as_fallback(self) -> None:
        """save_format_version is used if save_schema_version missing."""
        payload = {
            "save_format_version": 1,
            "scene_id": "scenes/test.json",
        }
        result = migrate_save(dict(payload))
        
        assert result["save_schema_version"] == SAVE_SCHEMA_VERSION
    
    def test_future_version_rejected(self) -> None:
        """Future versions raise ValueError with helpful message."""
        payload = {
            "save_schema_version": SAVE_SCHEMA_VERSION + 10,
            "scene_id": "scenes/future.json",
        }
        
        with pytest.raises(ValueError, match=r"newer game version"):
            migrate_save(payload)
    
    def test_non_dict_raises_validation_error(self) -> None:
        """Non-dict payloads raise SaveValidationError."""
        with pytest.raises(SaveValidationError, match=r"must be a JSON object"):
            migrate_save(as_any([1, 2, 3]))
    
    def test_state_renamed_to_game_state(self) -> None:
        """Old 'state' field is renamed to 'game_state'."""
        payload = {
            "state": {"flags": {"test": True}},
        }
        result = migrate_save(dict(payload))
        
        assert "game_state" in result
        assert "state" not in result
        assert result["game_state"]["flags"] == {"test": True}


class TestValidateSave:
    """Tests for validate_save()."""
    
    def test_valid_minimal_payload(self) -> None:
        """Minimal valid payload passes."""
        payload = {
            "save_schema_version": SAVE_SCHEMA_VERSION,
        }
        # Should not raise
        validate_save(payload)
    
    def test_valid_full_payload(self) -> None:
        """Full payload with all optional fields passes."""
        payload = {
            "save_schema_version": SAVE_SCHEMA_VERSION,
            "scene_id": "scenes/test.json",
            "scene_path": "scenes/test.json",
            "flags": {"found_key": True, "opened_door": False},
            "gold": 500,
            "game_state": {
                "flags": {"persistent_flag": True},
                "counters": {"kills": 10},
            },
        }
        # Should not raise
        validate_save(payload)
    
    def test_missing_version_rejected(self) -> None:
        """Payload without version is rejected."""
        payload = {
            "scene_id": "scenes/test.json",
        }
        
        with pytest.raises(SaveValidationError, match=r"Missing version field"):
            validate_save(payload)
    
    def test_flags_must_be_dict_or_list(self) -> None:
        """flags field must be dict or list, not other types."""
        payload = {
            "save_schema_version": SAVE_SCHEMA_VERSION,
            "flags": "not_a_dict",
        }
        
        with pytest.raises(SaveValidationError, match=r"flags must be a dict or list"):
            validate_save(payload)
    
    def test_game_state_must_be_dict(self) -> None:
        """game_state must be a dict."""
        payload = {
            "save_schema_version": SAVE_SCHEMA_VERSION,
            "game_state": "not_a_dict",
        }
        
        with pytest.raises(SaveValidationError, match=r"game_state must be a dict"):
            validate_save(payload)
    
    def test_nested_flags_must_be_dict(self) -> None:
        """game_state.flags must be a dict."""
        payload = {
            "save_schema_version": SAVE_SCHEMA_VERSION,
            "game_state": {
                "flags": ["list", "not", "dict"],
            },
        }
        
        with pytest.raises(SaveValidationError, match=r"game_state.flags must be a dict"):
            validate_save(payload)
    
    def test_scene_id_must_be_string(self) -> None:
        """scene_id must be a string."""
        payload = {
            "save_schema_version": SAVE_SCHEMA_VERSION,
            "scene_id": 12345,
        }
        
        with pytest.raises(SaveValidationError, match=r"scene_id must be a string"):
            validate_save(payload)
    
    def test_gold_must_be_non_negative(self) -> None:
        """gold cannot be negative."""
        payload = {
            "save_schema_version": SAVE_SCHEMA_VERSION,
            "gold": -100,
        }
        
        with pytest.raises(SaveValidationError, match=r"gold cannot be negative"):
            validate_save(payload)
    
    def test_gold_must_be_number(self) -> None:
        """gold must be numeric."""
        payload = {
            "save_schema_version": SAVE_SCHEMA_VERSION,
            "gold": "one hundred",
        }
        
        with pytest.raises(SaveValidationError, match=r"gold must be a number"):
            validate_save(payload)


class TestLoadAndValidate:
    """Tests for load_and_validate() convenience function."""
    
    def test_migrates_and_validates(self) -> None:
        """Combines migration and validation."""
        payload = {
            "scene_id": "scenes/test.json",
            "flags": ["flag_a"],  # Old format
        }
        
        result = load_and_validate(dict(payload))
        
        assert result["save_schema_version"] == SAVE_SCHEMA_VERSION
        assert result["flags"] == {"flag_a": True}
    
    def test_rejects_corrupt_after_migration(self) -> None:
        """Corruption detected after migration still fails."""
        payload = {
            "scene_id": 12345,  # Wrong type
        }
        
        with pytest.raises(SaveValidationError):
            load_and_validate(payload)
    
    def test_non_dict_rejected(self) -> None:
        """Non-dict input rejected immediately."""
        with pytest.raises(SaveValidationError, match=r"must be a JSON object"):
            load_and_validate(as_any("not a dict"))


class TestSaveValidationErrorFormatting:
    """Tests for SaveValidationError message formatting."""
    
    def test_error_with_path(self) -> None:
        """Error with path includes path in message."""
        err = SaveValidationError(
            path="game_state.flags",
            message="must be a dict",
        )
        assert "game_state.flags" in str(err)
        assert "must be a dict" in str(err)
    
    def test_error_without_path(self) -> None:
        """Error without path omits path prefix."""
        err = SaveValidationError(
            path="",
            message="payload is empty",
        )
        assert "payload is empty" in str(err)
        assert "''" not in str(err)
    
    def test_error_includes_value_for_debugging(self) -> None:
        """Error stores value for debugging."""
        err = SaveValidationError(
            path="gold",
            message="must be positive",
            value=-50,
        )
        assert err.value == -50


class TestMigrationDeterminism:
    """Tests that migration is deterministic."""
    
    def test_same_input_same_output(self) -> None:
        """Same input always produces same output."""
        payload = {
            "flags": ["b", "a", "c"],  # Unordered
            "scene_id": "scenes/test.json",
        }
        
        results = [migrate_save(dict(payload)) for _ in range(5)]
        
        # All results should be identical
        for i, result in enumerate(results[1:], 1):
            assert result == results[0], f"Result {i} differs from result 0"
    
    def test_flags_order_normalized(self) -> None:
        """Flag list order doesn't affect output."""
        payload1 = {"flags": ["a", "b", "c"]}
        payload2 = {"flags": ["c", "a", "b"]}
        
        result1 = migrate_save(dict(payload1))
        result2 = migrate_save(dict(payload2))
        
        assert result1["flags"] == result2["flags"]
