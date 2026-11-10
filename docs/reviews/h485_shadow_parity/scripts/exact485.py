"""H-485A: gameplay frames (HiddenGame: the game's own draw path, its own camera) for matched inputs, plus Studio's
default picture, hashed per frame, for comparing a worktree before and after the #485 correction.

    py -3.13 -I exact485.py WORKTREE SOURCE_PROJECTS_DIR OUT.json [--mesa]

Rooms: the village, the cottage (interior), the village with trees + meadow (proj_start_scatter). Each: settled
frames (camera still), then the player walked by moving its sprite a little every update (the camera following:
a moving camera), a frame drawn every few updates; wind/water/particles run on the fixed 1/60 s steps, the same
in every run."""
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
import hd2d_demo  # noqa: E402
from hd2d_demo import SCENES, HiddenGame  # noqa: E402

import engine.optional_arcade  # noqa: E402,F401

assert Path(hd2d_demo.__file__).resolve().is_relative_to(WT)
KINDS = ("texture", "framebuffer", "program", "buffer", "geometry", "vertex_array")
CASES = (("proj_start", "start"), ("proj_cottage", "cottage"), ("proj_start_scatter", "start"))


def sha(img) -> str:  # type: ignore[no-untyped-def]
    return hashlib.sha256(img.tobytes()).hexdigest()[:16]


report: dict = {"worktree": str(WT), "rooms": {}}
tmp = Path(tempfile.mkdtemp(prefix="h485_exact_"))
try:
    for proj, room in CASES:
        project = tmp / proj
        shutil.copytree(SRC / proj, project, ignore=shutil.ignore_patterns(".mesh"))
        game = HiddenGame(project, size=(960, 540))
        game.window.audio.set_muted(True)
        frames: list = []
        try:
            game.load(f"{SCENES}/{room}.json")
            game.step(30)
            hd = game.window.hd2d_renderer
            frames.append(["settled", sha(game.draw()), sha(game.draw())])
            player = next(s for s in game.window.scene_sprites if getattr(s, "mesh_tag", "") == "player") \
                if hasattr(game.window, "scene_sprites") else hd.followed()
            for k in range(24):  # walk up and right: the camera follows (moving camera)
                for _ in range(3):
                    player.center_x += 2.0
                    player.center_y += 1.5
                    game.step(1)
                frames.append([f"walk{k}", sha(game.draw()), list(round(v, 4) for v in hd.camera.target)])
            game.step(60)  # the camera settles at the new place
            frames.append(["arrived", sha(game.draw())])
            live = {k: getattr(game.window.ctx.stats, k)[0] - getattr(game.window.ctx.stats, k)[1] for k in KINDS}
            report["rooms"][f"{proj}:{room}"] = {"frames": frames, "pitch": hd.camera.pitch, "live": live,
                                                 "gl": game.window.ctx.info.RENDERER}
        finally:
            game.close()
finally:
    shutil.rmtree(tmp, ignore_errors=True)
OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
for name, r in report["rooms"].items():
    print(name, "pitch", r["pitch"], "frames", len(r["frames"]), "live", r["live"])
