"""Pure helpers for HD-2D controller operations.

Provides thin wrappers and compositions of existing HD-2D model functions
for use in controller methods. This module exists to:
1. Provide a single import point for controller HD-2D helpers
2. Compose multiple model functions into controller-friendly APIs
3. Keep controller methods thin

Import-safe and headless-safe.
"""

from __future__ import annotations

from typing import Any


def compute_clipboard_patch_from_entity(entity_dict: dict[str, Any]) -> dict[str, Any]:
    """Extract HD-2D override patch from an entity dict for clipboard storage.

    This is a thin wrapper around extract_override_patch for clarity.

    Args:
        entity_dict: The entity dict containing override fields.

    Returns:
        Dict of key -> value for non-None HD-2D overrides.
    """
    from engine.editor.hd2d_entity_overrides_model import extract_override_patch  # noqa: PLC0415

    return extract_override_patch(entity_dict)


def compute_next_batch_radius(current: int, delta: int) -> int:
    """Compute the next batch radius after nudging.

    Thin wrapper around nudge_batch_radius for clarity and consistency.

    Args:
        current: Current batch radius in pixels.
        delta: Amount to add (positive) or subtract (negative).

    Returns:
        New clamped batch radius.
    """
    from engine.editor.hd2d_batch_radius_model import nudge_batch_radius  # noqa: PLC0415

    return nudge_batch_radius(current, delta)


def get_batch_radius_default() -> int:
    """Get the default batch radius value.

    Returns:
        Default batch radius (96).
    """
    from engine.editor.hd2d_batch_radius_model import HD2D_BATCH_RADIUS_DEFAULT  # noqa: PLC0415

    return HD2D_BATCH_RADIUS_DEFAULT


def count_clipboard_patch_fields(patch: dict[str, Any]) -> int:
    """Count fields in a clipboard patch.

    Args:
        patch: The patch dict from compute_clipboard_patch_from_entity.

    Returns:
        Number of non-None override fields.
    """
    from engine.editor.hd2d_entity_overrides_model import count_patch_fields  # noqa: PLC0415

    return count_patch_fields(patch)


def format_batch_radius_display(radius: int) -> str:
    """Format batch radius for display in toasts/labels.

    Args:
        radius: The batch radius value.

    Returns:
        Formatted string like "Batch: 96px".
    """
    from engine.editor.hd2d_batch_radius_model import format_batch_radius_label  # noqa: PLC0415

    return format_batch_radius_label(radius)


def validate_clipboard_patch(patch: Any) -> bool:
    """Check if a patch is valid for pasting.

    Args:
        patch: The value to check.

    Returns:
        True if patch is a non-empty dict, False otherwise.
    """
    return isinstance(patch, dict) and len(patch) > 0
