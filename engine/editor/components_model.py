"""Pure dataclasses and functions for Component Inspector v1.

This module provides deterministic, side-effect-free functions for:
- Mapping entity JSON to inspector component sections
- Managing component defaults and back-compatibility with legacy flat fields
- CRUD operations on components (add, remove, set field)

All functions are pure and do not mutate inputs.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Tuple

# -----------------------------------------------------------------------------
# Type Definitions
# -----------------------------------------------------------------------------

ComponentKind = Literal["transform", "sprite", "light", "collider"]

COMPONENT_KINDS: Tuple[ComponentKind, ...] = ("transform", "sprite", "light", "collider")

# Ordering for stable component display
COMPONENT_ORDER: Tuple[ComponentKind, ...] = ("transform", "sprite", "light", "collider")

# Component titles for display
COMPONENT_TITLES: Dict[ComponentKind, str] = {
    "transform": "Transform",
    "sprite": "SpriteRenderer",
    "light": "LightSource",
    "collider": "Collider",
}


# -----------------------------------------------------------------------------
# Default Values
# -----------------------------------------------------------------------------

TRANSFORM_DEFAULTS: Dict[str, Any] = {
    "x": 0.0,
    "y": 0.0,
    "rot": 0.0,
}

SPRITE_DEFAULTS: Dict[str, Any] = {
    "asset": "",
}

LIGHT_DEFAULTS: Dict[str, Any] = {
    "radius_px": 160.0,
    "color_rgba": [255, 255, 255, 255],
    "flicker_enabled": False,
    "flicker_amount": 0.25,
    "flicker_speed": 1.0,
    "cookie_id": None,
    "cookie_scale": 1.0,
    "cookie_rotation_deg": 0.0,
}

COLLIDER_DEFAULTS: Dict[str, Any] = {
    "kind": "none",
    # rect defaults (only if kind == "rect"): w=16, h=16
    # circle default (only if kind == "circle"): r=8
}

COLLIDER_RECT_DEFAULTS: Dict[str, Any] = {
    "w": 16.0,
    "h": 16.0,
}

COLLIDER_CIRCLE_DEFAULTS: Dict[str, Any] = {
    "r": 8.0,
}

COMPONENT_DEFAULTS: Dict[ComponentKind, Dict[str, Any]] = {
    "transform": TRANSFORM_DEFAULTS,
    "sprite": SPRITE_DEFAULTS,
    "light": LIGHT_DEFAULTS,
    "collider": COLLIDER_DEFAULTS,
}

# Collider kind options
COLLIDER_KIND_OPTIONS: Tuple[str, ...] = ("none", "rect", "circle")


# -----------------------------------------------------------------------------
# Dataclasses
# -----------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class InspectorField:
    """A single editable field in a component section."""
    key: str
    label: str
    kind: Literal["float", "int", "bool", "color", "asset", "enum", "string"]
    value: object
    editable: bool = True
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step: Optional[float] = None
    options: Tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class InspectorComponent:
    """A component section with its fields."""
    kind: ComponentKind
    title: str
    fields: Tuple[InspectorField, ...]
    removable: bool


# -----------------------------------------------------------------------------
# Legacy Field Mapping (Back-Compat)
# -----------------------------------------------------------------------------

# Maps legacy top-level entity keys to (component_kind, field_key)
LEGACY_FIELD_MAP: Dict[str, Tuple[ComponentKind, str]] = {
    "x": ("transform", "x"),
    "y": ("transform", "y"),
    "rotation": ("transform", "rot"),
    "rotation_deg": ("transform", "rot"),
    "sprite": ("sprite", "asset"),
    "asset": ("sprite", "asset"),
}


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def _deep_copy(d: Dict[str, Any]) -> Dict[str, Any]:
    """Create a deep copy of a dictionary."""
    return copy.deepcopy(d)


def _get_components_container(entity_json: Dict[str, Any]) -> Dict[str, Any]:
    """Get or create the components container from entity JSON."""
    result = entity_json.get("components", {})
    return result if isinstance(result, dict) else {}


def _has_component(entity_json: Dict[str, Any], kind: ComponentKind) -> bool:
    """Check if entity has a specific component."""
    components = _get_components_container(entity_json)
    if kind in components:
        return True

    # Check legacy fields for back-compat
    if kind == "transform":
        # Transform is always present (implicit)
        return True
    if kind == "sprite":
        return "sprite" in entity_json or "asset" in entity_json
    if kind == "light":
        # Check behaviour_config.LightSource or behaviours list
        bc = entity_json.get("behaviour_config", {})
        if "LightSource" in bc:
            return True
        behaviours = entity_json.get("behaviours", [])
        for b in behaviours:
            if b == "LightSource" or (isinstance(b, dict) and b.get("type") == "LightSource"):
                return True
        return False
    if kind == "collider":
        return "collider" in components or "collision" in entity_json

    return False


def _read_legacy_transform(entity_json: Dict[str, Any], sprite_runtime: object | None) -> Dict[str, Any]:
    """Read transform values from legacy top-level fields or runtime sprite."""
    result: Dict[str, Any] = dict(TRANSFORM_DEFAULTS)

    # From entity JSON
    if "x" in entity_json:
        result["x"] = float(entity_json.get("x", 0.0))
    elif sprite_runtime and hasattr(sprite_runtime, "center_x"):
        result["x"] = float(getattr(sprite_runtime, "center_x", 0.0))

    if "y" in entity_json:
        result["y"] = float(entity_json.get("y", 0.0))
    elif sprite_runtime and hasattr(sprite_runtime, "center_y"):
        result["y"] = float(getattr(sprite_runtime, "center_y", 0.0))

    if "rotation" in entity_json:
        result["rot"] = float(entity_json.get("rotation", 0.0))
    elif "rotation_deg" in entity_json:
        result["rot"] = float(entity_json.get("rotation_deg", 0.0))
    elif sprite_runtime and hasattr(sprite_runtime, "angle"):
        result["rot"] = float(getattr(sprite_runtime, "angle", 0.0))

    return result


def _read_legacy_sprite(entity_json: Dict[str, Any]) -> Dict[str, Any]:
    """Read sprite values from legacy top-level fields."""
    result: Dict[str, Any] = dict(SPRITE_DEFAULTS)
    if "sprite" in entity_json:
        result["asset"] = str(entity_json.get("sprite", ""))
    elif "asset" in entity_json:
        result["asset"] = str(entity_json.get("asset", ""))
    return result


def _read_legacy_light(entity_json: Dict[str, Any]) -> Dict[str, Any]:
    """Read light values from behaviour_config.LightSource."""
    result: Dict[str, Any] = dict(LIGHT_DEFAULTS)
    bc = entity_json.get("behaviour_config", {})
    ls = bc.get("LightSource", {})

    if "radius" in ls:
        result["radius_px"] = float(ls.get("radius", 160.0))
    if "color" in ls:
        # Convert hex color to RGBA
        color_hex = ls.get("color", "#ffffff")
        result["color_rgba"] = _hex_to_rgba(color_hex)
    if "enabled" in ls:
        result["flicker_enabled"] = not ls.get("enabled", True)  # Inverted logic
    if "flicker_amount" in ls:
        result["flicker_amount"] = float(ls.get("flicker_amount", 0.25))
    if "flicker_speed" in ls:
        result["flicker_speed"] = float(ls.get("flicker_speed", 1.0))
    if "cookie" in ls or "cookie_id" in ls:
        result["cookie_id"] = ls.get("cookie") or ls.get("cookie_id")
    if "cookie_scale" in ls:
        result["cookie_scale"] = float(ls.get("cookie_scale", 1.0))
    if "cookie_rotation" in ls or "cookie_rotation_deg" in ls:
        result["cookie_rotation_deg"] = float(ls.get("cookie_rotation") or ls.get("cookie_rotation_deg", 0.0))

    return result


def _hex_to_rgba(hex_color: str) -> List[int]:
    """Convert hex color string to RGBA list."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 6:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return [r, g, b, 255]
    if len(hex_color) == 8:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        a = int(hex_color[6:8], 16)
        return [r, g, b, a]
    return [255, 255, 255, 255]


