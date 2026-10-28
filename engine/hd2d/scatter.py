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
- **Why not** (Milestone 22C): a ``Tally`` given to ``brush`` counts, for each place a dab tried and refused, the
  check that refused it (``refusal``: the same checks, in the same order, as ``allowed``), and which dabs found
  their circle already full or the room at its limit. Counting changes nothing: the same dabs place the same
  instances with or without one. ``explain`` says it in words, with what to do about it.
"""

from __future__ import annotations

import functools
import math
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

PX = 32.0  # px a metre
KIT = "assets/hd2d_starter/scatter"
SHEET = f"{KIT}/foliage.png"  # the sprites: 48 x 48 px cells (tooling/hd2d_assets/scatter_art.py)
# Milestone 20E's (animated decoration, a tree's canopy): cells from FIRST_MOTION on, in a sheet of their own, so
# 20D's sheet and every coordinate into it stay exactly as they were (20D's decoration draws pixel for pixel alike)
MOTION_SHEET = f"{KIT}/foliage_motion.png"
FIRST_MOTION = 17
CELL_PX = 48
MAX_INSTANCES = 50000  # a room's scatter, all assets (a 128 x 128 m meadow at three a square metre)
PER_DAB = 1500  # the most one dab adds: a huge dense brush fills as it moves, never freezing on one click
MATERIALS = ("grass", "earth", "stone", "mud", "sand")  # (engine.hd2d.terrain.MATERIALS)


@dataclass(frozen=True)
class Part:
    """A sprite attached to an asset (Milestone 20E): a torch's flame, a banner's cloth, a tree's canopy. ``at``: its
    anchor (m east, north, up of the instance's foot at size 1, turned with it), about which it sways; then how it
    moves (``Asset``'s fields of the same names); ``cast``: it casts the sun's shadow (a canopy); ``scale``: its
    size, times the instance's."""

    cell: int
    at: tuple[float, float, float] = (0.0, 0.0, 0.0)
    flex: float = 0.0
    frames: int = 1
    fps: float = 0.0
    loop: str = "loop"
    phase: float = 1.0
    glow: float = 0.0
    streams: bool = False
    cast: bool = False
    scale: float = 1.0
    nearer: float = 0.0  # m: drawn this much nearer the camera than its anchor (a flame in its cup, not behind it)
    lift: float = 0.0  # m: its light taken this far toward the sun (a canopy: its own clusters don't shade it)
    limp: int | None = None  # its cell in still air (a banner hanging; its frames when the wind blows)


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
    reach: float = 0.0  # m: how far it spreads above the ground (a tree's canopy): kept that far off structures
    # How it moves when the room's motion is on (engine.hd2d.motion, Milestone 20E): ``flex`` how much the wind
    # bends it (0 stiff .. 1 grass and reeds); ``frames`` its sprite's frames (cells after ``cell``), shown at
    # ``fps``, looping or ``pingpong``, instances out of step by ``phase`` (0-1); ``glow`` how much it shines in
    # the dark (0-1); ``streams``: points downwind (a banner); ``parts``: sprites attached to it.
    flex: float = 0.0
    frames: int = 1
    fps: float = 0.0
    loop: str = "loop"
    phase: float = 1.0
    glow: float = 0.0
    streams: bool = False
    parts: tuple[Part, ...] = ()

    def sprite_parts(self) -> list[tuple[int, Part | None]]:
        """Its sprites (part number, the part: None for its own ``cell``), in a fixed order."""
        return ([(0, None)] if self.cell is not None else []) + [(k + 1, p) for k, p in enumerate(self.parts)]


ASSETS: dict[str, Asset] = {a.id: a for a in (
    Asset("grass_tuft", "Grass tuft", cell=(0, 1, 2), spacing=0.16, size=(0.75, 1.15), flex=0.85),
    Asset("grass_tall", "Tall grass", cell=(3, 4), spacing=0.2, flex=1.0),
    Asset("grass_dry", "Dry grass", cell=(5, 6), spacing=0.35, on=("grass", "earth", "sand"), flex=0.7),
    Asset("flowers_yellow", "Yellow flowers", cell=(7, 8), spacing=0.4, flex=0.8),
    Asset("flowers_pink", "Pink flowers", cell=(9, 10), spacing=0.4, flex=0.8),
    Asset("bush", "Bush", cell=(11, 12), spacing=1.1, size=(0.9, 1.45), slope=30.0, flex=0.12),
    Asset("bush_berries", "Berry bush", cell=(13,), spacing=0.9, size=(0.85, 1.15), slope=30.0, flex=0.1),
    Asset("reeds", "Reeds", cell=(14, 15), spacing=0.3, size=(0.7, 1.2), on=("grass", "mud", "sand"), shore=0.3,
          flex=1.0),
    Asset("reeds_cattail", "Cattails", cell=(16,), spacing=0.35, on=("grass", "mud", "sand"), shore=0.3, flex=0.9),
    # Milestone 20E: animated decoration (frames on the GPU, from one shared sheet), and a small tree
    Asset("bellflowers", "Bellflowers", cell=(36,), spacing=0.4, flex=0.8, frames=3, fps=2.0, loop="pingpong"),
    Asset("glowcap", "Glowcaps", cell=(34,), spacing=0.5, size=(0.8, 1.2), on=("grass", "earth", "mud"), flex=0.1,
          frames=2, fps=1.5, glow=0.9),
    Asset("torch", "Torch", cell=(17,), spacing=1.5, size=(0.95, 1.05), slope=20.0, on=MATERIALS,
          parts=(Part(18, at=(0.0, 0.0, 0.97), flex=0.45, frames=6, fps=10.0, glow=1.0, nearer=0.05),)),
    Asset("banner", "Banner", cell=(24,), spacing=1.5, size=(0.95, 1.05), slope=20.0, on=MATERIALS,
          parts=(Part(25, at=(0.0, 0.0, 0.63), flex=0.2, frames=4, fps=6.0, streams=True, limp=29),)),
    Asset("dripping_rock", "Dripping rock", cell=(30,), spacing=1.0, size=(0.9, 1.1), slope=30.0, on=MATERIALS,
          frames=4, fps=3.0, phase=1.0),
    Asset("tree_small", "Small tree", model=f"{KIT}/tree_small.glb", spacing=3.0, size=(0.85, 1.2), slope=25.0,
          on=("grass", "earth"), blocks=True, shadow=True, reach=1.1,
          parts=(Part(40, at=(0.0, 0.05, 1.45), flex=0.45, cast=True, scale=1.5, lift=1.2),
                 Part(41, at=(-0.45, 0.15, 1.2), flex=0.5, cast=True, scale=1.2, lift=1.2),
                 Part(42, at=(0.5, 0.1, 1.3), flex=0.5, cast=True, scale=1.2, lift=1.2),
                 Part(41, at=(0.1, -0.2, 1.95), flex=0.45, cast=True, scale=1.15, lift=1.2))),
    Asset("rock_small", "Small rock", model=f"{KIT}/rock_small.glb", spacing=0.5, size=(0.8, 1.6), slope=40.0,
          on=MATERIALS, shadow=True),
    Asset("rock_medium", "Rock", model=f"{KIT}/rock_medium.glb", spacing=1.0, size=(0.75, 1.3), slope=40.0,
          on=MATERIALS, shadow=True),
    Asset("boulder", "Boulder", model=f"{KIT}/boulder.glb", spacing=2.2, size=(0.8, 1.2), slope=45.0,
          on=MATERIALS, blocks=True, shadow=True),
    Asset("fallen_branch", "Fallen branch", model=f"{KIT}/fallen_branch.glb", spacing=1.6, size=(0.8, 1.2),
          slope=12.0, on=("grass", "earth", "mud"), shadow=True),
)}
# A slot a sprite part (asset id, part number): its row in the shader's motion tables (engine.hd2d.motion).
SLOTS: dict[tuple[str, int], int] = {(a.id, k): n for n, (a, k) in enumerate(
    (a, k) for a in ASSETS.values() for k, _p in a.sprite_parts())}
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


def refusal(asset: Asset, x: float, y: float, ground: Ground, rules: Rules) -> str | None:
    """Why ``asset`` may not be put at (x, y) px, or None: "off_ground", "slope", "material" (the brush's materials
    don't include the ground's), "grows" (the asset never grows on it), "water" or "structure", checked in that
    order (the first that refuses)."""
    here = ground.surface(x, y)
    if here is None:
        return "off_ground"
    height, upright = here
    limit = min(rules.slope, asset.slope)
    if upright < math.cos(math.radians(limit)) - 1e-9:
        return "slope"
    material = ground.material(x, y)
    if material not in rules.on:  # (the brush's choice, then what the thing grows on)
        return "material"
    if material not in asset.on:
        return "grows"
    level = ground.water(x, y)
    if level is not None and rules.avoid_water and height < level + 0.05 * PX \
            and not (asset.shore and height >= level - asset.shore * PX):
        return "water"
    if not rules.avoid_structures:
        return None
    r = asset.reach * PX  # (a tree's canopy: clear of walls and doorways all round, not only at its trunk)
    if any(ground.structure(x + dx, y + dy) for dx, dy in ((0, 0), (r, 0), (-r, 0), (0, r), (0, -r))
           if r or (dx, dy) == (0, 0)):
        return "structure"
    return None


def allowed(asset: Asset, x: float, y: float, ground: Ground, rules: Rules) -> bool:
    return refusal(asset, x, y, ground, rules) is None


# ---------------------------------------------------------------------- the brush
@dataclass
class Scatter:
    """A room's instances while they are edited, with a 1 m grid index for the spacing checks."""

    instances: dict[str, Any] = field(default_factory=dict)  # asset -> its instances (kept as sets: removing is
    # quick at any count; ``stored`` orders them)

    def __post_init__(self) -> None:
        self.instances = {a: set(rows) for a, rows in self.instances.items()}
        # Each 1 m cell's instances in the order they came (a dict as an ordered set): ``near`` gives them in the same
        # order in every process (a set of (asset id, row) would follow the string-hash seed), so what a ``Tally``
        # says a place stood too near is the same everywhere. (Whether it is too near never depended on the order.)
        self._grid: dict[tuple[int, int], dict[tuple[str, tuple[int, int, int, int]], None]] = {}
        for asset, rows in self.instances.items():
            for r in rows:
                self._grid.setdefault(self._key(r[0], r[1]), {})[asset, r] = None

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
        self._grid.setdefault(self._key(row[0], row[1]), {})[asset, row] = None

    def remove(self, asset: str, row: tuple[int, int, int, int]) -> None:
        self.instances[asset].discard(row)
        if not self.instances[asset]:
            del self.instances[asset]
        self._grid[self._key(row[0], row[1])].pop((asset, row), None)

    def count(self) -> int:
        return sum(len(rows) for rows in self.instances.values())


@dataclass
class Tally:
    """What a stroke's "add" dabs did, counted as the brush decided (``brush(..., tally=)``): instances it set out to
    add (``wanted``) and added (``placed``); dabs whose circle already had the density (``full``), with the room at
    its limit (``at_limit``), or asking for less than one (``tiny``); for each place tried and refused, why
    (``refused``: a ``refusal``, "clump": outside a clump, "spacing": too near something already standing), the
    asset each "spacing" place stood too near (``crowded_by``: the first the index gives), the materials refused (``materials``), the brush's
    slope rule where the ground was too steep (``slope_rule``), and per asset tried, each refusal (``by_asset``:
    (asset, why) -> places; a mixed collection's things differ) and placed (``placed_by``); dabs that stopped short
    of what they set out to add
    (``gave_up``: too many refused in a row, or out of tries). "thin" and "remove" dabs count what was under the
    brush (``under``)."""

    wanted: int = 0
    placed: int = 0
    dabs: int = 0
    full: int = 0
    at_limit: int = 0
    tiny: int = 0
    gave_up: int = 0
    under: int = 0
    refused: Counter[str] = field(default_factory=Counter)
    crowded_by: Counter[str] = field(default_factory=Counter)
    materials: Counter[str] = field(default_factory=Counter)
    by_asset: Counter[tuple[str, str]] = field(default_factory=Counter)
    placed_by: Counter[str] = field(default_factory=Counter)
    slope_rule: float = 90.0


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
          tally: Tally | None = None) -> list[tuple[str, tuple[int, int, int, int], bool]]:
    """One dab at (x, y) px, ``radius`` px. ``mode`` "add": fill the circle up to ``density`` instances a square
    metre of the collection's assets (``weights``), in clumps (``clumping`` 0: even, 1: in patches); "thin": remove
    ``share`` of them; "remove": all of them (any asset if ``weights`` is empty). ``seed`` makes it repeatable;
    ``seen``: the instances a stroke's earlier dabs already thinned or spared (each is thinned once a stroke, however
    many dabs pass over it); ``tally``: counts why places were refused (``Tally``; nothing else changes). Returns
    what changed: (asset, instance, added)."""
    rng = random.Random(seed)
    names = [a for a in weights if a in ASSETS and weights[a] > 0]
    mine = [(a, r) for a, r in scatter.near(x, y, radius) if not names or a in names]
    changed: list[tuple[str, tuple[int, int, int, int], bool]] = []
    if tally is not None:
        tally.dabs += 1
        if mode in ("thin", "remove"):
            tally.under += len(mine)
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
    if tally is not None:
        tally.wanted += max(0, need)
        if MAX_INSTANCES - scatter.count() <= 0:
            tally.at_limit += 1
        elif not wanted:
            tally.tiny += 1
        elif min(wanted, fits) - len(mine) <= 0:
            tally.full += 1
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
            if tally is not None:
                tally.refused["clump"] += 1
            continue  # (outside a clump)
        kind = ASSETS[pick]
        why = refusal(kind, px, py, ground, rules)
        if why is not None:
            if tally is not None:
                tally.refused[why] += 1
                tally.by_asset[pick, why] += 1
                if why in ("material", "grows"):
                    tally.materials[ground.material(px, py)] += 1
                elif why == "slope":
                    tally.slope_rule = rules.slope
            continue
        reach = (kind.spacing + WIDEST) / 2 * PX  # (two things keep apart by the mean of their spacings: a boulder
        near = next((o for o, r in scatter.near(px, py, reach)  # may lie by a pebble)
                     if (r[0] - px) ** 2 + (r[1] - py) ** 2 < ((kind.spacing + ASSETS[o].spacing) / 2 * PX) ** 2), None)
        if near is not None:
            if tally is not None:
                tally.refused["spacing"] += 1
                tally.by_asset[pick, "spacing"] += 1
                tally.crowded_by[near] += 1
            continue
        row = (px, py, turn, round(size * 100))
        scatter.add(pick, row)
        changed.append((pick, row, True))
        placed, misses = placed + 1, 0
        if tally is not None:
            tally.placed_by[pick] += 1
    if tally is not None:
        tally.placed += placed
        tally.gave_up += placed < need  # (stopped looking: too many refused in a row, or out of tries)
    return changed


def _things(assets: Iterable[str]) -> str:
    names = [ASSETS[a].name.lower() for a in assets]
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0] if names else "them"


