"""M17-L4-4 captures (from L4-3's): the scratch Lakeside L1b copy as the game draws it (HiddenGame, hidden), 1280x720, the picture the
renderer makes (draw(read_final=True)) into an offscreen target; motion/water time reset, 120 settle frames.

Usage: py -3.13 capture.py WORKTREE OUT [--variants off,daytime,...] [--shots a,b] [--times day,evening] [--mesa]
A variant is "off" (the room as it is) or a callable name in VARIANTS (applied with dataclasses.replace to the settings).
Writes OUT/<shot>__<time>__<variant>.png and OUT/cameras.json.
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path
from typing import Any

WT, OUT = Path(sys.argv[1]), Path(sys.argv[2])
HERE = Path(__file__).resolve().parent
LAKE = HERE.parent / "l4h" / "lakeside"
OUT.mkdir(parents=True, exist_ok=True)
if "--mesa" in sys.argv:
    sys.path.insert(0, str(HERE))
    import mesa_preload  # noqa: F401
sys.path.insert(0, str(WT))
sys.path.insert(1, str(WT / "tooling"))
os.chdir(WT)
import engine.optional_arcade  # noqa: E402,F401
import engine.hd2d.renderer as R  # noqa: E402

assert Path(R.__file__).resolve().is_relative_to(WT.resolve()), R.__file__
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

W, H = 1280, 720
SC = "packs/core_regions/scenes"
SHOTS = {"village": ("lakeside", (1000, 520)), "shore": ("lakeside", (1400, 780)), "bridge": ("lakeside", (1100, 790)),
         "cottage": ("lakeside", (600, 540)), "interior": ("cottage", (294, 200))}
TIMES = {"day": "", "evening": "__l4_evening", "night_lamps": "__l4_night_lamps", "evening_lamps": "__l4b_evening_lamps", "night_hearth": "__l4b_night_hearth"}


def opt(name: str, default: str) -> str:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


class Variants(dict):
    """'off', a bloom preset or 'preset~k=v~k=v' (strength, threshold, spread), optionally '+haze=PRESET',
    '+post=PRESET' and '+dof' (Subtle depth of field)."""

    def __missing__(self, name: str) -> Any:
        from engine.hd2d.bloom import parse_bloom  # noqa: PLC0415
        from engine.hd2d.dof import SUBTLE  # noqa: PLC0415
        from engine.hd2d.haze import Haze  # noqa: PLC0415
        from engine.hd2d.post import Post  # noqa: PLC0415

        parts = name.split("+")
        head, extras = parts[0], parts[1:]
        bloom = None
        if head != "off":
            preset, *pairs = head.split("~")
            raw: dict[str, Any] = {"preset": preset}
            for pair in pairs:
                k, v = pair.split("=")
                raw[k] = float(v)
            bloom = parse_bloom(raw)
        change: dict[str, Any] = {"bloom": bloom}
        for e in extras:
            if e.startswith("post="):
                change["post"] = Post(e[5:])
            elif e.startswith("haze="):
                change["haze"] = Haze(e[5:])
            elif e == "dof":
                change["depth_of_field"] = SUBTLE
        return lambda s: dataclasses.replace(s, **change)


def variants() -> dict[str, Any]:
    return Variants(off=None)


def flip(raw: Any) -> Any:
    return np.flipud(np.frombuffer(raw, dtype=np.uint8).reshape(H, W, 3)).copy()


def main() -> None:
    from hd2d_demo import HiddenGame

    shots = opt("--shots", ",".join(SHOTS)).split(",")
    times = opt("--times", "day,evening").split(",")
    table = variants()
    names = opt("--variants", "off").split(",")
    cams: dict[str, Any] = {}
    game = HiddenGame(LAKE, size=(W, H))
    game.window.audio.set_muted(True)
    ctx = game.window.ctx
    tex = ctx.texture((W, H), components=4)
    fbo = ctx.framebuffer(color_attachments=[tex])
    try:
        for shot in shots:
            base, feet = SHOTS[shot]
            for time in times:
                if base != "cottage" and time == "night_hearth":
                    continue
                if base == "cottage" and time not in ("day", "night_lamps", "night_hearth"):
                    continue
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
                cams[f"{shot}__{time}"] = {"target": list(c.target), "pitch": c.pitch, "fov": c.fov,
                                           "distance": c.distance, "ortho": c.ortho}
                settings = hd.settings
                for name in names:
                    make = table[name]
                    hd.settings = settings if make is None else make(settings)
                    fbo.use()
                    Image.fromarray(flip(hd.draw(read_final=True))).save(OUT / f"{shot}__{time}__{name}.png")
                hd.settings = settings
                game.window.use()
    finally:
        game.close()
    (OUT / "cameras.json").write_text(json.dumps(cams, indent=1), encoding="utf-8")
    print("frames", len(list(OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
