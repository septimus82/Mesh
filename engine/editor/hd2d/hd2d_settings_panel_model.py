"""Pure model for HD-2D settings panel.

Provides functions to:
- Parse HD-2D settings from scene payload with defaults
- Sanitize/clamp setting patches
- Apply setting patches immutably
- Format undo labels for setting changes
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

# =============================================================================
# Default Values
# =============================================================================

HD2D_DEFAULTS: dict[str, Any] = {
    # Shadows
    "shadows_enabled": True,
    "shadows_contact_enabled": True,
    "shadows_ao_enabled": False,
    # Depth tint
    "depth_tint_enabled": False,
    "depth_tint_strength": 0.3,
    "depth_tint_near_color": [255, 255, 255, 255],
    "depth_tint_far_color": [200, 200, 220, 255],
    # Outline
    "outline_enabled": False,
    "outline_strength": 0.5,
    "outline_radius_px": 1,
    "outline_color_rgba": [0, 0, 0, 100],
}

# Keys that are boolean toggles
BOOL_KEYS: frozenset[str] = frozenset({
    "shadows_enabled",
    "shadows_contact_enabled",
    "shadows_ao_enabled",
    "depth_tint_enabled",
    "outline_enabled",
})

# Keys that are floats clamped to [0, 1]
STRENGTH_KEYS: frozenset[str] = frozenset({
    "depth_tint_strength",
    "outline_strength",
})

# Keys that are non-negative integers
INT_KEYS: frozenset[str] = frozenset({
    "outline_radius_px",
})

# Keys that are RGBA color arrays
COLOR_KEYS: frozenset[str] = frozenset({
    "depth_tint_near_color",
    "depth_tint_far_color",
    "outline_color_rgba",
})


# =============================================================================
# Data Classes
# =============================================================================


@dataclass(frozen=True, slots=True)
class Hd2dSettings:
    """Parsed HD-2D settings with all values."""

    # Shadows
    shadows_enabled: bool
    shadows_contact_enabled: bool
    shadows_ao_enabled: bool
    # Depth tint
    depth_tint_enabled: bool
    depth_tint_strength: float
    depth_tint_near_color: tuple[int, int, int, int]
    depth_tint_far_color: tuple[int, int, int, int]
    # Outline
    outline_enabled: bool
    outline_strength: float
    outline_radius_px: int
    outline_color_rgba: tuple[int, int, int, int]


# =============================================================================
# Parse Functions
# =============================================================================


def _coerce_rgba(value: Any, default: list[int]) -> tuple[int, int, int, int]:
    """Coerce a value to an RGBA tuple."""
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return (default[0], default[1], default[2], default[3])
    try:
        r = max(0, min(255, int(value[0])))
        g = max(0, min(255, int(value[1])))
        b = max(0, min(255, int(value[2])))
        a = max(0, min(255, int(value[3])))
        return (r, g, b, a)
    except (TypeError, ValueError):
        return (default[0], default[1], default[2], default[3])


def parse_hd2d_scene_settings(scene_payload: dict[str, Any]) -> Hd2dSettings:
    """Parse HD-2D settings from a scene payload.

    Extracts settings from scene_payload["settings"] with defaults
    for any missing values.

    Args:
        scene_payload: The scene payload dict.

    Returns:
        Hd2dSettings dataclass with all values.
    """
    if not isinstance(scene_payload, dict):
        settings: dict[str, Any] = {}
    else:
        settings = scene_payload.get("settings", {})
        if not isinstance(settings, dict):
            settings = {}

    def _bool(key: str) -> bool:
        val = settings.get(key, HD2D_DEFAULTS.get(key, False))
        return bool(val)

    def _float_clamped(key: str, min_val: float = 0.0, max_val: float = 1.0) -> float:
        val = settings.get(key, HD2D_DEFAULTS.get(key, 0.0))
        try:
            f = float(val)
        except (TypeError, ValueError):
            f = float(HD2D_DEFAULTS.get(key, 0.0))
        return max(min_val, min(max_val, f))

    def _int_clamped(key: str, min_val: int = 0) -> int:
        val = settings.get(key, HD2D_DEFAULTS.get(key, 0))
        try:
            i = int(val)
        except (TypeError, ValueError):
            i = int(HD2D_DEFAULTS.get(key, 0))
        return max(min_val, i)

    def _rgba(key: str) -> tuple[int, int, int, int]:
        default = HD2D_DEFAULTS.get(key, [0, 0, 0, 255])
        val = settings.get(key, default)
        return _coerce_rgba(val, default)

    return Hd2dSettings(
        shadows_enabled=_bool("shadows_enabled"),
        shadows_contact_enabled=_bool("shadows_contact_enabled"),
        shadows_ao_enabled=_bool("shadows_ao_enabled"),
        depth_tint_enabled=_bool("depth_tint_enabled"),
        depth_tint_strength=_float_clamped("depth_tint_strength", 0.0, 1.0),
        depth_tint_near_color=_rgba("depth_tint_near_color"),
        depth_tint_far_color=_rgba("depth_tint_far_color"),
        outline_enabled=_bool("outline_enabled"),
        outline_strength=_float_clamped("outline_strength", 0.0, 1.0),
        outline_radius_px=_int_clamped("outline_radius_px", 0),
        outline_color_rgba=_rgba("outline_color_rgba"),
    )


def parse_hd2d_scene_settings_dict(scene_payload: dict[str, Any]) -> dict[str, Any]:
    """Parse HD-2D settings from a scene payload as a dict.

    Same as parse_hd2d_scene_settings but returns a plain dict
    for easier provider use.

    Args:
        scene_payload: The scene payload dict.

    Returns:
        Dict with all HD-2D settings.
    """
    parsed = parse_hd2d_scene_settings(scene_payload)
    return {
        "shadows_enabled": parsed.shadows_enabled,
        "shadows_contact_enabled": parsed.shadows_contact_enabled,
        "shadows_ao_enabled": parsed.shadows_ao_enabled,
        "depth_tint_enabled": parsed.depth_tint_enabled,
        "depth_tint_strength": parsed.depth_tint_strength,
        "depth_tint_near_color": list(parsed.depth_tint_near_color),
        "depth_tint_far_color": list(parsed.depth_tint_far_color),
        "outline_enabled": parsed.outline_enabled,
        "outline_strength": parsed.outline_strength,
        "outline_radius_px": parsed.outline_radius_px,
        "outline_color_rgba": list(parsed.outline_color_rgba),
    }


# =============================================================================
# Sanitize Functions
# =============================================================================


def sanitize_hd2d_setting_value(key: str, value: Any) -> Any:
    """Sanitize a single HD-2D setting value.

    Args:
        key: The setting key.
        value: The value to sanitize.

    Returns:
        Sanitized value with correct type and clamping.
    """
    if key in BOOL_KEYS:
        return bool(value)

    if key in STRENGTH_KEYS:
        try:
            f = float(value)
        except (TypeError, ValueError):
            return HD2D_DEFAULTS.get(key, 0.0)
        return max(0.0, min(1.0, f))

    if key in INT_KEYS:
        try:
            i = int(value)
        except (TypeError, ValueError):
            return HD2D_DEFAULTS.get(key, 0)
        return max(0, i)

    if key in COLOR_KEYS:
        default = HD2D_DEFAULTS.get(key, [0, 0, 0, 255])
        return list(_coerce_rgba(value, default))

    # Unknown key - return as-is
    return value


def sanitize_hd2d_setting_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """Sanitize a patch of HD-2D settings.

    Clamps values and ensures correct types.

    Args:
        patch: Dict of setting key -> value to sanitize.

    Returns:
        New dict with sanitized values.
    """
    if not isinstance(patch, dict):
        return {}

    result: dict[str, Any] = {}
    for key, value in patch.items():
        if not isinstance(key, str):
            continue
        result[key] = sanitize_hd2d_setting_value(key, value)

    return result


# =============================================================================
# Apply Functions
# =============================================================================


def apply_hd2d_setting_patch(
    scene_payload: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Apply a sanitized patch to scene settings.

    Does NOT mutate the input. Returns a new scene payload.

    Args:
        scene_payload: The scene payload dict.
        patch: Dict of setting key -> value to apply.

    Returns:
        New scene payload with patched settings.
    """
    sanitized_patch = sanitize_hd2d_setting_patch(patch)
    if not sanitized_patch:
        return copy.deepcopy(scene_payload)

    result = copy.deepcopy(scene_payload) if isinstance(scene_payload, dict) else {}
    settings = result.get("settings")
    if not isinstance(settings, dict):
        settings = {}
    settings = dict(settings)
    settings.update(sanitized_patch)
    result["settings"] = settings
    return result


