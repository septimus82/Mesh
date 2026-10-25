"""Height-aware movement for HD-2D scenes: floors, stairs and bridges (Milestone 16 Stage 3).

The collision world is built from the colliders authored in the structures' GLB files (``engine.hd2d.glb``:
``solid``, ``floor`` and ``wall`` nodes), placed like the structures, plus the scene's ground (solid). Positions are
metres (Mesh px / 32): x east, y north, z height. A character is its 2D footprint (the movement collider) and a body
``BODY`` m tall standing at an elevation.

One rule decides where a character may stand (``World.stand``), and movement, the NPC navigation grid and loading
all use it:

- it needs a walkable surface under its feet within ``STEP`` m of its current elevation, and stands on it. Floors
  connect only where their surfaces meet within a step: stairs and ramps do; a platform's edge does not (no
  falling, no jumping up);
- nothing may be inside its body: no solid's surface above its feet (it would be inside the solid), no floor lower
  than its head above it (a bridge deck is fine overhead only with headroom), no wall box overlapping it.

Movement is axis-separated like the 2D sweep, so characters slide along walls. The scene's 2D solids (wall tiles,
solid objects) still apply, to characters on their level. 2D scenes never build a world.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable

from engine.hd2d.settings import PIXELS_PER_METRE, Hd2dSettings

if TYPE_CHECKING:  # the reader is only needed where models are loaded (engine.hd2d.runtime)
    from engine.hd2d.glb import Model

STEP = 0.35  # m: the highest a character steps up or down without stairs
BODY = 1.5  # m: a character's standing height (a 48 px sprite)
NAV_CELL = 0.5  # m: the navigation grid's cell
NAV_HALF = (0.3, 0.19)  # m: half the footprint the navigation grid plans for (a character's feet box)
_BUCKET = 2.0  # m: the spatial index's cell


@dataclass(frozen=True)
class Surface:
    """One walkable triangle: z = a x + b y + c inside it."""

    floor: str  # "<structure id>/<collider node>" or "ground"
    solid: bool  # solid underneath (a platform) or open (a bridge deck)
    corners: tuple[tuple[float, float, float], ...]
    plane: tuple[float, float, float]
    box: tuple[float, float, float, float]  # x0, y0, x1, y1

    def height(self, x: float, y: float) -> float | None:
        (ax, ay, _), (bx, by, _), (cx, cy, _) = self.corners
        x0, y0, x1, y1 = self.box
        if x < x0 - 1e-6 or x > x1 + 1e-6 or y < y0 - 1e-6 or y > y1 + 1e-6:
            return None
        d1 = (x - bx) * (ay - by) - (ax - bx) * (y - by)
        d2 = (x - cx) * (by - cy) - (bx - cx) * (y - cy)
        d3 = (x - ax) * (cy - ay) - (cx - ax) * (y - ay)
        if (d1 < -1e-9 or d2 < -1e-9 or d3 < -1e-9) and (d1 > 1e-9 or d2 > 1e-9 or d3 > 1e-9):
            return None
        a, b, c = self.plane
        return a * x + b * y + c


@dataclass(frozen=True)
class Wall:
    name: str
    lo: tuple[float, float, float]
    hi: tuple[float, float, float]


def _surface(floor: str, solid: bool, corners: tuple[tuple[float, float, float], ...]) -> Surface | None:
    (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = corners
    det = (x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)
    if abs(det) < 1e-12:
        return None  # seen edge-on from above: nothing to stand on
    a = ((z2 - z1) * (y3 - y1) - (z3 - z1) * (y2 - y1)) / det
    b = ((x2 - x1) * (z3 - z1) - (x3 - x1) * (z2 - z1)) / det
    xs, ys = (x1, x2, x3), (y1, y2, y3)
    return Surface(floor, solid, corners, (a, b, z1 - a * x1 - b * y1), (min(xs), min(ys), max(xs), max(ys)))


def _place(p: tuple[float, float, float], at: tuple[float, float, float], turn: float, scale: float) -> tuple[float, float, float]:
    c, s = math.cos(math.radians(turn)), math.sin(math.radians(turn))
    return (at[0] + (c * p[0] - s * p[1]) * scale, at[1] + (s * p[0] + c * p[1]) * scale, at[2] + p[2] * scale)


def elevation_of(sprite: Any) -> float:
    """A sprite's elevation in metres (its entity's ``elevation`` px)."""
    data = getattr(sprite, "mesh_entity_data", None) or {}
    value = data.get("elevation", 0.0) if isinstance(data, dict) else 0.0
    return float(value) / PIXELS_PER_METRE if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


class World:
    def __init__(self, settings: Hd2dSettings, models: dict[str, Model]) -> None:
        self.surfaces: list[Surface] = []
        self.walls: list[Wall] = []
        for st in settings.structures:
            at = (st.x / PIXELS_PER_METRE, st.y / PIXELS_PER_METRE, st.elevation / PIXELS_PER_METRE)
            for col in models[st.model].colliders:
                floor = f"{st.id}/{col.node}"
                if col.kind == "wall":
                    corners = [_place((x, y, z), at, st.rotation, st.scale)
                               for x in (col.lo[0], col.hi[0]) for y in (col.lo[1], col.hi[1]) for z in (col.lo[2], col.hi[2])]
                    xs, ys, zs = [p[0] for p in corners], [p[1] for p in corners], [p[2] for p in corners]
                    self.walls.append(Wall(floor, (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))))
                    continue
                for a, b, c in col.triangles:
                    placed = (_place(a, at, st.rotation, st.scale), _place(b, at, st.rotation, st.scale),
                              _place(c, at, st.rotation, st.scale))
                    surface = _surface(floor, col.kind == "solid", placed)
                    if surface is not None:
                        self.surfaces.append(surface)
        g = settings.ground
        if g is not None:  # the ground: solid, the whole of it walkable
            z = g.elevation / PIXELS_PER_METRE
            (x0, y0), (x1, y1) = [(v[0] / PIXELS_PER_METRE, v[1] / PIXELS_PER_METRE) for v in (g.lo, g.hi)]
            for tri in (((x0, y0, z), (x1, y0, z), (x1, y1, z)), ((x0, y0, z), (x1, y1, z), (x0, y1, z))):
                surface = _surface("ground", True, tri)
                if surface is not None:
                    self.surfaces.append(surface)
        self._index: dict[tuple[int, int], list[Surface]] = {}
        for surface in self.surfaces:
            x0, y0, x1, y1 = surface.box
            for i in range(math.floor(x0 / _BUCKET), math.floor(x1 / _BUCKET) + 1):
                for j in range(math.floor(y0 / _BUCKET), math.floor(y1 / _BUCKET) + 1):
                    self._index.setdefault((i, j), []).append(surface)
        boxes = [s.box for s in self.surfaces]
        self.bounds = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes),
                       max(b[3] for b in boxes)) if boxes else (0.0, 0.0, 0.0, 0.0)
        self._nav: dict[tuple[int, int], list[float]] | None = None

    # ------------------------------------------------------------------ the rule
    def heights_at(self, x: float, y: float) -> list[tuple[float, Surface]]:
        out = []
        for surface in self._index.get((math.floor(x / _BUCKET), math.floor(y / _BUCKET)), ()):
            h = surface.height(x, y)
            if h is not None:
                out.append((h, surface))
        return out

    def stand(self, x: float, y: float, z: float, half_w: float, half_h: float) -> tuple[float, str] | None:
        """Where a character whose feet box is centred at (x, y) and who stands at ``z`` stands: (elevation,
        floor), or None if it can't be there."""
        best: tuple[float, Surface] | None = None
        for h, surface in self.heights_at(x, y):
            if abs(h - z) <= STEP and (best is None or h > best[0]):
                best = (h, surface)
        if best is None:
            return None  # nothing to stand on within a step: a ledge, or the edge of the world
        h = best[0]
        for px, py in ((x, y), (x - half_w, y - half_h), (x + half_w, y - half_h), (x - half_w, y + half_h),
                       (x + half_w, y + half_h)):
            for top, surface in self.heights_at(px, py):
                if top > h + STEP and (surface.solid or top < h + BODY):
                    return None  # inside a solid, or a floor too low to fit under
        for wall in self.walls:
            if (wall.lo[0] < x + half_w and wall.hi[0] > x - half_w and wall.lo[1] < y + half_h
                    and wall.hi[1] > y - half_h and wall.lo[2] < h + BODY and wall.hi[2] > h + STEP):
                return None
        return h, best[1].floor

    # ------------------------------------------------------------------ moving a sprite
    def move(self, sprite: Any, delta: tuple[float, float], solids: Iterable[Any] | None) -> None:
        """Move ``sprite`` by ``delta`` (px) as far as the floors, walls and its level's 2D solids allow, and set its
        elevation to the floor it ends on (``mesh_entity_data["elevation"]``, px; saved with the game).

        Long moves (a slow frame) go in steps no longer than half the footprint's smaller side, so every wall,
        railing and gap on the way is met by some step: nothing is tunnelled through. A normal frame is one step."""
        from engine.physics_runtime import _sprite_to_aabb  # noqa: PLC0415

        box = _sprite_to_aabb(sprite)
        longest = max(abs(delta[0]), abs(delta[1]))
        steps = max(1, math.ceil(longest / max(1.0, min(box.w, box.h) / 2)))
        solids = list(solids or ())
        for _ in range(steps):
            self._step(sprite, (delta[0] / steps, delta[1] / steps), solids)

    def _step(self, sprite: Any, delta: tuple[float, float], solids: list[Any]) -> None:
        from engine.physics_runtime import _sprite_to_aabb, move_entity_with_physics  # noqa: PLC0415

        box = _sprite_to_aabb(sprite)
        hw, hh = box.w / 2 / PIXELS_PER_METRE, box.h / 2 / PIXELS_PER_METRE
        x, y, z = box.x / PIXELS_PER_METRE, box.y / PIXELS_PER_METRE, elevation_of(sprite)
        dx, dy = delta
        if dx and self.stand(x + dx / PIXELS_PER_METRE, y, z, hw, hh) is None:
            dx = 0.0
        if dy and self.stand(x + dx / PIXELS_PER_METRE, y + dy / PIXELS_PER_METRE, z, hw, hh) is None:
            dy = 0.0
        if not dx and not dy:
            self._settle(sprite, x, y, z, hw, hh)
            return
        start = (sprite.center_x, sprite.center_y)
        level = [s for s in solids if s is not sprite and abs(elevation_of(s) - z) < BODY]
        move_entity_with_physics(sprite, (dx, dy), level)  # the scene's 2D solids on this level
        moved = (sprite.center_x - start[0]) / PIXELS_PER_METRE, (sprite.center_y - start[1]) / PIXELS_PER_METRE
        if not self._settle(sprite, x + moved[0], y + moved[1], z, hw, hh):
            sprite.center_x, sprite.center_y = start  # (never expected: each axis was checked)

    def _settle(self, sprite: Any, x: float, y: float, z: float, hw: float, hh: float) -> bool:
        where = self.stand(x, y, z, hw, hh)
        if where is None:
            return False
        data = getattr(sprite, "mesh_entity_data", None)
        if isinstance(data, dict):
            data["elevation"] = round(where[0] * PIXELS_PER_METRE, 3)
        sprite.mesh_hd2d_floor = where[1]
        return True

    # ------------------------------------------------------------------ navigation (NPCs)
    def _nav_grid(self) -> dict[tuple[int, int], list[float]]:
        """Every cell centre's standing heights (several where floors overlap: under and on a bridge)."""
        if self._nav is None:
            self._nav = {}
            x0, y0, x1, y1 = self.bounds
            for i in range(int((x1 - x0) / NAV_CELL)):
                for j in range(int((y1 - y0) / NAV_CELL)):
                    x, y = x0 + (i + 0.5) * NAV_CELL, y0 + (j + 0.5) * NAV_CELL
                    heights = sorted({round(stood[0], 3) for h, _ in self.heights_at(x, y)
                                      if (stood := self.stand(x, y, h, *NAV_HALF)) is not None})
                    if heights:
                        self._nav[(i, j)] = heights
        return self._nav

    def walkable(self) -> int:
        """How many places (navigation cells, counting each floor of a stack) a character can stand."""
        return sum(len(heights) for heights in self._nav_grid().values())

    def _cell(self, x: float, y: float) -> tuple[int, int]:
        return int((x - self.bounds[0]) // NAV_CELL), int((y - self.bounds[1]) // NAV_CELL)

    def _centre(self, i: int, j: int) -> tuple[float, float]:
        return self.bounds[0] + (i + 0.5) * NAV_CELL, self.bounds[1] + (j + 0.5) * NAV_CELL

    def path(self, start: tuple[float, float, float], goal: tuple[float, float, float]) -> list[tuple[float, float, float]]:
        """A walkable route (metres) from start to goal across floors (A* over the navigation grid: neighbouring
        cells connect where a character can step between them), or [] if there is none."""
        grid = self._nav_grid()

        def node(p: tuple[float, float, float]) -> tuple[int, int, float] | None:
            heights = grid.get(self._cell(p[0], p[1]))
            if not heights:
                return None
            h = min(heights, key=lambda v: abs(v - p[2]))
            return (*self._cell(p[0], p[1]), h) if abs(h - p[2]) <= STEP else None

        a, b = node(start), node(goal)
        if a is None or b is None:
            return []
        frontier: list[tuple[float, int, tuple[int, int, float]]] = [(0.0, 0, a)]
        came: dict[tuple[int, int, float], tuple[int, int, float] | None] = {a: None}
        cost = {a: 0.0}
        counter = 0
        while frontier:
            _, _, current = heapq.heappop(frontier)
            if current == b:
                break
            i, j, h = current
            cx, cy = self._centre(i, j)
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                for h2 in grid.get((i + di, j + dj), ()):
                    if abs(h2 - h) > STEP:
                        continue
                    if di and dj and not all(any(abs(v - h) <= STEP for v in grid.get(c, ())) for c in ((i + di, j), (i, j + dj))):
                        continue  # no cutting corners past a wall or a ledge
                    nx, ny = self._centre(i + di, j + dj)
                    if self.stand((cx + nx) / 2, (cy + ny) / 2, h, *NAV_HALF) is None:
                        continue
                    step_cost = cost[current] + math.hypot(nx - cx, ny - cy, h2 - h)
                    nxt = (i + di, j + dj, h2)
                    if step_cost < cost.get(nxt, math.inf):
                        cost[nxt], came[nxt] = step_cost, current
                        bx, by = self._centre(b[0], b[1])
                        counter += 1
                        heapq.heappush(frontier, (step_cost + math.hypot(bx - nx, by - ny, b[2] - h2), counter, nxt))
        if b not in came:
            return []
        route: list[tuple[float, float, float]] = []
        at: tuple[int, int, float] | None = b
        while at is not None:
            route.append((*self._centre(at[0], at[1]), at[2]))
            at = came[at]
        route.reverse()
        return route[1:] + [goal]
