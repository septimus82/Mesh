"""Scratch (Lakeside visual audit): real engine frames from a hidden GameWindow (no mockups, nothing shown on screen).

Every shot: load the scene, put the player at (x, y) (position set directly, no walking), reset the motion/water
clocks so matched shots share the same wind sway and ripples, run 150 frames (2.5 s: past the fade-in, camera
settled), draw one frame, save the PNG and what was drawn (camera, sun, ambient, sky, depth of field, lights).
"post": the engine's own PostProcessPipeline effects (engine/post_processing.py ColorGrading / Vignette), attached at
runtime: no scene field, op or Studio control exists for them, so this is the only way to show them.
Usage: capture.py PROJECT OUT W H SHOTS_JSON
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Games\Mesh-lva")
sys.path.insert(0, r"D:\Games\Mesh-lva\tooling")

project, out, w, h, shots_file = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
out.mkdir(parents=True, exist_ok=True)
for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "MESH_USER_DIR", "MESH_PROJECTS_DIR"):
    os.environ[name] = str(out.parent / "env" / name.lower())
    Path(os.environ[name]).mkdir(parents=True, exist_ok=True)
shots = json.loads(Path(shots_file).read_text(encoding="utf-8"))

from hd2d_demo import HiddenGame  # noqa: E402

game = HiddenGame(project, size=(w, h))
window = game.window
window.audio.set_muted(True)  # (never plays aloud)
from engine.post_processing import ColorGrading, Vignette  # noqa: E402

meta = {}
for shot in shots:
    pp = window.post_process_pipeline
    pp.effects.clear()
    for eff in shot.get("post", []):
        kind = eff["kind"]
        args = {k: v for k, v in eff.items() if k != "kind"}
        pp.add_effect(ColorGrading(**args) if kind == "grade" else Vignette(**args))
    game.load(shot["scene"])
    game.step(5)
    if shot.get("player"):
        p = game.player()
        p.center_x, p.center_y = shot["player"]
    window.motion_time = 0.0
    if hasattr(window, "water_time"):
        window.water_time = 0.0
    game.step(150)
    img = game.draw().convert("RGB")
    img.save(out / f"{shot['name']}.png")
    hd = window.hd2d_renderer
    m = {"scene": shot["scene"], "player": shot.get("player"), "size": [w, h], "post": shot.get("post", [])}
    if hd is not None:
        s, c = hd.settings, hd.camera
        m.update(camera={"pitch": c.pitch, "fov": c.fov, "distance": round(c.distance, 3), "ortho": c.ortho,
                         "target_m": [round(v, 3) for v in c.target]},
                 sun={"direction": [round(v, 3) for v in s.sun], "color": [round(v, 3) for v in s.sun_color],
                      "intensity": s.sun_intensity},
                 ambient=s.ambient, ambient_color=[round(v, 3) for v in s.ambient_color],
                 sky=[round(v, 3) for v in s.sky], shadows=s.shadows, shadow_resolution=s.shadow_resolution,
                 dof=hd.dof_status()[0], dof_frame=({k: v for k, v in hd.last_dof.items() if k != "settings"}
                                                    if hd.last_dof else None),
                 lamps=len(getattr(s, "lights", ()) or ()), draw_calls=hd.draw_calls,
                 gl=window.ctx.info.RENDERER)
    meta[shot["name"]] = m
    (out / "shots.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
game.close()
print("done", len(meta))
