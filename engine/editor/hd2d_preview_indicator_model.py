"""Pure model for HD-2D preview indicator text formatting.

This module provides a pure function to format the indicator text
shown when an HD-2D look preset preview is active.

Format: "HD2D Preview: <PresetName> (Esc cancel, Enter apply)"
"""

from __future__ import annotations


def format_hd2d_preview_indicator_text(preset_id: str | None) -> str:
    """Format the indicator text for an active HD-2D preset preview.

    Args:
        preset_id: The preset ID being previewed (e.g., "soft", "crisp").
                   If None or empty, returns empty string (no indicator).

    Returns:
        Formatted indicator text, or empty string if no preview active.

    Example:
        >>> format_hd2d_preview_indicator_text("soft")
        'HD2D Preview: Soft (Esc cancel, Enter apply)'
        >>> format_hd2d_preview_indicator_text(None)
        ''
    """
    if not preset_id or not isinstance(preset_id, str):
        return ""

    preset_id = preset_id.strip()
    if not preset_id:
        return ""

    # Capitalize first letter for display
    display_name = preset_id.capitalize()

    return f"HD2D Preview: {display_name} (Esc cancel, Enter apply)"
