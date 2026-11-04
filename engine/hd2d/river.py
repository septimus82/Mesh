"""Rivers and streams in HD-2D rooms (#461, R1): ``settings.hd2d.rivers``, a list of watercourses, each drawn as one
continuous ribbon of water whose surface flows downstream.

A river is control points ``[x, y, width, level]`` (px, as the room's other positions; ``level`` the water's surface,
as an entity's ``elevation``), listed upstream to downstream: their order is the flow's direction. Its course in plan
is a centripetal Catmull-Rom spline through every point (no cusp or loop within a span); its width and level are
interpolated linearly along the course's length between the points, so they never overshoot what the points say and
the level never rises between two points that fall. The course is sampled every ``STEP_M`` (a quarter metre: 8 px of
the world's 32 px/m grid); the ribbon is the two banks at half the width either side, with ``u`` (metres downstream:
what the water's pattern flows along) and ``v`` (-1 left bank .. 1 right bank) on its vertices.

A river is refused, with a reason naming where, before anything is written (``parse_rivers``, which the ops and the
strict loader call), unless its generated banks are sound: each bank advances downstream at every step (at least
``MIN_ADVANCE`` of the course's own step: a bank that stalls or turns back is a fold or a cusp, where the width would
pinch to nothing), no step turns more than ``MAX_TURN_DEG``, the two banks and the ends never cross themselves or
each other, and parts of the ribbon that aren't neighbours along it stay ``CLEARANCE_M`` apart (no overlap, no
near-touching bends). The level, sampled, never rises downstream (beyond ``LEVEL_TOLERANCE_PX``, storage rounding).
Rivers don't cross or overlap one another (joining rivers comes later). Both banks stay on the room's ground
(``bounds``). What a room's rivers cost is bounded: at most ``MAX_RIVERS``, each at most ``MAX_LENGTH_M`` long and
``MAX_TOTAL_M`` together, checked from the course's length before it is sampled. Measured: checking or building a
river costs about 0.1 ms a metre each. Its GPU data: 25 floats (100 bytes) for each bank's vertex, two a sample,
four samples a metre, plus six 4-byte indices a sample: about 0.9 KiB a metre, 1.75 MiB for the room's 2,048 m.

Rivers are drawn by engine.water.WaterLayer (in the same pass as ponds, sharing its copy of the frame for
reflections) and edited in Mesh Studio with its River tool (engine.studio_river, R2). R3: ``carve`` lowers the ground
into a river's bed (project_ops.carve_river_bed), ``RiverIndex`` says where its water lies and how high, for
collision and wading (engine.hd2d.world) and scatter (engine.hd2d.scatter). R4: a river may flow into a pond
(``mouth: "auto"``, ``join``): none of its water is drawn in the pond's (one surface, the pond's), the pond's shore
opens where it enters, and over its last BLEND_M before the shore it takes on the pond's look, its current eased out.
Its free ends may finish in half circles (``ends``). What is drawn is what ``RiverIndex`` says is water.
"""

from __future__ import annotations

import dataclasses
import functools
import math
import re
from array import array
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from engine import water as water_mod

PX = 32.0  # px a metre
STEP_M = 0.25  # the course is sampled this often (m)
SPAN_SAMPLES = 64  # how finely each span of the spline is walked before it's resampled by length
MIN_POINTS, MAX_POINTS = 2, 64
WIDTH_PX = (16.0, 512.0)  # 0.5 m .. 16 m
COORD_PX = 65536.0  # positions and levels within +-2 km
FLOW_MAX = 8.0  # m/s
MIN_SPACING_PX = 8.0  # control points at least a quarter metre apart
LEVEL_TOLERANCE_PX = 0.25  # a quarter pixel: what storage rounds to (the terrain's own height step)
MIN_ADVANCE = 0.25  # each bank moves downstream by at least this share of the course's step
MAX_TURN_DEG = 30.0  # the most the course turns in one step (a quarter metre): radius >= ~0.48 m
CLEARANCE_M = 0.25  # parts of a ribbon (or two ribbons) that aren't neighbours along it stay this far apart
MAX_RIVERS = 16
MAX_MOUTHS = water_mod.MAX_MOUTHS  # rivers flowing into ponds, a room (what the water shaders hold)
MAX_LENGTH_M = 1024.0  # a river's course: four times the widest room (256 m), room to wind across it
MAX_TOTAL_M = 2048.0  # all of a room's rivers together: ~0.2 s to check, ~1.75 MiB of GPU data
BOUNDS_TOLERANCE_PX = 0.5  # (a bank exactly on the ground's edge, stored rounded, is on it)
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
KEYS = {"id", "points", "flow", "colour", "deep_colour", "opacity", "depth", "waves", "reflection", "rain_ripples",
        "mouth", "ends"}
MOUTHS = ("none", "auto")  # R4: "auto": its last point lies in a pond, which it flows into (``join``)
# R4: which of its free ends (its source; its last point, unless it flows into a pond) finish in a half circle (a
# river running off the room's edge keeps that end square: no gap of dry ground beside it there). Older: square
ENDS = ("square", "round", "round_source", "round_end")
# A stream's look, unless the river says otherwise (engine.water's vocabulary: the same meanings as a pond's)
DEFAULTS: dict[str, Any] = {"flow": 1.0, "colour": "#4a8f8c", "deep_colour": "#1f4d5a", "opacity": 0.86,
                            "depth": 0.6, "waves": 0.5, "reflection": 0.35, "rain_ripples": True}
FLOATS_PER_VERTEX = 25
# a bank segment or an end of a ribbon (_segments): river tag, line, index, from, to, along (s0, s1)
Seg = tuple[int, int, int, tuple[float, float], tuple[float, float], float, float]


class RiverError(ValueError):
    """A river that can't be: the message says which and where."""


@dataclass(frozen=True)
class River:
    id: str
    points: tuple[tuple[float, float, float, float], ...]  # (x, y, width, level) px, upstream to downstream
    flow: float  # m/s; 0: still
    colour: tuple[float, float, float]
    deep_colour: tuple[float, float, float]
    opacity: float
    depth: float  # how soon it looks deep (0..1, as a pond's)
    waves: float
    reflection: float
    rain_ripples: bool
    mouth: str = "none"  # MOUTHS
    ends: str = "square"  # ENDS


@dataclass(frozen=True)
class Ribbon:
    """A river's geometry in metres: per sample the centre (x, y), level z, ``u`` (metres downstream), half width,
    the unit tangent downstream, and the left and right bank points."""

    centre: tuple[tuple[float, float], ...]
    level: tuple[float, ...]
    u: tuple[float, ...]
    half: tuple[float, ...]
    tangent: tuple[tuple[float, float], ...]
    left: tuple[tuple[float, float], ...]
    right: tuple[tuple[float, float], ...]
    marks: tuple[float, ...] = ()  # each control point's place along it (``u``, m)

    @property
    def length_m(self) -> float:
        return self.u[-1]


