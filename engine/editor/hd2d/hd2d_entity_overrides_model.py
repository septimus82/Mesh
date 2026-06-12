"""Pure model for HD-2D per-entity overrides.

Provides functions to:
- Parse HD-2D overrides from entity dict with defaults (None = inherit scene)
- Sanitize/clamp override patches
- Apply override patches immutably to scene payload
- Format undo labels for override changes
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

# =============================================================================
# Entity Override Keys
# =============================================================================

# Keys that can be overridden at entity level
# None value means "inherit from scene settings"

# Boolean toggle keys (can be True, False, or None for inherit)
ENTITY_BOOL_KEYS: frozenset[str] = frozenset({
    "shadow_enabled",
    "shadow_contact_enabled",
    "shadow_ao_enabled",
    "depth_tint_enabled",
    "outline_enabled",
})

# Float strength keys clamped to [0, 1] (or None for inherit)
ENTITY_STRENGTH_KEYS: frozenset[str] = frozenset({
    "depth_tint_strength",
    "outline_strength",
})

# Non-negative integer keys (or None for inherit)
ENTITY_INT_KEYS: frozenset[str] = frozenset({
    "outline_radius_px",
})

# All entity override keys
ENTITY_OVERRIDE_KEYS: frozenset[str] = (
    ENTITY_BOOL_KEYS | ENTITY_STRENGTH_KEYS | ENTITY_INT_KEYS
)

# Default values for all entity override keys (None = inherit from scene)
ENTITY_OVERRIDE_DEFAULTS: dict[str, Any] = {
    "shadow_enabled": None,
    "shadow_contact_enabled": None,
    "shadow_ao_enabled": None,
    "depth_tint_enabled": None,
    "depth_tint_strength": None,
    "outline_enabled": None,
    "outline_strength": None,
    "outline_radius_px": None,
}

# Friendly names for display
ENTITY_OVERRIDE_FRIENDLY_NAMES: dict[str, str] = {
    "shadow_enabled": "Shadow",
    "shadow_contact_enabled": "Contact Shadow",
    "shadow_ao_enabled": "AO Shadow",
    "depth_tint_enabled": "Depth Tint",
    "depth_tint_strength": "Tint Strength",
    "outline_enabled": "Outline",
    "outline_strength": "Outline Strength",
    "outline_radius_px": "Outline Radius",
}


# =============================================================================
# Data Classes
# =============================================================================


@dataclass(frozen=True, slots=True)
class Hd2dEntityOverrides:
    """Parsed HD-2D overrides for a single entity.

    None values mean "inherit from scene settings".
    """

    shadow_enabled: bool | None
    shadow_contact_enabled: bool | None
    shadow_ao_enabled: bool | None
    depth_tint_enabled: bool | None
    depth_tint_strength: float | None
    outline_enabled: bool | None
    outline_strength: float | None
    outline_radius_px: int | None


# =============================================================================
# Parse Functions
# =============================================================================


def _parse_bool_or_none(value: Any) -> bool | None:
    """Parse a value as bool or None (inherit)."""
    if value is None:
        return None
    return bool(value)


def _parse_float_clamped_or_none(
    value: Any, min_val: float = 0.0, max_val: float = 1.0
) -> float | None:
    """Parse a value as float clamped to range, or None (inherit)."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return max(min_val, min(max_val, f))


def _parse_int_clamped_or_none(value: Any, min_val: int = 0) -> int | None:
    """Parse a value as non-negative int, or None (inherit)."""
    if value is None:
        return None
    try:
        i = int(value)
    except (TypeError, ValueError):
        return None
    return max(min_val, i)


def parse_hd2d_entity_overrides(entity_dict: dict[str, Any]) -> Hd2dEntityOverrides:
    """Parse HD-2D overrides from an entity dict.

    Extracts override values from entity_dict, returning None for any
    keys that are not present (meaning "inherit from scene").

    Args:
        entity_dict: The entity dict from scene payload.

    Returns:
        Hd2dEntityOverrides dataclass with all values (None = inherit).
    """
    if not isinstance(entity_dict, dict):
        entity_dict = {}

    return Hd2dEntityOverrides(
        shadow_enabled=_parse_bool_or_none(entity_dict.get("shadow_enabled")),
        shadow_contact_enabled=_parse_bool_or_none(entity_dict.get("shadow_contact_enabled")),
        shadow_ao_enabled=_parse_bool_or_none(entity_dict.get("shadow_ao_enabled")),
        depth_tint_enabled=_parse_bool_or_none(entity_dict.get("depth_tint_enabled")),
        depth_tint_strength=_parse_float_clamped_or_none(
            entity_dict.get("depth_tint_strength"), 0.0, 1.0
        ),
        outline_enabled=_parse_bool_or_none(entity_dict.get("outline_enabled")),
        outline_strength=_parse_float_clamped_or_none(
            entity_dict.get("outline_strength"), 0.0, 1.0
        ),
        outline_radius_px=_parse_int_clamped_or_none(
            entity_dict.get("outline_radius_px"), 0
        ),
    )


