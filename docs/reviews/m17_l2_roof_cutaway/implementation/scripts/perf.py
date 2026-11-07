"""M17-L2 scratch: the HD-2D renderer's whole draw, GPU time (timer query), for one engine checkout, on the cutaway
shots. Run once per engine in separate processes, alternating (clocks are not locked: compare runs A/B/A/B).
Usage: perf.py REPO PROJECT SHOTS_JSON OUT_JSON"""
import json
import os
import statistics
import sys
from pathlib import Path

repo, project, shots_file, out = sys.argv[1], Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
sys.path.insert(0, repo)
sys.path.insert(0, repo + r"\tooling")
for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "MESH_USER_DIR", "MESH_PROJECTS_DIR"):
    os.environ[name] = str(out.parent / "env_perf" / name.lower())
    Path(os.environ[name]).mkdir(parents=True, exist_ok=True)
import engine.hd2d.renderer as R  # noqa: E402

assert repo in R.__file__, R.__file__
from hd2d_demo import HiddenGame  # noqa: E402

KEEP = {"a1_front_of_cottage", "a2_beside_shop", "b3_behind_cottage_x608", "c1_partly_hidden", "d3_inside_shop",
        "e_close_behind_cottage", "e_indoor_behind_cottage", "v2_village_behind_cottage"}
shots = [s for s in json.loads(Path(shots_file).read_text(encoding="utf-8")) if s["name"] in KEEP]
game = HiddenGame(project, size=(1280, 720))
game.window.audio.set_muted(True)
q = game.window.ctx.query(samples=False, time=True, primitives=False)
res = {}
for shot in shots:
    game.load(shot["scene"])
    game.step(5)
    p = game.player()
    p.center_x, p.bottom = shot["player"]
    game.step(90)
    hd = game.window.hd2d_renderer
    draw = type(hd).draw
    t = []
    for _ in range(300):
        game.step(1)
        with q:
            draw(hd)
        t.append(q.time_elapsed / 1e6)
    t = t[60:]
    res[shot["name"]] = {"n": len(t), "p50_ms": round(statistics.median(t), 4), "p95_ms": round(sorted(t)[int(0.95 * len(t))], 4)}
game.close()
out.write_text(json.dumps({"engine": R.__file__, "has_new_rule": hasattr(R, "cutaway_cuts"), "shots": res}, indent=1), encoding="utf-8")
print("done", len(res))
