"""Scattered decoration for HD-2D rooms (Milestone 20D): grass, flowers, bushes, reeds, rocks and fallen branches over
the ground, many of them, cheaply.

A room's scatter is ``settings.hd2d.scatter``: for each asset, its instances as ``[x, y, turn, size]`` (px, px,
degrees 0-359, hundredths of the asset's size), sorted, so the same scatter always writes the same text.

    "scatter": {"grass_tuft": [[320, 96, 40, 104], ...], "rock_medium": [[512, 640, 275, 90]]}

- **Explicit, never regenerated.** Instances are stored where they were put, not as a seed and rules: loading a
  room shows exactly what was saved, and nothing moves when the rules or the code that scatters change.
- **Attached to the ground.** An instance has no height of its own: it stands on the ground under it (the sculpted
  ground's, else the plain ground's elevation), wherever that is now. Sculpting under one moves it up or down with
  the ground, never sideways; it never floats or sinks. Its placement rules (slope, material, water) are checked
  when it is placed, not again: ``out_of_rule`` says which ones later edits left standing where they couldn't now be
  put.
- **Decoration, mostly.** Characters walk through everything but the assets marked ``blocks`` (the boulder), which
  block like a structure's wall; ``obstructions`` says when one stands where people need to pass.
- **Brushes** (``brush``): a dab fills the brush's circle up to a density (instances a square metre), choosing among a
  collection's assets by weight, at random but from a seed (the same dabs give the same scatter), keeping a minimum
  spacing, in clumps (value noise), and only where the rules allow; or thins (removes a share) or removes. Studio,
  the CLI and AI scatter through ``engine.project_ops`` with these.
"""

from __future__ import annotations

import functools
import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

PX = 32.0  # px a metre
KIT = "assets/hd2d_starter/scatter"
SHEET = f"{KIT}/foliage.png"  # the sprites: 48 x 48 px cells (tooling/hd2d_assets/scatter_art.py)
CELL_PX = 48
MAX_INSTANCES = 50000  # a room's scatter, all assets (a 128 x 128 m meadow at three a square metre)
PER_DAB = 1500  # the most one dab adds: a huge dense brush fills as it moves, never freezing on one click
MATERIALS = ("grass", "earth", "stone", "mud", "sand")  # (engine.hd2d.terrain.MATERIALS)


@dataclass(frozen=True)
class Asset:
    """One thing to scatter. ``cell``: its sprite's cell in the sheet (sprites stand upright, facing the camera), or
    ``model``: a GLB (rocks, the branch: lit and shadowed like structures). ``spacing`` m between two instances'
    centres (two things: the mean of theirs); ``size`` the range of sizes (a share of drawn size); ``slope`` the steepest
    ground (degrees) and ``on`` the materials it is put on by default; ``shore``: may stand in water this shallow
    (m: reeds); ``blocks``: characters can't walk through it; ``shadow``: casts a shadow (models)."""

    id: str
    name: str
    cell: tuple[int, ...] | None = None  # its variants (an instance's is chosen by where it stands)
    model: str | None = None
    spacing: float = 0.3
    size: tuple[float, float] = (0.8, 1.2)
    slope: float = 35.0
    on: tuple[str, ...] = ("grass",)
    shore: float = 0.0
    blocks: bool = False
    shadow: bool = False


