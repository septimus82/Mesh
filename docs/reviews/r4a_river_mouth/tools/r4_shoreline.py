"""R4 evidence (scratch only): the floating-shoreline follow-up. A stream drawn over the village's ground (as Studio
draws one: 0.25 m above the ground clicked) with a dip in the ground beside it between two of its points, then
Carve the bed (the ops). Before (R3 at f552d6f) sinking measured the ground only at the points; after (R4A) every
quarter metre. Same camera; hidden Studio window.

    python r4_shoreline.py <repo> <out name>
"""
import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(sys.argv[1])
NAME = sys.argv[2]
HERE = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\c18a071c64bbe7a7\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\river4")
sys.path.insert(0, str(HERE))
from scratch_guard import inside_scratch  # noqa: E402

ROOT = inside_scratch(HERE / "shoreline" / NAME)
if ROOT.exists():
    shutil.rmtree(ROOT)  # (this script's own output from an earlier run)
ROOT.mkdir(parents=True)
sys.path[:0] = [str(REPO), str(REPO / "tooling")]
os.environ.update({"MESH_USER_DIR": str(ROOT / "user"), "MESH_PROJECTS_DIR": str(ROOT / "userprojects"),
                   "APPDATA": str(ROOT / "appdata"), "XDG_DATA_HOME": str(ROOT / "xdg"), "MESH_STUDIO_NO_AI_BRIDGE": "1"})
import hd2d_visual_study as vstudy  # noqa: E402
from hd2d_demo import SCENES  # noqa: E402
from hd2d_studio_demo import StudioDriver  # noqa: E402

from engine import project_ops as ops  # noqa: E402

COURSE = [[640.0, 430.0, 96.0, 8.0], [652.0, 640.0, 96.0, 8.0], [640.0, 700.0, 96.0, 8.0]]
DIPS = [[714.0, 520.0, 14], [718.0, 560.0, 14]]  # px, px, how far lowered: beside the stream between points 1 and 2

project = vstudy.new_project(ROOT, "shore", stage6a=False)
path = project / SCENES / "start.json"
scene = json.loads(path.read_text(encoding="utf-8"))
hd2d = scene["settings"]["hd2d"]
hd2d["structures"] = [s for s in hd2d["structures"] if not s["id"].startswith("path_north")]
scene = ops.sculpt_terrain_stroke(scene, "lower", DIPS, radius=40)
scene = ops.add_river(scene, "brook", COURSE)
scene = ops.carve_river_bed(scene, "brook")
path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
report = {"levels_px": [p[3] for p in ops.rivers(scene)[0]["points"]]}
d = StudioDriver(project)
try:
    v = d.studio.hd2d
    for cam, (target, dist, pitch) in {"top": ((20.6, 17.0, 0.0), 9.0, 89.0),
                                       "angled": ((21.0, 17.5, 0.0), 10.0, 35.0)}.items():
        v.camera.target, v.camera.distance, v.camera.pitch = target, dist, pitch
        d.advance(3)
        d.picture(ROOT / f"shoreline_{cam}.png")
finally:
    d.close()
(ROOT / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
print(json.dumps(report))
