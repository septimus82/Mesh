"""#485 minimal reproduction: Mesh Studio's HD-2D picture of a FIXED Studio camera changes when only the unseen game
camera's pitch changes. Nothing else of the game camera matters (target, yaw, fov, distance, ortho, aspect: see
probe485.py), and the sun's view-projection never changes (it's fitted to the room's box).

    py -3.13 -I minimal_repro.py WORKTREE [--mesa]     # prints the changed share; 0 once the drawing camera's
                                                       # pitch stands the billboards up (the proposed correction)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

WT = Path(sys.argv[1]).resolve()
if "--mesa" in sys.argv:
    sys.path.insert(0, str(Path(__file__).resolve().parent))  # mesa_preload.py beside this script (its mesa/x64 copy)
    import mesa_preload  # noqa: F401
sys.path[:0] = [str(WT), str(WT / "tooling")]
os.chdir(WT)
from hd2d_demo import SCENES, HiddenGame  # noqa: E402

import engine.optional_arcade  # noqa: E402,F401
from engine.project_scaffold import create_project  # noqa: E402
from engine.studio import open_studio  # noqa: E402

project = Path(tempfile.mkdtemp(prefix="h485_min_")) / "game"
create_project(project, "Game", template_id="hd2d_rpg")
game = HiddenGame(project, size=(1280, 720))
game.window.audio.set_muted(True)
game.load(f"{SCENES}/start.json")
studio = open_studio(game.window, project, "packs/core_regions/worlds/main.json", f"{SCENES}/start.json")
view = studio.hd2d
view.advance_motion = view.advance_weather = lambda dt: None
for _ in range(5):
    game.window.dispatch_event("on_update", 1 / 60)
    game.window.dispatch_event("on_draw")
hd, (_, _, w, h) = view.renderer, view.viewport()


def studio_picture() -> bytes:
    tex = hd.ctx.texture((int(w), int(h)), components=4)
    fbo = hd.ctx.framebuffer(color_attachments=[tex])
    fbo.use()
    pixels = bytes(hd.draw(read_final=True, camera=view.camera))  # Studio's call: its own camera
    game.window.use()
    return pixels


before, sun_before = studio_picture(), [list(r) for r in hd.lighting.sun_vp]
hd.camera.pitch += 30.0  # only the unseen game camera's pitch
after, sun_after = studio_picture(), [list(r) for r in hd.lighting.sun_vp]
changed = sum(1 for k in range(0, len(before), 3) if before[k:k + 3] != after[k:k + 3]) / (len(before) // 3)
print(f"studio camera pitch {view.camera.pitch}, game camera pitch {hd.camera.pitch - 30} -> {hd.camera.pitch}: "
      f"{changed:.4%} of Studio's picture changed; sun view-projection unchanged: {sun_before == sun_after}")
game.close()
import shutil  # noqa: E402

shutil.rmtree(project.parent, ignore_errors=True)
