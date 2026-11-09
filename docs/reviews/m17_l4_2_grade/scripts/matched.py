"""M17-L4-2 evidence: matched game and Mesh Studio frames of the scratch Lakeside L1b copy, per shot x time x preset.

Phase 1 (the game, HiddenGame 1280x720): each shot settled (feet placed, motion/water time 0, 120 frames); its camera
recorded; the frame the game draws (draw(read_final=True)) per preset -> game/<shot>__<time>__<preset>.png
Phase 2 (Mesh Studio, StudioDriver): the room opened (switch_room), the time of day applied as an unsaved scratch edit
(set_hd2d_sun; lamps on for night_lamps), each preset chosen with Studio's own control (Hd2dView.set_post), and:
  studio_canvas/<...>.png  the real editing view (Studio's canvas region of its window, its lines drawn), the view
                           aimed at the shot (Studio's camera = the game's)
  studio_1280/<...>.png    Studio's path (camera passed, as its view draws) at 1280x720, the game's camera set to the
                           same view first so the sun's shadow map is fitted alike (#485)
  game_path_in_studio      the game's path (no camera: cutaway on) in Studio's process, to tell what differs
Writes report.json: per frame, Studio-path vs game frame (changed share) and game-path-in-Studio vs game (bytes equal).
Usage: py -3.13 matched.py WORKTREE OUT
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path
from typing import Any

WT, OUT = Path(sys.argv[1]), Path(sys.argv[2])
L4A = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\c18a071c64bbe7a7\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\l4a")
for d in ("game", "studio_canvas", "studio_1280"):
    (OUT / d).mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(WT))
sys.path.insert(1, str(WT / "tooling"))
os.chdir(WT)
os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
import engine.optional_arcade  # noqa: E402,F401
import engine.hd2d.renderer as R  # noqa: E402

assert Path(R.__file__).resolve().is_relative_to(WT.resolve()), R.__file__
import numpy as np  # noqa: E402
from engine import project_ops as ops  # noqa: E402
from engine.hd2d.post import Post  # noqa: E402
from PIL import Image  # noqa: E402

W, H = 1280, 720
SC = "packs/core_regions/scenes"
SHOTS = {"village": ("lakeside", (1000, 520)), "shore": ("lakeside", (1400, 780)), "bridge": ("lakeside", (1100, 790)),
         "cottage": ("lakeside", (600, 540)), "interior": ("cottage", (294, 200))}
TIMES = {"day": "", "evening": "__l4_evening", "night_lamps": "__l4_night_lamps"}
PRESETS = ("off", "natural", "golden_hour", "moonlight", "interior_warm")


def jobs() -> list[tuple[str, str]]:
    return [(s, t) for s in SHOTS for t in TIMES if not (SHOTS[s][0] == "cottage" and t != "day")]


def flip(raw: Any, w: int, h: int) -> Any:
    return np.flipud(np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)).copy()


def phase_game(report: dict[str, Any]) -> None:
    from hd2d_demo import HiddenGame

    game = HiddenGame(L4A / "lakeside", size=(W, H))
    game.window.audio.set_muted(True)
    ctx = game.window.ctx
    tex = ctx.texture((W, H), components=4)
    fbo = ctx.framebuffer(color_attachments=[tex])
    try:
        for shot, time in jobs():
            base, feet = SHOTS[shot]
            game.load(f"{SC}/{base}{TIMES[time]}.json")
            game.step(5)
            p = game.player()
            p.center_x, p.bottom = feet
            game.window.motion_time = 0.0
            if hasattr(game.window, "water_time"):
                game.window.water_time = 0.0
            game.step(120)
            hd = game.window.hd2d_renderer
            c = hd.camera
            report["cameras"][f"{shot}__{time}"] = {"target": list(c.target), "pitch": c.pitch, "fov": c.fov,
                                                    "distance": c.distance, "ortho": c.ortho, "yaw": c.yaw}
            settings = hd.settings
            for preset in PRESETS:
                hd.settings = settings if preset == "off" else dataclasses.replace(settings, post=Post(preset))
                fbo.use()
                Image.fromarray(flip(hd.draw(read_final=True), W, H)).save(OUT / "game" / f"{shot}__{time}__{preset}.png")
            hd.settings = settings
            game.window.use()
    finally:
        game.close()


def phase_studio(report: dict[str, Any]) -> None:
    from hd2d_studio_demo import StudioDriver

    d = StudioDriver(L4A / "lakeside")
    try:
        d.advance(5)
        view = d.studio.hd2d
        view.advance_motion = view.advance_weather = lambda dt: None
        for shot, time in jobs():
            room = SHOTS[shot][0]
            if d.studio.project.current != room:
                d.studio.switch_room(room)
                d.advance(3)
            src = json.loads((L4A / "lakeside" / SC / f"{room}{TIMES[time]}.json").read_text(encoding="utf-8"))
            # the time of day as the variant has it (an unsaved scratch edit: sun, sky, ambient, lamps)
            d.studio.project.edit_scene(lambda s, src=src: {**s, "settings": {**s["settings"], "hd2d": {
                **s["settings"]["hd2d"], **{k: src["settings"]["hd2d"][k] for k in ("sun", "ambient", "sky")
                                            if k in src["settings"]["hd2d"]}}}, "lights": src.get("lights", [])})
            d.studio._after_change("")
            d.advance(3)
            d.window.motion_time = 0.0
            if hasattr(d.window, "water_time"):
                d.window.water_time = 0.0
            hd = d.renderer
            cam = report["cameras"][f"{shot}__{time}"]
            sc = view.camera
            sc.target, sc.pitch, sc.fov, sc.distance, sc.ortho, sc.yaw = (tuple(cam["target"]), cam["pitch"], cam["fov"],
                                                                          cam["distance"], cam["ortho"], cam["yaw"])
            gc = hd.camera
            gc.target, gc.pitch, gc.fov, gc.distance, gc.ortho, gc.yaw = (tuple(cam["target"]), cam["pitch"], cam["fov"],
                                                                          cam["distance"], cam["ortho"], cam["yaw"])
            hd._camera_ready = True
            for preset in PRESETS:
                view.set_post(f"Picture: {preset}.", preset=preset)  # (Studio's own control: one undo step)
                d.window.motion_time = 0.0
                key = f"{shot}__{time}__{preset}"
                d.window.clear()
                view.draw()
                x, y, w, h = (int(v) for v in view.viewport())
                Image.fromarray(np.asarray(d.arcade.get_image(x, y, w, h).convert("RGB"))).save(
                    OUT / "studio_canvas" / f"{key}.png")
                ctx = hd.ctx
                tex = ctx.texture((W, H), components=4)
                fbo = ctx.framebuffer(color_attachments=[tex])
                try:
                    fbo.use()
                    studio_path = flip(hd.draw(camera=sc, read_final=True), W, H)
                    game_path = flip(hd.draw(read_final=True), W, H)
                    stage = hd.last_stage
                finally:
                    d.window.use()
                    fbo.delete()
                    tex.delete()
                Image.fromarray(studio_path).save(OUT / "studio_1280" / f"{key}.png")
                game = np.asarray(Image.open(OUT / "game" / f"{key}.png").convert("RGB"))
                diff = np.abs(studio_path.astype(int) - game.astype(int)).max(axis=2) > 0
                ys, xs = np.nonzero(diff)
                report["frames"][key] = {
                    "stage": stage, "canvas": [x, y, w, h],
                    "studio_path_vs_game_changed_share": round(float(diff.mean()), 5),
                    "studio_path_diff_box": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if diff.any() else None,
                    "game_path_in_studio_equals_game": bool(np.array_equal(game_path, game))}
            view.set_post("Picture: off.", preset="off")
            print(shot, time, flush=True)
    finally:
        d.close()


def main() -> None:
    report: dict[str, Any] = {"cameras": {}, "frames": {}}
    phase_game(report)
    phase_studio(report)
    (OUT / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


main()