def _rgba_to_hex(rgba: List[int]) -> str:
    """Convert RGBA list to hex color string."""
    if len(rgba) >= 4:
        return f"#{rgba[0]:02x}{rgba[1]:02x}{rgba[2]:02x}{rgba[3]:02x}"
    if len(rgba) >= 3:
        return f"#{rgba[0]:02x}{rgba[1]:02x}{rgba[2]:02x}"
    return "#ffffff"


# -----------------------------------------------------------------------------
# Field Definitions
# -----------------------------------------------------------------------------

def _build_transform_fields(data: Dict[str, Any]) -> Tuple[InspectorField, ...]:
    """Build transform component fields."""
    return (
        InspectorField(
            key="x", label="X", kind="float", value=data.get("x", 0.0),
            editable=True, step=1.0
        ),
        InspectorField(
            key="y", label="Y", kind="float", value=data.get("y", 0.0),
            editable=True, step=1.0
        ),
        InspectorField(
            key="rot", label="Rotation", kind="float", value=data.get("rot", 0.0),
            editable=True, min_value=0.0, max_value=360.0, step=5.0
        ),
    )


def _build_sprite_fields(data: Dict[str, Any]) -> Tuple[InspectorField, ...]:
    """Build sprite component fields."""
    return (
        InspectorField(
            key="asset", label="Asset", kind="asset", value=data.get("asset", ""),
            editable=True
        ),
    )