# ---------------------------------------------------------------------- parsing
def _num(value: Any, where: str, lo: float, hi: float) -> float:
    try:
        return water_mod._number(value, where, lo, hi)
    except water_mod.WaterError as exc:
        raise RiverError(str(exc)) from exc


def _colour(value: Any, where: str) -> tuple[float, float, float]:
    try:
        return water_mod._hex(value, where)
    except water_mod.WaterError as exc:
        raise RiverError(str(exc)) from exc


def parse_river(raw: Any, where: str = "river") -> River:
    """One river's data, checked field by field (not its geometry: ``ribbon``)."""
    if not isinstance(raw, dict):
        raise RiverError(f"{where} must be an object")
    extra = set(raw) - KEYS
    if extra:
        raise RiverError(f"{where} has unknown keys: {', '.join(sorted(extra))}")
    rid = raw.get("id")
    if not isinstance(rid, str) or not ID_RE.match(rid):
        raise RiverError(f"{where}.id must be a short name of lowercase letters, digits, '-' or '_' (got {rid!r})")
    points = raw.get("points")
    if not isinstance(points, list) or not MIN_POINTS <= len(points) <= MAX_POINTS:
        raise RiverError(f"{where}.points must be a list of {MIN_POINTS} to {MAX_POINTS} points [x, y, width, level]")
    out = []
    for i, p in enumerate(points):
        w = f"{where}.points[{i}]"
        if not isinstance(p, list) or len(p) != 4:
            raise RiverError(f"{w} must be [x, y, width, level] (px)")
        out.append((_num(p[0], f"{w} x", -COORD_PX, COORD_PX), _num(p[1], f"{w} y", -COORD_PX, COORD_PX),
                    _num(p[2], f"{w} width", *WIDTH_PX), _num(p[3], f"{w} level", -COORD_PX, COORD_PX)))
    look = {**DEFAULTS, **{k: v for k, v in raw.items() if k in DEFAULTS}}
    rain = look["rain_ripples"]
    if not isinstance(rain, bool):
        raise RiverError(f"{where}.rain_ripples must be true or false (got {rain!r})")
    mouth, ends = raw.get("mouth", "none"), raw.get("ends", "square")
    if mouth not in MOUTHS:
        raise RiverError(f"{where}.mouth must be one of {', '.join(MOUTHS)} (got {mouth!r})")
    if ends not in ENDS:
        raise RiverError(f"{where}.ends must be one of {', '.join(ENDS)} (got {ends!r})")
    return River(rid, tuple(out), _num(look["flow"], f"{where}.flow", 0.0, FLOW_MAX),
                 _colour(look["colour"], f"{where}.colour"), _colour(look["deep_colour"], f"{where}.deep_colour"),
                 _num(look["opacity"], f"{where}.opacity", 0.05, 1.0), _num(look["depth"], f"{where}.depth", 0.0, 1.0),
                 _num(look["waves"], f"{where}.waves", 0.0, 1.0), _num(look["reflection"], f"{where}.reflection", 0.0, 1.0),
                 rain, mouth, ends)


def parse_rivers(raw: Any, bounds: tuple[float, float, float, float] | None = None) -> tuple[River, ...]:
    """``settings.hd2d.rivers``: each river parsed and its geometry checked (``ribbon``), ids unique, no two rivers
    crossing or overlapping, the room's allowance kept (count, length), and with ``bounds`` (x0, y0, x1, y1 px: the
    room's ground) both banks on it. Raises RiverError naming the river and where."""
    if not isinstance(raw, list):
        raise RiverError("settings.hd2d.rivers must be a list")
    if len(raw) > MAX_RIVERS:
        raise RiverError(f"A room may have at most {MAX_RIVERS} rivers (got {len(raw)})")
    rivers, ribbons, seen = [], [], set()
    total = 0.0
    for i, item in enumerate(raw):
        river = parse_river(item, f"settings.hd2d.rivers[{i}]")
        if river.id in seen:
            raise RiverError(f"settings.hd2d.rivers[{i}].id '{river.id}' is used twice; river ids must be unique")
        seen.add(river.id)
        length = course_length(river)  # (before any is sampled: what they would cost)
        if length > MAX_LENGTH_M:
            raise RiverError(f"River '{river.id}' is {length:.0f} m long: a river may be at most {MAX_LENGTH_M:.0f} m")
        total += length
        rivers.append(river)
    if total > MAX_TOTAL_M:
        raise RiverError(f"This room's rivers are {total:.0f} m long together: at most {MAX_TOTAL_M:.0f} m")
    if sum(r.mouth == "auto" for r in rivers) > MAX_MOUTHS:
        raise RiverError(f"A room may have at most {MAX_MOUTHS} rivers flowing into ponds (mouth \"auto\")")
    for river in rivers:
        rib = ribbon(river)
        if bounds is not None:
            _on_ground(river, rib, bounds)
        ribbons.append(rib)
    for a in range(len(rivers)):
        for b in range(a + 1, len(rivers)):
            near = _ribbons_meet(ribbons[a], ribbons[b])
            if near is not None:
                raise RiverError(f"Rivers '{rivers[a].id}' and '{rivers[b].id}' cross or overlap near "
                                 f"({near[0] * PX:.0f}, {near[1] * PX:.0f}) px: joining rivers comes later")
    return tuple(rivers)


def _on_ground(river: River, rib: Ribbon, bounds: tuple[float, float, float, float]) -> None:
    x0, y0 = bounds[0] - BOUNDS_TOLERANCE_PX, bounds[1] - BOUNDS_TOLERANCE_PX
    x1, y1 = bounds[2] + BOUNDS_TOLERANCE_PX, bounds[3] + BOUNDS_TOLERANCE_PX
    for x, y in (*rib.left, *rib.right):
        if not (x0 <= x * PX <= x1 and y0 <= y * PX <= y1):
            raise RiverError(f"River '{river.id}' reaches off the room's ground near ({x * PX:.0f}, {y * PX:.0f}) px "
                             f"(its ground is {bounds[0]:g}..{bounds[2]:g} by {bounds[1]:g}..{bounds[3]:g} px)")


