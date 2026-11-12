"""M17-L4-3 evidence, part 2 (hidden windows, 1280x720):
  template/  the HD-2D template village (a fresh `mesh new` project, a smaller room): off / Daytime / Evening, by day
             and under Studio's night sun
  studio/    Mesh Studio on a copy of the scratch Lakeside: its editing view (lines and all) with Evening haze, and the
             renderer's Studio path at 1280x720 with the game's own camera for the village shot, beside the game frame
Usage: py -3.13 template_and_studio.py WORKTREE OUT
"""
from __future__ import annotations

import dataclasses
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

WT, OUT = Path(sys.argv[1]), Path(sys.argv[2])
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(WT))
sys.path.insert(1, str(WT / "tooling"))
os.chdir(WT)
os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
import engine.optional_arcade  # noqa: E402,F401
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from engine import project_ops as ops  # noqa: E402
from engine.hd2d.haze import Haze  # noqa: E402

W, H = 1280, 720
SC = "packs/core_regions/scenes"


def flip(raw: Any, w: int = W, h: int = H) -> Any:
    return np.flipud(np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)).copy()


def template() -> None:
    from hd2d_demo import HiddenGame

    out = OUT / "template"
    out.mkdir(parents=True, exist_ok=True)
    proj_parent = OUT / "template_project"
    if proj_parent.exists():
        shutil.rmtree(proj_parent)
    proj_parent.mkdir()
    made = subprocess.run([sys.executable, "-m", "mesh_cli", "new", "game", "--dest", str(proj_parent), "--template",
                           "hd2d_rpg"], cwd=WT, capture_output=True, text=True, timeout=600)
    assert made.returncode == 0, made.stderr
    project = proj_parent / "game"
    doc = json.loads((project / SC / "start.json").read_text(encoding="utf-8"))
    (project / SC / "start_night.json").write_bytes(json.dumps(ops.set_hd2d_sun(doc, preset="night"), indent=2).encode())
    game = HiddenGame(project, size=(W, H))
    game.window.audio.set_muted(True)
    fbo = game.window.ctx.framebuffer(color_attachments=[game.window.ctx.texture((W, H), components=4)])
    try:
        for time, scene in (("day", "start.json"), ("night", "start_night.json")):
            game.load(f"{SC}/{scene}")
            game.window.motion_time = 0.0
            game.step(120)
            hd = game.window.hd2d_renderer
            base = hd.settings
            for name in ("off", "daytime", "evening"):
                hd.settings = base if name == "off" else dataclasses.replace(base, haze=Haze(name))
                fbo.use()
                Image.fromarray(flip(hd.draw(read_final=True))).save(out / f"template__{time}__{name}.png")
                game.window.use()
            hd.settings = base
    finally:
        game.close()


def studio() -> None:
    from hd2d_room_studio import _press
    from hd2d_studio_demo import StudioDriver

    out = OUT / "studio"
    out.mkdir(parents=True, exist_ok=True)
    copy = OUT / "lakeside_studio_copy"
    if copy.exists():
        shutil.rmtree(copy)
    shutil.copytree(HERE / "lakeside", copy)
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(OUT / "user_settings.json")
    cam = json.loads((HERE / "final" / "cameras.json").read_text(encoding="utf-8"))["village__day"]
    d = StudioDriver(copy)
    try:
        d.advance(5)
        if d.studio.project.current != "lakeside":
            d.studio.switch_room("lakeside")
            d.advance(3)
        view = d.studio.hd2d
        view.advance_motion = view.advance_weather = lambda dt: None
        _press(d, "Camera and sun...", lambda w: w.rect.left < 230)
        d.advance(2)
        d.window.motion_time = 0.0
        if hasattr(d.window, "water_time"):
            d.window.water_time = 0.0
        sc = view.camera
        sc.target, sc.pitch, sc.fov, sc.distance, sc.ortho = (tuple(cam["target"]), cam["pitch"], cam["fov"],
                                                              cam["distance"], cam["ortho"])
        hd = d.renderer
        gc = hd.camera  # (the sun's shadow map fits the game camera whichever camera draws: #485, as L4-2 did)
        gc.target, gc.pitch, gc.fov, gc.distance, gc.ortho = sc.target, sc.pitch, sc.fov, sc.distance, sc.ortho
        hd._camera_ready = True
        for name in ("off", "evening"):
            if name == "evening":
                view.set_haze("Haze: Evening.", preset="evening")  # (Studio's own control's action)
                d.advance(2)
            d._scroll_panels(lambda: "Falloff (m)" in d.texts() or ("Evening haze" in d.texts() and name == "off"))
            d.advance(2)
            d.picture(out / f"studio_window__{name}.png")  # the whole Studio window: panels, lines, the view
            ctx = hd.ctx
            fbo = ctx.framebuffer(color_attachments=[ctx.texture((W, H), components=4)])
            fbo.use()
            Image.fromarray(flip(hd.draw(camera=sc, read_final=True))).save(out / f"studio_path__{name}.png")
            d.window.use()
    finally:
        d.close()


if __name__ == "__main__":
    if "--studio-only" not in sys.argv:
        template()
    studio()
