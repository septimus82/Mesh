"""
Tests for behaviour save/load contract compliance.

These tests verify that:
1. SaveableBehaviour protocol is correctly defined and checkable
2. Behaviours implementing the protocol follow the contract
3. Round-trip serialization produces identical state
4. State validation catches invalid state dicts
5. Version migration works correctly
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from engine.behaviours.saveable import (
    DEFAULT_STATE_VERSION,
    SaveableBehaviour,
    VersionedSaveableBehaviour,
    apply_saveable_state,
    extract_saveable_state,
    get_behaviour_state_version,
    is_saveable_behaviour,
    validate_saveable_state,
)


# ============================================================================
# Mock behaviours for testing
# ============================================================================


class SimpleSaveableBehaviour:
    """Simple behaviour implementing SaveableBehaviour protocol."""

    def __init__(self) -> None:
        self.counter = 0
        self.enabled = True
        self.name = "test"

    def saveable_state(self) -> dict[str, Any]:
        return {
            "counter": self.counter,
            "enabled": self.enabled,
            "name": self.name,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        self.counter = state.get("counter", 0)
        self.enabled = state.get("enabled", True)
        self.name = state.get("name", "")


class VersionedBehaviour:
    """Behaviour with explicit state versioning."""

    STATE_VERSION = 2

    def __init__(self) -> None:
        self.health = 100
        self.max_health = 100
        self.shield = 0

    def saveable_state(self) -> dict[str, Any]:
        return {
            "health": self.health,
            "max_health": self.max_health,
            "shield": self.shield,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        self.health = state.get("health", self.max_health)
        self.max_health = state.get("max_health", 100)
        self.shield = state.get("shield", 0)

    @classmethod
    def migrate_state(
        cls,
        old_state: dict[str, Any],
        from_version: int,
    ) -> dict[str, Any]:
        if from_version < 2:
            # v1 had "hp" instead of "health"
            if "hp" in old_state and "health" not in old_state:
                old_state["health"] = old_state.pop("hp")
            # v1 had no shield
            if "shield" not in old_state:
                old_state["shield"] = 0
        return old_state


class NonSaveableBehaviour:
    """Behaviour that does NOT implement save/restore."""

    def __init__(self) -> None:
        self.value = 42

    def update(self, dt: float) -> None:
        pass


class PartialSaveableBehaviour:
    """Behaviour with only saveable_state (no restore_state)."""

    def saveable_state(self) -> dict[str, Any]:
        return {"partial": True}


class BadStateBehaviour:
    """Behaviour that returns invalid state."""

    def saveable_state(self) -> dict[str, Any]:
        # Returns non-JSON-serializable value
        return {"callback": lambda x: x}

    def restore_state(self, state: dict[str, Any]) -> None:
        pass


class CrashingBehaviour:
    """Behaviour that raises exceptions."""

    def saveable_state(self) -> dict[str, Any]:
        raise RuntimeError("saveable_state crashed")

    def restore_state(self, state: dict[str, Any]) -> None:
        raise RuntimeError("restore_state crashed")


# ============================================================================
# Protocol detection tests
# ============================================================================


class TestProtocolDetection:
    """Tests for is_saveable_behaviour() detection."""

    def test_simple_saveable_detected(self) -> None:
        """SimpleSaveableBehaviour should be detected as saveable."""
        b = SimpleSaveableBehaviour()
        assert is_saveable_behaviour(b)

    def test_versioned_saveable_detected(self) -> None:
        """VersionedBehaviour should be detected as saveable."""
        b = VersionedBehaviour()
        assert is_saveable_behaviour(b)

    def test_non_saveable_not_detected(self) -> None:
        """NonSaveableBehaviour should NOT be detected as saveable."""
        b = NonSaveableBehaviour()
        assert not is_saveable_behaviour(b)

    def test_partial_saveable_not_detected(self) -> None:
        """Behaviour with only saveable_state should NOT be detected."""
        b = PartialSaveableBehaviour()
        assert not is_saveable_behaviour(b)

    def test_none_not_saveable(self) -> None:
        """None should not be detected as saveable."""
        assert not is_saveable_behaviour(None)

    def test_string_not_saveable(self) -> None:
        """Arbitrary objects should not be detected as saveable."""
        assert not is_saveable_behaviour("not a behaviour")
        assert not is_saveable_behaviour(42)
        assert not is_saveable_behaviour({})

    def test_isinstance_protocol_check(self) -> None:
        """Protocol isinstance check should work (runtime_checkable)."""
        simple = SimpleSaveableBehaviour()
        versioned = VersionedBehaviour()
        non_saveable = NonSaveableBehaviour()

        assert isinstance(simple, SaveableBehaviour)
        assert isinstance(versioned, SaveableBehaviour)
        assert not isinstance(non_saveable, SaveableBehaviour)


# ============================================================================
# Version handling tests
# ============================================================================


class TestVersionHandling:
    """Tests for STATE_VERSION handling."""

    def test_default_version_no_attr(self) -> None:
        """Behaviours without STATE_VERSION get default version."""
        b = SimpleSaveableBehaviour()
        assert get_behaviour_state_version(b) == DEFAULT_STATE_VERSION

    def test_explicit_version(self) -> None:
        """Behaviours with STATE_VERSION return that version."""
        b = VersionedBehaviour()
        assert get_behaviour_state_version(b) == 2

    def test_invalid_version_uses_default(self) -> None:
        """Invalid STATE_VERSION falls back to default."""

        class BadVersion:
            STATE_VERSION = "not an int"

        assert get_behaviour_state_version(BadVersion()) == DEFAULT_STATE_VERSION

    def test_zero_version_uses_default(self) -> None:
        """Zero or negative version falls back to default."""

        class ZeroVersion:
            STATE_VERSION = 0

        class NegativeVersion:
            STATE_VERSION = -1

        assert get_behaviour_state_version(ZeroVersion()) == DEFAULT_STATE_VERSION
        assert get_behaviour_state_version(NegativeVersion()) == DEFAULT_STATE_VERSION


# ============================================================================
# State extraction tests
# ============================================================================


class TestStateExtraction:
    """Tests for extract_saveable_state()."""

    def test_extract_simple_state(self) -> None:
        """Extract state from simple behaviour."""
        b = SimpleSaveableBehaviour()
        b.counter = 42
        b.name = "test_name"

        result = extract_saveable_state(b)
        assert result is not None
        state, version = result
        assert state["counter"] == 42
        assert state["name"] == "test_name"
        assert version == DEFAULT_STATE_VERSION

    def test_extract_versioned_state(self) -> None:
        """Extract state with version from versioned behaviour."""
        b = VersionedBehaviour()
        b.health = 75
        b.shield = 25

        result = extract_saveable_state(b)
        assert result is not None
        state, version = result
        assert state["health"] == 75
        assert state["shield"] == 25
        assert version == 2

    def test_extract_non_saveable_returns_none(self) -> None:
        """Non-saveable behaviours return None."""
        b = NonSaveableBehaviour()
        assert extract_saveable_state(b) is None

    def test_extract_crashing_behaviour_returns_none(self) -> None:
        """Behaviours that crash return None instead of raising."""
        b = CrashingBehaviour()
        assert extract_saveable_state(b) is None


# ============================================================================
# State application tests
# ============================================================================


class TestStateApplication:
    """Tests for apply_saveable_state()."""

    def test_apply_simple_state(self) -> None:
        """Apply state to simple behaviour."""
        b = SimpleSaveableBehaviour()
        state = {"counter": 100, "enabled": False, "name": "restored"}

        result = apply_saveable_state(b, state)
        assert result is True
        assert b.counter == 100
        assert b.enabled is False
        assert b.name == "restored"

    def test_apply_partial_state(self) -> None:
        """Apply partial state (missing keys use defaults)."""
        b = SimpleSaveableBehaviour()
        b.counter = 999
        state = {"name": "partial"}

        result = apply_saveable_state(b, state)
        assert result is True
        assert b.counter == 0  # default from restore_state
        assert b.name == "partial"

    def test_apply_to_non_saveable_returns_false(self) -> None:
        """Applying to non-saveable behaviour returns False."""
        b = NonSaveableBehaviour()
        result = apply_saveable_state(b, {"value": 1})
        assert result is False

    def test_apply_with_migration(self) -> None:
        """Apply old state with migration."""
        b = VersionedBehaviour()
        old_state = {"hp": 50, "max_health": 100}

        result = apply_saveable_state(b, old_state, from_version=1)
        assert result is True
        assert b.health == 50  # migrated from "hp"
        assert b.shield == 0  # added by migration

    def test_apply_crashing_restore_returns_false(self) -> None:
        """Crashing restore_state returns False instead of raising."""
        b = CrashingBehaviour()
        result = apply_saveable_state(b, {"test": 1})
        assert result is False


# ============================================================================
# Round-trip tests
# ============================================================================


class TestRoundTrip:
    """Tests for save -> restore round-trip integrity."""

    def test_simple_roundtrip(self) -> None:
        """Simple behaviour state survives round-trip."""
        b1 = SimpleSaveableBehaviour()
        b1.counter = 42
        b1.enabled = False
        b1.name = "original"

        # Save
        state = b1.saveable_state()

        # Restore to new instance
        b2 = SimpleSaveableBehaviour()
        b2.restore_state(state)

        assert b2.counter == b1.counter
        assert b2.enabled == b1.enabled
        assert b2.name == b1.name

    def test_versioned_roundtrip(self) -> None:
        """Versioned behaviour state survives round-trip."""
        b1 = VersionedBehaviour()
        b1.health = 75
        b1.max_health = 150
        b1.shield = 25

        state = b1.saveable_state()

        b2 = VersionedBehaviour()
        b2.restore_state(state)

        assert b2.health == b1.health
        assert b2.max_health == b1.max_health
        assert b2.shield == b1.shield

    def test_roundtrip_is_idempotent(self) -> None:
        """Multiple round-trips produce identical state."""
        b = SimpleSaveableBehaviour()
        b.counter = 123
        b.name = "test"

        state1 = b.saveable_state()
        b.restore_state(state1)
        state2 = b.saveable_state()
        b.restore_state(state2)
        state3 = b.saveable_state()

        assert state1 == state2 == state3


# ============================================================================
# State validation tests
# ============================================================================


class TestStateValidation:
    """Tests for validate_saveable_state()."""

    def test_valid_simple_state(self) -> None:
        """Valid state passes validation."""
        state = {
            "counter": 42,
            "enabled": True,
            "name": "test",
        }
        errors = validate_saveable_state(state)
        assert errors == []

    def test_valid_nested_state(self) -> None:
        """Nested dicts and lists are valid."""
        state = {
            "items": ["a", "b", "c"],
            "nested": {"x": 1, "y": 2},
            "deep": [{"a": [1, 2]}, {"b": [3, 4]}],
        }
        errors = validate_saveable_state(state)
        assert errors == []

    def test_valid_none_value(self) -> None:
        """None values are valid."""
        state = {"value": None}
        errors = validate_saveable_state(state)
        assert errors == []

    def test_invalid_function_value(self) -> None:
        """Functions are not JSON-serializable."""
        state = {"callback": lambda x: x}
        errors = validate_saveable_state(state)
        assert len(errors) > 0
        assert "callback" in errors[0] or "function" in errors[0].lower()

    def test_invalid_non_dict(self) -> None:
        """Non-dict state is invalid."""
        errors = validate_saveable_state("not a dict")  # type: ignore
        assert len(errors) == 1
        assert "must be dict" in errors[0]

    def test_invalid_non_string_keys(self) -> None:
        """Dict keys must be strings."""
        state = {1: "value"}  # type: ignore
        errors = validate_saveable_state(state)
        assert len(errors) > 0
        assert "must be str" in errors[0]

    def test_invalid_object_value(self) -> None:
        """Custom objects are not JSON-serializable."""

        class CustomObj:
            pass

        state = {"obj": CustomObj()}
        errors = validate_saveable_state(state)
        assert len(errors) > 0


# ============================================================================
# Empty state tests
# ============================================================================


class TestEmptyState:
    """Tests for behaviours with empty state."""

    def test_empty_state_is_valid(self) -> None:
        """Empty dict {} is a valid state."""
        errors = validate_saveable_state({})
        assert errors == []

    def test_empty_state_roundtrip(self) -> None:
        """Behaviours can return empty state."""

        class EmptyStateBehaviour:
            def saveable_state(self) -> dict[str, Any]:
                return {}

            def restore_state(self, state: dict[str, Any]) -> None:
                pass

        b = EmptyStateBehaviour()
        result = extract_saveable_state(b)
        assert result is not None
        state, version = result
        assert state == {}


# ============================================================================
# Edge case tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and defensive handling."""

    def test_extra_keys_in_restore(self) -> None:
        """Extra keys in state should be ignored."""
        b = SimpleSaveableBehaviour()
        state = {
            "counter": 10,
            "enabled": True,
            "name": "test",
            "unknown_key": "should be ignored",
            "another_unknown": 12345,
        }
        b.restore_state(state)
        assert b.counter == 10
        assert not hasattr(b, "unknown_key")

    def test_missing_keys_use_defaults(self) -> None:
        """Missing keys should use defaults."""
        b = SimpleSaveableBehaviour()
        b.counter = 999
        b.name = "original"

        # Empty state should reset to defaults
        b.restore_state({})
        assert b.counter == 0
        assert b.name == ""

    def test_wrong_type_coercion(self) -> None:
        """Behaviours should handle wrong types gracefully."""

        class TypeSafeBehaviour:
            def __init__(self) -> None:
                self.count = 0
                self.rate = 1.0

            def saveable_state(self) -> dict[str, Any]:
                return {"count": self.count, "rate": self.rate}

            def restore_state(self, state: dict[str, Any]) -> None:
                # Safe type coercion
                try:
                    self.count = int(state.get("count", 0))
                except (TypeError, ValueError):
                    self.count = 0
                try:
                    self.rate = float(state.get("rate", 1.0))
                except (TypeError, ValueError):
                    self.rate = 1.0

        b = TypeSafeBehaviour()
        # Pass wrong types
        b.restore_state({"count": "42", "rate": "3.14"})
        assert b.count == 42
        assert b.rate == pytest.approx(3.14)

        # Pass invalid values
        b.restore_state({"count": "not a number", "rate": None})
        assert b.count == 0
        assert b.rate == 1.0


# ============================================================================
# Protocol structural tests
# ============================================================================


class TestProtocolStructure:
    """Tests verifying protocol structural requirements."""

    def test_saveable_protocol_has_required_methods(self) -> None:
        """SaveableBehaviour protocol requires both methods."""
        assert hasattr(SaveableBehaviour, "saveable_state")
        assert hasattr(SaveableBehaviour, "restore_state")

    def test_versioned_protocol_has_version(self) -> None:
        """VersionedSaveableBehaviour extends SaveableBehaviour."""
        # VersionedSaveableBehaviour should have the migrate_state method
        assert hasattr(VersionedSaveableBehaviour, "migrate_state")
        # A proper implementing class would have STATE_VERSION
        assert VersionedBehaviour.STATE_VERSION == 2

    def test_protocol_is_runtime_checkable(self) -> None:
        """Protocols should be runtime checkable."""
        from typing import runtime_checkable

        # The @runtime_checkable decorator should be applied
        assert getattr(SaveableBehaviour, "__protocol_attrs__", None) is not None or hasattr(
            SaveableBehaviour, "_is_protocol"
        )
