"""M17-W1 evidence and tests: a waterfall in a disposable HD-2D room (hidden windows only).

``make_project`` makes a project from the HD-2D RPG template and turns its start room into a waterfall glen: its
village taken away (the player kept), the ground sculpted into a plateau 3 m high in the north with a cliff along
y = 778 px, a natural pond at the cliff's foot (its bed 0.4 m down), and a 3 m stream running south across the plateau
(towards the game's camera) that falls from its lip at the cliff's edge into the pond (a waterfall from point 3 to point 4, 2.875 m high,
``mouth: "auto"``), its bed carved (0.4 m) as Studio's button carves it. The cliff and the lip are painted stone,
rocks are scattered along the cliff top and round the pond, and a boulder stands on the shore beside the fall's foot.
Everything is made with the project ops, as Studio or an AI would make it. ``variant`` adds the evidence's other
rooms' changes: "evening" (a low warm sun, lamps lit by the pool), "haze_bloom" (the evening with the room's haze and
warm bloom), "plain" (the same stream without its waterfall: the stretch an ordinary slope, not flowing into the pond,
which it can't meet so far above it), "tall" (a 16 m plateau and fall: the most allowed), "pond_landing" (the
pond 1.25 m further north and waded to 1.5 m, the fall's foot 1.1 m inside it), "many" (four more falls on
parallel streams, for the cost of several).
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
from hd2d_demo import SCENES  # noqa: E402

PX = 32.0
PLATEAU_PX = 96.0  # the plateau's ground: 3 m up
UPPER_PX = 92.0  # the stream's water on it: an eighth of a metre under its ground (in its carved bed)
ROOM_H = 1408.0  # px: the template's ground, south (y 0, the camera's side) to north


def Y(y: float) -> float:
    """A place's y measured from the north edge (px): the glen is laid out north to south."""
    return ROOM_H - y


CLIFF_Y = Y(630.0)  # px: the cliff's edge
# [x, y, width, level] px: across the plateau, its lip at the cliff's edge, its foot in the pond
COURSE = [[640.0, Y(150.0), 96.0, UPPER_PX], [652.0, Y(400.0), 96.0, UPPER_PX], [640.0, Y(612.0), 96.0, UPPER_PX],
          [640.0, Y(676.0), 96.0, 0.0], [640.0, Y(790.0), 112.0, 0.0]]
FALL = {"from": 2}
POND = {"x": 640.0, "y": Y(840.0), "width": 544.0, "height": 340.0}  # px: a natural pond, its level the ground's
POND_BED_PX = 12.8  # its sculpted bed: 0.4 m under its water in the middle
BED_M = 0.4
BOULDER = (716.0, Y(668.0))  # px: on the shore by the fall's foot, the east side
PLAYER = (560.0, Y(1010.0))  # px: south of the pond, looking at the fall
LAMPS = ((560.0, 288.0), (720.0, 288.0))  # px: the template's two lamps' lights, south of the pond


def _dabs(xs: Any, ys: Any, strength: float = 1.0) -> list[list[float]]:
    return [[float(x), float(y), strength] for y in ys for x in xs]


TALL_PLATEAU_PX, TALL_UPPER_PX = 510.0, 512.0  # "tall": a 16 m fall (the most allowed), its stream 2 px proud


