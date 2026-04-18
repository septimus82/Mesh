"""Lighting geometry processing.

This module provides headless geometry computation for the lighting system.
It integrates with shadow_geometry and shadow_geometry_adapter to compute
shadow hulls and other geometry without GPU/Arcade dependencies.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

from .shadow_geometry import (
    Point,
    Polygon,
    ShadowGeometryResult,
    ShadowParams,
    compute_shadow_geometry,
    compute_shadow_hulls,
)
from .shadow_geometry_adapter import (
    occluder_config_to_polygon,
    occluder_configs_to_polygons,
)

if TYPE_CHECKING:
    from .lighting_config import LightConfig, OccluderConfig


@dataclass(slots=True, frozen=True)
class LightGeometry:
    """Computed geometry for a single light source.

    Attributes:
        light_index: Index of the light in the configuration list.
        position: Light position (x, y).
        radius: Light radius.
        shadow_hulls: Shadow hull polygons for this light.
        hulls_digest: Deterministic digest of the shadow hulls.
    """

    light_index: int
    position: tuple[float, float]
    radius: float
    shadow_hulls: tuple[Polygon, ...]
    hulls_digest: str


@dataclass(slots=True, frozen=True)
class SceneGeometry:
    """Computed geometry for an entire lighting scene.

    Attributes:
        occluder_polygons: Normalized polygons from occluders.
        light_geometries: Geometry per light source.
        total_hulls_count: Total number of shadow hulls.
        combined_digest: Deterministic digest of all geometry.
    """

    occluder_polygons: tuple[Polygon, ...]
    light_geometries: tuple[LightGeometry, ...]
    total_hulls_count: int
    combined_digest: str


def compute_hulls_digest(hulls: Sequence[Polygon]) -> str:
    """Compute a deterministic digest of shadow hulls.

    Args:
        hulls: Sequence of shadow hull polygons.

    Returns:
        SHA256 digest string (first 16 chars).
    """
    if not hulls:
        return "empty"

    # Serialize hulls deterministically
    parts = []
    for hull in hulls:
        pts = ";".join(f"{p[0]:.6f},{p[1]:.6f}" for p in hull)
        parts.append(pts)

    # Sort for determinism
    parts.sort()
    combined = "|".join(parts)

    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def occluder_config_to_polygon_typed(config: "OccluderConfig") -> list[Point] | None:
    """Convert an OccluderConfig to a polygon.

    Args:
        config: OccluderConfig dataclass.

    Returns:
        List of points or None if invalid.
    """
    if config.occluder_type == "poly" and config.points:
        return list(config.points)

    if config.width > 0 and config.height > 0:
        x, y = config.x, config.y
        w, h = config.width, config.height
        return [
            (x, y),
            (x + w, y),
            (x + w, y + h),
            (x, y + h),
        ]

    return None


def occluder_configs_to_polygons_typed(
    configs: Sequence["OccluderConfig"],
) -> list[list[Point]]:
    """Convert OccluderConfig dataclasses to polygons.

    Args:
        configs: Sequence of OccluderConfig instances.

    Returns:
        List of valid polygons.
    """
    result: list[list[Point]] = []
    for cfg in configs:
        poly = occluder_config_to_polygon_typed(cfg)
        if poly:
            result.append(poly)
    return result


def compute_light_geometry(
    light_index: int,
    light: "LightConfig",
    occluder_polygons: Sequence[Polygon],
    shadow_params: ShadowParams | None = None,
) -> LightGeometry:
    """Compute shadow geometry for a single light.

    Args:
        light_index: Index of the light.
        light: Light configuration.
        occluder_polygons: Pre-converted occluder polygons.
        shadow_params: Optional shadow parameters override.

    Returns:
        LightGeometry with computed shadow hulls.
    """
    position = (light.x, light.y)
    radius = light.radius

    # Skip shadow computation for ambient lights or zero-radius lights
    if light.light_type == "ambient" or radius <= 0:
        return LightGeometry(
            light_index=light_index,
            position=position,
            radius=radius,
            shadow_hulls=(),
            hulls_digest="none",
        )

    params = shadow_params or ShadowParams(light_radius=radius)
    hulls = compute_shadow_hulls(list(occluder_polygons), position, params)

    return LightGeometry(
        light_index=light_index,
        position=position,
        radius=radius,
        shadow_hulls=hulls,
        hulls_digest=compute_hulls_digest(hulls),
    )


def compute_scene_geometry(
    lights: Sequence["LightConfig"],
    occluders: Sequence["OccluderConfig"],
    shadow_params: ShadowParams | None = None,
) -> SceneGeometry:
    """Compute all geometry for a lighting scene.

    This is the main entry point for headless geometry computation.
    It converts occluders to polygons and computes shadow hulls for
    each light source.

    Args:
        lights: Light configurations.
        occluders: Occluder configurations.
        shadow_params: Optional shadow parameters override.

    Returns:
        SceneGeometry with all computed geometry.
    """
    # Convert occluders to polygons
    polygons = occluder_configs_to_polygons_typed(occluders)
    occluder_polygons = tuple(tuple(p) for p in polygons)

    # Compute geometry for each light
    light_geometries: list[LightGeometry] = []
    total_hulls = 0

    for i, light in enumerate(lights):
        geom = compute_light_geometry(i, light, occluder_polygons, shadow_params)
        light_geometries.append(geom)
        total_hulls += len(geom.shadow_hulls)

    # Compute combined digest
    all_digests = [lg.hulls_digest for lg in light_geometries]
    all_digests.sort()
    combined = "|".join(all_digests)
    combined_digest = hashlib.sha256(combined.encode()).hexdigest()[:16]

    return SceneGeometry(
        occluder_polygons=occluder_polygons,
        light_geometries=tuple(light_geometries),
        total_hulls_count=total_hulls,
        combined_digest=combined_digest,
    )


def compute_shadow_geometry_for_light(
    light_pos: tuple[float, float],
    light_radius: float,
    occluder_configs: Sequence[dict],
) -> ShadowGeometryResult:
    """Compute shadow geometry for a light using dict configs.

    This is a convenience function for integration with existing code
    that uses dict-style occluder configs.

    Args:
        light_pos: Light position (x, y).
        light_radius: Light radius.
        occluder_configs: Occluder configuration dicts.

    Returns:
        ShadowGeometryResult from shadow_geometry module.
    """
    polygons = occluder_configs_to_polygons(occluder_configs)
    params = ShadowParams(light_radius=light_radius)
    return compute_shadow_geometry(polygons, light_pos, params)