def to_json(river: River) -> dict[str, Any]:
    """The river as ``settings.hd2d.rivers`` stores it: points rounded to a hundredth of a pixel, the look's fields
    only where they differ from a stream's defaults (so a plain river reads plainly)."""
    out: dict[str, Any] = {"id": river.id, "points": [[round(v, 2) for v in p] for p in river.points]}
    look = {"flow": river.flow, "colour": water_mod.colour_hex(river.colour),
            "deep_colour": water_mod.colour_hex(river.deep_colour), "opacity": river.opacity, "depth": river.depth,
            "waves": river.waves, "reflection": river.reflection, "rain_ripples": river.rain_ripples}
    for key, value in look.items():
        if value != DEFAULTS[key]:
            out[key] = round(value, 3) if isinstance(value, float) else value
    if river.mouth != "none":
        out["mouth"] = river.mouth
    if river.ends != "square":
        out["ends"] = river.ends
    return out


# ---------------------------------------------------------------------- geometry
def _spline(points: list[tuple[float, float]]) -> tuple[list[tuple[float, float]], list[int]]:
    """Centripetal Catmull-Rom through every point (the ends repeated), walked ``SPAN_SAMPLES`` steps a span; and
    the index in that walk of each control point."""
    pts = [points[0], *points, points[-1]]
    walk: list[tuple[float, float]] = []
    marks: list[int] = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        t1 = max(1e-9, math.dist(p0, p1)) ** 0.5
        t2 = t1 + max(1e-9, math.dist(p1, p2)) ** 0.5
        t3 = t2 + max(1e-9, math.dist(p2, p3)) ** 0.5
        marks.append(len(walk))
        for s in range(SPAN_SAMPLES):
            t = t1 + (t2 - t1) * s / SPAN_SAMPLES

            def lerp(a: tuple[float, float], b: tuple[float, float], ta: float, tb: float) -> tuple[float, float]:
                k = (t - ta) / (tb - ta) if tb - ta > 1e-12 else 0.0
                return (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)

            a1, a2, a3 = lerp(p0, p1, 0.0, t1), lerp(p1, p2, t1, t2), lerp(p2, p3, t2, t3)
            b1, b2 = lerp(a1, a2, 0.0, t2), lerp(a2, a3, t1, t3)
            walk.append(lerp(b1, b2, t1, t2))
    marks.append(len(walk))
    walk.append(points[-1])
    return walk, marks


def halfway(points: list[list[float]], i: int) -> tuple[float, float]:
    """Where the course is halfway between control points ``i`` and ``i + 1`` (px): on the curve, not the straight
    line between them (Studio's Insert point)."""
    walk, marks = _spline([(p[0] / PX, p[1] / PX) for p in points])
    x, y = walk[(marks[i] + marks[i + 1]) // 2]
    return (x * PX, y * PX)


def course_length(river: River) -> float:
    """How long the river's course is (m), from its spline walk alone (cheap: no samples, no banks)."""
    walk, _marks = _spline([(p[0] / PX, p[1] / PX) for p in river.points])
    return sum(math.dist(a, b) for a, b in zip(walk, walk[1:]))


@functools.lru_cache(maxsize=64)  # (the same river: the same ribbon; checked, drawn and picked from once)
def ribbon(river: River) -> Ribbon:
    """The river's sampled course and banks (metres), checked: raises RiverError at the first unsound place."""
    pts = river.points
    name = f"River '{river.id}'"
    for i in range(len(pts) - 1):
        if math.dist(pts[i][:2], pts[i + 1][:2]) < MIN_SPACING_PX:
            raise RiverError(f"{name}: points {i + 1} and {i + 2} are closer than a quarter metre")
        if pts[i + 1][3] > pts[i][3] + LEVEL_TOLERANCE_PX:
            raise RiverError(f"{name} would run uphill between points {i + 1} and {i + 2} (its level rises "
                             f"{(pts[i + 1][3] - pts[i][3]) / PX:.2f} m): a river's level only falls downstream")
    walk, marks = _spline([(p[0] / PX, p[1] / PX) for p in pts])
    # the length along the walk, and each control point's place on it
    along = [0.0]
    for a, b in zip(walk, walk[1:]):
        along.append(along[-1] + math.dist(a, b))
    at_point = [along[m] for m in marks]
    total = along[-1]
    if total > MAX_LENGTH_M:  # (before it is sampled)
        raise RiverError(f"{name} is {total:.0f} m long: a river may be at most {MAX_LENGTH_M:.0f} m")
    count = max(2, round(total / STEP_M) + 1)
    centre, u = [], []
    j = 0
    for k in range(count):
        target = total * k / (count - 1)
        while j < len(walk) - 2 and along[j + 1] < target:
            j += 1
        seg = along[j + 1] - along[j]
        f = (target - along[j]) / seg if seg > 1e-12 else 0.0
        centre.append((walk[j][0] + (walk[j + 1][0] - walk[j][0]) * f, walk[j][1] + (walk[j + 1][1] - walk[j][1]) * f))
        u.append(target)
    half, level = [], []
    span = 0
    for s in u:  # width and level: linear between the control points along the length (no overshoot)
        while span < len(pts) - 2 and at_point[span + 1] < s:
            span += 1
        lo, hi = at_point[span], at_point[span + 1]
        f = min(1.0, max(0.0, (s - lo) / (hi - lo))) if hi - lo > 1e-12 else 0.0
        half.append((pts[span][2] + (pts[span + 1][2] - pts[span][2]) * f) / PX / 2)
        level.append((pts[span][3] + (pts[span + 1][3] - pts[span][3]) * f) / PX)
    for k in range(1, count):
        if level[k] > level[k - 1] + LEVEL_TOLERANCE_PX / PX / 100:
            raise RiverError(f"{name} would run uphill near ({centre[k][0] * PX:.0f}, {centre[k][1] * PX:.0f}) px")
    tangent, left, right = [], [], []
    for k in range(count):
        a, b = centre[max(0, k - 1)], centre[min(count - 1, k + 1)]
        tx, ty = b[0] - a[0], b[1] - a[1]
        n = math.hypot(tx, ty) or 1.0
        tx, ty = tx / n, ty / n
        tangent.append((tx, ty))
        left.append((centre[k][0] - ty * half[k], centre[k][1] + tx * half[k]))
        right.append((centre[k][0] + ty * half[k], centre[k][1] - tx * half[k]))
    rib = Ribbon(tuple(centre), tuple(level), tuple(u), tuple(half), tuple(tangent), tuple(left), tuple(right),
                 tuple(at_point))
    problem = _check(rib)
    if problem is not None:
        what, at = problem
        raise RiverError(f"{name}: {what} near ({at[0] * PX:.0f}, {at[1] * PX:.0f}) px")
    return rib


def _check(r: Ribbon) -> tuple[str, tuple[float, float]] | None:
    """The first unsound place in a ribbon: (what, where in metres), or None."""
    n = len(r.centre)
    for k in range(n - 1):
        cx, cy = r.centre[k + 1][0] - r.centre[k][0], r.centre[k + 1][1] - r.centre[k][1]
        step2 = cx * cx + cy * cy
        if step2 < 1e-12:
            continue
        if k > 0:  # the course's turn at this step
            t0, t1 = r.tangent[k - 1], r.tangent[k + 1]
            turn = math.degrees(abs(math.atan2(t0[0] * t1[1] - t0[1] * t1[0], t0[0] * t1[0] + t0[1] * t1[1]))) / 2
            if turn > MAX_TURN_DEG:
                return "a bend too sharp for any river", r.centre[k]
        for bank in (r.left, r.right):  # each bank must keep moving downstream: else it folds or pinches to nothing
            bx, by = bank[k + 1][0] - bank[k][0], bank[k + 1][1] - bank[k][1]
            if bx * cx + by * cy < MIN_ADVANCE * step2:
                return "a bend too tight for a river this wide (its inner bank folds over itself)", r.centre[k]
        # each quad of the ribbon turns the same way: left of the course on the left
        for a, b, c in ((r.left[k], r.left[k + 1], r.right[k]), (r.left[k + 1], r.right[k + 1], r.right[k])):
            if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) >= 0.0:
                return "a bend where the river turns inside out", r.centre[k]
    segs = _segments(r, 0)
    hit = _crossing(segs, _neighbours)
    if hit is not None:
        return "a place where the river's banks cross or touch (it overlaps itself)", hit
    return None


