"""Probe: the BEND river seen from straight above, against the same village without it: holes and spill."""
import os
import sys
from pathlib import Path

REPO = Path(r"D:\Games\Mesh-rivers")
OUT = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\D--Games-Mesh\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\river\bend")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scratch_guard import inside_scratch  # noqa: E402

OUT = inside_scratch(OUT)  # (never a mis-converted path such as D:\c\...)
assert str(OUT).startswith("C:\\Users\\slebb\\AppData\\Local\\Temp\\claude\\"), OUT  # scratch only
sys.path[:0] = [str(REPO), str(REPO / "tooling")]
ENV = OUT.parent / "env"
os.environ.update({"MESH_USER_DIR": str(ENV / "u"), "MESH_PROJECTS_DIR": str(ENV / "p"), "APPDATA": str(ENV / "a"),
                   "XDG_DATA_HOME": str(ENV / "x")})
import r1_river_study as study  # noqa: E402
from hd2d_demo import SCENES, HiddenGame  # noqa: E402

target = (300 / 32, 140 / 32, 0.0)
frames = {}
for name, river in (("plain", False), ("bend", True)):
    game = HiddenGame(study.make_bend_project(OUT, name, river=river), size=study.study.SIZE)
    try:
        game.load(f"{SCENES}/start.json")
        game.step(3)
        game.window.hd2d_renderer.camera.pitch = 89.0
        frames[name] = study.frame(game, target, 10.0)
        frames[name].save(OUT / f"{name}.png")
        if river:
            inside, outside = study.bank_to_bank(game, "bend")
            spots = {"inside": inside, "outside": outside}
            screen = {k: [study.to_screen(game, p) for p in v] for k, v in spots.items()}
    finally:
        game.close()
for k, pts in screen.items():
    drawn = [at for at in pts if at and frames["bend"].getpixel((int(at[0]), int(at[1])))
             != frames["plain"].getpixel((int(at[0]), int(at[1])))]
    print(k, len(pts), "on screen", sum(1 for a in pts if a), "drawn", len(drawn))
