"""M17-L3 E2 evidence: real frames of the game (1280 x 720, hidden window), E1 base or E2, the same scenes.

    py -3.13 frames.py <worktree> <out dir> <tag>

Scenes (tooling/hd2d_lamp_glow_demo.py's rooms, built once per tag under <out>/proj-<tag>):
- the template village at noon / evening / night, its two lamps on (as shipped) and off;
- the village at night: the east lamp blue (#5080ff); the west lamp at intensity 0.5, 3 and 0;
- Lakeside's cottage and four lamp posts at night, lamps on; #459's fixture room; the template cottage interior.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WT, OUT, TAG = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sys.path.insert(0, str(WT))
sys.path.insert(0, str(WT / "tooling"))
os.chdir(WT)
import engine.optional_arcade  # noqa: E402,F401  (first, as the engine runs; and so `engine` is this worktree's)
import engine.hd2d.renderer as R  # noqa: E402
from hd2d_demo import HiddenGame  # noqa: E402

sys.path.insert(2, r"D:\Games\Mesh-l3g\tooling")  # E2's scene builders (they read no E2 engine code)
import hd2d_lamp_glow_demo as demo  # noqa: E402

assert Path(R.__file__).resolve().is_relative_to(WT.resolve()), R.__file__

project = OUT / f"proj-{TAG}"
SCENES = []
if not project.exists():
    rooms = demo.build(project)
else:
    rooms = {"village": f"{demo.SCENES}/start.json", "lakeside": f"{demo.SCENES}/glow_lakeside.json",
             "fixtures": f"{demo.SCENES}/lamp_fixtures.json", "cottage": f"{demo.SCENES}/cottage.json"}
keep = lambda li: li  # noqa: E731
off = demo.VARIANTS["off"]
for sun in ("noon", "evening", "night"):
    SCENES.append((f"village_on_{sun}", demo.village_variant(project, f"on_{sun}", keep)))
    SCENES.append((f"village_off_{sun}", demo.village_variant(project, f"off_{sun}", off)))
for name in ("blue_east", "dim_west", "bright_west", "zero_west"):
    SCENES.append((f"village_{name}_night", demo.village_variant(project, f"{name}_night", demo.VARIANTS[name])))


def night(path: str, name: str) -> str:
    from engine import project_ops as ops

    scene = json.loads((project / path).read_text(encoding="utf-8"))
    out = f"{demo.SCENES}/ev_{name}.json"
    (project / out).write_text(json.dumps(ops.set_hd2d_sun(scene, preset="night"), indent=2), encoding="utf-8")
    return out


SCENES += [("lakeside_night", night(rooms["lakeside"], "lakeside")), ("fixtures_night", night(rooms["fixtures"], "fixtures")),
           ("cottage", rooms["cottage"])]
frames = OUT / f"frames-{TAG}"
frames.mkdir(exist_ok=True)
facts = {}
game = HiddenGame(project, size=(1280, 720))
game.window.audio.set_muted(True)
try:
    for name, path in SCENES:
        game.load(path)
        game.step(120)
        game.window.motion_time = 0.0
        if hasattr(game.window, "water_time"):
            game.window.water_time = 0.0
        game.draw().convert("RGB").save(frames / f"{name}.png")
        st = game.window.hd2d_renderer.stats()
        facts[name] = {"draw_calls": st["draw_calls"], "static_draws": st["static_draws"],
                       "lamp_head_draws": st.get("lamp_head_draws", 0), "buffer_bytes": st["buffer_bytes"],
                       "texture_bytes": st["texture_bytes"], "boxes": demo.head_boxes(game) if TAG != "base" else None}
finally:
    game.close()
(OUT / f"facts-{TAG}.json").write_text(json.dumps(facts, indent=1), encoding="utf-8")
print(sorted(facts))
