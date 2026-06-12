"""Typed accessor layer for entity dictionaries.

This module provides a typed wrapper around raw entity dict data,
offering type-safe getters and setters for canonical entity fields.

Usage:
    from engine.entity_view import EntityView
    
    # Wrap a raw entity dict
    view = EntityView(entity_dict)
    
    # Type-safe access
    x = view.x  # float
    sprite = view.sprite  # str | None
    tags = view.tags  # list[str]
    
    # Setters update the underlying dict
    view.x = 100.0
    view.tags = ["enemy", "boss"]

The underlying dict is accessible via `view.data` for migration/serialization.

CANONICAL FIELDS:
    These fields should be accessed via EntityView, not direct dict access:
    - Position: x, y
    - Identity: id, name, prefab_id, variant_id, spawn_id
    - Rendering: sprite, sprite_sheet, scale, rotation, layer, alpha, tint
    - Collision: solid, collision_poly, occluder_poly
    - Behaviours: behaviours, behaviour_config
    - Tags: tags
    - Animation: animations, animation_state, animation_frame_rate
    - Depth: depth_z, render_layer
"""
from __future__ import annotations

from typing import Any, Iterator, MutableMapping, cast


class EntityView(MutableMapping[str, Any]):
    """Typed accessor wrapper for entity dictionaries.
    
    Provides typed getters/setters for canonical entity fields while
    maintaining full dict compatibility for non-canonical fields.
    """

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any]) -> None:
        """Wrap an entity dictionary.
        
        Args:
            data: The raw entity dict to wrap. Modifications via this
                  view will update the original dict.
        """
        self._data = data

    @property
    def data(self) -> dict[str, Any]:
        """Access the underlying entity dictionary."""
        return self._data

    # -------------------------------------------------------------------------
    # MutableMapping protocol (allows EntityView to be used like a dict)
    # -------------------------------------------------------------------------

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        del self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        return key in self._data

    # -------------------------------------------------------------------------
    # Position
    # -------------------------------------------------------------------------

    @property
    def x(self) -> float:
        """Entity X position."""
        val = self._data.get("x", 0.0)
        return float(val) if val is not None else 0.0

    @x.setter
    def x(self, value: float) -> None:
        self._data["x"] = float(value)

    @property
    def y(self) -> float:
        """Entity Y position."""
        val = self._data.get("y", 0.0)
        return float(val) if val is not None else 0.0

    @y.setter
    def y(self, value: float) -> None:
        self._data["y"] = float(value)

    def get_position(self) -> tuple[float, float]:
        """Get (x, y) position tuple."""
        return (self.x, self.y)

    def set_position(self, x: float, y: float) -> None:
        """Set position from x, y coordinates."""
        self.x = x
        self.y = y

    # -------------------------------------------------------------------------
    # Identity
    # -------------------------------------------------------------------------

    @property
    def id(self) -> str | None:
        """Unique entity ID (for stable references)."""
        val = self._data.get("id")
        return str(val) if val is not None else None

    @id.setter
    def id(self, value: str | None) -> None:
        if value is None:
            self._data.pop("id", None)
        else:
            self._data["id"] = str(value)

    @property
    def name(self) -> str | None:
        """Human-readable entity name."""
        val = self._data.get("name")
        return str(val) if val is not None else None

    @name.setter
    def name(self, value: str | None) -> None:
        if value is None:
            self._data.pop("name", None)
        else:
            self._data["name"] = str(value)

    @property
    def prefab_id(self) -> str | None:
        """Prefab ID this entity is based on."""
        val = self._data.get("prefab_id")
        return str(val) if val is not None else None

    @prefab_id.setter
    def prefab_id(self, value: str | None) -> None:
        if value is None:
            self._data.pop("prefab_id", None)
        else:
            self._data["prefab_id"] = str(value)

    @property
    def variant_id(self) -> str | None:
        """Variant ID applied to this entity."""
        val = self._data.get("variant_id")
        return str(val) if val is not None else None

    @variant_id.setter
    def variant_id(self, value: str | None) -> None:
        if value is None:
            self._data.pop("variant_id", None)
        else:
            self._data["variant_id"] = str(value)

    @property
    def spawn_id(self) -> str | None:
        """Spawn point ID for scene transitions."""
        val = self._data.get("spawn_id")
        return str(val) if val is not None else None

    @spawn_id.setter
    def spawn_id(self, value: str | None) -> None:
        if value is None:
            self._data.pop("spawn_id", None)
        else:
            self._data["spawn_id"] = str(value)

    # -------------------------------------------------------------------------
    # Rendering
    # -------------------------------------------------------------------------

    @property
    def sprite(self) -> str | None:
        """Sprite asset path."""
        val = self._data.get("sprite")
        return str(val) if val is not None else None

    @sprite.setter
    def sprite(self, value: str | None) -> None:
        if value is None:
            self._data["sprite"] = None
        else:
            self._data["sprite"] = str(value)

    @property
    def sprite_sheet(self) -> dict[str, Any]:
        """Sprite sheet configuration."""
        val = self._data.get("sprite_sheet")
        return val if isinstance(val, dict) else {}

    @sprite_sheet.setter
    def sprite_sheet(self, value: dict[str, Any]) -> None:
        self._data["sprite_sheet"] = dict(value)

    @property
    def scale(self) -> float:
        """Sprite scale factor."""
        val = self._data.get("scale", 1.0)
        return float(val) if val is not None else 1.0

    @scale.setter
    def scale(self, value: float) -> None:
        self._data["scale"] = float(value)

    @property
    def rotation(self) -> float:
        """Rotation in degrees."""
        val = self._data.get("rotation", 0.0)
        return float(val) if val is not None else 0.0

    @rotation.setter
    def rotation(self, value: float) -> None:
        self._data["rotation"] = float(value)

    @property
    def layer(self) -> str:
        """Render layer name."""
        val = self._data.get("layer", "entities")
        return str(val) if val else "entities"

    @layer.setter
    def layer(self, value: str) -> None:
        self._data["layer"] = str(value)

    @property
    def alpha(self) -> float:
        """Sprite alpha/opacity (0.0-1.0)."""
        val = self._data.get("alpha", 1.0)
        return float(val) if val is not None else 1.0

    @alpha.setter
    def alpha(self, value: float) -> None:
        self._data["alpha"] = float(value)

    @property
    def tint(self) -> tuple[int, int, int] | None:
        """RGB tint color."""
        val = self._data.get("tint")
        if val is None:
            return None
        if isinstance(val, (list, tuple)) and len(val) >= 3:
            return (int(val[0]), int(val[1]), int(val[2]))
        return None

    @tint.setter
    def tint(self, value: tuple[int, int, int] | None) -> None:
        if value is None:
            self._data.pop("tint", None)
        else:
            self._data["tint"] = list(value)

    # -------------------------------------------------------------------------
    # Collision
    # -------------------------------------------------------------------------

    @property
    def solid(self) -> bool:
        """Whether entity blocks movement."""
        return bool(self._data.get("solid", False))

    @solid.setter
    def solid(self, value: bool) -> None:
        self._data["solid"] = bool(value)

    @property
    def collision_poly(self) -> list[tuple[float, float]] | None:
        """Collision polygon points."""
        val = self._data.get("collision_poly")
        if val is None:
            return None
        if isinstance(val, list):
            return [(float(p[0]), float(p[1])) for p in val if isinstance(p, (list, tuple)) and len(p) >= 2]
        return None

    @collision_poly.setter
    def collision_poly(self, value: list[tuple[float, float]] | None) -> None:
        if value is None:
            self._data.pop("collision_poly", None)
        else:
            self._data["collision_poly"] = [[p[0], p[1]] for p in value]

    @property
    def occluder_poly(self) -> list[tuple[float, float]] | None:
        """Light occluder polygon points."""
        val = self._data.get("occluder_poly")
        if val is None:
            return None
        if isinstance(val, list):
            return [(float(p[0]), float(p[1])) for p in val if isinstance(p, (list, tuple)) and len(p) >= 2]
        return None

    @occluder_poly.setter
    def occluder_poly(self, value: list[tuple[float, float]] | None) -> None:
        if value is None:
            self._data.pop("occluder_poly", None)
        else:
            self._data["occluder_poly"] = [[p[0], p[1]] for p in value]

    # -------------------------------------------------------------------------
    # Behaviours
    # -------------------------------------------------------------------------

    @property
    def behaviours(self) -> list[str | dict[str, Any]]:
        """List of behaviour names or config dicts."""
        val = self._data.get("behaviours")
        return list(val) if isinstance(val, list) else []

    @behaviours.setter
    def behaviours(self, value: list[str | dict[str, Any]]) -> None:
        self._data["behaviours"] = list(value)

    @property
    def behaviour_config(self) -> dict[str, Any]:
        """Behaviour configuration dictionary."""
        val = self._data.get("behaviour_config")
        return val if isinstance(val, dict) else {}

    @behaviour_config.setter
    def behaviour_config(self, value: dict[str, Any]) -> None:
        self._data["behaviour_config"] = dict(value)

    def has_behaviour(self, name: str) -> bool:
        """Check if entity has a specific behaviour."""
        for b in self.behaviours:
            if isinstance(b, str) and b == name:
                return True
            if isinstance(b, dict) and b.get("type") == name:
                return True
        return False

    def get_behaviour_config(self, name: str) -> dict[str, Any]:
        """Get configuration for a specific behaviour."""
        val = self.behaviour_config.get(name)
        return val if isinstance(val, dict) else {}

    # -------------------------------------------------------------------------
    # Tags
    # -------------------------------------------------------------------------

    @property
    def tags(self) -> list[str]:
        """Entity tags."""
        val = self._data.get("tags")
        if isinstance(val, list):
            return [str(t) for t in val]
        return []

    @tags.setter
    def tags(self, value: list[str]) -> None:
        self._data["tags"] = [str(t) for t in value]

    def has_tag(self, tag: str) -> bool:
        """Check if entity has a specific tag."""
        return tag in self.tags

    def add_tag(self, tag: str) -> None:
        """Add a tag if not already present."""
        current = self.tags
        if tag not in current:
            current.append(tag)
            self.tags = current

    def remove_tag(self, tag: str) -> None:
        """Remove a tag if present."""
        current = self.tags
        if tag in current:
            current.remove(tag)
            self.tags = current

    # -------------------------------------------------------------------------
    # Animation
    # -------------------------------------------------------------------------

    @property
    def animations(self) -> dict[str, list[str]]:
        """Animation definitions (state -> frame list)."""
        val = self._data.get("animations")
        return val if isinstance(val, dict) else {}

    @animations.setter
    def animations(self, value: dict[str, list[str]]) -> None:
        self._data["animations"] = dict(value)

    @property
    def animation_state(self) -> str:
        """Current animation state name."""
        val = self._data.get("animation_state", "idle")
        return str(val) if val else "idle"

    @animation_state.setter
    def animation_state(self, value: str) -> None:
        self._data["animation_state"] = str(value)

    @property
    def animation_frame_rate(self) -> float:
        """Animation frames per second."""
        val = self._data.get("animation_frame_rate", 8.0)
        return float(val) if val is not None else 8.0

    @animation_frame_rate.setter
    def animation_frame_rate(self, value: float) -> None:
        self._data["animation_frame_rate"] = float(value)

    # -------------------------------------------------------------------------
    # Depth / Render order
    # -------------------------------------------------------------------------

    @property
    def depth_z(self) -> float:
        """Depth Z for HD2D rendering."""
        val = self._data.get("depth_z", 0.0)
        return float(val) if val is not None else 0.0

    @depth_z.setter
    def depth_z(self, value: float) -> None:
        self._data["depth_z"] = float(value)

    @property
    def render_layer(self) -> int:
        """Render layer index."""
        val = self._data.get("render_layer", 0)
        return int(val) if val is not None else 0

    @render_layer.setter
    def render_layer(self, value: int) -> None:
        self._data["render_layer"] = int(value)

    # -------------------------------------------------------------------------
    # Flags (for gating)
    # -------------------------------------------------------------------------

    @property
    def require_flags(self) -> list[str]:
        """Flags required for entity to be active."""
        val = self._data.get("require_flags")
        if isinstance(val, list):
            return [str(f) for f in val]
        return []

    @require_flags.setter
    def require_flags(self, value: list[str]) -> None:
        self._data["require_flags"] = [str(f) for f in value]

    @property
    def forbid_flags(self) -> list[str]:
        """Flags that prevent entity from being active."""
        val = self._data.get("forbid_flags")
        if isinstance(val, list):
            return [str(f) for f in val]
        return []

    @forbid_flags.setter
    def forbid_flags(self, value: list[str]) -> None:
        self._data["forbid_flags"] = [str(f) for f in value]

    # -------------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------------

    def __repr__(self) -> str:
        name = self.name or self.prefab_id or self.id or "<anonymous>"
        return f"EntityView({name!r}, x={self.x}, y={self.y})"

    @classmethod
    def wrap(cls, entity: dict[str, Any] | "EntityView") -> "EntityView":
        """Wrap an entity dict or return existing EntityView.
        
        Useful for functions that accept either raw dicts or views.
        """
        if isinstance(entity, cls):
            return entity
        return cls(cast(dict[str, Any], entity))