def _group(assets: list[str]) -> str:
    """The decoration these are, in words: a collection of more than one thing holding them all ("the Meadow"),
    else the things themselves."""
    for name, weights in COLLECTIONS.items():
        if len(weights) > 1 and all(a in weights for a in assets):
            return f"the {name} already there"
    return f"the {_things(assets)} already there"


def _reason(reason: str, n: int, tried: int, who: list[str], names: list[str], tally: Tally) -> tuple[str, str]:
    """One verified reason, in words, and what to do about it: (said, to do). ``who``: the assets it refused. Short:
    Studio says it on one line."""
    part = f"{n:,} of {tried:,} tries"
    if reason == "spacing":
        others = [a for a, _n in tally.crowded_by.most_common() if a not in names]
        if others and sum(tally.crowded_by[a] for a in others) * 2 >= tally.refused["spacing"]:
            return (f"{_group(others[:3])} leaves too little room ({part})",
                    "thin it first (Ctrl+drag) or scatter these before it")
        return f"they are as close as their spacing allows ({part})", "brush somewhere emptier"
    if reason == "slope":
        steepest = max(ASSETS[a].slope for a in (who or names))
        return (f"the ground is too steep ({part})",
                f"raise Slope (°) (up to {steepest:g}° for these) or smooth it" if tally.slope_rule < steepest
                else "smooth or flatten it (Sculpt)")
    if reason == "material":
        ground = _things_plain(tally.materials)
        return (f"the ground is {ground}, not chosen in the materials row ({part})",
                f"turn on {ground.split(' and ')[0].capitalize()} there or paint the ground")
    if reason == "grows":
        ground = _things_plain(tally.materials)
        grow = sorted({m for a in (who or names) for m in ASSETS[a].on})
        return (f"{'these do' if len(who or names) > 1 else 'this does'} not grow on {ground} ({part})",
                f"paint it {' or '.join(grow)}, or pick something else")
    if reason == "water":
        return f"in water ({part})", "brush beside it, turn off Out of water, or use Pond edge"
    if reason == "structure":
        return f"on or by a structure or doorway ({part})", "brush away from it or turn off Off buildings"
    return f"past the edge of the room's ground ({part})", "brush on the ground"


