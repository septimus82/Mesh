"""M17-L4-4 evidence frames beyond capture.py (hidden windows, 1280x720, the renderer's final picture):
  emission   Lakeside night (village, bridge) and the hearth interior: the frame beside the world's emission buffer
  moving     Lakeside night, the player walking right (the camera following): off and Warm at every 8th frame, and per
             frame the glow's light over the light that passed (no flicker)
  template   a fresh HD-2D template village (two lamp posts) by day and at night: off, Subtle, Warm, full
  campfire   M23B's clearing at night: the campfire's flames and embers, a torch: off, Subtle, Warm, full
Usage: py -3.13 evidence.py WORKTREE OUT [parts...]"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path

WT, OUT = Path(sys.argv[1]), Path(sys.argv[2])
PARTS = sys.argv[3:] or ["emission", "moving", "template", "campfire"]
HERE = Path(__file__).resolve().parent
LAKE = HERE.parent / "l4h" / "lakeside"
sys.path.insert(0, str(WT))
sys.path.insert(1, str(WT / "tooling"))
os.chdir(WT)
import engine.optional_arcade  # noqa: E402,F401
import engine.hd2d.renderer as R  # noqa: E402

assert Path(R.__file__).resolve().is_relative_to(WT.resolve()), R.__file__
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import hd2d_bloom_study as S  # noqa: E402
from engine.hd2d.bloom import Bloom  # noqa: E402

W, H = 1280, 720
SC = "packs/core_regions/scenes"
LOOKS = {"off": None, "subtle": Bloom("subtle"), "warm": Bloom("warm"),
         "full": Bloom("warm", strength=3.0, threshold=0.0, spread=0.8)}


def final(game, hd, camera=None) -> Image.Image:
    game.window.use()
    raw = hd.draw(read_final=True, camera=camera)
    return Image.fromarray(np.flipud(np.frombuffer(raw, dtype=np.uint8).reshape(H, W, 3)).copy())


def emission_image(hd) -> Image.Image:
    e = S.floats(hd._bloom.emission)
    m = np.clip(e / max(1e-6, float(e.max())), 0.0, 1.0) ** (1 / 2.2)
    return Image.fromarray(np.flipud((m * 255).astype(np.uint8)).copy())


def settle_at(game, scene: str, feet) -> object:
    game.load(scene)
    game.step(5)
    p = game.player()
    p.center_x, p.bottom = feet
    game.window.motion_time = 0.0
    if hasattr(game.window, "water_time"):
        game.window.water_time = 0.0
    game.step(120)
    return game.window.hd2d_renderer


def emission(out: Path) -> dict:
    from hd2d_demo import HiddenGame

    out.mkdir(parents=True, exist_ok=True)
    game = HiddenGame(LAKE, size=(W, H))
    game.window.audio.set_muted(True)
    found = {}
    try:
        for name, scene, feet in (("village_night", "lakeside__l4_night_lamps", (1000, 520)),
                                  ("bridge_night", "lakeside__l4_night_lamps", (1100, 790)),
                                  ("hearth_interior", "cottage__l4b_night_hearth", (294, 200))):
            hd = settle_at(game, f"{SC}/{scene}.json", feet)
            base = hd.settings
            hd.settings = dataclasses.replace(base, bloom=LOOKS["warm"])
            frame = final(game, hd)
            em = emission_image(hd)
            sheet = Image.new("RGB", (W * 2, H))
            sheet.paste(frame, (0, 0))
            sheet.paste(em, (W, 0))
            sheet.save(out / f"{name}.png")
            e = S.floats(hd._bloom.emission)
            found[name] = {"emitting_px": int((S.luma(e) > 0).sum()), "max_luminance": float(S.luma(e).max())}
            hd.settings = base
    finally:
        game.close()
    return found


def moving(out: Path) -> dict:
    from hd2d_demo import HiddenGame

    out.mkdir(parents=True, exist_ok=True)
    game = HiddenGame(LAKE, size=(W, H))
    game.window.audio.set_muted(True)
    ratios = []
    try:
        hd = settle_at(game, f"{SC}/lakeside__l4_night_lamps.json", (930, 520))
        base = hd.settings
        key = game.arcade.key
        game.window.dispatch_event("on_key_press", key.RIGHT, 0)
        for i in range(48):
            game.step(1)
            hd.settings = dataclasses.replace(base, bloom=LOOKS["warm"])
            on = final(game, hd)
            _e, level, glow = S.levels(hd)
            ratios.append(round(float(S.luma(glow).sum() / max(S.luma(level).sum(), 1e-9)), 5))
            if i % 8 == 0:
                hd.settings = base
                off = final(game, hd)
                sheet = Image.new("RGB", (W * 2, H))
                sheet.paste(off, (0, 0))
                sheet.paste(on, (W, 0))
                sheet.save(out / f"walk_{i:02d}.png")
        game.window.dispatch_event("on_key_release", key.RIGHT, 0)
    finally:
        game.close()
    return {"glow_over_passed": ratios, "min": min(ratios), "max": max(ratios)}


def template(out: Path) -> dict:
    import hd2d_lamp_glow_demo as glow
    from hd2d_demo import HiddenGame

    out.mkdir(parents=True, exist_ok=True)
    project = out / "game"
    rooms = glow.build(project)
    night = glow.village_variant(project, "evidence_night", lambda lights: lights)
    game = HiddenGame(project, size=(W, H))
    game.window.audio.set_muted(True)
    try:
        for time, scene in (("day", rooms["village"]), ("night", night)):
            hd = S.settle(game, scene)
            base = hd.settings
            for look, bloom in LOOKS.items():
                hd.settings = dataclasses.replace(base, bloom=bloom)
                final(game, hd).save(out / f"template__{time}__{look}.png")
            hd.settings = base
    finally:
        game.close()
    return {}


def campfire(out: Path) -> dict:
    import m23b_fire_study as fire
    from hd2d_demo import HiddenGame

    out.mkdir(parents=True, exist_ok=True)
    project = fire.make_project(out, "clearing", night=True)
    game = HiddenGame(project, size=(W, H))
    game.window.audio.set_muted(True)
    try:
        game.load(fire.ROOM)
        game.step(30)
        hd = game.window.hd2d_renderer
        x, y = fire.FIRE
        hd.camera.target = (x, y - 0.8, 0.8)
        hd._camera_ready = True
        game.window.motion_time = 10.0
        base = hd.settings
        for look, bloom in LOOKS.items():
            hd.settings = dataclasses.replace(base, bloom=bloom)
            final(game, hd, camera=hd.camera).save(out / f"campfire__night__{look}.png")
        hd.settings = base
    finally:
        game.close()
    return {}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    for part in PARTS:
        report[part] = globals()[part](OUT / part)
    (OUT / f"evidence_{'_'.join(PARTS)}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1)[:3000])


if __name__ == "__main__":
    main()
