"""M17-L4-1 evidence: the same frames drawn by a worktree (argv[1]: 0fa2f25's or L4-1's), into an offscreen RGBA8
target (exactly what lands in the window), on the scratch Lakeside copy: per shot the frame's sha256, draw calls,
the renderer's GL object count and live GL objects per kind; with DoF Subtle (in-process) too; and Mesh Studio's
canvas of the start room. With --identity (L4-1 only) the forced identity composite is on.
    py -3.13 exact.py WORKTREE OUT.json [--identity] [--mesa]
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sys
from pathlib import Path

WT, OUT = Path(sys.argv[1]), Path(sys.argv[2])
L4A = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\c18a071c64bbe7a7\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\l4a")
IDENTITY = "--identity" in sys.argv
if "--mesa" in sys.argv:
    sys.path.insert(0, str(L4A))
    import mesa_preload  # noqa: F401
sys.path.insert(0, str(WT))
sys.path.insert(1, str(WT / "tooling"))
os.chdir(WT)
import engine.optional_arcade  # noqa: E402,F401
import engine.hd2d.renderer as R  # noqa: E402

assert Path(R.__file__).resolve().is_relative_to(WT.resolve()), R.__file__
from engine.hd2d.dof import SUBTLE  # noqa: E402
from hd2d_demo import HiddenGame  # noqa: E402

PROJECT = L4A / "lakeside"
SC = "packs/core_regions/scenes"
SHOTS = {"village": ("lakeside", (1000, 520)), "shore": ("lakeside", (1400, 780)), "cottage": ("lakeside", (600, 540)),
         "interior": ("cottage", (294, 200))}
TIMES = {"authored": "", "night_lamps": "__l4_night_lamps", "evening": "__l4_evening"}
KINDS = ("texture", "framebuffer", "program", "buffer", "geometry")


def live(ctx):
    return {k: getattr(ctx.stats, k)[0] - getattr(ctx.stats, k)[1] for k in KINDS}


def main() -> None:
    res: dict = {"worktree": str(WT), "identity": IDENTITY}
    game = HiddenGame(PROJECT, size=(1280, 720))
    game.window.audio.set_muted(True)
    ctx = game.window.ctx
    res["gl"] = str(ctx.info.RENDERER)
    tex = ctx.texture((1280, 720), components=4)
    fbo = ctx.framebuffer(color_attachments=[tex])
    try:
        for shot, (base, feet) in SHOTS.items():
            for time, suffix in TIMES.items():
                if base == "cottage" and time != "authored":
                    continue
                game.load(f"{SC}/{base}{suffix}.json")
                game.step(5)
                p = game.player()
                p.center_x, p.bottom = feet
                game.window.motion_time = 0.0
                if hasattr(game.window, "water_time"):
                    game.window.water_time = 0.0
                game.step(120)
                hd = game.window.hd2d_renderer
                if IDENTITY:
                    hd.force_identity_composite = True
                for dof in (False, True):
                    settings = hd.settings
                    if dof:
                        hd.settings = dataclasses.replace(settings, depth_of_field=SUBTLE)
                    fbo.use()
                    fbo.clear(color=(0, 0, 0, 0))
                    hd.draw()
                    pixels = fbo.read(components=4)
                    hd.settings = settings
                    res[f"{shot}__{time}{'__dof' if dof else ''}"] = {
                        "sha256": hashlib.sha256(bytes(pixels)).hexdigest(), "draw_calls": hd.draw_calls,
                        "shadow_draws": hd.lighting.shadow_draws, "renderer_gl_objects": len(hd.gl_objects()),
                        "live": live(ctx), "dof_drawn": hd.last_dof is not None}
                game.window.use()
    finally:
        game.close()
    # Mesh Studio's editing canvas (offset viewport, its lines) of the start room
    from hd2d_studio_demo import StudioDriver  # noqa: PLC0415

    d = StudioDriver(PROJECT)
    try:
        view = d.studio.hd2d
        view.advance_motion = view.advance_weather = lambda dt: None
        d.advance(5)
        d.window.motion_time = 0.0
        if IDENTITY:
            d.renderer.force_identity_composite = True
        x, y, w, h = (int(v) for v in view.viewport())
        for lines in (False, True):
            kept = view._overlay
            if not lines:
                view._overlay = lambda vp: None
            d.window.clear()
            view.draw()
            view._overlay = kept
            img = d.arcade.get_image(x, y, w, h).convert("RGB")
            res[f"studio_canvas{'_lines' if lines else ''}"] = {
                "sha256": hashlib.sha256(img.tobytes()).hexdigest(), "viewport": [x, y, w, h],
                "draw_calls": d.renderer.draw_calls, "renderer_gl_objects": len(d.renderer.gl_objects())}
            img.save(OUT.with_name(OUT.stem + f"_studio{'_lines' if lines else ''}.png"))
    finally:
        d.close()
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("done", len(res))


main()
