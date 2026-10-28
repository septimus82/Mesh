"""Scatter strokes over rooms with every kind of refusal: a dense meadow then trees and rocks over it, steep ground,
painted paths, a pond, a hut, the room's edge, density already reached. Shared by the scatter diagnostics tests
(M22C) and their placement digests: each step's scatter, as stored, hashed."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

import engine.project_ops as ops


def room(size: tuple[int, int] = (1280, 960)) -> dict[str, Any]:
    return {"entities": [], "settings": {"world_width": size[0], "world_height": size[1],
                                         "hd2d": {"ground": {"from": [0, 0], "to": list(size)}}}}


def sweep(x0: int = 96, x1: int = 1184, y0: int = 96, y1: int = 864, step: int = 64) -> list[list[float]]:
    return [[float(x), float(y)] for y in range(y0, y1 + 1, step) for x in range(x0, x1 + 1, step)]


def varied() -> dict[str, Any]:
    """A room with a steep mound, an earth path, a pond and a hut."""
    r = ops.sculpt_terrain_stroke(room(), "raise", [[900, 640, 120]] * 3, 96)
    r = ops.paint_terrain_stroke(r, "earth", [[128 + 16 * k, 200, 1.0] for k in range(50)], 40)
    r, pond = ops.place_blank(r, "r", "Pond", 300, 560)
    r = ops.set_water(r, pond, preset="natural_pond", width=192, height=160)
    r["settings"]["hd2d"]["structures"] = [{"id": "hut", "model": "assets/models/none.glb", "x": 700.0, "y": 360.0}]
    return r


def digest(scene: dict[str, Any]) -> str:
    rows = scene["settings"]["hd2d"].get("scatter", {})
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]


def _t(t: Any) -> dict[str, Any]:
    return {} if t is None else {"tally": t}  # (the placements are compared with and without one)


Step = tuple[str, Callable[[dict[str, Any], Any], dict[str, Any]]]

STEPS: dict[str, tuple[Callable[[], dict[str, Any]], list[Step]]] = {
    "meadow_then_trees_and_rocks": (room, [
        ("meadow", lambda s, t: ops.scatter_stroke(s, "Meadow", sweep(), 96, seed=1, **_t(t))),
        ("trees", lambda s, t: ops.scatter_stroke(s, "Small tree", sweep(step=128), 160, seed=2, **_t(t))),
        ("rocks", lambda s, t: ops.scatter_stroke(s, "Rock", sweep(step=128), 160, seed=3, **_t(t))),
        ("meadow_again", lambda s, t: ops.scatter_stroke(s, "Meadow", sweep(), 96, seed=4, **_t(t))),
    ]),
    "varied_ground": (varied, [
        ("meadow", lambda s, t: ops.scatter_stroke(s, "Meadow", sweep(step=48), 64, seed=3, **_t(t))),
        ("pond_edge", lambda s, t: ops.scatter_stroke(s, "Pond edge", [[300, 560]], 96, seed=3, **_t(t))),
        ("rocks_on_path", lambda s, t: ops.scatter_stroke(s, "Rocks", [[x, 200] for x in range(140, 900, 48)], 48,
                                                          seed=3, on=["earth"], **_t(t))),
        ("trees_on_mound", lambda s, t: ops.scatter_stroke(s, "Small tree", [[900, 640]], 128, seed=5, **_t(t))),
        ("shrubs", lambda s, t: ops.scatter_stroke(s, "Shrubs", sweep(step=96), 128, seed=6, **_t(t))),
    ]),
    "mixed_collections": (room, [
        ("deadfall", lambda s, t: ops.scatter_stroke(s, "Deadfall", sweep(step=96), 128, seed=7, **_t(t))),
        ("wildflowers", lambda s, t: ops.scatter_stroke(s, "Wildflowers", sweep(step=96), 96, seed=8,
                                                        clumping=1.0, **_t(t))),
        ("boulders", lambda s, t: ops.scatter_stroke(s, "Boulder", sweep(step=192), 192, seed=9, **_t(t))),
    ]),
}


COLLECTION = {"meadow": "Meadow", "trees": "Small tree", "rocks": "Rock", "meadow_again": "Meadow",
              "pond_edge": "Pond edge", "rocks_on_path": "Rocks", "trees_on_mound": "Small tree", "shrubs": "Shrubs",
              "deadfall": "Deadfall", "wildflowers": "Wildflowers", "boulders": "Boulder"}  # step -> what it scatters


def run(name: str, *, tally: Callable[[], Any] = lambda: None) -> list[tuple[str, dict[str, Any], Any]]:
    """Each step of a scenario: (step, the room after it, its tally)."""
    make, steps = STEPS[name]
    scene, out = make(), []
    for step, stroke in steps:
        t = tally()
        scene = stroke(scene, t)
        out.append((step, scene, t))
    return out
