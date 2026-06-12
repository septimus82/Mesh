"""
SaveableBehaviour Protocol - Formal save/load lifecycle contract.

This module defines the protocol that behaviours must implement to participate
in the save/restore system. Behaviours are NOT required to be saveable - only
those with meaningful runtime state should implement this protocol.

Protocol Requirements:
- saveable_state() -> dict: Return JSON-serializable state dict
- restore_state(state: dict) -> None: Apply previously saved state

Optional Version Support:
- STATE_VERSION: int - Version number for state schema (default: 1)
- migrate_state(old_state, from_version) -> dict: Migrate older state formats

Design Principles:
1. Opt-in: Behaviours without saveable_state() are safely skipped
2. Defensive: restore_state() must handle missing/extra keys gracefully
3. Deterministic: saveable_state() must return sorted, stable output
4. Minimal: Only persist state that changes during gameplay
5. Idempotent: restore_state(saveable_state()) should be a no-op
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# Default state version for behaviours without explicit versioning
DEFAULT_STATE_VERSION = 1


@runtime_checkable
class SaveableBehaviour(Protocol):
    """Protocol for behaviours that participate in save/restore.
    
    Behaviours implementing this protocol can have their runtime state
    persisted to save files and restored when loading.
    
    Required Methods:
        saveable_state: Return current state as JSON-serializable dict
        restore_state: Apply previously saved state dict
        
    Optional Attributes:
        STATE_VERSION: int indicating current state schema version (default: 1)
        
    Optional Methods:
        migrate_state: Convert old state format to current version
        
    Example::
    
        class HealthBehaviour(Behaviour):
            STATE_VERSION = 2
            
            def saveable_state(self) -> dict[str, Any]:
                return {
                    "current_hp": self.current_hp,
                    "max_hp": self.max_hp,
                    "invulnerable": self.invulnerable,
                }
                
            def restore_state(self, state: dict[str, Any]) -> None:
                self.current_hp = state.get("current_hp", self.max_hp)
                self.max_hp = state.get("max_hp", self.max_hp)
                self.invulnerable = state.get("invulnerable", False)
                
            @classmethod
            def migrate_state(
                cls,
                old_state: dict[str, Any],
                from_version: int,
            ) -> dict[str, Any]:
                if from_version < 2:
                    # v1 had "hp" instead of "current_hp"
                    if "hp" in old_state and "current_hp" not in old_state:
                        old_state["current_hp"] = old_state.pop("hp")
                return old_state
    """

    def saveable_state(self) -> dict[str, Any]:
        """Return current behaviour state as JSON-serializable dict.
        
        Requirements:
        - All values must be JSON-serializable (str, int, float, bool, list, dict, None)
        - Dict keys should be sorted for deterministic output
        - Only include state that changes during gameplay
        - Do NOT include references to entities, windows, or other runtime objects
        
        Returns:
            Dict containing behaviour state. Empty dict {} is valid for
            behaviours that have no dynamic state to persist.
        """
        ...

    def restore_state(self, state: dict[str, Any]) -> None:
        """Apply previously saved state to this behaviour.
        
        Requirements:
        - Must handle missing keys gracefully (use defaults)
        - Must handle extra/unknown keys gracefully (ignore them)
        - Must validate values before applying (clamp, type coerce, etc.)
        - Should NOT raise exceptions - log warnings instead
        
        Args:
            state: Dict from saveable_state(), possibly from older version.
        """
        ...


@runtime_checkable
class VersionedSaveableBehaviour(SaveableBehaviour, Protocol):
    """Extended protocol for behaviours with versioned state schemas.
    
    Use this when your behaviour's state schema may change between
    versions and you need to migrate old saves.
    """

    STATE_VERSION: int
    """Current state schema version. Increment when changing state format."""

    @classmethod
    def migrate_state(
        cls,
        old_state: dict[str, Any],
        from_version: int,
    ) -> dict[str, Any]:
        """Migrate state from an older schema version.
        
        Called when loading state with a version older than STATE_VERSION.
        Should transform old_state in-place or return new dict.
        
        Args:
            old_state: State dict from older save
            from_version: Version number the state was saved with
            
        Returns:
            Migrated state dict compatible with current schema
        """
        ...


def get_behaviour_state_version(behaviour: Any) -> int:
    """Get the state version for a behaviour instance.
    
    Args:
        behaviour: Behaviour instance to check
        
    Returns:
        STATE_VERSION if defined, else DEFAULT_STATE_VERSION (1)
    """
    version = getattr(behaviour, "STATE_VERSION", DEFAULT_STATE_VERSION)
    if isinstance(version, int) and version > 0:
        return version
    return DEFAULT_STATE_VERSION


def is_saveable_behaviour(obj: Any) -> bool:
    """Check if an object implements the SaveableBehaviour protocol.
    
    Args:
        obj: Object to check
        
    Returns:
        True if obj has both saveable_state() and restore_state() methods
    """
    return (
        hasattr(obj, "saveable_state")
        and callable(getattr(obj, "saveable_state", None))
        and hasattr(obj, "restore_state")
        and callable(getattr(obj, "restore_state", None))
    )


def extract_saveable_state(behaviour: Any) -> tuple[dict[str, Any], int] | None:
    """Extract state and version from a saveable behaviour.
    
    Args:
        behaviour: Behaviour instance to extract state from
        
    Returns:
        Tuple of (state_dict, version) or None if not saveable
    """
    if not is_saveable_behaviour(behaviour):
        return None

    try:
        state = behaviour.saveable_state()
        if not isinstance(state, dict):
            return None
        version = get_behaviour_state_version(behaviour)
        return (state, version)
    except Exception:
        return None


def apply_saveable_state(
    behaviour: Any,
    state: dict[str, Any],
    from_version: int | None = None,
) -> bool:
    """Apply saved state to a behaviour with migration if needed.
    
    Args:
        behaviour: Target behaviour instance
        state: State dict to apply
        from_version: Version the state was saved with (for migration)
        
    Returns:
        True if state was applied successfully
    """
    if not is_saveable_behaviour(behaviour):
        return False

    try:
        # Check if migration is needed
        current_version = get_behaviour_state_version(behaviour)
        effective_version = from_version if from_version is not None else current_version

        migrated_state = state
        if effective_version < current_version:
            # Check if behaviour supports migration
            migrate_fn = getattr(behaviour, "migrate_state", None)
            if migrate_fn is not None and callable(migrate_fn):
                try:
                    migrated_state = migrate_fn(dict(state), effective_version)
                    if not isinstance(migrated_state, dict):
                        migrated_state = state
                except Exception:
                    migrated_state = state

        behaviour.restore_state(migrated_state)
        return True
    except Exception:
        return False


def validate_saveable_state(state: dict[str, Any]) -> list[str]:
    """Validate that a state dict is JSON-serializable.
    
    Args:
        state: State dict to validate
        
    Returns:
        List of validation error messages (empty if valid)
    """
    import json

    errors: list[str] = []

    if not isinstance(state, dict):
        errors.append(f"State must be dict, got {type(state).__name__}")
        return errors

    def check_value(value: Any, path: str) -> None:
        if value is None:
            return
        if isinstance(value, (str, int, float, bool)):
            return
        if isinstance(value, list):
            for i, item in enumerate(value):
                check_value(item, f"{path}[{i}]")
            return
        if isinstance(value, dict):
            for k, v in value.items():
                if not isinstance(k, str):
                    errors.append(f"{path}: dict key must be str, got {type(k).__name__}")
                check_value(v, f"{path}.{k}")
            return
        errors.append(f"{path}: unsupported type {type(value).__name__}")

    # Check top-level keys are strings
    for key in state.keys():
        if not isinstance(key, str):
            errors.append(f"Top-level dict key must be str, got {type(key).__name__}")

    # Check all values recursively
    for key, value in state.items():
        path = str(key) if isinstance(key, str) else f"<{type(key).__name__}:{key}>"
        check_value(value, path)

    # Final check: try to serialize
    if not errors:
        try:
            json.dumps(state, sort_keys=True)
        except (TypeError, ValueError) as e:
            errors.append(f"JSON serialization failed: {e}")

    return errors
