"""
Pure model for deterministic physics (movement, collision, sensors).

This module provides rendering-agnostic physics primitives and algorithms
for collision detection and resolution. It's designed to be:

- **Deterministic**: Same inputs always produce same outputs (replay-safe)
- **Pure**: No side effects, no Arcade/GL dependencies
- **Testable**: Can be unit tested without graphics context

Key Components:
    - :class:`Aabb`: Axis-aligned bounding box for collision shapes
    - :class:`Hit`: Collision result with contact information
    - :class:`MoveRequest`/:class:`MoveResult`: Movement transaction types
    - :func:`sweep_axis_separate`: Classic platformer collision resolution

Physics Pipeline (per frame):
    1. Collect movement requests from behaviours
    2. For each request, call :func:`sweep_axis_separate`
    3. Apply final positions to entities
    4. Process sensor overlaps via :func:`compute_sensor_events`

Example::

    # Create a bounding box for an entity
    entity_box = Aabb(x=100, y=50, w=32, h=48)

    # Check intersection with a wall
    wall_box = Aabb(x=120, y=50, w=16, h=64)
    overlap = entity_box.intersection(wall_box)
    if overlap:
        print(f"Collision! Overlap area: {overlap.w * overlap.h}")

See Also:
    - :mod:`engine.physics_runtime` for integration with Arcade sprites
    - :mod:`engine.sensors_runtime` for trigger zone handling
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Protocol, Tuple, Sequence


@dataclass
class Aabb:
    """Axis-Aligned Bounding Box for collision detection.

    Represents a rectangle that cannot be rotated, making collision
    detection fast and simple. The box is defined by its center point
    and dimensions.

    Attributes:
        x: Center X coordinate in world space.
        y: Center Y coordinate in world space.
        w: Width of the box in pixels.
        h: Height of the box in pixels.

    Properties:
        left, right, top, bottom: Edge coordinates.

    Example::

        # Create a 32x48 box centered at (100, 50)
        box = Aabb(100, 50, 32, 48)

        # Check edges
        print(f"Left edge: {box.left}")    # 84.0
        print(f"Right edge: {box.right}")  # 116.0

        # Move the box
        moved = box.move(10, -5)  # New box at (110, 45)
    """
    x: float  # Center X
    y: float  # Center Y
    w: float  # Width
    h: float  # Height

    @property
    def left(self) -> float:
        return self.x - self.w / 2

    @property
    def right(self) -> float:
        return self.x + self.w / 2

    @property
    def top(self) -> float:
        return self.y + self.h / 2

    @property
    def bottom(self) -> float:
        return self.y - self.h / 2

    def move(self, dx: float, dy: float) -> Aabb:
        """Return a new AABB offset by the given delta.

        Args:
            dx: Horizontal offset in pixels.
            dy: Vertical offset in pixels.

        Returns:
            New Aabb instance at the offset position (original unchanged).
        """
        return Aabb(self.x + dx, self.y + dy, self.w, self.h)

    def intersection(self, other: Aabb) -> Optional[Aabb]:
        """Compute the overlapping region between two AABBs.

        Args:
            other: Another AABB to test intersection with.

        Returns:
            A new Aabb representing the overlap region, or None if no overlap.
            The returned box's area indicates penetration depth.
        """
        x1 = max(self.left, other.left)
        y1 = max(self.bottom, other.bottom)
        x2 = min(self.right, other.right)
        y2 = min(self.top, other.top)

        if x1 < x2 and y1 < y2:
            return Aabb((x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1)
        return None


@dataclass
class Circle:
    """Circle collider shape centered in world space."""

    x: float
    y: float
    radius: float

    def bounds(self) -> Aabb:
        r = max(0.0, float(self.radius))
        d = r * 2.0
        return Aabb(float(self.x), float(self.y), d, d)


def circle_circle_overlap(
    c1: Tuple[float, float],
    r1: float,
    c2: Tuple[float, float],
    r2: float,
) -> bool:
    """Return True when two circles overlap (strict, non-touching)."""
    rr = max(0.0, float(r1)) + max(0.0, float(r2))
    if rr <= 0.0:
        return False
    dx = float(c1[0]) - float(c2[0])
    dy = float(c1[1]) - float(c2[1])
    return (dx * dx) + (dy * dy) < (rr * rr)


def circle_aabb_overlap(
    circle_center: Tuple[float, float],
    radius: float,
    aabb: Aabb,
) -> bool:
    """Return True when circle overlaps AABB (strict, non-touching)."""
    r = max(0.0, float(radius))
    if r <= 0.0:
        return False
    cx = float(circle_center[0])
    cy = float(circle_center[1])
    nearest_x = min(max(cx, aabb.left), aabb.right)
    nearest_y = min(max(cy, aabb.bottom), aabb.top)
    dx = cx - nearest_x
    dy = cy - nearest_y
    return (dx * dx) + (dy * dy) < (r * r)


@dataclass
class Hit:
    """Describes a collision detected during movement.

    Attributes:
        kind: Type of object hit ("tile", "entity", or "sensor").
        target_id: Identifier of the hit object (tile coords, entity name, etc.).
        normal: Surface normal at contact point as (nx, ny). Points away from
            the surface that was hit:
            - (-1, 0): Hit right side of obstacle (moving right)
            - (1, 0): Hit left side (moving left)
            - (0, -1): Hit top (moving up)
            - (0, 1): Hit bottom (moving down)
        overlap: Optional Aabb representing the penetration region.
    """
    kind: str  # "tile", "entity", "sensor"
    target_id: str
    normal: Tuple[float, float] = (0.0, 0.0)
    overlap: Optional[Aabb] = None


@dataclass
class MoveRequest:
    """Request to move an entity by a given delta.

    Used as input to :func:`sweep_axis_separate` for collision resolution.

    Attributes:
        entity_id: Unique identifier for the moving entity.
        from_pos: Starting center position as (x, y).
        delta: Requested movement as (dx, dy) in pixels.
        aabb: The entity's collision box at from_pos.
        sensor_query: If True, also report sensor overlaps (triggers).
    """
    entity_id: str
    from_pos: Tuple[float, float]  # Center (x, y)
    delta: Tuple[float, float]     # (dx, dy)
    aabb: Aabb                     # Current AABB at from_pos
    sensor_query: bool = False     # If True, also returns sensor overlaps


@dataclass
class MoveResult:
    """Result of processing a movement request through collision detection.

    Attributes:
        final_pos: The resolved position after collision response.
        hit_x: True if horizontal movement was blocked.
        hit_y: True if vertical movement was blocked.
        hits: Tuple of :class:`Hit` objects describing collisions.
        sensor_overlaps: IDs of sensors overlapped at final position.
    """
    final_pos: Tuple[float, float]
    hit_x: bool
    hit_y: bool
    hits: Tuple[Hit, ...] = ()
    sensor_overlaps: Tuple[str, ...] = ()

class TileQuery(Protocol):
    """Protocol for querying blocking tiles in a region.

    Implementations should return all solid tile AABBs that overlap
    the query region. Used by physics to detect wall collisions.
    """
    def __call__(self, aabb: Aabb) -> List[Aabb]:
        """Return list of blocking tile AABBs overlapping the given AABB."""


class SensorQuery(Protocol):
    """Protocol for querying trigger zones/sensors in a region.

    Implementations return (id, aabb) pairs for each sensor overlapping
    the query region. Used for detecting zone enter/exit events.
    """
    def __call__(self, aabb: Aabb) -> List[Tuple[str, Aabb]]:
        """Return list of (id, Aabb) for sensors overlapping the given AABB."""


def sweep_axis_separate(
    req: MoveRequest,
    query_tiles: TileQuery,
) -> MoveResult:
    """Resolve movement collision using axis-separated sweep.

    This implements classic platformer physics: move on X axis first,
    resolve any collisions by snapping to wall edges, then repeat for Y.
    This approach prevents corner-cutting through diagonal walls.

    Algorithm:
        1. Move AABB by (dx, 0)
        2. Query overlapping walls
        3. If collision: snap to wall edge based on movement direction
        4. Move AABB by (0, dy)
        5. Query overlapping walls
        6. If collision: snap to wall edge
        7. Return final position and collision info

    Args:
        req: Movement request containing entity, start pos, delta, and AABB.
        query_tiles: Callback returning blocking tiles in a region.

    Returns:
        MoveResult with final position, hit flags, and collision details.

    Example::

        def my_tile_query(aabb: Aabb) -> List[Aabb]:
            # Return solid tiles overlapping aabb
            return tilemap.get_solid_tiles_in_region(aabb)

        request = MoveRequest(
            entity_id="player",
            from_pos=(100, 50),
            delta=(5, -2),
            aabb=Aabb(100, 50, 32, 48)
        )
        result = sweep_axis_separate(request, my_tile_query)
        player.center_x, player.center_y = result.final_pos
    """
    dx, dy = req.delta
    curr_aabb = req.aabb
    
    hits: List[Hit] = []
    hit_x = False
    hit_y = False

    # 1. Move X
    if abs(dx) > 1e-9:
        # Proposed X move
        next_aabb_x = curr_aabb.move(dx, 0)
        
        # Check collisions
        walls_x = query_tiles(next_aabb_x)
        
        if walls_x:
            hit_x = True
            
            # Snap logic matches SceneController
            if dx > 0:
                # Moving right: snap to left-most wall edge
                min_left = min(w.left for w in walls_x)
                # New right = min_left -> New center = min_left - w/2
                snapped_x = min_left - curr_aabb.w / 2
                
                # Record hit
                for w in walls_x:
                    # Approximation: we only care about the one we hit first? 
                    # SceneController logic grabs ALL overlapping and takes min.
                    # We'll just record generic hits for now as we don't use them for physics response other than snap
                    hits.append(Hit("tile", "wall", (-1.0, 0.0), overlap=None))
                
                curr_aabb = Aabb(snapped_x, curr_aabb.y, curr_aabb.w, curr_aabb.h)
                
            elif dx < 0:
                # Moving left: snap to right-most wall edge
                max_right = max(w.right for w in walls_x)
                snapped_x = max_right + curr_aabb.w / 2
                
                hits.append(Hit("tile", "wall", (1.0, 0.0), overlap=None))
                curr_aabb = Aabb(snapped_x, curr_aabb.y, curr_aabb.w, curr_aabb.h)
        else:
            # No hit
            curr_aabb = next_aabb_x

    # 2. Move Y
    if abs(dy) > 1e-9:
        next_aabb_y = curr_aabb.move(0, dy)
        walls_y = query_tiles(next_aabb_y)
        
        if walls_y:
            hit_y = True
            if dy > 0:
                # Moving up: snap to bottom of wall
                min_bottom = min(w.bottom for w in walls_y)
                snapped_y = min_bottom - curr_aabb.h / 2
                
                hits.append(Hit("tile", "wall", (0.0, -1.0), overlap=None))
                curr_aabb = Aabb(curr_aabb.x, snapped_y, curr_aabb.w, curr_aabb.h)

            elif dy < 0:
                # Moving down: snap to top of wall
                max_top = max(w.top for w in walls_y)
                snapped_y = max_top + curr_aabb.h / 2
                
                hits.append(Hit("tile", "wall", (0.0, 1.0), overlap=None))
                curr_aabb = Aabb(curr_aabb.x, snapped_y, curr_aabb.w, curr_aabb.h)
        else:
            curr_aabb = next_aabb_y

    return MoveResult(
        final_pos=(curr_aabb.x, curr_aabb.y),
        hit_x=hit_x,
        hit_y=hit_y,
        hits=tuple(hits)
    )

def compute_sensor_events(
    prev_overlaps: Sequence[str],
    next_overlaps: Sequence[str]
) -> Tuple[List[str], List[str]]:
    """Compute which sensors were entered or exited between frames.

    Compares previous and current sensor overlaps to determine zone
    transitions. Used to trigger enter/exit events for trigger zones.

    Args:
        prev_overlaps: Sensor IDs overlapped in the previous frame.
        next_overlaps: Sensor IDs overlapped in the current frame.

    Returns:
        Tuple of (entered, exited) where:
        - entered: Sorted list of sensor IDs newly overlapped
        - exited: Sorted list of sensor IDs no longer overlapped

    Example::

        prev = ["zone_a", "zone_b"]
        curr = ["zone_b", "zone_c"]
        entered, exited = compute_sensor_events(prev, curr)
        # entered = ["zone_c"]
        # exited = ["zone_a"]
    """
    prev_set = set(prev_overlaps)
    next_set = set(next_overlaps)

    entered = sorted(list(next_set - prev_set))
    exited = sorted(list(prev_set - next_set))

    return entered, exited


def aabb_at(pos: Tuple[float, float], w: float, h: float) -> Aabb:
    """Create an AABB centered at the given position.

    Convenience factory for creating collision boxes from entity positions.

    Args:
        pos: Center position as (x, y).
        w: Width of the box.
        h: Height of the box.

    Returns:
        New Aabb instance centered at pos with given dimensions.
    """
    return Aabb(pos[0], pos[1], w, h)
