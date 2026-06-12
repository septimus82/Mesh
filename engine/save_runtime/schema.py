"""
Save schema validation and migration framework.

This module provides:
- SAVE_SCHEMA_VERSION tracking
- migrate_save() for upgrading old saves
- validate_save() for structural validation
- SaveValidationError for actionable error reporting

Migration policy:
- Old versions are auto-upgraded on load
- Future versions are rejected with clear error
- Corrupt data raises SaveValidationError with path/field info
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

# Current save schema version.
# Increment when adding new required fields or changing semantics.
# v1: Initial schema with flags, counters, player position
# v2: Added saved_entities and saved_quests blocks
SAVE_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class SaveValidationError(Exception):
    """Raised when save validation fails."""
    path: str  # JSON path to invalid field (e.g. "game_state.flags")
    message: str  # Human-readable error
    value: Any = None  # The invalid value (for debugging)

    def __str__(self) -> str:
        if self.path:
            return f"Save validation failed at '{self.path}': {self.message}"
        return f"Save validation failed: {self.message}"


# Type alias for migration functions
MigrationFn = Callable[[dict[str, Any]], dict[str, Any]]


# Registry of migrations: version -> function that upgrades to next version
_MIGRATIONS: dict[int, MigrationFn] = {}


def register_migration(from_version: int) -> Callable[[MigrationFn], MigrationFn]:
    """Decorator to register a migration function."""
    def decorator(fn: MigrationFn) -> MigrationFn:
        _MIGRATIONS[from_version] = fn
        return fn
    return decorator


@register_migration(0)
def _migrate_v0_to_v1(data: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate v0 (no version field) to v1.
    
    v0 saves may be missing:
    - save_schema_version field
    - Consistent field naming
    """
    # Ensure version field exists
    data["save_schema_version"] = 1

    # Normalize flags to dict if it's a list
    flags = data.get("flags")
    if isinstance(flags, list):
        data["flags"] = {str(f): True for f in flags if f}
    elif not isinstance(flags, dict):
        data["flags"] = {}

    # Ensure game_state wrapper exists for slot saves
    if "game_state" not in data and "state" in data:
        data["game_state"] = data.pop("state")

    return data


@register_migration(1)
def _migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate v1 to v2.
    
    v2 adds:
    - saved_entities block for entity state persistence
    - saved_quests block for quest state persistence
    
    v1 saves without these blocks get empty defaults.
    """
    data["save_schema_version"] = 2

    # Add empty saved_entities if missing
    if "saved_entities" not in data:
        data["saved_entities"] = {
            "schema_version": 1,
            "entities": [],
        }

    # Add empty saved_quests if missing
    if "saved_quests" not in data:
        data["saved_quests"] = {
            "schema_version": 1,
            "quests": {},
        }

    return data


def migrate_save(data: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate a save payload to the current schema version.
    
    Args:
        data: Raw save payload (will be modified in place)
        
    Returns:
        The migrated payload
        
    Raises:
        SaveValidationError: If payload is fundamentally invalid
        ValueError: If save is from a future version
    """
    if not isinstance(data, dict):
        raise SaveValidationError(
            path="",
            message="Save payload must be a JSON object",
            value=type(data).__name__,
        )

    # Determine current version
    raw_version = data.get("save_schema_version")
    if raw_version is None:
        # Also check save_format_version for backward compat
        raw_version = data.get("save_format_version", 0)

    try:
        version = int(raw_version)
    except (TypeError, ValueError):
        version = 0

    # Reject future versions
    if version > SAVE_SCHEMA_VERSION:
        raise ValueError(
            f"Save file is from a newer game version (schema v{version}, "
            f"this game supports up to v{SAVE_SCHEMA_VERSION}). "
            f"Please update your game."
        )

    # Apply migrations sequentially
    while version < SAVE_SCHEMA_VERSION:
        migration = _MIGRATIONS.get(version)
        if migration is None:
            # No explicit migration - just bump version
            version += 1
            data["save_schema_version"] = version
        else:
            data = migration(data)
            version = data.get("save_schema_version", version + 1)

    # Ensure save_schema_version is always present after migration
    if "save_schema_version" not in data:
        data["save_schema_version"] = SAVE_SCHEMA_VERSION

    return data


