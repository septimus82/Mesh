"""Pure model for HD-2D preset preview.

Provides deterministic, headless-safe helpers for temporarily previewing
HD-2D look presets without pushing undo history or marking dirty.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from engine.editor.hd2d_look_presets_model import get_hd2d_preset_patch


# Keys that HD-2D presets touch - used to snapshot only what's needed
HD2D_PRESET_KEYS: frozenset[str] = frozenset([
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
])


@dataclass(frozen=True, slots=True)
class PreviewSnapshot:
    """Immutable snapshot of original scene settings for preview revert."""

    original_settings: dict[str, Any]
    preset_id: str


def begin_preset_preview(
    scene_payload: dict[str, Any],
    preset_id: str,
) -> tuple[dict[str, Any], PreviewSnapshot]:
    """Begin a preview by applying a preset and returning a snapshot for revert.

    Args:
        scene_payload: Current scene data dict.
        preset_id: ID of the preset to preview (e.g., "soft", "crisp").

    Returns:
        Tuple of (preview_payload, snapshot_token) where:
        - preview_payload has the preset applied (copy, not mutated original)
        - snapshot_token contains original settings for later revert
    """
    patch = get_hd2d_preset_patch(preset_id)
    if patch is None:
        # Unknown preset - return unchanged copy
        snapshot = PreviewSnapshot(original_settings={}, preset_id=preset_id)
        return copy.deepcopy(scene_payload), snapshot

    # Extract only the keys that presets touch
    settings = scene_payload.get("settings")
    if not isinstance(settings, dict):
        settings = {}

    original_settings: dict[str, Any] = {}
    for key in HD2D_PRESET_KEYS:
        if key in settings:
            original_settings[key] = copy.deepcopy(settings[key])

    snapshot = PreviewSnapshot(original_settings=original_settings, preset_id=preset_id)

    # Apply preview
    preview_payload = copy.deepcopy(scene_payload)
    preview_settings = preview_payload.get("settings")
    if not isinstance(preview_settings, dict):
        preview_settings = {}
    preview_settings = dict(preview_settings)
    preview_settings.update(patch)
    preview_payload["settings"] = preview_settings

    return preview_payload, snapshot


def update_preset_preview(
    scene_payload: dict[str, Any],
    preset_id: str,
    snapshot: PreviewSnapshot,
) -> dict[str, Any]:
    """Update preview to a different preset while keeping the original snapshot.

    First reverts to original, then applies new preset.

    Args:
        scene_payload: Current (possibly previewed) scene data.
        preset_id: New preset ID to preview.
        snapshot: Original snapshot from begin_preset_preview.

    Returns:
        New preview payload with the new preset applied.
    """
    # Revert first
    reverted = end_preset_preview(scene_payload, snapshot)

    # Apply new preset
    patch = get_hd2d_preset_patch(preset_id)
    if patch is None:
        return reverted

    preview_payload = copy.deepcopy(reverted)
    settings = preview_payload.get("settings")
    if not isinstance(settings, dict):
        settings = {}
    settings = dict(settings)
    settings.update(patch)
    preview_payload["settings"] = settings

    return preview_payload


def end_preset_preview(
    scene_payload: dict[str, Any],
    snapshot: PreviewSnapshot,
) -> dict[str, Any]:
    """End preview by restoring original settings from snapshot.

    Args:
        scene_payload: Current (previewed) scene data.
        snapshot: Snapshot from begin_preset_preview.

    Returns:
        Restored payload with original settings.
    """
    restored = copy.deepcopy(scene_payload)
    settings = restored.get("settings")
    if not isinstance(settings, dict):
        settings = {}
    settings = dict(settings)

    # Remove any HD2D keys that weren't in the original
    for key in HD2D_PRESET_KEYS:
        if key not in snapshot.original_settings:
            settings.pop(key, None)

    # Restore original values
    settings.update(snapshot.original_settings)
    restored["settings"] = settings

    return restored


def is_hd2d_preset_command(command_id: str) -> bool:
    """Check if a command ID is an HD-2D preset apply command.

    Args:
        command_id: The command/action ID to check.

    Returns:
        True if this is an HD-2D preset command.
    """
    return str(command_id or "").startswith("editor.hd2d.preset.") and command_id.endswith(".apply")


def extract_preset_id_from_command(command_id: str) -> str | None:
    """Extract the preset ID from an HD-2D preset command ID.

    Args:
        command_id: e.g., "editor.hd2d.preset.soft.apply"

    Returns:
        The preset ID (e.g., "soft") or None if not a valid preset command.
    """
    if not is_hd2d_preset_command(command_id):
        return None
    # "editor.hd2d.preset.soft.apply" -> ["editor", "hd2d", "preset", "soft", "apply"]
    parts = str(command_id).split(".")
    if len(parts) != 5:
        return None
    return parts[3]