def parse_hd2d_entity_overrides_dict(entity_dict: dict[str, Any]) -> dict[str, Any]:
    """Parse HD-2D overrides from an entity dict as a plain dict.

    Same as parse_hd2d_entity_overrides but returns a dict for provider use.

    Args:
        entity_dict: The entity dict from scene payload.

    Returns:
        Dict with all override values (None = inherit).
    """
    parsed = parse_hd2d_entity_overrides(entity_dict)
    return {
        "shadow_enabled": parsed.shadow_enabled,
        "shadow_contact_enabled": parsed.shadow_contact_enabled,
        "shadow_ao_enabled": parsed.shadow_ao_enabled,
        "depth_tint_enabled": parsed.depth_tint_enabled,
        "depth_tint_strength": parsed.depth_tint_strength,
        "outline_enabled": parsed.outline_enabled,
        "outline_strength": parsed.outline_strength,
        "outline_radius_px": parsed.outline_radius_px,
    }


# =============================================================================
# Sanitize Functions
# =============================================================================


def sanitize_hd2d_entity_override_value(key: str, value: Any) -> Any:
    """Sanitize a single HD-2D entity override value.

    Args:
        key: The override key.
        value: The value to sanitize.

    Returns:
        Sanitized value with correct type and clamping, or None.
    """
    # None means "inherit" - always valid
    if value is None:
        return None

    if key in ENTITY_BOOL_KEYS:
        return bool(value)

    if key in ENTITY_STRENGTH_KEYS:
        try:
            f = float(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(1.0, f))

    if key in ENTITY_INT_KEYS:
        try:
            i = int(value)
        except (TypeError, ValueError):
            return None
        return max(0, i)

    # Unknown key - return as-is
    return value


def sanitize_hd2d_entity_override_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """Sanitize a patch of HD-2D entity overrides.

    Clamps values and ensures correct types.

    Args:
        patch: Dict of override key -> value to sanitize.

    Returns:
        New dict with sanitized values.
    """
    if not isinstance(patch, dict):
        return {}

    result: dict[str, Any] = {}
    for key, value in patch.items():
        if not isinstance(key, str):
            continue
        if key not in ENTITY_OVERRIDE_KEYS:
            continue
        result[key] = sanitize_hd2d_entity_override_value(key, value)

    return result


# =============================================================================
# Apply Functions
# =============================================================================


def _find_entity_index(scene_payload: dict[str, Any], entity_id: str) -> int | None:
    """Find the index of an entity by ID in the scene payload.

    Args:
        scene_payload: The scene payload dict.
        entity_id: The entity ID to find.

    Returns:
        Index of the entity, or None if not found.
    """
    entities = scene_payload.get("entities")
    if not isinstance(entities, list):
        return None

    key = str(entity_id or "").strip()
    if not key:
        return None

    for i, entity in enumerate(entities):
        if not isinstance(entity, dict):
            continue
        # Check common ID fields
        eid = entity.get("id") or entity.get("mesh_name") or entity.get("name")
        if str(eid or "").strip() == key:
            return i

    return None


