"""#500 Linux HUD failure, investigated locally: the study's hud() captures, with repeats and the world alone, every
pixel of its mask classified. Usage: py -3.13 hud_probe.py WORKTREE OUT [--mesa]"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path

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

import hd2d_lamp_glow_demo as glow  # noqa: E402
from engine.hd2d.haze import Haze  # noqa: E402
from hd2d_demo import HiddenGame  # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)
rooms = glow.build(OUT / "game")
game = HiddenGame(OUT / "game", size=(960, 540))
game.window.audio.set_muted(True)
try:
    report: dict = {"gl": str(game.window.ctx.info.RENDERER)}
    game.load(rooms["village"])
    game.step(30)
    game.window.motion_time = 0.0
    hd = game.window.hd2d_renderer
    base = hd.settings

    def window():
        return np.asarray(game.draw().convert("RGB")).astype(int)

    plain = window()
    plain2 = window()
    hd.settings = dataclasses.replace(base, haze=Haze("evening", strength=0.5, start=0.0, falloff=1.0))
    hazed = window()
    kept = hd.draw
    hd.draw = lambda *a, **k: None
    hd.settings = base
    alone = window()
    alone2 = window()
    hd.draw = kept
    # the world alone, as the window shows it under the HUD (the picture the renderer makes)
    world = np.flipud(np.frombuffer(hd.draw(read_final=True), dtype=np.uint8).reshape(540, 960, 3)).astype(int)
    hd.settings = dataclasses.replace(base, haze=Haze("evening", strength=0.5, start=0.0, falloff=1.0))
    world_h = np.flipud(np.frombuffer(hd.draw(read_final=True), dtype=np.uint8).reshape(540, 960, 3)).astype(int)
    hd.settings = base
    game.window.use()
    covered = (np.abs(plain - alone).max(axis=2) == 0) & (alone.max(axis=2) > 0)
    differ = covered & (np.abs(hazed - plain).max(axis=2) > 0)
    opaque = covered & (np.abs(world - alone).max(axis=2) > 0)  # the world there differs: the HUD hides it fully
    coincide = covered & ~opaque  # the world there equals what the HUD-alone frame shows
    ys, xs = np.nonzero(differ)
    report.update({
        "plain_repeat_same": bool(np.array_equal(plain, plain2)), "alone_repeat_same": bool(np.array_equal(alone, alone2)),
        "covered": int(covered.sum()), "differ": int(differ.sum()), "opaque": int(opaque.sum()),
        "coincide": int(coincide.sum()), "differ_in_opaque": int((differ & opaque).sum()),
        "differ_in_coincide": int((differ & coincide).sum()),
        "world_changed_under_coincide": int((coincide & (np.abs(world_h - world).max(axis=2) > 0)).sum()),
        "differ_px": [[int(x), int(y), plain[y, x].tolist(), hazed[y, x].tolist(), alone[y, x].tolist(),
                       world[y, x].tolist(), world_h[y, x].tolist()] for y, x in list(zip(ys, xs))[:40]],
        "alone_bbox": None})
    yy, xx = np.nonzero(alone.max(axis=2) > 0)
    if yy.size:
        report["alone_bbox"] = [int(xx.min()), int(yy.min()), int(xx.max()), int(yy.max())]
    for name, img in (("plain", plain), ("hazed", hazed), ("alone", alone), ("world", world), ("world_hazed", world_h)):
        Image.fromarray(img.astype(np.uint8)).save(OUT / f"{name}.png")
    vis = np.zeros_like(plain)
    vis[opaque] = (0, 160, 0)
    vis[coincide] = (0, 0, 220)
    vis[differ] = (255, 0, 0)
    Image.fromarray(vis.astype(np.uint8)).save(OUT / "mask.png")
    (OUT / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "differ_px"}, indent=1))
    print("first differing", report["differ_px"][:8])
finally:
    game.close()
