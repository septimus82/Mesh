"""M17-L1: the HD-2D renderer's whole draw, GPU time (timer query), shipped scene vs candidate, at 1280x720.
Rounds alternate the two scenes (so clock changes fall on both); each round: load, settle, 120 timed frames.
Clocks are not locked (no system setting changes): read the medians as a comparison, not absolute costs.
Usage: gpu_cost.py PROJECT OUT.json"""
import json
import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Games\Mesh-lva")
sys.path.insert(0, r"D:\Games\Mesh-lva\tooling")
project, out = Path(sys.argv[1]), Path(sys.argv[2])
for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "MESH_USER_DIR", "MESH_PROJECTS_DIR"):
    os.environ[name] = str(out.parent / "env_gpu" / name.lower())
    Path(os.environ[name]).mkdir(parents=True, exist_ok=True)

from hd2d_demo import HiddenGame  # noqa: E402

game = HiddenGame(project, size=(1280, 720))
game.window.audio.set_muted(True)
ctx = game.window.ctx
query = ctx.query(samples=False, time=True, primitives=False)
S = "packs/core_regions/scenes/"
SCENES = {"before": S + "lakeside.json", "l1": S + "lakeside__l1.json", "l1b": S + "lakeside__l1b.json"}
VIEWS = {"v1_village": (1100, 650), "v4b_north": (1000, 1300), "v4_paths": (960, 250)}
times = {f"{v}/{s}": [] for v in VIEWS for s in SCENES}
try:
    for rnd in range(4):
        for view, (x, y) in VIEWS.items():
            for scene in (("before", "l1", "l1b") if rnd % 2 == 0 else ("l1b", "l1", "before")):
                game.load(SCENES[scene])
                game.step(5)
                p = game.player()
                p.center_x, p.center_y = x, y
                game.step(90)
                hd = game.window.hd2d_renderer
                original = type(hd).draw
                for _ in range(120):
                    game.step(1)
                    with query:
                        original(hd)
                    times[f"{view}/{scene}"].append(query.time_elapsed / 1e6)
finally:
    game.close()
res = {k: {"n": len(v), "p50_ms": round(statistics.median(v), 3), "p95_ms": round(sorted(v)[int(0.95 * len(v))], 3)}
       for k, v in times.items()}
out.write_text(json.dumps(res, indent=1), encoding="utf-8")
print(json.dumps(res, indent=1))