def _segments(r: Ribbon, tag: int) -> list[Seg]:
    """Every bank segment and the two ends: (river tag, line (0 left, 1 right, 2 start, 3 end), index, a, b, s0, s1)
    with s0..s1 where a bank segment lies along its own bank (m); an end's s0 and s1: where it meets the left and
    the right bank, along each."""
    n = len(r.centre)
    out: list[Seg] = []
    ends = []
    for li, line in enumerate((r.left, r.right)):
        s = 0.0
        for k in range(n - 1):
            step = math.dist(line[k], line[k + 1])
            out.append((tag, li, k, line[k], line[k + 1], s, s + step))
            s += step
        ends.append(s)
    out += [(tag, 2, 0, r.left[0], r.right[0], 0.0, 0.0), (tag, 3, n - 2, r.left[-1], r.right[-1], ends[0], ends[1])]
    return out


def _neighbours(a: Seg, b: Seg) -> bool:
    """Two segments of one river allowed to come close: along the same bank, within 3 x CLEARANCE_M of each other
    along it (a smooth bank's nearby points; one that comes back to touch itself is far along it but near in the
    plane); an end and a bank segment within that distance of where the end meets that bank. The left and right
    banks never (they are a river's width apart, at least half a metre), nor the two ends."""
    la, lb = a[1], b[1]
    if la == lb and la < 2:
        return max(0.0, max(a[5], b[5]) - min(a[6], b[6])) <= 3 * CLEARANCE_M
    if la >= 2 and lb >= 2:
        return False
    end, seg = (a, b) if la >= 2 else (b, a)
    at = end[5] if seg[1] == 0 else end[6]  # where the end meets this segment's bank
    return max(0.0, max(at, seg[5]) - min(at, seg[6])) <= 3 * CLEARANCE_M


def _crossing(segs: list[Seg], allowed: Callable[[Seg, Seg], bool]) -> tuple[float, float] | None:
    """The first pair of segments (not ``allowed`` to touch) that cross or come within CLEARANCE_M of each other."""
    cell = 1.0
    buckets: dict[tuple[int, int], list[int]] = {}
    for i, s in enumerate(segs):
        x0, x1 = sorted((s[3][0], s[4][0]))
        y0, y1 = sorted((s[3][1], s[4][1]))
        for gx in range(math.floor((x0 - CLEARANCE_M) / cell), math.floor((x1 + CLEARANCE_M) / cell) + 1):
            for gy in range(math.floor((y0 - CLEARANCE_M) / cell), math.floor((y1 + CLEARANCE_M) / cell) + 1):
                for j in buckets.get((gx, gy), ()):
                    t = segs[j]
                    if allowed(s, t):
                        continue
                    if _segment_distance(s[3], s[4], t[3], t[4]) < CLEARANCE_M:
                        return s[3]
                buckets.setdefault((gx, gy), []).append(i)
    return None