def glen(scene: dict[str, Any], *, fall: bool = True, carved: bool = True, extra: int = 0,
         tall: bool = False, landing: bool = False) -> dict[str, Any]:
    """The waterfall glen, built into ``scene`` (the template's start room) with the project ops (``tall``: its plateau
    16 m up, its stream on it uncarved, 2 px proud of the ground, falling the most a waterfall may: 16 m)."""
    plateau = TALL_PLATEAU_PX if tall else PLATEAU_PX
    course = [[x, y, w, TALL_UPPER_PX if tall and level == UPPER_PX else level] for x, y, w, level in COURSE]
    if landing:  # ("pond_landing": its foot 1.1 m inside a pond waded to 1.5 m: the curtain's lower part over it)
        course[3][1] = Y(696.0)
    from engine import project_ops as ops

    hd2d = scene["settings"]["hd2d"]
    hd2d["structures"] = []
    scene["lights"] = [li for li in scene.get("lights") or [] if li.get("type") == "ambient"]  # (lamps: evening)
    scene["entities"] = [e for e in scene["entities"] if e.get("prefab_id") == "player"]
    for e in scene["entities"]:
        e["x"], e["y"] = PLAYER
    # the plateau (3 m), its edge kept crisp by small brushes along the cliff, the ground below it at 0
    scene = ops.sculpt_terrain_stroke(scene, "flatten", _dabs(range(0, 1281, 64), [Y(v) for v in range(0, 577, 64)]), radius=96.0,
                                      target=plateau)
    scene = ops.sculpt_terrain_stroke(scene, "flatten", _dabs(range(0, 1281, 12), (Y(606.0), Y(618.0))), radius=18.0,
                                      target=plateau)
    scene = ops.sculpt_terrain_stroke(scene, "flatten", _dabs(range(0, 1281, 12), (Y(648.0), Y(662.0))), radius=18.0,
                                      target=0.0)
    scene = ops.paint_terrain_stroke(scene, "stone", [[float(x), y, 1.0] for x in range(0, 1281, 24)
                                                      for y in (Y(622.0), Y(640.0))], radius=26.0)
    scene, pond = ops.place_blank(scene, "start", "Pool", POND["x"], POND["y"] + (40.0 if landing else 0.0))
    scene = ops.set_water(scene, pond, preset="natural_pond", width=POND["width"], height=POND["height"],
                          **({"passable": "wade", "wade_depth": 1.5} if landing else {}))
    scene = ops.sculpt_terrain_stroke(scene, "flatten", _dabs(range(480, 801, 48), [Y(v) for v in range(780, 901, 48)]), radius=80.0,
                                      target=-POND_BED_PX)
    # (without its waterfall it can't flow into the pond: 2.9 m above it at the shore; its mouth stays none)
    scene = ops.add_river(scene, "glen_falls", course, flow=1.2, mouth="auto" if fall else "none", ends="round_source",
                          **({"falls": [dict(FALL)]} if fall else {}))
    if carved:
        scene = ops.carve_river_bed(scene, "glen_falls", depths=[BED_M] * len(COURSE))
    for k in range(extra):  # (the cost of several: four more on parallel streams, west and east)
        x = (200.0, 330.0, 950.0, 1080.0)[k]
        course = [[x, Y(150.0), 64.0, UPPER_PX], [x, Y(400.0), 64.0, UPPER_PX], [x, Y(612.0), 64.0, UPPER_PX],
                  [x, Y(668.0), 64.0, 0.0], [x, Y(760.0), 64.0, 0.0]]
        scene = ops.add_river(scene, f"side_{k}", course, flow=1.0, falls=[{"from": 2}])
        if carved:
            scene = ops.carve_river_bed(scene, f"side_{k}", depths=[BED_M] * len(course))
    scene = ops.scatter_stroke(scene, "Rocks", [[float(x), Y(600.0)] for x in range(300, 981, 40)
                                                if abs(x - 640) > 90], radius=28.0, seed=3)
    scene = ops.scatter_stroke(scene, "Rocks", [[float(x), Y(690.0)] for x in range(380, 901, 40)], radius=30.0, seed=5)
    scene = ops.scatter_stroke(scene, "Boulder", [list(BOULDER)], radius=20.0, density=20.0, seed=1)
    return scene


def make_project(out: Path, name: str, *, variant: str = "day", carved: bool = True) -> Path:
    from engine import project_ops as ops

    project: Path = study.new_project(out, name, stage6a=False)
    path = project / SCENES / "start.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    lamps = [li for li in scene.get("lights") or [] if li.get("type") != "ambient"]  # (at LAMPS)
    # (the plain stream isn't carved: carving a slope standing over the ground below the cliff would sink it)
    scene = glen(scene, fall=variant != "plain", carved=carved and variant not in ("plain", "tall"),
                 extra=4 if variant == "many" else 0, tall=variant == "tall", landing=variant == "pond_landing")
    if variant in ("evening", "haze_bloom"):
        hd2d = scene["settings"]["hd2d"]
        hd2d["sun"] = {"color": "#ffb070", "direction": [-0.75, -0.35, 0.28], "intensity": 0.75}
        hd2d["ambient"] = 0.3
        hd2d["sky"] = "#d98a5a"
        hd2d["structures"] = [{"id": f"lamp_{i}", "model": "assets/models/lamp_post.glb", "x": x, "y": y}
                              for i, (x, y) in enumerate(LAMPS)]
        scene["lights"] = [*scene["lights"], *lamps]
    if variant == "haze_bloom":
        scene = ops.set_hd2d_haze(scene, "evening")
        scene = ops.set_hd2d_bloom(scene, "warm")
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    return project


def scene_of(project: Path) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((project / SCENES / "start.json").read_text(encoding="utf-8"))
    return doc
