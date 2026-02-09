"""
Integration adapter for shadow_geometry module.

This provides a thin adapter to integrate the pure shadow_geometry module
with the existing lighting pipeline without changing runtime behavior.
"""
from __future__ import annotations

from typing import Any, Sequence

from .shadow_geometry import (
    Point,
    Polygon,
    ShadowGeometryResult,
    ShadowParams,
    compute_shadow_geometry,
    compute_shadow_hulls,
    normalize_polygon,
)
from .occluders import Rect


def rect_to_polygon(rect: Rect) -> list[Point]:
    """Convert a Rect to a polygon (list of points).
    
    The returned polygon is counter-clockwise.
    """
    return [
        (rect.x, rect.y),
        (rect.x + rect.width, rect.y),
        (rect.x + rect.width, rect.y + rect.height),
        (rect.x, rect.y + rect.height),
    ]


def rects_to_polygons(rects: Sequence[Rect]) -> list[list[Point]]:
    """Convert a sequence of Rects to polygons."""
    return [rect_to_polygon(r) for r in rects]


def occluder_config_to_polygon(config: dict[str, Any]) -> list[Point] | None:
    """Convert an occluder config dict to a polygon.
    
    Supports both rect-style configs (x, y, width, height) and
    polygon-style configs (points).
    
    Returns None if config is invalid.
    """
    # Check for polygon-style config
    points = config.get("points")
    if points and isinstance(points, list):
        try:
            return [(float(p[0]), float(p[1])) for p in points]
        except (TypeError, IndexError, ValueError):
            return None
    
    # Check for rect-style config
    try:
        x = float(config.get("x", 0.0))
        y = float(config.get("y", 0.0))
        width = float(config.get("width", 0.0))
        height = float(config.get("height", 0.0))
        
        if width <= 0 or height <= 0:
            return None
        
        return [
            (x, y),
            (x + width, y),
            (x + width, y + height),
            (x, y + height),
        ]
    except (TypeError, ValueError):
        return None


def occluder_configs_to_polygons(
    configs: Sequence[dict[str, Any]],
) -> list[list[Point]]:
    """Convert occluder config dicts to polygons.
    
    Filters out invalid configs.
    """
    result: list[list[Point]] = []
    for cfg in configs:
        poly = occluder_config_to_polygon(cfg)
        if poly:
            result.append(poly)
    return result


def compute_shadow_hulls_from_rects(
    rects: Sequence[Rect],
    light_pos: Point,
    light_radius: float = 100.0,
    **kwargs: Any,
) -> tuple[Polygon, ...]:
    """Compute shadow hulls from Rect occluders.
    
    This is a convenience adapter for code using Rect occluders.
    
    Args:
        rects: Rect occluders
        light_pos: Light position
        light_radius: Light radius
        **kwargs: Additional ShadowParams fields
        
    Returns:
        Tuple of shadow hull polygons
    """
    polygons = rects_to_polygons(rects)
    params = ShadowParams(light_radius=light_radius, **kwargs)
    return compute_shadow_hulls(polygons, light_pos, params)


def compute_shadow_hulls_from_configs(
    configs: Sequence[dict[str, Any]],
    light_pos: Point,
    light_radius: float = 100.0,
    **kwargs: Any,
) -> tuple[Polygon, ...]:
    """Compute shadow hulls from occluder config dicts.
    
    Args:
        configs: Occluder configurations (rect or polygon style)
        light_pos: Light position
        light_radius: Light radius
        **kwargs: Additional ShadowParams fields
        
    Returns:
        Tuple of shadow hull polygons
    """
    polygons = occluder_configs_to_polygons(configs)
    params = ShadowParams(light_radius=light_radius, **kwargs)
    return compute_shadow_hulls(polygons, light_pos, params)


def compute_shadow_geometry_from_configs(
    configs: Sequence[dict[str, Any]],
    light_pos: Point,
    light_radius: float = 100.0,
    **kwargs: Any,
) -> ShadowGeometryResult:
    """Compute full shadow geometry from occluder config dicts.
    
    Args:
        configs: Occluder configurations
        light_pos: Light position
        light_radius: Light radius
        **kwargs: Additional ShadowParams fields
        
    Returns:
        ShadowGeometryResult with hulls, segments, and metadata
    """
    polygons = occluder_configs_to_polygons(configs)
    params = ShadowParams(light_radius=light_radius, **kwargs)
    return compute_shadow_geometry(polygons, light_pos, params)
