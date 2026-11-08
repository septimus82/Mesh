"""M17-L3 E1 evidence: real frames (noon / evening / night) and GPU draw time, base engine or E1, same scenes.

    py -3.13 evidence.py <worktree> <out dir> <tag> frames|perf

The project (hd2d_rpg template, built once per tag under <out>/proj-<tag>) gets, per sun:
- start__<sun>.json: the template village as shipped (no glTF emission anywhere: ordinary materials);
- start__<sun>_glow.json: the same, its two lamp posts using lamp_post_glow.glb, a copy of the kit lamp post whose
  "lantern" material has emissiveFactor [1, 0.8, 0.55] (as Blender exports an Emission colour);
- swatches__<sun>.json: the village with E1's test panels (tooling/hd2d_emissive_demo.py) in front of the player.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

WT, OUT, TAG, MODE = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
sys.path.insert(0, str(WT))
sys.path.insert(0, str(WT / "tooling"))
os.chdir(WT)
import engine.hd2d.renderer as R  # noqa: E402

assert Path(R.__file__).resolve().is_relative_to(WT.resolve()), R.__file__
sys.path.insert(1, r"D:\Games\Mesh-l3e\tooling")  # the panels' builder (E1's tooling; it uses only join_glb)
import hd2d_emissive_demo as demo  # noqa: E402
from hd2d_demo import HiddenGame  # noqa: E402

from engine import project_ops as ops  # noqa: E402
from engine.hd2d import glb  # noqa: E402

SUNS = ("noon", "evening", "night")
SCENES = "packs/core_regions/scenes"
project = OUT / f"proj-{TAG}"


def build() -> None:
    from engine.hd2d import catalog
    from engine.project_scaffold import create_project

    create_project(project, "E1", "hd2d_rpg")
    doc, binary = glb.split_glb((project / "assets/models/lamp_post.glb").read_bytes())
    next(m for m in doc["materials"] if m["name"] == "lantern")["emissiveFactor"] = [1.0, 0.8, 0.55]
    (project / "assets/models/lamp_post_glow.glb").write_bytes(glb.join_glb(doc, binary))
    swatches = catalog.import_model(project, demo.swatches_glb(OUT / f"swatches-{TAG}.glb"), name="swatches")
    start = json.loads((project / SCENES / "start.json").read_text(encoding="utf-8"))
    for sun in SUNS:
        scene = ops.set_hd2d_sun(start, preset=sun)
        (project / SCENES / f"start__{sun}.json").write_text(json.dumps(scene, indent=2), encoding="utf-8")
        glow = json.loads(json.dumps(scene))
        for st in glow["settings"]["hd2d"]["structures"]:
            if st["model"] == "assets/models/lamp_post.glb":
                st["model"] = "assets/models/lamp_post_glow.glb"
        (project / SCENES / f"start__{sun}_glow.json").write_text(json.dumps(glow, indent=2), encoding="utf-8")
        panels = json.loads(json.dumps(scene))
        panels["settings"]["hd2d"]["structures"].append({"id": "swatches", "model": swatches.model, "x": 640.0,
                                                         "y": 120.0})
        (project / SCENES / f"swatches__{sun}.json").write_text(json.dumps(panels, indent=2), encoding="utf-8")


def settle(game: HiddenGame, scene: str) -> None:
    game.load(f"{SCENES}/{scene}.json")
    game.step(120)
    game.window.motion_time = 0.0
    if hasattr(game.window, "water_time"):
        game.window.water_time = 0.0


if not project.exists():
    build()
game = HiddenGame(project, size=(1280, 720))
game.window.audio.set_muted(True)
result: dict = {"worktree": str(WT), "renderer": R.__file__}
try:
    if MODE == "frames":
        frames = OUT / f"frames-{TAG}"
        frames.mkdir(exist_ok=True)
        for kind in ("start", "glow", "swatches"):
            for sun in SUNS:
                name = {"start": f"start__{sun}", "glow": f"start__{sun}_glow", "swatches": f"swatches__{sun}"}[kind]
                settle(game, name)
                game.draw().convert("RGB").save(frames / f"{name}.png")
        result["frames"] = sorted(p.name for p in frames.iterdir())
    else:
        q = game.window.ctx.query(samples=False, time=True, primitives=False)
        for name in ("start__night", "start__night_glow", "swatches__night", "start__noon"):
            settle(game, name)
            hd = game.window.hd2d_renderer
            draw = type(hd).draw
            t = []
            for _ in range(660):  # the same settled frame drawn again (no update between): only the draw's cost varies
                with q:
                    draw(hd)
                t.append(q.time_elapsed / 1e6)
            t = sorted(t[60:])
            result[name] = {"n": len(t), "p10_ms": round(t[len(t) // 10], 4), "p50_ms": round(statistics.median(t), 4),
                            "p95_ms": round(t[int(0.95 * len(t))], 4), "target": [round(c, 3) for c in hd.camera.target],
                            "draw_calls": hd.draw_calls}
finally:
    game.close()
(OUT / f"{MODE}-{TAG}{'-' + sys.argv[5] if len(sys.argv) > 5 else ''}.json").write_text(json.dumps(result, indent=1))
print(json.dumps(result)[:400])
