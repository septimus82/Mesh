"""
Pure shadow/occlusion geometry module - GPU-free shadow hull computation.

This module provides deterministic, headless shadow geometry operations
that can be tested without any Arcade/GPU dependencies.

Design Principles:
1. Headless: No GPU/Arcade/window dependencies
2. Deterministic: Identical inputs -> identical outputs
3. Stable: Output ordering is consistent across runs
4. Testable: All operations are pure functions on simple types

Key Types:
- Point: tuple[float, float]
- Polygon: tuple[Point, ...]  (immutable for hashing)
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Sequence


# =============================================================================
# Type Definitions
# =============================================================================

Point = tuple[float, float]
MutablePolygon = list[Point]
Polygon = tuple[Point, ...]  # Immutable for stable hashing


# =============================================================================
# Validation
# =============================================================================

@dataclass
class PolygonValidationResult:
    """Result of polygon validation."""
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_point(point: Point, label: str = "point") -> list[str]:
    """Validate a single point. Returns list of error strings."""
    errors: list[str] = []
    if not isinstance(point, (tuple, list)) or len(point) < 2:
        errors.append(f"{label}: Invalid structure (expected 2-tuple)")
        return errors
    
    try:
        x, y = float(point[0]), float(point[1])
    except (TypeError, ValueError) as e:
        errors.append(f"{label}: Cannot convert to float ({e})")
        return errors
    
    if not math.isfinite(x):
        errors.append(f"{label}: x coordinate is not finite ({x})")
    if not math.isfinite(y):
        errors.append(f"{label}: y coordinate is not finite ({y})")
    
    return errors


def validate_polygon(poly: Sequence[Point]) -> PolygonValidationResult:
    """Validate a polygon for use in shadow computation.
    
    Checks:
    1. Has at least 3 points
    2. All coordinates are finite (no NaN/Inf)
    3. Has non-zero area (not degenerate)
    
    Args:
        poly: Sequence of (x, y) points
        
    Returns:
        PolygonValidationResult with errors and warnings
    """
    errors: list[str] = []
    warnings: list[str] = []
    
    # Check minimum points
    if not poly or len(poly) < 3:
        errors.append(f"Polygon has {len(poly) if poly else 0} points (minimum 3 required)")
        return PolygonValidationResult(valid=False, errors=errors)
    
    # Check all points are valid
    for i, point in enumerate(poly):
        point_errors = validate_point(point, f"vertex[{i}]")
        errors.extend(point_errors)
    
    if errors:
        return PolygonValidationResult(valid=False, errors=errors, warnings=warnings)
    
    # Check for duplicate consecutive vertices (warning)
    points = [(float(p[0]), float(p[1])) for p in poly]
    for i in range(len(points)):
        p0 = points[i]
        p1 = points[(i + 1) % len(points)]
        if abs(p0[0] - p1[0]) < 1e-9 and abs(p0[1] - p1[1]) < 1e-9:
            warnings.append(f"Consecutive duplicate vertices at index {i}")
    
    # Check for degenerate (zero area) polygon
    area = _polygon_signed_area(points)
    if abs(area) < 1e-9:
        errors.append("Polygon has zero area (degenerate)")
        return PolygonValidationResult(valid=False, errors=errors, warnings=warnings)
    
    return PolygonValidationResult(valid=True, errors=errors, warnings=warnings)


def assert_polygon_valid(poly: Sequence[Point], context: str = "") -> None:
    """Assert that a polygon is valid for shadow computation.
    
    Raises:
        AssertionError: If validation fails
    """
    result = validate_polygon(poly)
    if not result.valid:
        prefix = f"[{context}] " if context else ""
        error_msg = f"{prefix}Polygon validation failed:\n"
        error_msg += "\n".join(f"  - {e}" for e in result.errors)
        raise AssertionError(error_msg)


# =============================================================================
# Polygon Normalization
# =============================================================================

def _polygon_signed_area(points: Sequence[Point]) -> float:
    """Compute signed area using shoelace formula.
    
    Positive = counter-clockwise, Negative = clockwise.
    """
    area = 0.0
    n = len(points)
    for i in range(n):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % n]
        area += (x0 * y1) - (x1 * y0)
    return area * 0.5


def _polygon_centroid(points: Sequence[Point]) -> Point:
    """Compute centroid of a polygon."""
    n = len(points)
    if n == 0:
        return (0.0, 0.0)
    cx = sum(p[0] for p in points) / n
    cy = sum(p[1] for p in points) / n
    return (cx, cy)


def _angle_from_centroid(point: Point, centroid: Point) -> float:
    """Compute angle from centroid to point."""
    dx = point[0] - centroid[0]
    dy = point[1] - centroid[1]
    return math.atan2(dy, dx)


def normalize_polygon(
    poly: Sequence[Point],
    *,
    precision: int = 6,
    ensure_ccw: bool = True,
) -> Polygon:
    """Normalize a polygon to a canonical form for stable comparison.
    
    Normalization steps:
    1. Round all coordinates to fixed precision
    2. Remove consecutive duplicate points
    3. Ensure counter-clockwise winding (optional)
    4. Rotate so the lexicographically smallest vertex is first
    
    This ensures:
    - Same polygon with different starting vertex -> same output
    - Same polygon with different winding -> same output
    - Floating point noise is eliminated
    
    Args:
        poly: Input polygon as sequence of (x, y) points
        precision: Decimal places for rounding (default 6)
        ensure_ccw: If True, ensure counter-clockwise winding
        
    Returns:
        Normalized polygon as immutable tuple
    """
    if not poly or len(poly) < 3:
        return ()
    
    # Round coordinates
    points: MutablePolygon = [
        (round(float(p[0]), precision), round(float(p[1]), precision))
        for p in poly
    ]
    
    # Remove consecutive duplicates
    cleaned: MutablePolygon = []
    for i, pt in enumerate(points):
        prev = points[i - 1] if i > 0 else points[-1]
        if pt != prev:
            cleaned.append(pt)
    
    # Remove closing duplicate
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1]:
        cleaned.pop()
    
    if len(cleaned) < 3:
        return ()
    
    # Ensure counter-clockwise winding
    if ensure_ccw:
        area = _polygon_signed_area(cleaned)
        if area < 0:  # Clockwise, reverse
            cleaned = list(reversed(cleaned))
    
    # Find lexicographically smallest vertex
    min_idx = 0
    for i in range(1, len(cleaned)):
        if cleaned[i] < cleaned[min_idx]:
            min_idx = i
    
    # Rotate to start at smallest vertex
    rotated = cleaned[min_idx:] + cleaned[:min_idx]
    
    return tuple(rotated)


def normalize_polygon_list(
    polygons: Sequence[Sequence[Point]],
    *,
    precision: int = 6,
) -> tuple[Polygon, ...]:
    """Normalize a list of polygons and sort for deterministic ordering."""
    normalized = [normalize_polygon(p, precision=precision) for p in polygons]
    # Filter out empty/degenerate
    valid = [p for p in normalized if len(p) >= 3]
    # Sort for deterministic ordering
    return tuple(sorted(valid))


# =============================================================================
# Shadow Hull Parameters
# =============================================================================

@dataclass(frozen=True, slots=True)
class ShadowParams:
    """Parameters for shadow hull computation."""
    light_radius: float = 100.0
    max_hulls: int = 512
    extrusion_distance: float | None = None  # None = use light_radius
    cull_outside_radius: bool = True
    round_precision: int = 3
    
    def effective_extrusion(self) -> float:
        """Get the actual extrusion distance to use."""
        return self.extrusion_distance if self.extrusion_distance is not None else self.light_radius


# =============================================================================
# Shadow Hull Computation (Pure Functions)
# =============================================================================

def _bbox_intersects_circle(
    points: Sequence[Point],
    cx: float,
    cy: float,
    radius: float,
) -> bool:
    """Check if polygon's bounding box intersects a circle's bounding square."""
    if not points:
        return False
    
    min_x = min(p[0] for p in points)
    max_x = max(p[0] for p in points)
    min_y = min(p[1] for p in points)
    max_y = max(p[1] for p in points)
    
    left = cx - radius
    right = cx + radius
    bottom = cy - radius
    top = cy + radius
    
    return max_x >= left and min_x <= right and max_y >= bottom and min_y <= top


def _extrude_point(
    point: Point,
    light_pos: Point,
    distance: float,
) -> Point:
    """Extrude a point away from light to given distance."""
    px, py = point
    lx, ly = light_pos
    dx = px - lx
    dy = py - ly
    dist = math.hypot(dx, dy)
    
    if dist < 1e-9:
        # Point is at light position, can't determine direction
        return point
    
    scale = distance / dist
    return (lx + dx * scale, ly + dy * scale)


def _compute_visible_edge_indices(
    points: Sequence[Point],
    light_pos: Point,
) -> list[tuple[int, int]]:
    """Find edges of polygon that face away from the light.
    
    Returns list of (start_idx, end_idx) for each shadow-casting edge.
    """
    n = len(points)
    if n < 3:
        return []
    
    lx, ly = light_pos
    
    # Compute winding
    area = _polygon_signed_area(points)
    outward_sign = 1.0 if area > 0 else -1.0
    
    edges: list[tuple[int, int]] = []
    
    for i in range(n):
        p0 = points[i]
        p1 = points[(i + 1) % n]
        
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            continue
        
        # Compute outward normal
        if outward_sign > 0:
            nx, ny = dy, -dx
        else:
            nx, ny = -dy, dx
        
        # Vector from edge midpoint to light
        mid_x = (p0[0] + p1[0]) * 0.5
        mid_y = (p0[1] + p1[1]) * 0.5
        to_light_x = lx - mid_x
        to_light_y = ly - mid_y
        
        # If dot product is negative, edge faces away from light
        dot = nx * to_light_x + ny * to_light_y
        if dot < 0:
            edges.append((i, (i + 1) % n))
    
    return edges


def compute_shadow_hull_for_occluder(
    occluder: Sequence[Point],
    light_pos: Point,
    params: ShadowParams,
) -> list[Polygon]:
    """Compute shadow hull(s) for a single occluder polygon.
    
    This extrudes each shadow-casting edge away from the light,
    creating quad shadow volumes.
    
    Args:
        occluder: Polygon points defining the occluder shape
        light_pos: Position of the light source (x, y)
        params: Shadow computation parameters
        
    Returns:
        List of shadow hull polygons (normalized quads)
    """
    if len(occluder) < 3:
        return []
    
    # Validate and clean input
    points: MutablePolygon = [
        (float(p[0]), float(p[1])) for p in occluder
    ]
    
    # Early cull if outside light radius
    if params.cull_outside_radius:
        lx, ly = light_pos
        if not _bbox_intersects_circle(points, lx, ly, params.light_radius):
            return []
    
    # Find shadow-casting edges
    edge_indices = _compute_visible_edge_indices(points, light_pos)
    if not edge_indices:
        return []
    
    extrusion = params.effective_extrusion()
    precision = params.round_precision
    hulls: list[Polygon] = []
    
    for start_idx, end_idx in edge_indices:
        p0 = points[start_idx]
        p1 = points[end_idx]
        
        # Extrude edge points
        far0 = _extrude_point(p0, light_pos, extrusion)
        far1 = _extrude_point(p1, light_pos, extrusion)
        
        # Create quad: near_a, near_b, far_b, far_a
        quad: MutablePolygon = [p0, p1, far1, far0]
        
        # Round for determinism
        rounded = tuple(
            (round(x, precision), round(y, precision))
            for x, y in quad
        )
        
        hulls.append(rounded)
    
    return hulls


def compute_shadow_hulls(
    occluders: Sequence[Sequence[Point]],
    light_pos: Point,
    params: ShadowParams | None = None,
) -> tuple[Polygon, ...]:
    """Compute shadow hulls for all occluders relative to a light.
    
    This is the main entry point for shadow geometry computation.
    
    Args:
        occluders: List of occluder polygons
        light_pos: Light position (x, y)
        params: Shadow parameters (uses defaults if None)
        
    Returns:
        Tuple of shadow hull polygons, deterministically sorted
    """
    if params is None:
        params = ShadowParams()
    
    lx, ly = float(light_pos[0]), float(light_pos[1])
    
    if params.light_radius <= 0:
        return ()
    
    all_hulls: list[Polygon] = []
    
    # Sort occluders for deterministic processing order
    # Use normalized form for sorting key
    indexed_occluders = [
        (i, normalize_polygon(occ, precision=params.round_precision))
        for i, occ in enumerate(occluders)
    ]
    indexed_occluders.sort(key=lambda x: x[1])
    
    for _, norm_occ in indexed_occluders:
        if len(norm_occ) < 3:
            continue
        
        hulls = compute_shadow_hull_for_occluder(norm_occ, (lx, ly), params)
        all_hulls.extend(hulls)
    
    # Sort hulls for deterministic output
    all_hulls.sort()
    
    # Apply limit
    if len(all_hulls) > params.max_hulls:
        all_hulls = all_hulls[:params.max_hulls]
    
    return tuple(all_hulls)


# =============================================================================
# Occlusion Segment Computation
# =============================================================================

@dataclass(frozen=True, slots=True)
class OcclusionSegment:
    """A line segment that blocks light.
    
    Represents an edge of an occluder that faces away from a light source.
    """
    start: Point
    end: Point
    occluder_id: int
    edge_index: int
    
    def length(self) -> float:
        """Compute segment length."""
        dx = self.end[0] - self.start[0]
        dy = self.end[1] - self.start[1]
        return math.hypot(dx, dy)
    
    def midpoint(self) -> Point:
        """Get segment midpoint."""
        return (
            (self.start[0] + self.end[0]) * 0.5,
            (self.start[1] + self.end[1]) * 0.5,
        )
    
    def to_tuple(self) -> tuple[Point, Point, int, int]:
        """Convert to tuple for hashing/sorting."""
        return (self.start, self.end, self.occluder_id, self.edge_index)


def compute_occlusion_segments(
    occluders: Sequence[Sequence[Point]],
    light_pos: Point,
    params: ShadowParams | None = None,
) -> tuple[OcclusionSegment, ...]:
    """Compute all occlusion segments for a light.
    
    Returns the edges of occluders that face away from the light,
    i.e., the edges that block light.
    
    Args:
        occluders: List of occluder polygons
        light_pos: Light position (x, y)
        params: Shadow parameters
        
    Returns:
        Tuple of OcclusionSegment, deterministically sorted
    """
    if params is None:
        params = ShadowParams()
    
    lx, ly = float(light_pos[0]), float(light_pos[1])
    
    if params.light_radius <= 0:
        return ()
    
    segments: list[OcclusionSegment] = []
    precision = params.round_precision
    
    # Process occluders in deterministic order
    # Use normalized form as the canonical ID (not original index)
    indexed_occluders = [
        (i, normalize_polygon(occ, precision=precision))
        for i, occ in enumerate(occluders)
    ]
    indexed_occluders.sort(key=lambda x: x[1])
    
    # Re-index based on sorted order for determinism
    for sorted_idx, (_, norm_occ) in enumerate(indexed_occluders):
        occ_id = sorted_idx  # Use sorted index, not original
        if len(norm_occ) < 3:
            continue
        
        # Cull distant occluders
        if params.cull_outside_radius:
            if not _bbox_intersects_circle(norm_occ, lx, ly, params.light_radius):
                continue
        
        # Find shadow-casting edges
        edge_indices = _compute_visible_edge_indices(norm_occ, (lx, ly))
        
        for edge_idx, (start_idx, end_idx) in enumerate(edge_indices):
            start = (
                round(norm_occ[start_idx][0], precision),
                round(norm_occ[start_idx][1], precision),
            )
            end = (
                round(norm_occ[end_idx][0], precision),
                round(norm_occ[end_idx][1], precision),
            )
            
            segments.append(OcclusionSegment(
                start=start,
                end=end,
                occluder_id=occ_id,
                edge_index=edge_idx,
            ))
    
    # Sort for determinism
    segments.sort(key=lambda s: s.to_tuple())
    
    return tuple(segments)


# =============================================================================
# Result Container with Digest
# =============================================================================

@dataclass
class ShadowGeometryResult:
    """Result of shadow geometry computation with metadata."""
    
    hulls: tuple[Polygon, ...]
    segments: tuple[OcclusionSegment, ...]
    light_pos: Point
    params: ShadowParams
    occluder_count: int
    
    def hull_digest(self) -> str:
        """Compute SHA-256 digest of hull data."""
        data = json.dumps(
            [list(h) for h in self.hulls],
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(data.encode("utf-8")).hexdigest()
    
    def segment_digest(self) -> str:
        """Compute SHA-256 digest of segment data."""
        data = json.dumps(
            [s.to_tuple() for s in self.segments],
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(data.encode("utf-8")).hexdigest()
    
    def full_digest(self) -> str:
        """Compute SHA-256 digest of full result."""
        data = {
            "hulls": [list(h) for h in self.hulls],
            "segments": [s.to_tuple() for s in self.segments],
            "light_pos": list(self.light_pos),
            "light_radius": self.params.light_radius,
            "occluder_count": self.occluder_count,
        }
        json_str = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()


def compute_shadow_geometry(
    occluders: Sequence[Sequence[Point]],
    light_pos: Point,
    params: ShadowParams | None = None,
) -> ShadowGeometryResult:
    """Compute complete shadow geometry including hulls and segments.
    
    This is the high-level entry point that computes both shadow hulls
    and occlusion segments.
    
    Args:
        occluders: List of occluder polygons
        light_pos: Light position (x, y)
        params: Shadow parameters
        
    Returns:
        ShadowGeometryResult with hulls, segments, and metadata
    """
    if params is None:
        params = ShadowParams()
    
    hulls = compute_shadow_hulls(occluders, light_pos, params)
    segments = compute_occlusion_segments(occluders, light_pos, params)
    
    return ShadowGeometryResult(
        hulls=hulls,
        segments=segments,
        light_pos=(float(light_pos[0]), float(light_pos[1])),
        params=params,
        occluder_count=len(occluders),
    )


# =============================================================================
# Validation Helpers
# =============================================================================

@dataclass
class ShadowGeometryValidationResult:
    """Result of validating shadow geometry output."""
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_shadow_hulls(hulls: Sequence[Polygon]) -> ShadowGeometryValidationResult:
    """Validate shadow hull output for invariants.
    
    Checks:
    1. Each hull has at least 3 vertices
    2. No NaN/Inf in coordinates
    3. Hulls are non-degenerate (non-zero area)
    """
    errors: list[str] = []
    warnings: list[str] = []
    
    for i, hull in enumerate(hulls):
        if len(hull) < 3:
            errors.append(f"hull[{i}]: Has {len(hull)} vertices (minimum 3)")
            continue
        
        for j, point in enumerate(hull):
            point_errors = validate_point(point, f"hull[{i}].vertex[{j}]")
            errors.extend(point_errors)
        
        if not errors:
            area = abs(_polygon_signed_area(hull))
            if area < 1e-9:
                warnings.append(f"hull[{i}]: Near-zero area ({area})")
    
    return ShadowGeometryValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def assert_shadow_hulls_valid(hulls: Sequence[Polygon], context: str = "") -> None:
    """Assert shadow hulls pass validation.
    
    Raises:
        AssertionError: If validation fails
    """
    result = validate_shadow_hulls(hulls)
    if not result.valid:
        prefix = f"[{context}] " if context else ""
        error_msg = f"{prefix}Shadow hull validation failed:\n"
        error_msg += "\n".join(f"  - {e}" for e in result.errors)
        raise AssertionError(error_msg)
