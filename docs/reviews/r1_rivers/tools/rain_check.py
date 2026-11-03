"""R1 evidence: the template study's north river in rain (rings on open water; under the bridge's deck, sheltered)."""
import json
import os
import sys
from pathlib import Path

REPO = Path(r"D:\Games\Mesh-rivers")
OUT = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\D--Games-Mesh\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\river\evidence")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scratch_guard import inside_scratch  # noqa: E402

OUT = inside_scratch(OUT)  # (never a mis-converted path such as D:\c\...)
sys.path[:0] = [str(REPO), str(REPO / "tooling")]
ENV = OUT.parent / "env"
os.environ.update({"MESH_USER_DIR": str(ENV / "u"), "MESH_PROJECTS_DIR": str(ENV / "p"), "APPDATA": str(ENV / "a"),
                   "XDG_DATA_HOME": str(ENV / "x")})
import r1_river_study as study  # noqa: E402
from hd2d_demo import SCENES, HiddenGame  # noqa: E402

from engine import project_ops as ops  # noqa: E402

project = study.make_project(OUT / "rain", "rain", flow=0.0)
path = project / SCENES / "start.json"
scene = ops.set_particles(json.loads(path.read_text(encoding="utf-8")), [{"preset": "rain", "count": 4000, "seed": 2}])
path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
game = HiddenGame(project, size=(1280, 720))
try:
    game.load(f"{SCENES}/start.json")
    game.step(30)
    target = (640 / 32, 700 / 32, -0.25)
    for t in (10.0, 10.3):
        study.frame(game, target, t).save(OUT / f"rain_still_river_t{t:.1f}.png")
    a, b = study.frame(game, target, 10.0), study.frame(game, target, 10.3)
    changed = [study.to_screen(game, p) for p in study.course(game, "north")]
    moved = {}
    for p, at in zip(study.course(game, "north"), changed):
        if at is not None:
            key = "under_deck" if 720 <= p[1] * 32 <= 816 else "open"
            xy = (int(at[0]), int(at[1]))
            moved.setdefault(key, [0, 0])
            moved[key][0] += a.getpixel(xy) != b.getpixel(xy)
            moved[key][1] += 1
    print("flow 0 in rain: course texels changed between t=10.0 and 10.3 (rings) / seen:", moved)
finally:
    game.close()