# =============================================================================
# Undo Label Formatting
# =============================================================================


def format_hd2d_setting_change_label(
    key: str,
    old_value: Any,
    new_value: Any,
) -> str:
    """Format an undo label for a single setting change.

    Args:
        key: The setting key.
        old_value: The old value.
        new_value: The new value.

    Returns:
        Label like "Set HD2D Tint Strength · 0.35 → 0.50"
    """
    # Map keys to friendly names
    friendly_names = {
        "shadows_enabled": "Shadows",
        "shadows_contact_enabled": "Contact Shadows",
        "shadows_ao_enabled": "AO Shadows",
        "depth_tint_enabled": "Depth Tint",
        "depth_tint_strength": "Tint Strength",
        "outline_enabled": "Outline",
        "outline_strength": "Outline Strength",
        "outline_radius_px": "Outline Radius",
    }

    name = friendly_names.get(key, key.replace("_", " ").title())

    if key in BOOL_KEYS:
        action = "Enable" if new_value else "Disable"
        return f"{action} HD2D {name}"

    if key in STRENGTH_KEYS:
        old_str = f"{float(old_value):.2f}" if isinstance(old_value, (int, float)) else str(old_value)
        new_str = f"{float(new_value):.2f}" if isinstance(new_value, (int, float)) else str(new_value)
        return f"Set HD2D {name} · {old_str} → {new_str}"

    if key in INT_KEYS:
        return f"Set HD2D {name} · {old_value} → {new_value}"

    return f"Set HD2D {name}"


