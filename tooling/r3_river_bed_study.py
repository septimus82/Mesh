"""#461 R3 evidence: a river's bed, its scatter and its water underfoot, in the HD-2D starter village (hidden windows
only).

The test village: a project from the HD-2D RPG template whose north path (the paving under the bridge) gives way to
a 3 m stream flowing north under the bridge, its water 0.25 m below the ground (unseen until its bed is carved), with
meadow scattered over its course. ``make_project(carved=True)`` carves its bed with ``project_ops.carve_river_bed``
(shallow at its second point: a ford) and clears the scatter in its water, as Studio's buttons do.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
import hd2d_visual_study as study  # noqa: E402
from hd2d_demo import SCENES, HiddenGame  # noqa: E402

PX = 32.0
# [x, y, width, level] px: 3 m wide, its water 8 px (0.25 m) under the ground, falling 1 px a point
COURSE = [[640.0, 430.0, 96.0, -8.0], [652.0, 600.0, 96.0, -9.0], [640.0, 768.0, 96.0, -10.0],
          [610.0, 930.0, 96.0, -11.0], [600.0, 1080.0, 96.0, -12.0]]
DEPTHS = [0.8, 0.3, 0.8, 0.8, 0.8]  # m: deep everywhere but the ford at its second point (y 600 px)
FORD_Y, DEEP_Y = 600.0, 1000.0  # px: across the ford, across the deep stretch
EAST_BANK_X, WEST_BANK_X = 736.0, 544.0  # px: dry ground either side (the stream: x 590-700 px)
DECK = (720.0, 768.0, 2.0)  # px, px, m: on the bridge's deck, east end


def make_project(out: Path, name: str, *, carved: bool = False) -> Path:
    from engine import project_ops as ops

    project: Path = study.new_project(out, name, stage6a=False)
    path = project / SCENES / "start.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    hd2d = scene["settings"]["hd2d"]
    hd2d["structures"] = [s for s in hd2d["structures"] if not s["id"].startswith("path_north")]
    scene = ops.add_river(scene, "brook", COURSE)
    scene = ops.scatter_stroke(scene, "Meadow", [[c[0], c[1]] for c in COURSE], radius=96, seed=7,
                               avoid_water=False)  # (as if scattered before the river: some in its water)
    if carved:
        scene = ops.carve_river_bed(scene, "brook", depths=DEPTHS)
        scene = ops.clear_scatter_in_rivers(scene, "brook")
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    return project


def walk(game: HiddenGame, start: tuple[float, float, float], key: int, frames: int) -> dict[str, Any]:
    """The player stood at ``start`` (px, px, elevation m) holds ``key`` for ``frames`` frames (the window's own key
    events): where it ended, the lowest it stood, the deepest water over its feet, its wading steps."""
    player = game.player()
    player.center_x = start[0]
    player.center_y = start[1] + (player.center_y - player.bottom)
    player.mesh_entity_data["elevation"] = start[2] * PX
    steps = len(getattr(game.window, "water_steps", None) or [])
    game.window.water_steps = []
    game.step(2)
    lowest, deepest, waded = start[2], 0.0, 0
    game.window.dispatch_event("on_key_press", key, 0)
    for _ in range(frames):
        game.step(1)
        lowest = min(lowest, float(player.mesh_entity_data.get("elevation", 0.0)) / PX)
        water = getattr(player, "mesh_hd2d_wading", None)
        if water is not None:
            deepest = max(deepest, water[0])
        waded = max(waded, len(game.window.water_steps or []))
    game.window.dispatch_event("on_key_release", key, 0)
    game.step(2)
    del steps
    return {"x": float(player.center_x), "y": float(player.bottom), "z": float(player.mesh_entity_data["elevation"]) / PX,
            "lowest": lowest, "deepest": deepest, "wading_steps": waded}
