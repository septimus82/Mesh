"""#461 R4 evidence and tests: a stream flowing into a pond, in the HD-2D starter village (hidden windows only).

The test village: a project from the HD-2D RPG template whose north path (the paving under the bridge) gives way to
a 3 m stream at the ground's level flowing south under the bridge into a natural pond (a grassy bank, reeds, a deep
middle) at the same level. ``make_project(mouth=True)`` joins it to the pond (``mouth: "auto"``), its source rounded
(``ends: "round_source"``); ``carved=True`` carves its bed shallow enough to wade (0.3 m) with the ops, as Studio's
buttons do.
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
# [x, y, width, level] px: 3 m wide, at the ground's level, its last point in the pond
COURSE = [[640.0, 430.0, 96.0, 0.0], [652.0, 600.0, 96.0, 0.0], [640.0, 768.0, 96.0, 0.0],
          [615.0, 930.0, 96.0, 0.0], [610.0, 1240.0, 96.0, 0.0]]
POND = {"x": 620.0, "y": 1240.0, "width": 448.0, "height": 288.0}  # px: a natural pond, its level the ground's
DEPTH_M = 0.3  # the carved bed: wadeable all along


def make_project(out: Path, name: str, *, mouth: bool = True, carved: bool = False,
                 ends: str = "round_source") -> Path:
    from engine import project_ops as ops

    project: Path = study.new_project(out, name, stage6a=False)
    path = project / SCENES / "start.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    hd2d = scene["settings"]["hd2d"]
    hd2d["structures"] = [s for s in hd2d["structures"] if not s["id"].startswith("path_north")]
    scene, pond = ops.place_blank(scene, "start", "Pond", POND["x"], POND["y"])
    scene = ops.set_water(scene, pond, preset="natural_pond", width=POND["width"], height=POND["height"])
    scene = ops.add_river(scene, "brook", COURSE, ends=ends, **({"mouth": "auto"} if mouth else {}))
    if carved:
        scene = ops.carve_river_bed(scene, "brook", depths=[DEPTH_M] * len(COURSE))
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    return project


def pond_id(project: Path) -> str:
    scene = json.loads((project / SCENES / "start.json").read_text(encoding="utf-8"))
    return next(str(e["id"]) for e in scene["entities"] if e.get("name") == "Pond")


def scene_of(project: Path) -> dict[str, Any]:
    scene: dict[str, Any] = json.loads((project / SCENES / "start.json").read_text(encoding="utf-8"))
    return scene