def format_hd2d_toggle_label(key: str, new_value: bool) -> str:
    """Format an undo label for a toggle change.

    Args:
        key: The setting key.
        new_value: The new boolean value.

    Returns:
        Label like "Enable HD2D Shadows" or "Disable HD2D Outline"
    """
    friendly_names = {
        "shadows_enabled": "Shadows",
        "shadows_contact_enabled": "Contact Shadows",
        "shadows_ao_enabled": "AO Shadows",
        "depth_tint_enabled": "Depth Tint",
        "outline_enabled": "Outline",
    }

    name = friendly_names.get(key, key.replace("_", " ").title())
    action = "Enable" if new_value else "Disable"
    return f"{action} HD2D {name}"


# =============================================================================
# Inspector Rows
# =============================================================================


@dataclass(frozen=True, slots=True)
class Hd2dSettingRow:
    """A row in the HD-2D settings panel."""

    key: str
    label: str
    value: Any
    value_type: str  # "bool", "float", "int"
    editable: bool = True
    min_value: float | int | None = None
    max_value: float | int | None = None
    step: float | int | None = None


def build_hd2d_settings_rows(settings: Hd2dSettings) -> list[Hd2dSettingRow]:
    """Build rows for the HD-2D settings panel.

    Args:
        settings: Parsed HD-2D settings.

    Returns:
        List of rows for display.
    """
    return [
        # Shadows section
        Hd2dSettingRow("shadows_enabled", "Shadows", settings.shadows_enabled, "bool"),
        Hd2dSettingRow("shadows_contact_enabled", "Contact", settings.shadows_contact_enabled, "bool"),
        Hd2dSettingRow("shadows_ao_enabled", "AO", settings.shadows_ao_enabled, "bool"),
        # Tint section
        Hd2dSettingRow("depth_tint_enabled", "Tint", settings.depth_tint_enabled, "bool"),
        Hd2dSettingRow(
            "depth_tint_strength", "Strength", settings.depth_tint_strength, "float",
            min_value=0.0, max_value=1.0, step=0.05
        ),
        # Outline section
        Hd2dSettingRow("outline_enabled", "Outline", settings.outline_enabled, "bool"),
        Hd2dSettingRow(
            "outline_strength", "Strength", settings.outline_strength, "float",
            min_value=0.0, max_value=1.0, step=0.05
        ),
        Hd2dSettingRow(
            "outline_radius_px", "Radius", settings.outline_radius_px, "int",
            min_value=0, max_value=8, step=1
        ),
    ]


# =============================================================================
# Preset Detection
# =============================================================================


def detect_active_preset(settings: Hd2dSettings) -> str | None:
    """Detect if current settings match a known preset.

    Args:
        settings: Current HD-2D settings.

    Returns:
        Preset ID ("soft", "crisp", "noir", "dreamy") if exact match, else None.
    """
    from .hd2d_look_presets_model import get_hd2d_preset_patch, list_hd2d_presets  # noqa: PLC0415

    settings_dict = {
        "shadows_enabled": settings.shadows_enabled,
        "shadows_contact_enabled": settings.shadows_contact_enabled,
        "shadows_ao_enabled": settings.shadows_ao_enabled,
        "depth_tint_enabled": settings.depth_tint_enabled,
        "depth_tint_strength": settings.depth_tint_strength,
        "depth_tint_near_color": list(settings.depth_tint_near_color),
        "depth_tint_far_color": list(settings.depth_tint_far_color),
        "outline_enabled": settings.outline_enabled,
        "outline_strength": settings.outline_strength,
        "outline_radius_px": settings.outline_radius_px,
        "outline_color_rgba": list(settings.outline_color_rgba),
    }

    for preset in list_hd2d_presets():
        patch = get_hd2d_preset_patch(preset.id)
        if patch is None:
            continue
        # Check if all preset keys match current settings
        match = True
        for k, v in patch.items():
            if k not in settings_dict:
                continue
            current = settings_dict.get(k)
            if current != v:
                match = False
                break
        if match:
            return preset.id

    return None