def _build_light_fields(data: Dict[str, Any]) -> Tuple[InspectorField, ...]:
    """Build light component fields."""
    return (
        InspectorField(
            key="radius_px", label="Radius", kind="float", value=data.get("radius_px", 160.0),
            editable=True, min_value=8.0, step=4.0
        ),
        InspectorField(
            key="color_rgba", label="Color", kind="color", value=data.get("color_rgba", [255, 255, 255, 255]),
            editable=True
        ),
        InspectorField(
            key="flicker_enabled", label="Flicker", kind="bool", value=data.get("flicker_enabled", False),
            editable=True
        ),
        InspectorField(
            key="flicker_amount", label="Flicker Amt", kind="float", value=data.get("flicker_amount", 0.25),
            editable=True, min_value=0.0, max_value=1.0, step=0.05
        ),
        InspectorField(
            key="flicker_speed", label="Flicker Spd", kind="float", value=data.get("flicker_speed", 1.0),
            editable=True, min_value=0.0, step=0.25
        ),
        InspectorField(
            key="cookie_id", label="Cookie", kind="string", value=data.get("cookie_id"),
            editable=True
        ),
        InspectorField(
            key="cookie_scale", label="Cookie Scale", kind="float", value=data.get("cookie_scale", 1.0),
            editable=True, min_value=0.0, step=0.1
        ),
        InspectorField(
            key="cookie_rotation_deg", label="Cookie Rot", kind="float", value=data.get("cookie_rotation_deg", 0.0),
            editable=True, min_value=0.0, max_value=360.0, step=5.0
        ),
    )


