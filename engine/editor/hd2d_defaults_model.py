"""Pure model for HD-2D defaults feature.

Provides functions to:
- Check if a default preset is configured
- Determine if auto-apply should run (scene lacks HD2D keys)
- Compute a safe merge patch (fills missing keys only)
- Apply upgrade patch for explicit upgrade action
"""

from __future__ import annotations

import copy
from typing import Any

from engine.editor.hd2d_look_presets_model import get_hd2d_preset_name, get_hd2d_preset_patch


# All keys that HD2D presets can set
HD2D_SETTING_KEYS: frozenset[str] = frozenset({
    "depth_tint_enabled",
    "depth_tint_strength",
    "depth_tint_near_color",
    "depth_tint_far_color",
    "shadows_enabled",
    "shadows_contact_enabled",
    "shadows_ao_enabled",
    "outline_enabled",
    "outline_strength",
    "outline_radius_px",
    "outline_color_rgba",
})


def is_valid_default_preset_id(preset_id: str | None) -> bool:
    """Check if a preset ID is a valid default (non-null, known preset).

    Args:
        preset_id: The preset ID to validate.

    Returns:
        True if valid preset ID that can be used as default.
    """
    if not preset_id or not isinstance(preset_id, str):
        return False
    return get_hd2d_preset_name(preset_id) is not None


def scene_has_hd2d_keys(scene_payload: dict[str, Any]) -> bool:
    """Check if scene payload already has any HD2D setting keys.

    Args:
        scene_payload: The scene payload dict.

    Returns:
        True if at least one HD2D key exists in settings.
    """
    if not isinstance(scene_payload, dict):
        return False
    settings = scene_payload.get("settings")
    if not isinstance(settings, dict):
        return False
    return any(key in settings for key in HD2D_SETTING_KEYS)


def should_auto_apply_default(
    scene_payload: dict[str, Any],
    default_preset_id: str | None,
) -> bool:
    """Determine if HD2D defaults should be auto-applied to this scene.

    Auto-apply runs when:
    1. A valid default preset is configured
    2. Scene does NOT already have any HD2D keys

    Args:
        scene_payload: The scene payload dict.
        default_preset_id: The configured default preset ID (or None).

    Returns:
        True if auto-apply should run.
    """
    if not is_valid_default_preset_id(default_preset_id):
        return False
    return not scene_has_hd2d_keys(scene_payload)


def compute_safe_merge_patch(
    scene_payload: dict[str, Any],
    preset_id: str,
) -> dict[str, Any]:
    """Compute a patch that only fills missing HD2D keys.

    Existing keys are NOT overwritten. Only keys that don't exist
    in the scene's settings will be added from the preset.

    Args:
        scene_payload: The scene payload dict.
        preset_id: The preset ID to use.

    Returns:
        A dict of settings to merge (only missing keys).
        Empty dict if preset invalid or no missing keys.
    """
    preset_patch = get_hd2d_preset_patch(preset_id)
    if preset_patch is None:
        return {}

    settings = scene_payload.get("settings") if isinstance(scene_payload, dict) else None
    if not isinstance(settings, dict):
        settings = {}

    # Only include keys that don't exist in current settings
    return {k: v for k, v in preset_patch.items() if k not in settings}


def apply_safe_merge(
    scene_payload: dict[str, Any],
    preset_id: str,
) -> dict[str, Any]:
    """Apply a preset using safe merge (fill missing keys only).

    Does NOT mutate the input. Returns a new scene payload.

    Args:
        scene_payload: The scene payload dict.
        preset_id: The preset ID to use.

    Returns:
        New scene payload with missing HD2D keys filled.
    """
    merge_patch = compute_safe_merge_patch(scene_payload, preset_id)
    if not merge_patch:
        return copy.deepcopy(scene_payload)

    result = copy.deepcopy(scene_payload)
    settings = result.get("settings")
    if not isinstance(settings, dict):
        settings = {}
    settings = dict(settings)
    settings.update(merge_patch)
    result["settings"] = settings
    return result


def format_upgrade_undo_label(preset_id: str) -> str:
    """Format the undo label for an upgrade action.

    Args:
        preset_id: The preset ID used.

    Returns:
        Label like "Upgrade Scene · HD2D Defaults (Soft)"
    """
    preset_name = get_hd2d_preset_name(preset_id)
    if preset_name is None:
        preset_name = preset_id.capitalize()
    return f"Upgrade Scene · HD2D Defaults ({preset_name})"
