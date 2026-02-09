"""Lighting plan model for headless determinism testing.

This module provides a headless LightingPlan model that captures the complete
state of a lighting computation without any GPU/Arcade dependencies. This
enables deterministic golden testing of the lighting pipeline.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from .lighting_config import LightConfig, LightingSceneConfig, OccluderConfig
    from .lighting_geometry import LightGeometry, SceneGeometry


@dataclass(slots=True, frozen=True)
class LightPlanEntry:
    """A single light in the lighting plan.

    Attributes:
        index: Light index in the source configuration.
        light_type: Type of light ("point", "ambient", etc.).
        position: Light position (x, y).
        radius: Light radius.
        color: RGBA color tuple.
        intensity: Brightness multiplier.
        shadow_hulls_count: Number of shadow hulls for this light.
        hulls_digest: Digest of shadow hull geometry.
    """

    index: int
    light_type: str
    position: tuple[float, float]
    radius: float
    color: tuple[int, int, int, int]
    intensity: float
    shadow_hulls_count: int
    hulls_digest: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "index": self.index,
            "light_type": self.light_type,
            "position": list(self.position),
            "radius": round(self.radius, 6),
            "color": list(self.color),
            "intensity": round(self.intensity, 6),
            "shadow_hulls_count": self.shadow_hulls_count,
            "hulls_digest": self.hulls_digest,
        }


@dataclass(slots=True, frozen=True)
class OccluderPlanEntry:
    """A single occluder in the lighting plan.

    Attributes:
        occluder_id: Unique identifier.
        occluder_type: Type ("rect", "poly").
        digest: Digest of occluder geometry.
    """

    occluder_id: str
    occluder_type: str
    digest: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "occluder_id": self.occluder_id,
            "occluder_type": self.occluder_type,
            "digest": self.digest,
        }


@dataclass(slots=True)
class LightingPlan:
    """Complete lighting plan for a scene.

    This is the main model for headless lighting computation. It captures
    all light and occluder configurations, computed geometry digests,
    and cache state flags. The digest() method provides a deterministic
    hash for regression testing.

    Attributes:
        ambient_color: Scene ambient color RGBA.
        shadows_mode: Shadow mode ("none", "hard", "soft").
        lights: List of light plan entries.
        occluders: List of occluder plan entries.
        geometry_digest: Combined digest of all shadow geometry.
        cache_hit: Whether this plan matched cached state.
        layer_rebuilt: Whether light layer was rebuilt.
        shadows_rebuilt: Whether shadow geometry was rebuilt.
    """

    ambient_color: tuple[int, int, int, int] = (128, 128, 128, 255)
    shadows_mode: str = "none"
    lights: list[LightPlanEntry] = field(default_factory=list)
    occluders: list[OccluderPlanEntry] = field(default_factory=list)
    geometry_digest: str = ""
    cache_hit: bool = False
    layer_rebuilt: bool = True
    shadows_rebuilt: bool = True

    def digest(self) -> str:
        """Compute a deterministic digest of the entire lighting plan.

        This digest can be used for golden testing - if the digest changes,
        the lighting computation has changed.

        Returns:
            SHA256 digest string (first 32 chars).
        """
        # Build deterministic representation
        data = {
            "ambient_color": list(self.ambient_color),
            "shadows_mode": self.shadows_mode,
            "lights": sorted(
                [light.to_dict() for light in self.lights],
                key=lambda x: x["index"],
            ),
            "occluders": sorted(
                [occ.to_dict() for occ in self.occluders],
                key=lambda x: (x["occluder_id"], x["occluder_type"]),
            ),
            "geometry_digest": self.geometry_digest,
        }

        # Serialize deterministically
        json_str = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(json_str.encode()).hexdigest()[:32]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization/debugging."""
        return {
            "ambient_color": list(self.ambient_color),
            "shadows_mode": self.shadows_mode,
            "lights": [light.to_dict() for light in self.lights],
            "occluders": [occ.to_dict() for occ in self.occluders],
            "geometry_digest": self.geometry_digest,
            "cache_hit": self.cache_hit,
            "layer_rebuilt": self.layer_rebuilt,
            "shadows_rebuilt": self.shadows_rebuilt,
            "plan_digest": self.digest(),
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LightingPlan":
        """Create a LightingPlan from a dictionary."""
        lights = [
            LightPlanEntry(
                index=ld["index"],
                light_type=ld["light_type"],
                position=tuple(ld["position"]),
                radius=ld["radius"],
                color=tuple(ld["color"]),
                intensity=ld["intensity"],
                shadow_hulls_count=ld["shadow_hulls_count"],
                hulls_digest=ld["hulls_digest"],
            )
            for ld in data.get("lights", [])
        ]
        occluders = [
            OccluderPlanEntry(
                occluder_id=od["occluder_id"],
                occluder_type=od["occluder_type"],
                digest=od["digest"],
            )
            for od in data.get("occluders", [])
        ]
        return cls(
            ambient_color=tuple(data.get("ambient_color", (128, 128, 128, 255))),
            shadows_mode=data.get("shadows_mode", "none"),
            lights=lights,
            occluders=occluders,
            geometry_digest=data.get("geometry_digest", ""),
            cache_hit=data.get("cache_hit", False),
            layer_rebuilt=data.get("layer_rebuilt", True),
            shadows_rebuilt=data.get("shadows_rebuilt", True),
        )


def build_lighting_plan(
    scene_config: "LightingSceneConfig",
    scene_geometry: "SceneGeometry",
    cache_hit: bool = False,
    layer_rebuilt: bool = True,
    shadows_rebuilt: bool = True,
) -> LightingPlan:
    """Build a LightingPlan from scene config and computed geometry.

    This is the main entry point for creating a lighting plan from
    the configuration and geometry modules.

    Args:
        scene_config: Scene lighting configuration.
        scene_geometry: Computed scene geometry.
        cache_hit: Whether this was a cache hit.
        layer_rebuilt: Whether layer was rebuilt.
        shadows_rebuilt: Whether shadows were rebuilt.

    Returns:
        LightingPlan capturing the complete state.
    """
    # Build light entries
    lights: list[LightPlanEntry] = []
    for i, light_cfg in enumerate(scene_config.lights):
        # Find matching geometry
        hulls_count = 0
        hulls_digest = "none"
        for geom in scene_geometry.light_geometries:
            if geom.light_index == i:
                hulls_count = len(geom.shadow_hulls)
                hulls_digest = geom.hulls_digest
                break

        lights.append(
            LightPlanEntry(
                index=i,
                light_type=light_cfg.light_type,
                position=(light_cfg.x, light_cfg.y),
                radius=light_cfg.radius,
                color=light_cfg.color,
                intensity=light_cfg.intensity,
                shadow_hulls_count=hulls_count,
                hulls_digest=hulls_digest,
            )
        )

    # Build occluder entries
    occluders: list[OccluderPlanEntry] = []
    for occ_cfg in scene_config.occluders:
        occluders.append(
            OccluderPlanEntry(
                occluder_id=occ_cfg.occluder_id,
                occluder_type=occ_cfg.occluder_type,
                digest=occ_cfg.digest(),
            )
        )

    return LightingPlan(
        ambient_color=scene_config.ambient_color,
        shadows_mode=scene_config.shadows_mode,
        lights=lights,
        occluders=occluders,
        geometry_digest=scene_geometry.combined_digest,
        cache_hit=cache_hit,
        layer_rebuilt=layer_rebuilt,
        shadows_rebuilt=shadows_rebuilt,
    )


def build_lighting_plan_from_dicts(
    lights_data: list[dict[str, Any]] | None = None,
    occluders_data: list[dict[str, Any]] | None = None,
    ambient_color: tuple[int, ...] | list[int] | None = None,
    shadows_mode: str = "none",
) -> LightingPlan:
    """Build a LightingPlan directly from dictionary data.

    This is a convenience function that handles parsing and geometry
    computation in one step.

    Args:
        lights_data: List of light config dictionaries.
        occluders_data: List of occluder config dictionaries.
        ambient_color: Ambient color as RGB or RGBA.
        shadows_mode: Shadow mode string.

    Returns:
        Complete LightingPlan.
    """
    from .lighting_config import parse_scene_config
    from .lighting_geometry import compute_scene_geometry

    # Parse configuration
    scene_config = parse_scene_config(
        lights_data=lights_data,
        occluders_data=occluders_data,
        ambient_color=ambient_color,
        shadows_mode=shadows_mode,
    )

    # Compute geometry
    scene_geometry = compute_scene_geometry(
        lights=scene_config.lights,
        occluders=scene_config.occluders,
    )

    # Build plan
    return build_lighting_plan(
        scene_config=scene_config,
        scene_geometry=scene_geometry,
        cache_hit=False,
        layer_rebuilt=True,
        shadows_rebuilt=True,
    )