def _build_collider_fields(data: Dict[str, Any]) -> Tuple[InspectorField, ...]:
    """Build collider component fields."""
    kind_val = data.get("kind", "none")
    fields: List[InspectorField] = [
        InspectorField(
            key="kind", label="Type", kind="enum", value=kind_val,
            editable=True, options=COLLIDER_KIND_OPTIONS
        ),
    ]

    if kind_val == "rect":
        fields.append(InspectorField(
            key="w", label="Width", kind="float", value=data.get("w", 16.0),
            editable=True, min_value=1.0, step=1.0
        ))
        fields.append(InspectorField(
            key="h", label="Height", kind="float", value=data.get("h", 16.0),
            editable=True, min_value=1.0, step=1.0
        ))
    elif kind_val == "circle":
        fields.append(InspectorField(
            key="r", label="Radius", kind="float", value=data.get("r", 8.0),
            editable=True, min_value=1.0, step=1.0
        ))

    return tuple(fields)


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def get_component_dict(entity_json: Dict[str, Any], kind: ComponentKind) -> Optional[Dict[str, Any]]:
    """Get component data dictionary for a specific component kind.
    
    Prefers entity_json["components"][kind] if present.
    Falls back to reading legacy top-level fields for back-compat.
    
    Args:
        entity_json: Entity JSON data
        kind: Component kind to retrieve
        
    Returns:
        Component data dict or None if component not present
    """
    components = _get_components_container(entity_json)

    # Prefer explicit components container
    if kind in components:
        return dict(components[kind])

    # Back-compat: read from legacy fields
    if kind == "transform":
        return _read_legacy_transform(entity_json, None)

    if kind == "sprite":
        if "sprite" in entity_json or "asset" in entity_json:
            return _read_legacy_sprite(entity_json)
        return None

    if kind == "light":
        if _has_component(entity_json, "light"):
            return _read_legacy_light(entity_json)
        return None

    if kind == "collider":
        if "collision" in entity_json:
            return {"kind": entity_json.get("collision", "none")}
        return None

    return None


