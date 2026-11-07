"""Scratch AUTHORING PROBE (Lakeside visual audit): can the existing authoring tools (engine.project_ops, what
Studio's Scatter and Paint brushes record) break up the uniform meadow? Not a proposed art pass: one quick, crude
attempt, so the audit can say whether the weakness is composition or engine. Writes lakeside__probe.json and
lakeside__probe_wide.json beside the shipped scene in the SCRATCH copy (shipped files checked unchanged).
Usage: probe.py PROJECT
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Games\Mesh-lva")
from engine import project_ops as ops  # noqa: E402
from engine.hd2d.scatter import parse_scatter  # noqa: E402,F401

project = Path(sys.argv[1])
scenes = project / "packs" / "core_regions" / "scenes"
src = scenes / "lakeside.json"
assert hashlib.sha256(src.read_bytes()).hexdigest() == "18a7ee94b1c8e9444326f9643ebb4bbbb9315bad1edff5b777ab67da8c7f3901"
doc = json.loads(src.read_text(encoding="utf-8"))
before = {k: len(v) for k, v in doc["settings"]["hd2d"]["scatter"].items()}

# 1. flowers: not sprinkled everywhere, but in clumps where a villager would leave them (fence lines, house walls,
#    the lake's grassy edge, a few drifts in the open)
doc = ops.clear_scatter(doc, ["flowers_pink", "flowers_yellow"])
clumps = [(470, 400), (720, 760), (520, 610), (700, 610), (500, 230), (640, 230), (1300, 470), (1260, 700),
          (1600, 760), (1650, 1180), (300, 900), (850, 1100), (1500, 400), (250, 300)]
for i, (x, y) in enumerate(clumps):
    doc = ops.scatter_stroke(doc, "Wildflowers", [[x, y], [x + 24, y - 16]], radius=56, density=2.5, clumping=0.9,
                             seed=100 + i)
# 2. worn ground: the paths' ends and the doorsteps trodden to earth, lamp feet to bare ground
worn = [(608, 590, 56), (560, 205, 56), (1168, 500, 72), (1100, 520, 48)]
for x, y, r in worn:
    doc = ops.paint_terrain_stroke(doc, "earth", [[x, y, 0.55], [x + 12, y - 10, 0.45]], radius=r)
for x, y in [(800, 326), (941, 442), (1043, 755), (678, 586)]:
    doc = ops.paint_terrain_stroke(doc, "earth", [[x, y, 0.5]], radius=22)
# 3. a few broad patches of dry, paler grass, so the meadow has light and dark areas instead of one green
for i, (x, y) in enumerate([(300, 520), (900, 150), (1400, 300), (1750, 600), (420, 1000), (1000, 1250)]):
    doc = ops.scatter_stroke(doc, {"grass_dry": 1.0}, [[x, y], [x + 60, y + 30], [x + 120, y - 10]], radius=110,
                             density=2.0, clumping=0.8, seed=200 + i)
    doc = ops.paint_terrain_stroke(doc, "earth", [[x, y, 0.18], [x + 60, y + 30, 0.18], [x + 120, y - 10, 0.15]],
                                   radius=120)
after = {k: len(v) for k, v in doc["settings"]["hd2d"]["scatter"].items()}
(scenes / "lakeside__probe.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
(scenes / "lakeside__probe_wide.json").write_text(json.dumps(ops.set_hd2d_camera(doc, preset="wide"), indent=2),
                                                  encoding="utf-8")
assert hashlib.sha256(src.read_bytes()).hexdigest() == "18a7ee94b1c8e9444326f9643ebb4bbbb9315bad1edff5b777ab67da8c7f3901"
print(json.dumps({"scatter_before": before, "scatter_after": after,
                  "total": [sum(before.values()), sum(after.values())]}, indent=1))