ASSETS: dict[str, Asset] = {a.id: a for a in (
    Asset("grass_tuft", "Grass tuft", cell=(0, 1, 2), spacing=0.16, size=(0.75, 1.15)),
    Asset("grass_tall", "Tall grass", cell=(3, 4), spacing=0.2),
    Asset("grass_dry", "Dry grass", cell=(5, 6), spacing=0.35, on=("grass", "earth", "sand")),
    Asset("flowers_yellow", "Yellow flowers", cell=(7, 8), spacing=0.4),
    Asset("flowers_pink", "Pink flowers", cell=(9, 10), spacing=0.4),
    Asset("bush", "Bush", cell=(11, 12), spacing=1.1, size=(0.9, 1.45), slope=30.0),
    Asset("bush_berries", "Berry bush", cell=(13,), spacing=0.9, size=(0.85, 1.15), slope=30.0),
    Asset("reeds", "Reeds", cell=(14, 15), spacing=0.3, size=(0.7, 1.2), on=("grass", "mud", "sand"), shore=0.3),
    Asset("reeds_cattail", "Cattails", cell=(16,), spacing=0.35, on=("grass", "mud", "sand"), shore=0.3),
    Asset("rock_small", "Small rock", model=f"{KIT}/rock_small.glb", spacing=0.5, size=(0.8, 1.6), slope=40.0,
          on=MATERIALS, shadow=True),
    Asset("rock_medium", "Rock", model=f"{KIT}/rock_medium.glb", spacing=1.0, size=(0.75, 1.3), slope=40.0,
          on=MATERIALS, shadow=True),
    Asset("boulder", "Boulder", model=f"{KIT}/boulder.glb", spacing=2.2, size=(0.8, 1.2), slope=45.0,
          on=MATERIALS, blocks=True, shadow=True),
    Asset("fallen_branch", "Fallen branch", model=f"{KIT}/fallen_branch.glb", spacing=1.6, size=(0.8, 1.2),
          slope=12.0, on=("grass", "earth", "mud"), shadow=True),
)}
WIDEST = max(a.spacing for a in ASSETS.values())  # m: the most two instances keep apart
COLLECTIONS: dict[str, dict[str, float]] = {  # name -> asset weights: what a brush scatters together
    "Meadow": {"grass_tuft": 6, "grass_tall": 3, "flowers_yellow": 1, "flowers_pink": 1},
    "Wildflowers": {"flowers_yellow": 3, "flowers_pink": 3, "grass_tuft": 2},
    "Pond edge": {"reeds": 3, "reeds_cattail": 2, "grass_tall": 2},
    "Shrubs": {"bush": 3, "bush_berries": 1},
    "Rocks": {"rock_small": 5, "rock_medium": 2},
    "Deadfall": {"grass_dry": 5, "fallen_branch": 1, "rock_small": 1},
    **{a.name: {a.id: 1.0} for a in ASSETS.values()},
}
DENSITY = {"Meadow": 2.5, "Wildflowers": 1.5, "Pond edge": 3.0, "Shrubs": 0.25, "Rocks": 0.6, "Deadfall": 0.8}


class ScatterError(ValueError):
    """Scatter settings or a brush that can't be used."""


# ---------------------------------------------------------------------- storage
def parse_scatter(raw: Any, where: str = "settings.hd2d.scatter") -> dict[str, list[tuple[int, int, int, int]]]:
    """``settings.hd2d.scatter`` checked: known assets, whole-number instances in range, not too many."""
    if not isinstance(raw, dict):
        raise ScatterError(f"{where} must be an object of asset ids to [[x, y, turn, size], ...]")
    out: dict[str, list[tuple[int, int, int, int]]] = {}
    total = 0
    for asset, items in raw.items():
        if asset not in ASSETS:
            raise ScatterError(f"{where} has an unknown asset '{asset}' (one of: {', '.join(ASSETS)})")
        if not isinstance(items, list):
            raise ScatterError(f"{where}.{asset} must be a list of [x, y, turn, size]")
        rows = []
        for k, item in enumerate(items):
            if not (isinstance(item, list) and len(item) == 4 and all(type(v) is int for v in item)):
                raise ScatterError(f"{where}.{asset}[{k}] must be [x, y, turn, size], whole numbers (got {item!r})")
            x, y, turn, size = item
            if not (-1_000_000 <= x <= 1_000_000 and -1_000_000 <= y <= 1_000_000 and 0 <= turn < 360
                    and 10 <= size <= 400):
                raise ScatterError(f"{where}.{asset}[{k}] is out of range: x, y px; turn 0-359; size 10-400")
            rows.append((x, y, turn, size))
        total += len(rows)
        if rows:
            out[asset] = rows
    if total > MAX_INSTANCES:
        raise ScatterError(f"{where} holds {total} instances; a room holds at most {MAX_INSTANCES}")
    return out