# ---------------------------------------------------------------------------
# Canonical field registry for policy enforcement
# ---------------------------------------------------------------------------

#: Set of canonical entity fields that should be accessed via EntityView.
#: This is used by policy tests to forbid direct dict access in production code.
CANONICAL_ENTITY_FIELDS: frozenset[str] = frozenset({
    # Position
    "x", "y",
    # Identity
    "id", "name", "prefab_id", "variant_id", "spawn_id",
    # Rendering
    "sprite", "sprite_sheet", "scale", "rotation", "layer", "alpha", "tint",
    # Collision
    "solid", "collision_poly", "occluder_poly",
    # Behaviours
    "behaviours", "behaviour_config",
    # Tags
    "tags",
    # Animation
    "animations", "animation_state", "animation_frame_rate",
    # Depth
    "depth_z", "render_layer",
    # Flags
    "require_flags", "forbid_flags",
})

#: Modules exempt from the EntityView policy (serialization, migration, tests).
ENTITY_VIEW_POLICY_EXEMPT_MODULES: frozenset[str] = frozenset({
    # Core serialization/migration
    "engine/scene_loader.py",
    "engine/scene_serializer.py",
    "engine/migrations.py",
    "engine/prefabs.py",
    "engine/prefab_overrides.py",
    "engine/entity_view.py",
    # Validators (need raw dict access for validation)
    "engine/validators/schema_validation.py",
    "engine/validators/prefab_validator.py",
    "engine/validators/reference_validator.py",
    # Tooling (operates on raw JSON)
    "engine/tooling/",
    "engine/tooling_runtime/",
    "mesh_cli/",
    # Tests
    "tests/",
    "conftest.py",
})
