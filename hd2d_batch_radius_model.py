"""Pure model for HD-2D batch radius settings.

Provides pure functions for:
- Clamping batch radius to valid bounds
- Nudging batch radius deterministically
- Formatting batch radius labels
"""

from __future__ import annotations


# =============================================================================
# Constants
# =============================================================================

HD2D_BATCH_RADIUS_DEFAULT: int = 96
HD2D_BATCH_RADIUS_MIN: int = 16
HD2D_BATCH_RADIUS_MAX: int = 512
HD2D_BATCH_RADIUS_STEP: int = 16


# =============================================================================
# Pure Functions
# =============================================================================


def clamp_batch_radius(value: int | float) -> int:
    """Clamp batch radius to valid bounds.

    Args:
        value: The radius value to clamp.

    Returns:
        Clamped integer radius between HD2D_BATCH_RADIUS_MIN and HD2D_BATCH_RADIUS_MAX.
    """
    try:
        int_value = int(value)
    except (TypeError, ValueError):
        return HD2D_BATCH_RADIUS_DEFAULT

    return max(HD2D_BATCH_RADIUS_MIN, min(HD2D_BATCH_RADIUS_MAX, int_value))


def nudge_batch_radius(current: int, delta: int) -> int:
    """Nudge batch radius by delta, clamping to valid bounds.

    Args:
        current: Current radius value.
        delta: Amount to add (positive) or subtract (negative).

    Returns:
        New clamped radius value.
    """
    try:
        current_int = int(current)
        delta_int = int(delta)
    except (TypeError, ValueError):
        return HD2D_BATCH_RADIUS_DEFAULT

    return clamp_batch_radius(current_int + delta_int)


def format_batch_radius_label(radius: int) -> str:
    """Format batch radius as a display label.

    Args:
        radius: The radius value.

    Returns:
        Formatted string like "Batch: 96px" or "Batch: 112px".
    """
    try:
        int_radius = int(radius)
    except (TypeError, ValueError):
        int_radius = HD2D_BATCH_RADIUS_DEFAULT

    return f"Batch: {int_radius}px"
