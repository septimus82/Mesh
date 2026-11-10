"""H-485A: Mesh Studio's own canvas (view.draw(), read from the window) for a fixed Studio camera: saved, then drawn
again after the unseen game camera's pitch (and everything else) moves; and Studio's picture of the game's own
camera pose against the game path's picture of it.

    py -3.13 -I studio485.py WORKTREE SOURCE_PROJECTS_DIR OUT_DIR [--mesa]
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

WT, SRC, OUT = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()
if "--mesa" in sys.argv:
    sys.path.insert(0, str(Path(__file__).resolve().parent))  # mesa_preload.py beside this script (its mesa/x64 copy)
    import mesa_preload  # noqa: F401
sys.path.insert(0, str(WT))
sys.path.insert(1, str(WT / "tooling"))
os.chdir(WT)
import numpy as np  # noqa: E402
from hd2d_demo import SCENES, HiddenGame  # noqa: E402
from PIL import Image  # noqa: E402

import engine.optional_arcade  # noqa: E402,F401
from engine.studio import open_studio  # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)
FIELDS = ("target", "pitch", "fov", "distance", "ortho", "yaw")
report: dict = {"worktree": str(WT)}
tmp = Path(tempfile.mkdtemp(prefix="h485_studio_"))
try:
    for proj, room in (("proj_start", "start"), ("proj_cottage", "cottage"), ("proj_start_scatter", "start")):
        project = tmp / proj
        shutil.copytree(SRC / proj, project, ignore=shutil.ignore_patterns(".mesh"))
        game = HiddenGame(project, size=(1280, 720))
        game.window.audio.set_muted(True)
        scene = f"{SCENES}/{room}.json"
        game.load(scene)
        studio = open_studio(game.window, project, "packs/core_regions/worlds/main.json", scene)
        assert studio is not None
        w, view = game.window, studio.hd2d
        view.advance_motion = view.advance_weather = lambda dt: None
        try:
            for _ in range(5):
                w.dispatch_event("on_update", 1 / 60)
                w.dispatch_event("on_draw")
                w.ctx.gc()
            w.motion_time = 0.0
            hd = view.renderer
            x, y, vw, vh = (int(v) for v in view.viewport())

            def canvas() -> np.ndarray:
                w.clear()
                view.draw()  # Studio's own call: its camera, its canvas, its lines
                pic = np.asarray(game.arcade.get_image(x, y, vw, vh).convert("RGB")).copy()
                w.ctx.gc()
                return pic

            first = canvas()
            gc = hd.camera
            saved = tuple(getattr(gc, f) for f in FIELDS) + (hd._camera_ready,)
            moved: dict = {}
            for label, change in (("game_pitch_60", {"pitch": 60.0}),
                                  ("game_cam_far_away", {"target": (99.0, -40.0, 3.0), "pitch": 15.0, "yaw": 90.0,
                                                         "distance": 120.0, "fov": 50.0})):
                for f, v in change.items():
                    setattr(gc, f, v)
                pic = canvas()
                for f, v in zip(FIELDS, saved):
                    setattr(gc, f, v)
                m = np.abs(pic.astype(int) - first.astype(int)).max(axis=2) > 0
                moved[label] = round(float(m.mean()), 5)
            Image.fromarray(first).save(OUT / f"studio_{proj}.png")
            report[proj] = {"studio_cam": {f: (list(getattr(view.camera, f)) if f == "target" else getattr(view.camera, f))
                                           for f in FIELDS},
                            "game_pitch": gc.pitch, "canvas": hashlib.sha256(first.tobytes()).hexdigest()[:16],
                            "canvas_changed_when_game_camera_moved": moved}
        finally:
            game.close()
finally:
    shutil.rmtree(tmp, ignore_errors=True)
(OUT / "studio485.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
print(json.dumps(report, indent=1))
