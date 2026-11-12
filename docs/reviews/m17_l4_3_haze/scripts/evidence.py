"""M17-L4-3 visual evidence (real engine frames, hidden windows, 1280x720) on the scratch Lakeside L1b copy.

  depth_map/   per shot: the haze amount each pixel gets from its own depth (false colour), beside the frame
  walking/     the player walking with Daytime haze: frames along the way, and the same frames without
  combined/    haze + grade (Golden hour) + vignette + depth of field (Subtle), each step alone and together
  template/    the HD-2D template village (a smaller room): off / Daytime / Evening, day and night
Usage: py -3.13 evidence.py WORKTREE OUT [--mesa]
"""
from __future__ import annotations

import ctypes
import dataclasses
import json
import os
import sys
from pathlib import Path
from typing import Any

WT, OUT = Path(sys.argv[1]), Path(sys.argv[2])
HERE = Path(__file__).resolve().parent
if "--mesa" in sys.argv:
    sys.path.insert(0, str(HERE))
    import mesa_preload  # noqa: F401
sys.path.insert(0, str(WT))
sys.path.insert(1, str(WT / "tooling"))
os.chdir(WT)
import engine.optional_arcade  # noqa: E402,F401
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from engine.hd2d.dof import SUBTLE  # noqa: E402
from engine.hd2d.haze import Haze  # noqa: E402
from engine.hd2d.post import Post  # noqa: E402
from hd2d_demo import HiddenGame  # noqa: E402

W, H = 1280, 720
SC = "packs/core_regions/scenes"
SHOTS = {"village": (1000, 520), "shore": (1400, 780), "bridge": (1100, 790), "cottage": (600, 540)}


def flip(raw: Any) -> Any:
    return np.flipud(np.frombuffer(raw, dtype=np.uint8).reshape(H, W, 3)).copy()


def depth(hd: Any) -> Any:
    from pyglet import gl

    tex = hd._fbo_parts[1]
    buf = (ctypes.c_float * (W * H))()
    gl.glActiveTexture(gl.GL_TEXTURE0)
    gl.glBindTexture(gl.GL_TEXTURE_2D, tex.glo.value if hasattr(tex.glo, "value") else tex.glo)
    gl.glGetTexImage(gl.GL_TEXTURE_2D, 0, gl.GL_DEPTH_COMPONENT, gl.GL_FLOAT, buf)
    gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
    return np.flipud(np.frombuffer(buf, dtype=np.float32).reshape(H, W).astype(np.float64))


def amount_map(hd: Any) -> Any:
    from engine.hd2d.dof import FAR, NEAR

    d = depth(hd)
    z = NEAR * FAR / (FAR - d * (FAR - NEAR))
    h = hd.last_haze
    x = np.maximum(0.0, z - h["onset"]) / h["falloff"]
    a = h["strength"] * (1.0 - np.exp(-3.0 * x * x))
    t = np.clip(a / max(1e-6, h["strength"]), 0, 1)  # 0 (none) .. 1 (full strength)
    rgb = np.stack([t, 0.25 + 0.0 * t, 1.0 - t], axis=-1)  # blue: none -> red: full
    rgb[a <= 0] = (0.08, 0.08, 0.12)
    return (rgb * 255).astype(np.uint8)


def settle(game: Any, scene: str, feet: tuple[int, int] | None) -> Any:
    game.load(scene)
    game.step(5)
    if feet:
        p = game.player()
        p.center_x, p.bottom = feet
    game.window.motion_time = 0.0
    if hasattr(game.window, "water_time"):
        game.window.water_time = 0.0
    game.step(120)
    return game.window.hd2d_renderer


def main() -> None:
    for d in ("depth_map", "walking", "combined", "template"):
        (OUT / d).mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    game = HiddenGame(HERE / "lakeside", size=(W, H))
    game.window.audio.set_muted(True)
    ctx = game.window.ctx
    fbo = ctx.framebuffer(color_attachments=[ctx.texture((W, H), components=4)])

    def frame(hd: Any) -> Any:
        fbo.use()
        img = flip(hd.draw(read_final=True))
        game.window.use()
        return img

    try:
        for shot, feet in SHOTS.items():  # depth maps
            hd = settle(game, f"{SC}/lakeside.json", feet)
            base = hd.settings
            hd.settings = dataclasses.replace(base, haze=Haze("daytime"))
            img = frame(hd)
            fbo.use()
            hd.draw(read_final=True)
            amap = amount_map(hd)
            game.window.use()
            Image.fromarray(np.concatenate([img, amap], axis=1)).save(OUT / "depth_map" / f"{shot}.png")
            hd.settings = base
        hd = settle(game, f"{SC}/lakeside.json", (900, 560))  # walking
        base = hd.settings
        key = game.arcade.key
        steps = []
        for i, k in enumerate((key.RIGHT, key.RIGHT, key.UP, key.UP, key.RIGHT, key.RIGHT)):
            game.hold(k, 20)
            hd.settings = base
            off = frame(hd)
            hd.settings = dataclasses.replace(base, haze=Haze("daytime"))
            on = frame(hd)
            Image.fromarray(np.concatenate([off, on], axis=1)).save(OUT / "walking" / f"step{i}.png")
            steps.append({"step": i, "target": [round(v, 2) for v in hd.camera.target],
                          "onset_minus_focus": round(hd.last_haze["onset"] - hd.last_haze["focus"], 4)})
        hd.settings = base
        report["walking"] = steps
        for time, scene, haze in (("day", "lakeside.json", "daytime"), ("evening", "lakeside__l4_evening.json",
                                                                         "evening")):  # combined
            hd = settle(game, f"{SC}/{scene}", SHOTS["bridge"])
            hd.dof_allow_software = True
            base = hd.settings
            grade = "golden_hour" if time == "evening" else "natural"
            for name, change in (("off", {}), ("haze", {"haze": Haze(haze)}), ("grade_vignette", {"post": Post(grade)}),
                                 ("dof", {"depth_of_field": SUBTLE}),
                                 ("all", {"haze": Haze(haze), "post": Post(grade), "depth_of_field": SUBTLE})):
                hd.settings = dataclasses.replace(base, **change)
                Image.fromarray(frame(hd)).save(OUT / "combined" / f"bridge__{time}__{name}.png")
                report.setdefault("combined_stage", {})[f"{time}__{name}"] = hd.last_stage
            hd.settings = base
            hd.dof_allow_software = False
    finally:
        game.close()
    (OUT / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