def validate_save(data: dict[str, Any]) -> None:
    """
    Validate a save payload's structure.
    
    This checks:
    - Required fields are present
    - Field types are correct
    - Values are within valid ranges
    
    Args:
        data: Save payload (after migration)
        
    Raises:
        SaveValidationError: With path and message if invalid
    """
    if not isinstance(data, dict):
        raise SaveValidationError(
            path="",
            message="Save payload must be a JSON object",
            value=type(data).__name__,
        )

    # Check version field
    version = data.get("save_schema_version")
    if version is None:
        version = data.get("save_format_version")
    if version is None:
        raise SaveValidationError(
            path="save_schema_version",
            message="Missing version field",
        )

    # Validate flags structure
    flags = data.get("flags")
    if flags is not None and not isinstance(flags, (dict, list)):
        raise SaveValidationError(
            path="flags",
            message=f"flags must be a dict or list, got {type(flags).__name__}",
            value=flags,
        )

    # Validate nested game_state if present
    game_state = data.get("game_state")
    if game_state is not None:
        if not isinstance(game_state, dict):
            raise SaveValidationError(
                path="game_state",
                message=f"game_state must be a dict, got {type(game_state).__name__}",
                value=game_state,
            )

        # Check nested flags
        nested_flags = game_state.get("flags")
        if nested_flags is not None and not isinstance(nested_flags, dict):
            raise SaveValidationError(
                path="game_state.flags",
                message=f"game_state.flags must be a dict, got {type(nested_flags).__name__}",
                value=nested_flags,
            )

        # Check counters
        counters = game_state.get("counters")
        if counters is not None and not isinstance(counters, dict):
            raise SaveValidationError(
                path="game_state.counters",
                message=f"game_state.counters must be a dict, got {type(counters).__name__}",
                value=counters,
            )

    # Validate scene_id/scene_path if present
    for field in ("scene_id", "scene_path"):
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            raise SaveValidationError(
                path=field,
                message=f"{field} must be a string, got {type(value).__name__}",
                value=value,
            )

    # Validate gold/currency if present
    gold = data.get("gold")
    if gold is not None:
        try:
            gold_int = int(gold)
            if gold_int < 0:
                raise SaveValidationError(
                    path="gold",
                    message=f"gold cannot be negative, got {gold_int}",
                    value=gold,
                )
        except (TypeError, ValueError):
            raise SaveValidationError(
                path="gold",
                message=f"gold must be a number, got {type(gold).__name__}",
                value=gold,
            )

    # Validate saved_entities (v2)
    saved_entities = data.get("saved_entities")
    if saved_entities is not None:
        if not isinstance(saved_entities, dict):
            raise SaveValidationError(
                path="saved_entities",
                message=f"saved_entities must be a dict, got {type(saved_entities).__name__}",
                value=saved_entities,
            )
        entities_list = saved_entities.get("entities")
        if entities_list is not None and not isinstance(entities_list, list):
            raise SaveValidationError(
                path="saved_entities.entities",
                message=f"saved_entities.entities must be a list, got {type(entities_list).__name__}",
                value=entities_list,
            )

    # Validate saved_quests (v2)
    saved_quests = data.get("saved_quests")
    if saved_quests is not None:
        if not isinstance(saved_quests, dict):
            raise SaveValidationError(
                path="saved_quests",
                message=f"saved_quests must be a dict, got {type(saved_quests).__name__}",
                value=saved_quests,
            )
        quests_dict = saved_quests.get("quests")
        if quests_dict is not None and not isinstance(quests_dict, dict):
            raise SaveValidationError(
                path="saved_quests.quests",
                message=f"saved_quests.quests must be a dict, got {type(quests_dict).__name__}",
                value=quests_dict,
            )


def load_and_validate(data: Any) -> dict[str, Any]:
    """
    Convenience function to migrate and validate a save payload.
    
    Args:
        data: Raw save payload
        
    Returns:
        Validated, migrated payload
        
    Raises:
        SaveValidationError: If validation fails
        ValueError: If from future version
    """
    if not isinstance(data, dict):
        raise SaveValidationError(
            path="",
            message="Save payload must be a JSON object",
            value=type(data).__name__,
        )

    migrated = migrate_save(data)
    validate_save(migrated)
    return migrated