def explain(tally: Tally, collection: str, weights: dict[str, float]) -> str:
    """Why a stroke added fewer than its density asked for (under 90% of it), from its ``tally`` (what the brush
    counted): the most relevant reasons, then what to do, in Mesh Studio's words (its scatter controls); and in a
    mixed collection, a thing it never placed and why. "" if nothing held it back. ``weights``: the collection's
    assets (a mixed collection's things are named when a reason is only theirs)."""
    if tally.dabs and tally.at_limit == tally.dabs:
        return f"The room holds the most scattered things it can ({MAX_INSTANCES:,}). Thin or remove some first."
    if not tally.wanted:
        if tally.tiny and not tally.full:
            return "The brush is too small for Per m² to place one. Make it bigger ([ ]) or raise Per m²."
        if tally.full:
            return "Already as dense as Per m² asks here. Raise Per m² or brush somewhere sparser."
        return ""
    names = [a for a in weights if a in ASSETS]
    tried = sum(tally.refused.values()) + tally.placed
    if tally.placed >= 0.9 * tally.wanted or not tally.gave_up:  # (nearly all: only a mixed collection's missing)
        missing = [a for a in names if len(names) > 1 and not tally.placed_by[a]
                   and sum(n for (b, _r), n in tally.by_asset.items() if b == a) >= 5]
        if not missing:
            return ""
        said, todo = [], []
        for a in missing:
            reason, n = max(((r, n) for (b, r), n in tally.by_asset.items() if b == a), key=lambda rn: rn[1])
            words, do = _reason(reason, n, tried, [a], names, tally)
            said.append(f"no {ASSETS[a].name.lower()}: {words}")
            todo.append(do)
        return "; ".join(said)[0].upper() + "; ".join(said)[1:] + ". " + todo[0][0].upper() + todo[0][1:] + "."
    counts = Counter({r: n for r, n in tally.refused.items() if r != "clump"})
    if not counts or sum(counts.values()) < tally.refused["clump"] * 0.25:
        if tally.refused["clump"]:
            return (f"Most tries ({tally.refused['clump']:,} of {tried:,}) fell between the Clumps patches. Lower "
                    "Clumps or brush more ground.")
        return ""
    ranked = counts.most_common()
    shown = [ranked[0]] + [rn for rn in ranked[1:2] if rn[1] * 3 >= ranked[0][1]]
    said, todo = [], []
    for reason, n in shown:
        who = [a for a, r in sorted(tally.by_asset, key=lambda ar: -tally.by_asset[ar]) if r == reason]
        only = f"for the {_things(who)}, " if len(names) > 1 and who and set(who) != set(names) else ""
        words, do = _reason(reason, n, tried, who, names, tally)
        said.append(only + words)
        todo.append(do)
    return ("Held back: " + "; ".join(said) + ". " + todo[0][0].upper() + todo[0][1:]
            + "".join(f"; {t}" for t in todo[1:] if t != todo[0]) + ".")


def stroke_message(what: str, why: str, blocked: list[str]) -> str:
    """What Mesh Studio says when a scatter stroke that changed something ends: ``what`` it did, then what now blocks
    where people pass (``obstructions``: a warning), then ``why`` fewer were added (``explain``). Studio says it on
    one line: the warning comes before the explanation, so a long explanation never pushes it out of sight."""
    said = f"{what}: one undo step."
    if blocked:
        said += " In the way (not moved): " + "; ".join(blocked[:2]) + (" ..." if len(blocked) > 2 else "") + "."
    return said + (f" {why}" if why else "")


def _things_plain(materials: Counter[str]) -> str:
    names = [m for m, _n in materials.most_common()]
    return " and ".join(names[:2]) if names else "another material"


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