def ensure_components_container(entity_json: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of entity_json with "components" dict present.
    
    Args:
        entity_json: Entity JSON data (not mutated)
        
    Returns:
        New dict with "components" key guaranteed to exist
    """
    result = _deep_copy(entity_json)
    if "components" not in result:
        result["components"] = {}
    return result


def build_components(
    entity_json: Dict[str, Any],
    sprite_runtime: object | None = None,
) -> Tuple[InspectorComponent, ...]:
    """Build ordered list of inspector components for an entity.
    
    Always includes Transform. Other components only if present.
    Order is stable: Transform, SpriteRenderer, LightSource, Collider.
    
    Args:
        entity_json: Entity JSON data
        sprite_runtime: Optional runtime sprite for position fallbacks
        
    Returns:
        Tuple of InspectorComponent in stable order
    """
    components: List[InspectorComponent] = []

    for kind in COMPONENT_ORDER:
        if kind == "transform":
            # Transform is always present
            comp_data = _get_components_container(entity_json).get("transform")
            if comp_data is None:
                comp_data = _read_legacy_transform(entity_json, sprite_runtime)
            fields = _build_transform_fields(comp_data)
            components.append(InspectorComponent(
                kind="transform",
                title=COMPONENT_TITLES["transform"],
                fields=fields,
                removable=False,
            ))
        elif _has_component(entity_json, kind):
            comp_data = get_component_dict(entity_json, kind)
            if comp_data is None:
                comp_data = dict(COMPONENT_DEFAULTS[kind])

            if kind == "sprite":
                fields = _build_sprite_fields(comp_data)
            elif kind == "light":
                fields = _build_light_fields(comp_data)
            elif kind == "collider":
                fields = _build_collider_fields(comp_data)
            else:
                continue

            components.append(InspectorComponent(
                kind=kind,
                title=COMPONENT_TITLES[kind],
                fields=fields,
                removable=True,
            ))

    return tuple(components)


def add_component(entity_json: Dict[str, Any], kind: ComponentKind) -> Dict[str, Any]:
    """Add a component with defaults to entity JSON.
    
    No-op if component already present. Transform cannot be added (always exists).
    
    Args:
        entity_json: Entity JSON data (not mutated)
        kind: Component kind to add
        
    Returns:
        New dict with component added
    """
    if kind == "transform":
        # Transform always exists, no-op
        return _deep_copy(entity_json)

    if _has_component(entity_json, kind):
        # Already present, no-op
        return _deep_copy(entity_json)

    result = ensure_components_container(entity_json)
    defaults = dict(COMPONENT_DEFAULTS[kind])

    # Add collider shape defaults based on kind
    if kind == "collider" and defaults.get("kind") == "rect":
        defaults.update(COLLIDER_RECT_DEFAULTS)

    result["components"][kind] = defaults
    return result


def remove_component(entity_json: Dict[str, Any], kind: ComponentKind) -> Dict[str, Any]:
    """Remove a component from entity JSON.
    
    Transform is not removable (returns unchanged copy).
    
    Args:
        entity_json: Entity JSON data (not mutated)
        kind: Component kind to remove
        
    Returns:
        New dict with component removed
    """
    if kind == "transform":
        # Transform cannot be removed
        return _deep_copy(entity_json)

    result = _deep_copy(entity_json)

    # Remove from components container
    if "components" in result and kind in result["components"]:
        del result["components"][kind]

    # Also remove legacy top-level fields for cleanliness
    if kind == "sprite":
        result.pop("sprite", None)
        result.pop("asset", None)
    elif kind == "light":
        # Remove from behaviours list
        if "behaviours" in result:
            result["behaviours"] = [
                b for b in result["behaviours"]
                if b != "LightSource" and not (isinstance(b, dict) and b.get("type") == "LightSource")
            ]
        # Remove from behaviour_config
        if "behaviour_config" in result:
            result["behaviour_config"].pop("LightSource", None)
    elif kind == "collider":
        result.pop("collision", None)

    return result


def set_component_field(
    entity_json: Dict[str, Any],
    kind: ComponentKind,
    field_key: str,
    new_value: object,
) -> Dict[str, Any]:
    """Set a field value in a component.
    
    Writes into components container even if entity was legacy-flat before.
    Immutable: does not mutate input dict.
    Preserves all unrelated keys.
    
    Args:
        entity_json: Entity JSON data (not mutated)
        kind: Component kind
        field_key: Field key to set
        new_value: New value for the field
        
    Returns:
        New dict with field updated
    """
    result = ensure_components_container(entity_json)

    # Ensure component exists in container
    if kind not in result["components"]:
        # Initialize from defaults or legacy values
        comp_data = get_component_dict(entity_json, kind)
        if comp_data is None:
            comp_data = dict(COMPONENT_DEFAULTS.get(kind, {}))
        result["components"][kind] = comp_data
    else:
        # Make a copy of the component dict
        result["components"][kind] = dict(result["components"][kind])

    # Set the field value
    result["components"][kind][field_key] = new_value

    # Special handling for collider kind changes
    if kind == "collider" and field_key == "kind":
        collider = result["components"]["collider"]
        if new_value == "rect":
            # Add rect defaults if not present
            if "w" not in collider:
                collider["w"] = COLLIDER_RECT_DEFAULTS["w"]
            if "h" not in collider:
                collider["h"] = COLLIDER_RECT_DEFAULTS["h"]
            # Remove circle fields
            collider.pop("r", None)
        elif new_value == "circle":
            # Add circle defaults if not present
            if "r" not in collider:
                collider["r"] = COLLIDER_CIRCLE_DEFAULTS["r"]
            # Remove rect fields
            collider.pop("w", None)
            collider.pop("h", None)
        elif new_value == "none":
            # Remove shape-specific fields
            collider.pop("w", None)
            collider.pop("h", None)
            collider.pop("r", None)

    return result


def get_addable_components(entity_json: Dict[str, Any]) -> Tuple[ComponentKind, ...]:
    """Get list of component kinds that can be added to this entity.
    
    Excludes Transform (always present) and any already-present components.
    
    Args:
        entity_json: Entity JSON data
        
    Returns:
        Tuple of addable component kinds
    """
    addable: List[ComponentKind] = []
    for kind in COMPONENT_ORDER:
        if kind == "transform":
            continue  # Transform always exists
        if not _has_component(entity_json, kind):
            addable.append(kind)
    return tuple(addable)