def stored(instances: dict[str, list[tuple[int, int, int, int]]]) -> dict[str, list[list[int]]]:
    """Instances as saved: assets in ``ASSETS`` order, each sorted by y then x; none: nothing."""
    return {a: [list(r) for r in sorted(instances[a], key=lambda r: (r[1], r[0], r[2], r[3]))]
            for a in ASSETS if instances.get(a)}


# ---------------------------------------------------------------------- the ground and the rules
@dataclass
class Ground:
    """What the brush asks of a room (all px): the ground's height and upright-ness at a point (None off the
    ground), its material, the water there (its level, or None), and whether a structure stands there."""

    surface: Callable[[float, float], tuple[float, float] | None]
    material: Callable[[float, float], str] = lambda x, y: "grass"
    water: Callable[[float, float], float | None] = lambda x, y: None
    structure: Callable[[float, float], bool] = lambda x, y: False  # on a structure, or where people step on and off


def ground_for(terrain: Any, flat: tuple[tuple[float, float], tuple[float, float], float] | None,
               waters: list[tuple[Any, tuple[float, float], float]],
               footprints: list[tuple[float, float, float, float, float]], margin: float = 0.3 * PX,
               spots: Iterable[tuple[float, float]] = (), clear: float = 1.0 * PX) -> Ground:
    """A room's ``Ground``: its sculpted ``terrain`` (engine.hd2d.terrain.Terrain), else the ``flat`` ground (from,
    to, elevation px); ``waters``: (engine.water.Water, centre px, level px); ``footprints``: structures as (x, y,
    half width, half depth, turn degrees) px, kept ``margin`` px clear; ``spots``: where people step in and out
    (doors, arrivals, the player's start, the ends of stairs and bridges), kept ``clear`` px clear."""
    from engine import water as water_mod  # noqa: PLC0415

    def surface(x: float, y: float) -> tuple[float, float] | None:
        if terrain is not None:
            here: tuple[float, float] | None = terrain.surface_at(x, y)
            return here
        if flat is not None and flat[0][0] <= x <= flat[1][0] and flat[0][1] <= y <= flat[1][1]:
            return flat[2], 1.0
        return None

    def water(x: float, y: float) -> float | None:
        levels = [level for w, centre, level in waters if water_mod.inside(w, centre, (x, y))]
        return max(levels) if levels else None

    spot_list = list(spots)
    near_side = clear * 1.6  # (towards the camera, south: what stands there is drawn over a character's feet)

    def structure(x: float, y: float) -> bool:
        if any((x - sx) ** 2 + (y - sy) ** 2 < (near_side if y < sy else clear) ** 2 for sx, sy in spot_list):
            return True
        for cx, cy, hw, hd, turn in footprints:
            a = math.radians(-turn)
            lx = (x - cx) * math.cos(a) - (y - cy) * math.sin(a)
            ly = (x - cx) * math.sin(a) + (y - cy) * math.cos(a)
            if abs(lx) <= hw + margin and abs(ly) <= hd + margin:
                return True
        return False

    material = terrain.material_at if terrain is not None else (lambda x, y: "grass")
    return Ground(surface, material, water, structure)


@dataclass
class Rules:
    """Where a brush may put things: on these materials, no steeper than ``slope`` degrees (each asset's own limit
    applies too), out of water (each asset's shore allowance apart) and off structures when asked."""

    on: tuple[str, ...] = ("grass",)
    slope: float = 35.0
    avoid_water: bool = True
    avoid_structures: bool = True


def allowed(asset: Asset, x: float, y: float, ground: Ground, rules: Rules) -> bool:
    here = ground.surface(x, y)
    if here is None:
        return False
    height, upright = here
    limit = min(rules.slope, asset.slope)
    if upright < math.cos(math.radians(limit)) - 1e-9:
        return False
    material = ground.material(x, y)
    if material not in rules.on or material not in asset.on:  # (the brush's choice, and what the thing grows on)
        return False
    level = ground.water(x, y)
    if level is not None and rules.avoid_water and height < level + 0.05 * PX \
            and not (asset.shore and height >= level - asset.shore * PX):
        return False
    return not (rules.avoid_structures and ground.structure(x, y))


