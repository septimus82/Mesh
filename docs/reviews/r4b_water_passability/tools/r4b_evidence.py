r"""R4B evidence (scratch only): Lakeside's lake (blocking: Walk through it off) and its brook mouth, played in a
hidden 1280x720 window, before (R4A merged, b5ef725) and after (R4B), the same walks and cameras.

    python r4b_evidence.py <repo> before|after

A fresh scratch copy of D:\Games\Lakeside Village (read only); the R4A setup (Puddle 2 removed, the brook into the
lake, mouth auto, its source round, carved, plants cleared).
"""
import json
import os
import shutil
import sys
import time
from pathlib import Path

REPO, PHASE = Path(sys.argv[1]), sys.argv[2]
HERE = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\c18a071c64bbe7a7\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\river4")
sys.path.insert(0, str(HERE))
from scratch_guard import inside_scratch  # noqa: E402

ROOT = inside_scratch(HERE / "r4b" / PHASE)
if ROOT.exists():
    shutil.rmtree(ROOT)  # (this script's own output from an earlier run)
ROOT.mkdir(parents=True)
PROJECT = inside_scratch(ROOT / "lakeside")
shutil.copytree(Path(r"D:\Games\Lakeside Village"), PROJECT, ignore=shutil.ignore_patterns("saves", "artifacts"))
sys.path[:0] = [str(REPO), str(REPO / "tooling")]
os.environ.update({"MESH_USER_DIR": str(ROOT / "user"), "MESH_PROJECTS_DIR": str(ROOT / "userprojects"),
                   "APPDATA": str(ROOT / "appdata"), "XDG_DATA_HOME": str(ROOT / "xdg"), "MESH_STUDIO_NO_AI_BRIDGE": "1"})
import r3_river_bed_study as walker  # noqa: E402
from hd2d_demo import HiddenGame  # noqa: E402

from engine import project_ops as ops  # noqa: E402
from engine.water import extent, inside  # noqa: E402

COURSE = [[700, 960, 56, -4.0], [800, 930, 60, -5.0], [900, 905, 64, -6.0], [990, 870, 66, -7.5],
          [1060, 852, 68, -9.0], [1130, 860, 70, -10.5], [1190, 890, 74, -12.0], [1250, 935, 84, -13.25]]
report: dict = {"phase": PHASE, "repo": str(REPO)}
scenes = PROJECT / "packs" / "core_regions" / "scenes"
scene = json.loads((scenes / "lakeside.json").read_text(encoding="utf-8"))
scene = ops.remove_entity(scene, next(e for e in scene["entities"] if e.get("name") == "Puddle 2")["id"])
scene = ops.add_river(scene, "brook", COURSE, mouth="auto", ends="round_source")
scene = ops.carve_river_bed(scene, "brook")
(scenes / "lakeside_r4b.json").write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")

game = HiddenGame(PROJECT, size=(1280, 720))
try:
    t = time.perf_counter()
    game.load("packs/core_regions/scenes/lakeside_r4b.json")
    report["load_ms"] = round((time.perf_counter() - t) * 1000, 1)
    game.step(3)
    world = game.window.hd2d_world
    t = time.perf_counter()
    report["nav_cells"] = world.walkable()
    report["nav_grid_ms"] = round((time.perf_counter() - t) * 1000, 1)
    lake = next(b for b in game.window.water_bodies if b.entity.mesh_entity_data.get("id", "").startswith("lakeside_puddle_1632"))
    centre = (float(lake.entity.center_x), float(lake.entity.center_y))
    bw, bh = extent(lake.water)
    walks = {}
    for name, start, key, axis in (("from_the_east", (1700.0, 1000.0, 0.0), game.arcade.key.A, 0),
                                   ("from_the_north_by_the_mouth", (1300.0, 760.0, 0.0), game.arcade.key.S, 1)):
        probe = walker.walk(game, start, key, 3)
        if axis == 1 and probe["y"] < start[1]:
            key = game.arcade.key.W
        went = walker.walk(game, start, key, 240)
        if axis == 0:
            shore = next(x for x in range(int(start[0]), 1000, -1) if inside(lake.water, centre, (x, start[1])))
            box_edge = centre[0] + bw / 2
            stop = went["x"]
        else:
            ys = range(int(start[1]), 1300) if key == game.arcade.key.S or True else ()
            shore = next(y for y in range(int(start[1]), 1300) if inside(lake.water, centre, (start[0], y)))
            box_edge = centre[1] - bh / 2
            stop = went["y"]
        walks[name] = {"stopped_at": round(stop, 1), "visible_shore_at": shore, "box_edge_at": round(box_edge, 1),
                       "short_of_the_shore_px": round(abs(stop - shore), 1)}
        game.draw().convert("RGB").save(ROOT / f"{name}.png")
    report["walks"] = walks
    # cost: World.stand over the lake's surroundings, and the play frame
    pts = [(x / 32, y / 32) for x in range(1150, 1700, 9) for y in range(800, 1200, 9)]
    t = time.perf_counter()
    for x, y in pts:
        world.stand(x, y, min((h for h, _s in world.heights_at(x, y)), default=0.0), 0.3, 0.19)
    report["stand_us"] = round((time.perf_counter() - t) / len(pts) * 1e6, 2)
    frames = []
    for _ in range(90):
        t = time.perf_counter()
        game.step(1)
        game.draw()
        frames.append((time.perf_counter() - t) * 1000)
    report["play_frame_ms_median"] = round(sorted(frames)[len(frames) // 2], 2)
finally:
    game.close()
(ROOT / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
print(json.dumps(report, indent=1))