def apply_hd2d_entity_override_patch(
    scene_payload: dict[str, Any],
    entity_id: str,
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Apply a sanitized patch to a specific entity's overrides.

    Does NOT mutate the input. Returns a new scene payload.

    Args:
        scene_payload: The scene payload dict.
        entity_id: The ID of the entity to update.
        patch: Dict of override key -> value to apply.

    Returns:
        New scene payload with patched entity overrides.
    """
    sanitized_patch = sanitize_hd2d_entity_override_patch(patch)
    if not sanitized_patch:
        return copy.deepcopy(scene_payload) if isinstance(scene_payload, dict) else {}

    result = copy.deepcopy(scene_payload) if isinstance(scene_payload, dict) else {}

    idx = _find_entity_index(result, entity_id)
    if idx is None:
        return result

    entities = result.get("entities")
    if not isinstance(entities, list) or idx >= len(entities):
        return result

    entity = entities[idx]
    if not isinstance(entity, dict):
        return result

    # Apply patch to entity
    for key, value in sanitized_patch.items():
        if value is None:
            # Remove override (inherit from scene)
            entity.pop(key, None)
        else:
            entity[key] = value

    return result


def get_entity_override_value(
    scene_payload: dict[str, Any],
    entity_id: str,
    key: str,
) -> Any:
    """Get the current value of an entity override.

    Args:
        scene_payload: The scene payload dict.
        entity_id: The ID of the entity.
        key: The override key.

    Returns:
        The current value, or None if not set (inherit).
    """
    idx = _find_entity_index(scene_payload, entity_id)
    if idx is None:
        return None

    entities = scene_payload.get("entities")
    if not isinstance(entities, list) or idx >= len(entities):
        return None

    entity = entities[idx]
    if not isinstance(entity, dict):
        return None

    return entity.get(key)


# =============================================================================
# Undo Label Formatting
# =============================================================================


def format_entity_override_label(
    entity_id: str,
    field_name: str,
    old_value: Any,
    new_value: Any,
) -> str:
    """Format an undo label for an entity override change.

    Args:
        entity_id: The entity ID.
        field_name: The override field name.
        old_value: The old value.
        new_value: The new value.

    Returns:
        Label like "Set Shadow · entity_1 · ON" or "Clear Outline Strength · entity_1"
    """
    friendly_name = ENTITY_OVERRIDE_FRIENDLY_NAMES.get(
        field_name, field_name.replace("_", " ").title()
    )

    # Truncate long entity IDs
    display_id = entity_id
    if len(display_id) > 20:
        display_id = display_id[:17] + "..."

    # Handle "clear override" (set to None/inherit)
    if new_value is None:
        return f"Clear {friendly_name} · {display_id}"

    # Handle boolean toggles
    if field_name in ENTITY_BOOL_KEYS:
        action = "Enable" if new_value else "Disable"
        return f"{action} {friendly_name} · {display_id}"

    # Handle numeric values
    if field_name in ENTITY_STRENGTH_KEYS:
        new_str = f"{float(new_value):.2f}" if isinstance(new_value, (int, float)) else str(new_value)
        return f"Set {friendly_name} · {display_id} · {new_str}"

    if field_name in ENTITY_INT_KEYS:
        return f"Set {friendly_name} · {display_id} · {new_value}"

    return f"Set {friendly_name} · {display_id}"


def format_entity_toggle_label(entity_id: str, key: str, new_value: bool | None) -> str:
    """Format an undo label for an entity toggle change.

    Args:
        entity_id: The entity ID.
        key: The override key.
        new_value: The new boolean value (or None for inherit).

    Returns:
        Label like "Enable Shadow · entity_1" or "Inherit Shadow · entity_1"
    """
    friendly_name = ENTITY_OVERRIDE_FRIENDLY_NAMES.get(
        key, key.replace("_", " ").title()
    )

    # Truncate long entity IDs
    display_id = entity_id
    if len(display_id) > 20:
        display_id = display_id[:17] + "..."

    if new_value is None:
        return f"Inherit {friendly_name} · {display_id}"

    action = "Enable" if new_value else "Disable"
    return f"{action} {friendly_name} · {display_id}"


# =============================================================================
# Override State Helpers
# =============================================================================


def has_any_override(entity_dict: dict[str, Any]) -> bool:
    """Check if entity has any HD-2D overrides set.

    Args:
        entity_dict: The entity dict.

    Returns:
        True if any override key is present (not None).
    """
    if not isinstance(entity_dict, dict):
        return False

    for key in ENTITY_OVERRIDE_KEYS:
        if key in entity_dict and entity_dict[key] is not None:
            return True

    return False


def count_overrides(entity_dict: dict[str, Any]) -> int:
    """Count how many HD-2D overrides are set on an entity.

    Args:
        entity_dict: The entity dict.

    Returns:
        Number of override keys with non-None values.
    """
    if not isinstance(entity_dict, dict):
        return 0

    count = 0
    for key in ENTITY_OVERRIDE_KEYS:
        if key in entity_dict and entity_dict[key] is not None:
            count += 1

    return count


def clear_all_overrides(
    scene_payload: dict[str, Any],
    entity_id: str,
) -> dict[str, Any]:
    """Clear all HD-2D overrides from an entity.

    Args:
        scene_payload: The scene payload dict.
        entity_id: The entity ID.

    Returns:
        New scene payload with all overrides cleared.
    """
    # Create patch with all keys set to None
    patch = {key: None for key in ENTITY_OVERRIDE_KEYS}
    return apply_hd2d_entity_override_patch(scene_payload, entity_id, patch)


def extract_override_patch(entity_dict: dict[str, Any]) -> dict[str, Any]:
    """Extract a minimal patch of only non-None overrides from an entity.

    Returns a deterministic dict containing only override keys that have
    non-None values. Keys are sorted for deterministic ordering.

    Args:
        entity_dict: The entity dict with override fields.

    Returns:
        Dict of key -> value for non-None overrides only.
    """
    if not isinstance(entity_dict, dict):
        return {}

    patch: dict[str, Any] = {}
    # Use sorted keys for deterministic order
    for key in sorted(ENTITY_OVERRIDE_KEYS):
        if key in entity_dict and entity_dict[key] is not None:
            patch[key] = entity_dict[key]

    return patch


def count_patch_fields(patch: dict[str, Any]) -> int:
    """Count the number of non-None fields in a patch.

    Args:
        patch: A dict patch (e.g. from extract_override_patch).

    Returns:
        Number of keys with non-None values.
    """
    if not isinstance(patch, dict):
        return 0
    return sum(1 for v in patch.values() if v is not None)