# ---------------------------------------------------------------------- the brush
@dataclass
class Scatter:
    """A room's instances while they are edited, with a 1 m grid index for the spacing checks."""

    instances: dict[str, Any] = field(default_factory=dict)  # asset -> its instances (kept as sets: removing is
    # quick at any count; ``stored`` orders them)

    def __post_init__(self) -> None:
        self.instances = {a: set(rows) for a, rows in self.instances.items()}
        self._grid: dict[tuple[int, int], set[tuple[str, tuple[int, int, int, int]]]] = {}
        for asset, rows in self.instances.items():
            for r in rows:
                self._grid.setdefault(self._key(r[0], r[1]), set()).add((asset, r))

    @staticmethod
    def _key(x: float, y: float) -> tuple[int, int]:
        return math.floor(x / PX), math.floor(y / PX)

    def near(self, x: float, y: float, r: float) -> Iterable[tuple[str, tuple[int, int, int, int]]]:
        """Instances within ``r`` px of (x, y)."""
        k0, k1 = self._key(x - r, y - r), self._key(x + r, y + r)
        for i in range(k0[0], k1[0] + 1):
            for j in range(k0[1], k1[1] + 1):
                for asset, row in self._grid.get((i, j), ()):
                    if (row[0] - x) ** 2 + (row[1] - y) ** 2 <= r * r:
                        yield asset, row

    def add(self, asset: str, row: tuple[int, int, int, int]) -> None:
        self.instances.setdefault(asset, set()).add(row)
        self._grid.setdefault(self._key(row[0], row[1]), set()).add((asset, row))

    def remove(self, asset: str, row: tuple[int, int, int, int]) -> None:
        self.instances[asset].discard(row)
        if not self.instances[asset]:
            del self.instances[asset]
        self._grid[self._key(row[0], row[1])].discard((asset, row))

    def count(self) -> int:
        return sum(len(rows) for rows in self.instances.values())


@functools.lru_cache(maxsize=65536)
def _lattice(seed: int, a: int, b: int) -> float:
    return random.Random(f"{seed}:{a}:{b}").random()


def _noise(x: float, y: float, seed: int, across: float = 3.0 * PX) -> float:
    """Smooth value noise in [0, 1], ``across`` px between its points: where clumps gather."""
    cx, cy = x / across, y / across
    i, j = math.floor(cx), math.floor(cy)
    fx, fy = cx - i, cy - j
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)

    def h(a: int, b: int) -> float:
        return _lattice(seed, a, b)

    top = h(i, j) + (h(i + 1, j) - h(i, j)) * fx
    bottom = h(i, j + 1) + (h(i + 1, j + 1) - h(i, j + 1)) * fx
    return top + (bottom - top) * fy


