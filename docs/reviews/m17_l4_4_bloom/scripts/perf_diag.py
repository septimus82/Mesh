"""Where bloom's whole-frame cost goes (RTX, GL timer query; Lakeside at night, its lamps lit). Interleaved, rotated,
an untimed frame before each timed one, the first 10% dropped.
  off       bloom off
  world     bloom on, its chain skipped (the world drawn with its emission attachment, the composite reading a glow)
  bloom     bloom on
With --off-only (any tree, base included): only "off", for an A/B of the bloom-off frame between trees.
    py -3.13 perf_diag.py WORKTREE OUT.json W H [--off-only] [--rounds N]"""
from __future__ import annotations

import dataclasses
import json
import os
import statistics
import sys
import time
from pathlib import Path

WT, OUT, W, H = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
OFF_ONLY = "--off-only" in sys.argv
ROUNDS = int(sys.argv[sys.argv.index("--rounds") + 1]) if "--rounds" in sys.argv else 400
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(WT))
sys.path.insert(1, str(WT / "tooling"))
os.chdir(WT)
import engine.optional_arcade  # noqa: E402,F401
import engine.hd2d.renderer as R  # noqa: E402

assert Path(R.__file__).resolve().is_relative_to(WT.resolve()), R.__file__
from hd2d_demo import HiddenGame  # noqa: E402


def stats(t):
    t = sorted(t[len(t) // 10:])
    return {"p50_ms": round(statistics.median(t), 4), "p95_ms": round(t[int(0.95 * len(t))], 4), "n": len(t)}


def main() -> None:
    game = HiddenGame(HERE.parent / "l4h" / "lakeside", size=(W, H))
    game.window.audio.set_muted(True)
    ctx = game.window.ctx
    tex = ctx.texture((W, H), components=4)
    fbo = ctx.framebuffer(color_attachments=[tex])
    q = ctx.query(samples=False, time=True, primitives=False)
    res = {"worktree": str(WT), "size": [W, H], "rounds": ROUNDS}
    try:
        game.load("packs/core_regions/scenes/lakeside__l4_night_lamps.json")
        game.step(5)
        p = game.player()
        p.center_x, p.bottom = 1000, 520
        game.window.motion_time = 0.0
        game.step(120)
        hd = game.window.hd2d_renderer
        base = hd.settings
        modes = {"off": base}
        if not OFF_ONLY:
            from engine.hd2d.bloom import Bloom, BloomPass

            modes["world"] = modes["bloom"] = dataclasses.replace(base, bloom=Bloom("warm"))
            real = BloomPass.render
        gpu = {n: [] for n in modes}
        cpu = {n: [] for n in modes}

        def run(n):
            if not OFF_ONLY:
                BloomPass.render = (lambda self, *a, **k: self._chain[2][0][1] if self._chain else real(self, *a, **k)) if n == "world" else real
            hd.settings = modes[n]
            fbo.use()
            hd.draw()

        for n in modes:
            run("bloom" if n == "world" else n)  # (the chain made once before "world" skips it)
            run(n)
        names = list(modes)
        for r in range(ROUNDS):
            for n in names[r % len(names):] + names[:r % len(names)]:
                run(n)
                with q:
                    t0 = time.perf_counter()
                    run(n)
                    c = time.perf_counter() - t0
                gpu[n].append(q.time_elapsed / 1e6)
                cpu[n].append(c * 1000)
        if not OFF_ONLY:
            BloomPass.render = real
        res["whole_frame"] = {n: {"gpu": stats(gpu[n]), "cpu": stats(cpu[n])} for n in modes}
    finally:
        game.close()
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res["whole_frame"]))


if __name__ == "__main__":
    main()
