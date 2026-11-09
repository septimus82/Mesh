"""M17-L4-2 evidence: a play session with movement, the original and a preset, the same walk (held arrow keys) from
the same start in the scratch Lakeside copy: the whole window (world + HUD) every 30 frames -> play/<run>__<n>.png,
and per frame: the composite's stage, how much of the window the grade changed, and the player's contrast against a
ring round it (its sprite drawn flat against the world's depth) in both runs.
Usage: py -3.13 play.py WORKTREE OUT
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path

WT, OUT = Path(sys.argv[1]), Path(sys.argv[2])
L4A = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\c18a071c64bbe7a7\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\l4a")
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(WT))
sys.path.insert(1, str(WT / "tooling"))
os.chdir(WT)
import engine.optional_arcade  # noqa: E402,F401
import numpy as np  # noqa: E402
from engine.hd2d.post import Post  # noqa: E402
from hd2d_demo import HiddenGame  # noqa: E402
from hd2d_post_study import readability  # noqa: E402

W, H = 1280, 720
RUNS = {"day": ("packs/core_regions/scenes/lakeside.json", "natural"),
        "night": ("packs/core_regions/scenes/lakeside__l4_night_lamps.json", "moonlight")}
WALK = (("RIGHT", 45), ("UP", 45), ("LEFT", 45), ("DOWN", 45))


def run(game, scene: str, preset: str | None, tag: str) -> list[dict]:
    game.load(scene)
    game.step(5)
    p = game.player()
    p.center_x, p.bottom = 900, 480
    game.window.motion_time = 0.0
    if hasattr(game.window, "water_time"):
        game.window.water_time = 0.0
    game.step(30)
    hd = game.window.hd2d_renderer
    if preset:
        hd.settings = dataclasses.replace(hd.settings, post=Post(preset))
    frames, n = [], 0
    key = game.arcade.key
    for name, count in WALK:
        for _ in range(count // 15):
            game.hold(getattr(key, name), 15)
            n += 15
            if n % 30 == 0:
                img = np.asarray(game.draw().convert("RGB"))
                from PIL import Image  # noqa: PLC0415

                Image.fromarray(img).save(OUT / f"{tag}__{n:03d}.png")
                sp = game.player()
                game.window.use()
                mask = np.flipud(np.frombuffer(hd.draw(solid=sp, read=True), dtype=np.uint8).reshape(H, W, 3)[..., 0] > 128)
                world = np.flipud(np.frombuffer(hd.draw(read_final=True), dtype=np.uint8).reshape(H, W, 3))
                weber, edge = readability(world, mask) if mask.sum() > 40 else (None, None)
                frames.append({"frame": n, "stage": hd.last_stage, "player": [round(sp.center_x), round(sp.bottom)],
                               "weber": weber, "edge": edge})
    return frames


def main() -> None:
    game = HiddenGame(L4A / "lakeside", size=(W, H))
    game.window.audio.set_muted(True)
    report: dict = {}
    try:
        for name, (scene, preset) in RUNS.items():
            report[f"{name}__off"] = run(game, scene, None, f"{name}__off")
            report[f"{name}__{preset}"] = run(game, scene, preset, f"{name}__{preset}")
    finally:
        game.close()
    (OUT / "play.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    for name, (_scene, preset) in RUNS.items():
        a, b = report[f"{name}__off"], report[f"{name}__{preset}"]
        same_path = all(x["player"] == y["player"] for x, y in zip(a, b))
        print(name, preset, "same path:", same_path, "stages:", {y["stage"] for y in b},
              "weber off/on:", [(round(x["weber"], 3), round(y["weber"], 3)) for x, y in zip(a, b) if x["weber"] is not None])


main()
