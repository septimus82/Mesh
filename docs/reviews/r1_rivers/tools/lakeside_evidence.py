"""R1 evidence on the scratch Lakeside copy: flow sequence (flowing and still), a close bend crop, the measured drift
along the brook, and a contact sheet. Real 1280x720 hidden-window frames from the R1 checkout's renderer."""
import json
import os
import sys
from pathlib import Path

REPO = Path(r"D:\Games\Mesh-rivers")
M17 = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\D--Games-Mesh\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\m17")
OUT = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\D--Games-Mesh\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\river\evidence")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scratch_guard import inside_scratch  # noqa: E402

OUT = inside_scratch(OUT)  # (never a mis-converted path such as D:\c\...)
sys.path[:0] = [str(REPO), str(REPO / "tooling")]
os.environ.update({"MESH_USER_DIR": str(M17 / "user"), "MESH_PROJECTS_DIR": str(M17 / "userprojects"),
                   "APPDATA": str(M17 / "appdata"), "XDG_DATA_HOME": str(M17 / "xdg")})
OUT.mkdir(parents=True, exist_ok=True)

import r1_river_study as study  # noqa: E402
from hd2d_demo import HiddenGame  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

TARGET = (1040 / 32, 820 / 32, -8 / 32)  # beside the footbridge, looking at the brook passing under it
BEND = (900 / 32, 905 / 32, -6 / 32)
TIMES = (10.0, 10.25, 10.5, 10.75)
report = {}
for name in ("lakeside_river", "lakeside_river_still"):
    game = HiddenGame(M17 / "projects" / "lakeside", size=(1280, 720))
    try:
        game.load(f"packs/core_regions/scenes/{name}.json")
        game.step(3)
        frames = [study.frame(game, TARGET, t) for t in TIMES]
        for t, f in zip(TIMES, frames):
            f.save(OUT / f"{name}_t{t:.2f}.png")
        report[name] = {"drift_texels_per_0.25s": study.drift(game, "brook", TARGET, 10.25),
                        "frames_identical": all(f.tobytes() == frames[0].tobytes() for f in frames),
                        "rivers_error": getattr(game.window, "hd2d_rivers_error", None),
                        "stats": {k: v for k, v in game.window.hd2d_renderer.stats().items()
                                  if k in ("rivers", "water_surfaces", "water_bytes", "water_error")}}
        report[name]["frame_ms"] = study.frame_ms(game, TARGET, 120)
        bend = study.frame(game, BEND, 10.0)
        at = study.to_screen(game, BEND)
        if at:  # a close crop of the bend, 3x (nearest: the texels as drawn)
            x, y = int(at[0]), int(at[1])
            crop = bend.crop((x - 160, y - 90, x + 160, y + 90))
            crop.resize((crop.width * 3, crop.height * 3), Image.NEAREST).save(OUT / f"{name}_bend_x3.png")
    finally:
        game.close()
# flow sequence sheet: a strip of the river near the bridge at each moment, flowing above, still below
sheet = Image.new("RGB", (4 * 420 + 50, 2 * 250 + 60), (20, 20, 20))
d = ImageDraw.Draw(sheet)
for row, name in enumerate(("lakeside_river", "lakeside_river_still")):
    for col, t in enumerate(TIMES):
        im = Image.open(OUT / f"{name}_t{t:.2f}.png").crop((380, 230, 590, 355))
        sheet.paste(im.resize((420, 250), Image.NEAREST), (10 + col * 430, 30 + row * 280))
        d.text((12 + col * 430, 14 + row * 280), f"{'flow 1.2 m/s' if row == 0 else 'flow 0 (control)'}  t={t:.2f}s",
               fill=(255, 255, 255))
sheet.save(OUT / "flow_sequence_sheet.png")
(OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=1))