def _segment_distance(p1: tuple[float, float], p2: tuple[float, float], p3: tuple[float, float],
                      p4: tuple[float, float]) -> float:
    def orient(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1, d2, d3, d4 = orient(p3, p4, p1), orient(p3, p4, p2), orient(p1, p2, p3), orient(p1, p2, p4)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0

    def to_seg(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        dx, dy = b[0] - a[0], b[1] - a[1]
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 < 1e-18 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
        return math.dist(p, (a[0] + dx * t, a[1] + dy * t))

    return min(to_seg(p1, p3, p4), to_seg(p2, p3, p4), to_seg(p3, p1, p2), to_seg(p4, p1, p2))


def _ribbons_meet(a: Ribbon, b: Ribbon) -> tuple[float, float] | None:
    """Where two rivers' ribbons cross, come within CLEARANCE_M, or one lies inside the other; else None."""
    hit = _crossing(_segments(a, 0) + _segments(b, 1), lambda s, t: s[0] == t[0])
    if hit is not None:
        return hit
    for inner, outer in ((a, b), (b, a)):  # wholly inside the other (no bank crossing): its middle in the other's quads
        mid = inner.centre[len(inner.centre) // 2]
        if inside(outer, mid):
            return mid
    return None


def inside(r: Ribbon, p: tuple[float, float]) -> bool:
    """Whether p (metres) lies on the ribbon's water (its quads)."""
    for k in range(len(r.centre) - 1):
        quad = (r.left[k], r.left[k + 1], r.right[k + 1], r.right[k])
        sign = 0
        for i in range(4):
            a, b = quad[i], quad[(i + 1) % 4]
            c = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
            if c != 0.0:
                s = 1 if c > 0 else -1
                if sign and s != sign:
                    break
                sign = s
        else:
            return True
    return False


# ---------------------------------------------------------------------- into a pond, and its ends (R4)
MOUTH_LEVEL_PX = 1.6  # where it enters a pond its water is within 5 cm of the pond's (one waterline)
BLEND_M = water_mod.MOUTH_BLEND_M  # over its last 1.5 m before the pond's shore it takes on the pond's look


@dataclass(frozen=True)
class Pond:
    """A pond or lake (an object with a WaterSurface, engine.water) as a river's mouth sees it."""

    id: str  # the object's id (project_ops), or its place in the room's list (engine.water.WaterLayer)
    centre: tuple[float, float]  # px
    level: float  # px: its surface (the object's elevation)
    water: Any  # engine.water.Water
    gated: bool = False  # it shows only when flags say ("Show when", or its own require/forbid flags)


@dataclass(frozen=True)
class Mouth:
    """Where a river (``mouth: "auto"``) flows into a pond: its course crosses the pond's shore once, at ``at`` (m),
    heading ``tangent``, ``half`` (m) wide either side, ``u`` (m) along it; from its sample ``entry`` on it lies in
    the pond, whose water is drawn there (the river's is not: one water surface)."""

    river: str
    pond: Pond
    entry: int
    at: tuple[float, float]
    tangent: tuple[float, float]
    half: float
    u: float


def _in_pond(pond: Pond, p: tuple[float, float]) -> bool:
    return bool(water_mod.inside(pond.water, pond.centre, (p[0] * PX, p[1] * PX)))


def _mouth_pond(river: River, ponds: tuple[Pond, ...]) -> Pond | None:
    """The pond the river's last point lies in (of several, the one whose level is nearest its own), or None."""
    found = [p for p in ponds if _in_pond(p, ribbon(river).centre[-1])]
    return min(found, key=lambda p: (abs(p.level - river.points[-1][3]), p.id)) if found else None


def join(river: River, ponds: tuple[Pond, ...]) -> Mouth:
    """Where ``river`` flows into one of ``ponds``: the pond its last point lies in. Raises RiverError, saying what to
    change, if none does; if that pond has the older look (a simple pond or puddle, CLASSIC: drawn another way, so its
    water couldn't meet the river's as one) or shows only when flags say (it may not be there); if the river's end
    isn't wholly in it; if it crosses the pond's shore more than once, or runs with a bank in the pond's water before
    its mouth (more than its own width and BLEND_M short of where it enters: an angled mouth's near bank enters
    first); or if over its last BLEND_M before the shore (where its surface eases to the pond's) and in the pond its
    water isn't within 5 cm of the pond's. Nothing is moved or relevelled to make it fit."""
    rib = ribbon(river)
    name = f"River '{river.id}'"
    pond = _mouth_pond(river, ponds)
    if pond is None:
        end = rib.centre[-1]
        raise RiverError(f"{name} flows into a pond (mouth \"auto\") but its last point, ({end[0] * PX:.0f}, "
                         f"{end[1] * PX:.0f}) px, isn't in one: move it into a pond's water, or set its mouth to none")
    if pond.water.preset in water_mod.CLASSIC:
        raise RiverError(f"{name} can't flow into the pond '{pond.id}': it has the older simple look "
                         f"(\"{pond.water.preset}\"); give it a natural pond, stone pool or muddy puddle look, "
                         "or set the river's mouth to none")
    if pond.gated:
        raise RiverError(f"{name} can't flow into the pond '{pond.id}': it shows only when flags say, so it may not "
                         "be there; take its \"Show when\" off, or set the river's mouth to none")
    if not (_in_pond(pond, rib.left[-1]) and _in_pond(pond, rib.right[-1])):
        raise RiverError(f"{name}'s end isn't wholly in the pond '{pond.id}' (a bank of it is on the shore): move its "
                         "last point further into the water, or narrow it there")
    inside = [_in_pond(pond, c) for c in rib.centre]
    entry = len(inside) - 1
    while entry > 0 and inside[entry - 1]:
        entry -= 1
    if entry == 0:
        raise RiverError(f"{name} lies wholly in the pond '{pond.id}': start it on the shore, outside the water")
    early = next((k for k in range(entry) if inside[k]), None)
    if early is not None:
        x, y = rib.centre[early]
        raise RiverError(f"{name} crosses the pond '{pond.id}''s shore more than once (it is in the water near "
                         f"({x * PX:.0f}, {y * PX:.0f}) px, then out again): keep its course out of the pond until "
                         "its mouth")
    (ax, ay), (bx, by) = rib.centre[entry - 1], rib.centre[entry]
    lo, hi = 0.0, 1.0  # where between the last sample out and the first in it crosses the shore
    for _ in range(12):
        mid = (lo + hi) / 2
        if _in_pond(pond, (ax + (bx - ax) * mid, ay + (by - ay) * mid)):
            hi = mid
        else:
            lo = mid
    f = (lo + hi) / 2
    tx, ty = bx - ax, by - ay
    n = math.hypot(tx, ty) or 1.0
    half = rib.half[entry - 1] + (rib.half[entry] - rib.half[entry - 1]) * f
    u = rib.u[entry - 1] + (rib.u[entry] - rib.u[entry - 1]) * f
    near = u - BLEND_M - 2.0 * half  # (the shaders blend from here on: engine.water's near_mouth)
    banked = next((k for k in range(entry) if rib.u[k] < near
                   and (_in_pond(pond, rib.left[k]) or _in_pond(pond, rib.right[k]))), None)
    if banked is not None:
        x, y = rib.centre[banked]
        raise RiverError(f"{name} runs with a bank in the pond '{pond.id}''s water near ({x * PX:.0f}, {y * PX:.0f}) "
                         "px, before its mouth: keep its course a little further from the shore until it turns in")
    window = [k for k in range(len(rib.level)) if rib.u[k] >= u - BLEND_M - STEP_M]
    worst = max(window, key=lambda k: abs(rib.level[k] * PX - pond.level))
    gap = rib.level[worst] * PX - pond.level
    if abs(gap) > MOUTH_LEVEL_PX:
        first = max(i for i, m in enumerate(rib.marks) if m <= rib.u[window[0]] + 1e-9)
        x, y = rib.centre[worst]
        hint = "; or carve its bed, which sinks water standing over the ground beside it" if gap > 0 else ""
        raise RiverError(f"{name} meets the pond '{pond.id}' {abs(gap) / PX:.2f} m {'above' if gap > 0 else 'below'} "
                         f"its water near ({x * PX:.0f}, {y * PX:.0f}) px: over its last {BLEND_M:g} m before the "
                         f"shore and in the pond, its level must be within 5 cm of the pond's, {pond.level:g} px "
                         f"(points {first + 1} to {len(river.points)}{hint})")
    return Mouth(river.id, pond, entry, (ax + tx * f, ay + ty * f), (tx / n, ty / n), half, u)


def mouths(rivers: tuple[River, ...], ponds: tuple[Pond, ...]) -> tuple[dict[str, Mouth], dict[str, str]]:
    """Each river with ``mouth: "auto"``'s join (``join``), and for those that can't join, why (as a room plays: a
    pond moved since, say; such a river is drawn as if its mouth were none, never reshaped)."""
    joined, problems = {}, {}
    for river in rivers:
        if river.mouth == "auto":
            try:
                joined[river.id] = join(river, ponds)
            except RiverError as exc:
                problems[river.id] = str(exc)
    return joined, problems


def gated(payload: Any) -> bool:
    """Whether an object (a scene document's entry, or the data a sprite was made from) shows only when flags say:
    Studio's "Show when" (a ConditionalActivator) or its own require/forbid flags (engine.water.active)."""
    if not isinstance(payload, dict):
        return False
    behaviours = payload.get("behaviours")
    return bool(payload.get("require_flags") or payload.get("forbid_flags")
                or (isinstance(behaviours, list) and "ConditionalActivator" in behaviours))


def ponds_of(entities: Any) -> tuple[Pond, ...]:
    """The ponds among a scene document's objects (``WaterSurface``, read as its behaviour reads it: unknown keys
    left aside; one whose settings can't be read is left out)."""
    out = []
    for e in entities if isinstance(entities, list) else ():
        configs = e.get("behaviour_config") if isinstance(e, dict) else None
        config = configs.get("WaterSurface") if isinstance(configs, dict) else None
        if not isinstance(config, dict) or not all(
                isinstance(e.get(k), (int, float)) and not isinstance(e.get(k), bool) for k in ("x", "y")):
            continue
        try:
            water = water_mod.parse_water({k: v for k, v in config.items() if k in water_mod._KEYS})
        except water_mod.WaterError:
            continue
        level = e.get("elevation", 0.0)
        level = float(level) if isinstance(level, (int, float)) and not isinstance(level, bool) else 0.0
        out.append(Pond(str(e.get("id")), (float(e["x"]), float(e["y"])), level, water, gated(e)))
    return tuple(out)


def capped(river: River, mouth: Mouth | None) -> tuple[float, float]:
    """The radii (m) of the round caps its free ends finish in (``ends``): at its source ("round", "round_source"),
    and at its last point ("round", "round_end") unless it flows into a pond there; 0: square."""
    if river.ends == "square":
        return 0.0, 0.0
    r = ribbon(river)
    start = r.half[0] if river.ends in ("round", "round_source") else 0.0
    end = r.half[-1] if river.ends in ("round", "round_end") and mouth is None else 0.0
    return start, end


def _off_cap(r: Ribbon, caps: tuple[float, float], u: float, across: float) -> bool:
    """Whether a point ``u`` m along the course and ``across`` m from its middle is past a round end (no water)."""
    start, end = caps
    if start and u < start:
        return math.hypot(start - u, across) > start
    if end and u > r.u[-1] - end:
        return math.hypot(u - (r.u[-1] - end), across) > end
    return False


# ---------------------------------------------------------------------- for the GPU
def vertices(rivers: tuple[River, ...], lift: float,
             joined: dict[str, tuple[int, Mouth]] | None = None) -> tuple[array, array]:
    """Every river's ribbon as one interleaved vertex array (FLOATS_PER_VERTEX a vertex: position x, y, z (m: the
    level plus ``lift``), the tangent downstream (2), u (m), v (-1 left .. 1 right), half width (m), flow (m/s), the
    colour and opacity (4), the deep colour and depth (4), waves, reflection, seed, rain ripples, then its ends (R4):
    the radii of its round caps at its source and its last point (m; 0 square), its length (m) and which mouth
    (``joined``: river id -> (slot, Mouth); -1 none)) and its triangles' indices (two a step). The same rivers give
    the same arrays, byte for byte."""
    data, idx = array("f"), array("I")
    for i, river in enumerate(rivers):
        r = ribbon(river)
        slot, mouth = (joined or {}).get(river.id, (-1, None))
        base = len(data) // FLOATS_PER_VERTEX
        look = (*river.colour, river.opacity, *river.deep_colour, river.depth, river.waves, river.reflection,
                1.7 * (i + 1), 1.0 if river.rain_ripples else 0.0, *capped(river, mouth), r.u[-1], float(slot))
        for k in range(len(r.centre)):
            for (x, y), v in ((r.left[k], -1.0), (r.right[k], 1.0)):
                data.extend((x, y, r.level[k] + lift, *r.tangent[k], r.u[k], v, r.half[k], river.flow, *look))
        for k in range(len(r.centre) - 1):
            a, b, c, d = base + 2 * k, base + 2 * k + 1, base + 2 * k + 2, base + 2 * k + 3
            idx.extend((a, c, b, b, c, d))
    return data, idx


# ---------------------------------------------------------------------- the water where it stands (R3)
class RiverIndex:
    """The rooms' rivers as their water lies in the plane: which river's ribbon covers a point, and its surface
    there (each quad of the ribbon at its two samples' mean level: as drawn, less the lift). Quads are kept in 1 m
    buckets, so a lookup reads a handful of them. Collision (engine.hd2d.world), scatter and its clearing ask it."""

    def __init__(self, rivers: tuple[River, ...], ponds: tuple[Pond, ...] = ()) -> None:
        self._quads: list[tuple[tuple[tuple[float, float], ...], float, str]] = []
        self._buckets: dict[tuple[int, int], list[int]] = {}
        # R4: what is drawn: a river flowing into a pond has none of its water in the pond (the pond's is there), and
        # its round ends have none past their caps. Per quad, if either applies: (ribbon, sample, caps, pond or None)
        self._ends: dict[int, tuple[Ribbon, int, tuple[float, float], Pond | None]] = {}
        joined, _problems = mouths(rivers, ponds)
        for river in rivers:
            r = ribbon(river)
            mouth = joined.get(river.id)
            caps = capped(river, mouth)
            for k in range(len(r.centre) - 1):
                quad = (r.left[k], r.left[k + 1], r.right[k + 1], r.right[k])
                index = len(self._quads)
                self._quads.append((quad, (r.level[k] + r.level[k + 1]) / 2, river.id))
                in_pond = mouth is not None and (k >= mouth.entry - 1 or any(_in_pond(mouth.pond, c) for c in quad))
                if in_pond or (caps[0] and r.u[k] < caps[0] + STEP_M) \
                        or (caps[1] and r.u[k + 1] > r.u[-1] - caps[1] - STEP_M):
                    self._ends[index] = (r, k, caps, mouth.pond if mouth is not None else None)
                xs, ys = [q[0] for q in quad], [q[1] for q in quad]
                for i in range(math.floor(min(xs)), math.floor(max(xs)) + 1):
                    for j in range(math.floor(min(ys)), math.floor(max(ys)) + 1):
                        self._buckets.setdefault((i, j), []).append(index)

    def __bool__(self) -> bool:
        return bool(self._quads)

    def level_at(self, x: float, y: float, in_ponds: bool = True) -> tuple[float, str] | None:
        """The water's surface (m) at (x, y) m and its river's id, or None where no river's water lies. Where a river
        flows into a pond, over its course in the pond the water is the pond's (its level: as drawn there), so its
        channel stays water (deep water stops characters there too); ``in_ponds`` False: None there (the pond's own
        water, which ripples itself: no wading step twice)."""
        best: tuple[float, str] | None = None
        for index in self._buckets.get((math.floor(x), math.floor(y)), ()):
            quad, level, rid = self._quads[index]
            if not _in_quad(quad, (x, y)):
                continue
            here = self._past_end(index, (x, y), level)
            if here is not None and (in_ponds or not here[1]) and (best is None or here[0] > best[0]):
                best = (here[0], rid)
        return best

    def _past_end(self, index: int, p: tuple[float, float], level: float) -> tuple[float, bool] | None:
        """The water at p on the quad ``index``: (its own ``level``, False), or (the level of the pond the river flows
        into, True) where p is in it, or None past a round cap (as the river's shader works it out: along and across
        the course from the quad's sample)."""
        found = self._ends.get(index)
        if found is None:
            return level, False
        r, k, caps, pond = found
        if pond is not None and _in_pond(pond, p):
            return pond.level / PX, True
        (cx, cy), (tx, ty) = r.centre[k], r.tangent[k]
        dx, dy = p[0] - cx, p[1] - cy
        return None if _off_cap(r, caps, r.u[k] + dx * tx + dy * ty, dy * tx - dx * ty) else (level, False)


def _in_quad(quad: tuple[tuple[float, float], ...], p: tuple[float, float]) -> bool:
    signs = set()
    for i in range(4):
        (ax, ay), (bx, by) = quad[i], quad[(i + 1) % 4]
        c = (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax)
        if c != 0.0:
            signs.add(c > 0)
    return len(signs) < 2


# ---------------------------------------------------------------------- carving its bed (R3)
DEPTH_PER_WIDTH = 0.25  # a bed's depth at its middle, unless given: a quarter of the river's width ...
DEPTH_M = (0.2, 1.2)  # ... kept within these (m)
BANK_SLOPE = 0.6  # the bank rises this much a metre from the water's edge (31 degrees: walkable, MAX_SLOPE 0.7)
BANK_REACH_M = 12.0  # ... until it meets the ground, for at most this far (7.2 m up): past it the ground is kept
SINK_M = 0.05  # carving lowers water standing proud of the ground beside it to this far under that ground
_BLOCK = 8  # corners a side of the coarse grid of highest ground (how far a stretch's bank may need to reach)


def bed_depths(river: River, depths: Any = None) -> list[float]:
    """Each control point's bed depth (m): ``depths`` (one a point, m) if given, else a quarter of its width (within
    DEPTH_M). Raises RiverError for a wrong list."""
    if depths is None:
        return [min(DEPTH_M[1], max(DEPTH_M[0], DEPTH_PER_WIDTH * p[2] / PX)) for p in river.points]
    if not isinstance(depths, list) or len(depths) != len(river.points):
        raise RiverError(f"River '{river.id}': give one bed depth a point ({len(river.points)}), in metres")
    return [_num(d, f"River '{river.id}' bed depth {i + 1}", 0.0, 8.0) for i, d in enumerate(depths)]


def sunk(terrain: Any, river: River, ponds: tuple["Pond", ...] = (), others: tuple[River, ...] = ()) -> River:
    """The river with its water lowered, where it stands above the ground beside it (half a metre and a terrain cell out
    from each bank, the lower side, at every sample along it: every quarter metre), to SINK_M under that ground. A sample
    standing over it lowers both control points of its stretch by as much (so the level between them, linear, is
    under it there too); the level still falls downstream (each point no higher than the one before). Water at or
    under the ground beside it is kept as it is, so a carved river (its banks rising from the water) is kept, and so
    is one sunk already, though carving nearby lowers that ground a little: sinking twice is sinking once. Where the
    place beside it is in a pond's water (``ponds``) or another river's (``others``), the ground there is that water's
    bed, not this river's bank: it isn't measured (so carving a neighbour never sinks this one again). A river flowing
    into a pond (``mouth: "auto"``) is never sunk below that pond's level: it must meet the pond's water (``join``).
    (Studio draws new rivers a little over the ground clicked, so they show before their bed is carved: carved, they
    lie in it.)"""
    rib = ribbon(river)
    pond = _mouth_pond(river, ponds) if river.mouth == "auto" else None
    cell = terrain.cell / PX  # (measured a cell further out: past every corner its own carve lowers into its bed)
    near = RiverIndex(tuple(o for o in others if o.id != river.id))
    pts = river.points
    need = [0.0] * len(pts)  # how far each control point comes down (px)
    span = 0
    for k in range(len(rib.u)):
        while span < len(pts) - 2 and rib.marks[span + 1] < rib.u[k]:
            span += 1
        (cx, cy), (tx, ty), out = rib.centre[k], rib.tangent[k], rib.half[k] + 0.5 + cell
        known = []
        for side in (1, -1):
            x, y = (cx + side * -ty * out) * PX, (cy + side * tx * out) * PX
            g = terrain.height(x, y)
            beside_water = near.level_at(x / PX, y / PX) is not None or any(
                water_mod.inside(p.water, p.centre, (x, y)) for p in ponds)
            if g is not None and not beside_water:
                known.append(g)
        level = rib.level[k] * PX
        if known and level > min(known):  # (standing over it: its stretch sunk)
            drop = level - (min(known) - SINK_M * PX)
            need[span], need[span + 1] = max(need[span], drop), max(need[span + 1], drop)
    levels: list[float] = []
    for p, d in zip(pts, need):
        level = p[3] - d if pond is None else max(min(p[3], pond.level), p[3] - d)
        levels.append(min(level, levels[-1]) if levels else level)
    if all(abs(a - p[3]) < 1e-9 for a, p in zip(levels, pts)):
        return river
    points = tuple((p[0], p[1], p[2], round(level, 2)) for p, level in zip(river.points, levels))
    return dataclasses.replace(river, points=points)


def carve(terrain: Any, river: River, depths: list[float], mouth: Mouth | None = None) -> set[tuple[int, int]]:
    """Lower ``terrain`` (engine.hd2d.terrain.Terrain) into the river's bed. Each corner is measured from the nearest
    point of the river's course: under its water the ground goes down to ``level - depth * (1 - (d / half) ** 2)``
    (d: from the middle; the depth there ``depths``, by control point, linear between them along the river),
    meeting the water's surface exactly at its edge; past the edge a bank rises from the water at BANK_SLOPE until
    it meets the ground (up to BANK_REACH_M out). Where the nearest point is one of its two ends, past it, the bank
    rises from that end's water level all round (no bed carries on past the water). A round end (``ends``, R4; not a
    mouth into a pond, ``mouth``) is a bowl: within a half width of that end, the bed and its bank are
    measured from the middle of the course a half width in from it, so the water there (drawn the same way) ends in
    a half circle and no bed lies past it. Ground only ever goes down, so
    carving twice is carving once, and ground already lower is kept. Returns the corner chunks changed (as
    ``Terrain.sculpt`` does); ``terrain.changed`` notes the stored chunks."""
    from engine.hd2d.terrain import CHUNK, LIMIT, QUANTUM, chunks_of  # noqa: PLC0415

    r = ribbon(river)
    n = len(r.centre)
    marks = r.marks
    depth = []
    span = 0
    for s in r.u:  # each sample's depth: linear between the control points along the river, as its width and level
        while span < len(marks) - 2 and marks[span + 1] < s:
            span += 1
        a, b = marks[span], marks[span + 1]
        f = min(1.0, max(0.0, (s - a) / (b - a))) if b - a > 1e-12 else 0.0
        depth.append(depths[span] + (depths[span + 1] - depths[span]) * f)
    cell = terrain.cell / PX
    ox, oy = terrain.origin[0] / PX, terrain.origin[1] / PX
    stride = terrain.nx + 1
    # the highest ground in each block of _BLOCK x _BLOCK corners: how far a stretch's bank may need to reach
    high: dict[tuple[int, int], float] = {}
    for key, h in enumerate(terrain.heights):
        block = (key % stride // _BLOCK, key // stride // _BLOCK)
        if h > high.get(block, -math.inf):
            high[block] = h
    nearest: dict[int, tuple[float, int, float, float]] = {}  # corner -> (distance m, segment, t, t unclamped)
    for k in range(n - 1):
        (ax, ay), (bx, by) = r.centre[k], r.centre[k + 1]
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        if length2 < 1e-12:
            continue
        lo_level = min(r.level[k], r.level[k + 1])
        span_m = max(r.half[k], r.half[k + 1]) + BANK_REACH_M
        b0 = (max(0, math.floor((min(ax, bx) - span_m - ox) / cell)) // _BLOCK,
              max(0, math.floor((min(ay, by) - span_m - oy) / cell)) // _BLOCK)
        b1 = (min(terrain.nx, math.ceil((max(ax, bx) + span_m - ox) / cell)) // _BLOCK,
              min(terrain.ny, math.ceil((max(ay, by) + span_m - oy) / cell)) // _BLOCK)
        top = max((high.get((bi, bj), -math.inf) for bi in range(b0[0], b1[0] + 1) for bj in range(b0[1], b1[1] + 1)),
                  default=-math.inf)
        rise = (terrain.base + top) / PX - lo_level  # (the most this stretch's bank might climb to meet the ground)
        reach = max(r.half[k], r.half[k + 1]) + min(BANK_REACH_M, max(0.0, rise) / BANK_SLOPE + cell)
        i0 = max(0, math.floor((min(ax, bx) - reach - ox) / cell))
        i1 = min(terrain.nx, math.ceil((max(ax, bx) + reach - ox) / cell))
        j0 = max(0, math.floor((min(ay, by) - reach - oy) / cell))
        j1 = min(terrain.ny, math.ceil((max(ay, by) + reach - oy) / cell))
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                cx, cy = (v / PX for v in terrain.corner_xy(i, j))
                t_raw = ((cx - ax) * dx + (cy - ay) * dy) / length2
                tc = min(1.0, max(0.0, t_raw))
                dist = math.hypot(cx - (ax + dx * tc), cy - (ay + dy * tc))
                key = i + j * stride
                if dist < nearest.get(key, (math.inf,))[0]:
                    nearest[key] = (dist, k, tc, t_raw)
    changed: set[tuple[int, int]] = set()
    caps = capped(river, mouth)

    def middle(s: float) -> tuple[float, float, float, float]:  # the course's middle at s m along: x, y, level, depth
        k = min(n - 2, max(0, int(s / max(1e-9, r.u[1])))) if n > 1 else 0
        f = min(1.0, max(0.0, (s - r.u[k]) / max(1e-9, r.u[k + 1] - r.u[k])))
        return (r.centre[k][0] + (r.centre[k + 1][0] - r.centre[k][0]) * f,
                r.centre[k][1] + (r.centre[k + 1][1] - r.centre[k][1]) * f,
                r.level[k] + (r.level[k + 1] - r.level[k]) * f, depth[k] + (depth[k + 1] - depth[k]) * f)

    bowls = [(caps[0], middle(caps[0])) if caps[0] else None,
             (caps[1], middle(r.u[-1] - caps[1])) if caps[1] else None]
    for key, (dist, k, tc, t_raw) in nearest.items():
        half = r.half[k] + (r.half[k + 1] - r.half[k]) * tc
        level = r.level[k] + (r.level[k + 1] - r.level[k]) * tc
        start_end, last_end = k == 0 and t_raw < 0.0, k == n - 2 and t_raw > 1.0
        along = r.u[k] + t_raw * (r.u[k + 1] - r.u[k])
        bowl = bowls[0] if bowls[0] and along < caps[0] else (bowls[1] if bowls[1] and along > r.u[-1] - caps[1]
                                                                   else None)
        if bowl is not None:  # a round end: measured from the middle of its half circle
            radius, (mx, my, b_level, b_depth) = bowl
            cx, cy = (v / PX for v in terrain.corner_xy(key % stride, key // stride))
            d = math.hypot(cx - mx, cy - my)
            target = (b_level - b_depth * (1.0 - (d / radius) ** 2) if d <= radius
                      else b_level + BANK_SLOPE * (d - radius))
        elif start_end or last_end:  # past one of its ends: a bank from that end's water all round
            (ax, ay), (bx, by) = r.centre[k], r.centre[k + 1]
            length = math.hypot(bx - ax, by - ay)
            beyond = (-t_raw if start_end else t_raw - 1.0) * length
            across = math.sqrt(max(0.0, dist * dist - beyond * beyond))
            target = level + BANK_SLOPE * math.hypot(beyond, max(0.0, across - half))
        elif dist <= half:
            d = depth[k] + (depth[k + 1] - depth[k]) * tc
            target = level - d * (1.0 - (dist / half) ** 2)
        else:
            target = level + BANK_SLOPE * (dist - half)
        new = round(max(-LIMIT, min(LIMIT, target * PX - terrain.base)) / QUANTUM) * QUANTUM
        if new < terrain.heights[key]:
            terrain.heights[key] = new
            changed.add((key % stride, key // stride))
    terrain.changed |= {(i // CHUNK, j // CHUNK) for i, j in changed}
    return chunks_of(changed)
