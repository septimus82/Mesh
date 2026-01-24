"""Pure helper functions for component editing operations.

This module provides deterministic, side-effect-free functions for:
- Clamping and wrapping numeric values
- Applying inspector deltas with proper constraints
- Resetting fields to defaults

All functions are pure and do not mutate inputs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .components_model import (
    ComponentKind,
    COMPONENT_DEFAULTS,
    COLLIDER_RECT_DEFAULTS,
    COLLIDER_CIRCLE_DEFAULTS,
    COLLIDER_KIND_OPTIONS,
    get_component_dict,
    set_component_field,
    InspectorField,
)


# -----------------------------------------------------------------------------
# Clamp/Wrap Helpers
# -----------------------------------------------------------------------------

def clamp_float(x: float, lo: Optional[float] = None, hi: Optional[float] = None) -> float:
    """Clamp a float to [lo, hi] range.
    
    Args:
        x: Value to clamp
        lo: Minimum value (None = no minimum)
        hi: Maximum value (None = no maximum)
        
    Returns:
        Clamped value
    """
    if lo is not None and x < lo:
        return lo
    if hi is not None and x > hi:
        return hi
    return x


def clamp_int(x: int, lo: Optional[int] = None, hi: Optional[int] = None) -> int:
    """Clamp an int to [lo, hi] range.
    
    Args:
        x: Value to clamp
        lo: Minimum value (None = no minimum)
        hi: Maximum value (None = no maximum)
        
    Returns:
        Clamped value
    """
    if lo is not None and x < lo:
        return lo
    if hi is not None and x > hi:
        return hi
    return x


def clamp_rgba(rgba: List[int]) -> List[int]:
    """Clamp RGBA values to [0, 255].
    
    Args:
        rgba: List of [r, g, b, a] values
        
    Returns:
        New list with clamped values
    """
    result = list(rgba)  # Copy
    for i in range(min(4, len(result))):
        result[i] = max(0, min(255, int(result[i])))
    # Ensure we have 4 components
    while len(result) < 4:
        result.append(255)
    return result[:4]


def wrap_deg(x: float) -> float:
    """Wrap degrees to [0, 360) range.
    
    Args:
        x: Angle in degrees
        
    Returns:
        Wrapped angle in [0, 360)
    """
    x = x % 360.0
    if x < 0:
        x += 360.0
    return x


# -----------------------------------------------------------------------------
# Field Constraint Definitions
# -----------------------------------------------------------------------------

# Constraints per component kind and field key
# Format: (min_value, max_value, wraps)
FIELD_CONSTRAINTS: Dict[Tuple[ComponentKind, str], Tuple[Optional[float], Optional[float], bool]] = {
    # Transform
    ("transform", "x"): (None, None, False),  # Free float
    ("transform", "y"): (None, None, False),  # Free float
    ("transform", "rot"): (0.0, 360.0, True),  # Wraps [0, 360)
    
    # Light
    ("light", "radius_px"): (8.0, None, False),  # Min 8
    ("light", "flicker_amount"): (0.0, 1.0, False),  # [0, 1]
    ("light", "flicker_speed"): (0.0, None, False),  # >= 0
    ("light", "cookie_scale"): (0.0, None, False),  # >= 0
    ("light", "cookie_rotation_deg"): (0.0, 360.0, True),  # Wraps [0, 360)
    
    # Collider
    ("collider", "w"): (1.0, None, False),  # Min 1
    ("collider", "h"): (1.0, None, False),  # Min 1
    ("collider", "r"): (1.0, None, False),  # Min 1
}


def _get_field_constraints(
    kind: ComponentKind, field_key: str
) -> Tuple[Optional[float], Optional[float], bool]:
    """Get constraints for a field.
    
    Returns:
        (min_value, max_value, wraps)
    """
    return FIELD_CONSTRAINTS.get((kind, field_key), (None, None, False))


def _apply_constraints(
    value: float,
    kind: ComponentKind,
    field_key: str,
) -> float:
    """Apply constraints to a numeric value.
    
    Args:
        value: Input value
        kind: Component kind
        field_key: Field key
        
    Returns:
        Constrained value
    """
    lo, hi, wraps = _get_field_constraints(kind, field_key)
    
    if wraps:
        value = wrap_deg(value)
    else:
        value = clamp_float(value, lo, hi)
    
    return value


# -----------------------------------------------------------------------------
# Delta Application
# -----------------------------------------------------------------------------

def apply_inspector_delta(
    entity_json: Dict[str, Any],
    kind: ComponentKind,
    field_key: str,
    delta: float,
    shift: bool = False,
) -> Dict[str, Any]:
    """Apply a delta to a component field with proper constraints.
    
    - For bool fields: delta toggles the value
    - For enum fields: delta chooses next (+) or prev (-) option
    - For numeric fields: applies delta with shift multiplier and clamps
    
    Args:
        entity_json: Entity JSON data (not mutated)
        kind: Component kind
        field_key: Field key to modify
        delta: Delta to apply (or direction for bool/enum)
        shift: If True, use larger step (10x for numeric)
        
    Returns:
        New dict with field updated
    """
    comp_data = get_component_dict(entity_json, kind)
    if comp_data is None:
        return entity_json  # Component doesn't exist
    
    current_value = comp_data.get(field_key)
    
    # Handle bool fields
    if isinstance(current_value, bool):
        bool_value = not current_value
        return set_component_field(entity_json, kind, field_key, bool_value)
    
    # Handle enum fields (collider kind)
    if field_key == "kind" and kind == "collider":
        options = COLLIDER_KIND_OPTIONS
        try:
            current_idx = options.index(str(current_value))
        except ValueError:
            current_idx = 0
        
        if delta > 0:
            new_idx = (current_idx + 1) % len(options)
        else:
            new_idx = (current_idx - 1) % len(options)
        
        enum_value: str = options[new_idx]
        return set_component_field(entity_json, kind, field_key, enum_value)
    
    # Handle color fields
    if field_key == "color_rgba":
        # Color editing is complex; for now, just return unchanged
        # Could implement per-channel adjustment later
        return entity_json
    
    # Handle numeric fields
    try:
        current_float = float(current_value) if current_value is not None else 0.0
    except (TypeError, ValueError):
        return entity_json  # Can't convert to float
    
    # Apply shift multiplier
    actual_delta = delta * 10.0 if shift else delta
    
    numeric_value = current_float + actual_delta
    numeric_value = _apply_constraints(numeric_value, kind, field_key)
    
    return set_component_field(entity_json, kind, field_key, numeric_value)


def reset_field_to_default(
    entity_json: Dict[str, Any],
    kind: ComponentKind,
    field_key: str,
) -> Dict[str, Any]:
    """Reset a field to its default value.
    
    Args:
        entity_json: Entity JSON data (not mutated)
        kind: Component kind
        field_key: Field key to reset
        
    Returns:
        New dict with field reset to default
    """
    defaults = COMPONENT_DEFAULTS.get(kind, {})
    
    # Handle collider shape-specific defaults
    default_value: Any = None
    if kind == "collider":
        if field_key == "kind":
            default_value = "none"
        elif field_key in COLLIDER_RECT_DEFAULTS:
            default_value = COLLIDER_RECT_DEFAULTS.get(field_key)
        elif field_key in COLLIDER_CIRCLE_DEFAULTS:
            default_value = COLLIDER_CIRCLE_DEFAULTS.get(field_key)
        else:
            default_value = defaults.get(field_key)
    else:
        default_value = defaults.get(field_key)
    
    if default_value is None and field_key not in defaults:
        # Unknown field, return unchanged
        return entity_json
    
    return set_component_field(entity_json, kind, field_key, default_value)


def get_step_for_field(kind: ComponentKind, field_key: str) -> float:
    """Get the step size for a field.
    
    Args:
        kind: Component kind
        field_key: Field key
        
    Returns:
        Step size for the field
    """
    # Define step sizes per field
    STEP_SIZES: Dict[Tuple[ComponentKind, str], float] = {
        ("transform", "x"): 1.0,
        ("transform", "y"): 1.0,
        ("transform", "rot"): 5.0,
        ("light", "radius_px"): 4.0,
        ("light", "flicker_amount"): 0.05,
        ("light", "flicker_speed"): 0.25,
        ("light", "cookie_scale"): 0.1,
        ("light", "cookie_rotation_deg"): 5.0,
        ("collider", "w"): 1.0,
        ("collider", "h"): 1.0,
        ("collider", "r"): 1.0,
    }
    return STEP_SIZES.get((kind, field_key), 1.0)


def cycle_enum_value(
    current: str,
    options: Tuple[str, ...],
    direction: int,
) -> str:
    """Cycle through enum options.
    
    Args:
        current: Current value
        options: Available options
        direction: +1 for next, -1 for prev
        
    Returns:
        New value
    """
    try:
        idx = options.index(current)
    except ValueError:
        idx = 0
    
    new_idx = (idx + direction) % len(options)
    return options[new_idx]