def brush(scatter: Scatter, mode: str, weights: dict[str, float], x: float, y: float, radius: float,
          density: float, seed: str, ground: Ground, rules: Rules, clumping: float = 0.5,
          share: float = 1.0, seen: set[tuple[str, tuple[int, int, int, int]]] | None = None,
          ) -> list[tuple[str, tuple[int, int, int, int], bool]]:
    """One dab at (x, y) px, ``radius`` px. ``mode`` "add": fill the circle up to ``density`` instances a square
    metre of the collection's assets (``weights``), in clumps (``clumping`` 0: even, 1: in patches); "thin": remove
    ``share`` of them; "remove": all of them (any asset if ``weights`` is empty). ``seed`` makes it repeatable;
    ``seen``: the instances a stroke's earlier dabs already thinned or spared (each is thinned once a stroke, however
    many dabs pass over it). Returns what changed: (asset, instance, added)."""
    rng = random.Random(seed)
    names = [a for a in weights if a in ASSETS and weights[a] > 0]
    mine = [(a, r) for a, r in scatter.near(x, y, radius) if not names or a in names]
    changed: list[tuple[str, tuple[int, int, int, int], bool]] = []
    if mode in ("thin", "remove"):
        for asset, row in sorted(mine, key=lambda ar: (ar[0], ar[1]))[:PER_DAB]:
            if mode == "thin" and seen is not None:
                if (asset, row) in seen:
                    continue
                seen.add((asset, row))
            if mode == "remove" or rng.random() < share:
                scatter.remove(asset, row)
                changed.append((asset, row, False))
        return changed
    if mode != "add":
        raise ScatterError(f"a scatter brush adds, thins or removes (got {mode!r})")
    if not names:
        raise ScatterError("choose something to scatter")
    total = sum(weights[a] for a in names)
    spacing = sum(ASSETS[a].spacing * weights[a] for a in names) / total
    area = math.pi * (radius / PX) ** 2
    wanted = round(density * area)  # (but no more than the spacing lets stand: more is only wasted tries; one
    fits = max(1 if wanted else 0, round(0.9 / (spacing * spacing) * area))  # asked for is always tried)
    need = min(PER_DAB, max(0, min(wanted, fits) - len(mine)), MAX_INSTANCES - scatter.count())
    placed = misses = 0
    for _try in range(max(0, need) * 12):
        if placed >= need or misses > 40 + need:  # (the rules or the spacing leave no room: stop looking)
            break
        misses += 1
        a, d = rng.uniform(0, math.tau), radius * math.sqrt(rng.random())
        px, py = round(x + d * math.cos(a)), round(y + d * math.sin(a))  # (as stored: what is checked is what stands)
        pick, roll = names[-1], rng.uniform(0, total)
        for n in names:
            roll -= weights[n]
            if roll <= 0:
                pick = n
                break
        turn, size = rng.randrange(360), rng.uniform(*ASSETS[pick].size)
        if rng.random() > 1 - clumping + clumping * 2 * (_noise(px, py, 7) - 0.25):
            continue  # (outside a clump)
        kind = ASSETS[pick]
        if not allowed(kind, px, py, ground, rules):
            continue
        reach = (kind.spacing + WIDEST) / 2 * PX  # (two things keep apart by the mean of their spacings: a boulder
        if any((r[0] - px) ** 2 + (r[1] - py) ** 2 < ((kind.spacing + ASSETS[o].spacing) / 2 * PX) ** 2  # may lie by a pebble)
               for o, r in scatter.near(px, py, reach)):
            continue
        row = (px, py, turn, round(size * 100))
        scatter.add(pick, row)
        changed.append((pick, row, True))
        placed, misses = placed + 1, 0
    return changed


def out_of_rule(instances: dict[str, list[tuple[int, int, int, int]]], ground: Ground,
                rules_for: Callable[[Asset], Rules] | None = None) -> dict[str, int]:
    """Per asset, how many instances now stand where its own rules wouldn't put them (ground sculpted steeper,
    painted another material, water risen, off the ground): kept, never moved; said, so the creator can thin them."""
    out: dict[str, int] = {}
    for name, rows in instances.items():
        asset = ASSETS[name]
        rules = rules_for(asset) if rules_for else Rules(on=asset.on, slope=asset.slope, avoid_structures=False)
        n = sum(1 for x, y, _t, _s in rows if not allowed(asset, x, y, ground, rules))
        if n:
            out[name] = n
    return out


def obstructions(instances: dict[str, list[tuple[int, int, int, int]]],
                 spots: list[tuple[str, tuple[float, float]]], routes: list[tuple[str, list[tuple[float, float]]]],
                 reach: float = 1.0 * PX) -> list[str]:
    """Blocking instances standing where people need to pass: within ``reach`` px of a spot (a door, an arrival, the
    player's start, a walkable structure's foot) or of an NPC's route. In words, one line each."""
    out = []
    for name, rows in instances.items():
        asset = ASSETS[name]
        if not asset.blocks:
            continue
        for x, y, _t, size in rows:
            r = reach + 0.6 * PX * size / 100
            for label, (sx, sy) in spots:
                if math.hypot(sx - x, sy - y) < r:
                    out.append(f"a {asset.name.lower()} at ({x / PX:.1f} m, {y / PX:.1f} m) blocks {label}")
                    break
            else:
                for label, points in routes:  # (a patrol goes round: the leg back to its first point too)
                    if any(_segment_distance((x, y), a, b) < r for a, b in zip(points, points[1:] + points[:1])):
                        out.append(f"a {asset.name.lower()} at ({x / PX:.1f} m, {y / PX:.1f} m) is on {label}")
                        break
    return out


def _segment_distance(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / max(1e-9, dx * dx + dy * dy)))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)
