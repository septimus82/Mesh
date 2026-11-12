"""M17-L4-4 timing (from L4-3's) on the scratch Lakeside village (L1b), as the L4-2 method: the same settled frame, every mode
interleaved in one process (the same GPU clock state for all), the order rotated each round, the first 10% dropped.
  whole frame  Hd2dRenderer.draw() into an offscreen target: GPU time (timer query) and CPU time (perf_counter round
               the call), per mode: off, bloom (Warm), bloom+haze+graded, dof (Subtle), all four; Lakeside at night
               with its lamps lit (the evening-lamps and night variants of the scratch copy)
  passes       bloom's own pass alone (prefilter, chain) and the final stage: blit vs composite with the glow
  moving       the player walking (the camera following): bloom on and off alternating every frame, each frame drawn
  objects      draw calls, bloom's passes, GL objects and target memory, off vs on vs off again
On Mesa llvmpipe (--mesa) wall time round ctx.finish() replaces the timer query (not trustworthy there, #460).
    py -3.13 perf_l43.py WORKTREE OUT.json W H [--mesa] [--rounds N]
"""
from __future__ import annotations

import dataclasses
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

WT, OUT, W, H = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
MESA = "--mesa" in sys.argv
ROUNDS = int(sys.argv[sys.argv.index("--rounds") + 1]) if "--rounds" in sys.argv else (30 if MESA else 300)
HERE = Path(__file__).resolve().parent
if MESA:
    sys.path.insert(0, str(HERE))
    import mesa_preload  # noqa: F401
sys.path.insert(0, str(WT))
sys.path.insert(1, str(WT / "tooling"))
os.chdir(WT)
import engine.optional_arcade  # noqa: E402,F401
import engine.hd2d.renderer as R  # noqa: E402

assert Path(R.__file__).resolve().is_relative_to(WT.resolve()), R.__file__
from engine.hd2d.bloom import Bloom  # noqa: E402
from engine.hd2d.dof import SUBTLE  # noqa: E402
from engine.hd2d.haze import Haze  # noqa: E402
from engine.hd2d.post import Post  # noqa: E402
from hd2d_demo import HiddenGame  # noqa: E402


def clocks() -> str:
    if MESA:
        return "software"
    try:
        return subprocess.run(["nvidia-smi", "--query-gpu=clocks.gr,clocks.mem,pstate", "--format=csv,noheader"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "?"


def stats(t: list[float]) -> dict[str, float]:
    t = sorted(t[len(t) // 10:])
    return {"p50_ms": round(statistics.median(t), 4), "p95_ms": round(t[int(0.95 * len(t))], 4), "n": len(t)}


def main() -> None:
    game = HiddenGame(HERE.parent / "l4h" / "lakeside", size=(W, H))
    game.window.audio.set_muted(True)
    ctx = game.window.ctx
    res: dict = {"worktree": str(WT), "gl": str(ctx.info.RENDERER), "size": [W, H], "rounds": ROUNDS,
                 "method": "wall round ctx.finish()" if MESA else "GL timer query; CPU perf_counter round the call"}
    tex = ctx.texture((W, H), components=4)
    fbo = ctx.framebuffer(color_attachments=[tex])
    q = ctx.query(samples=False, time=True, primitives=False)

    def timed(run) -> tuple[float, float]:
        if MESA:
            ctx.finish()
            t0 = time.perf_counter()
            run()
            c = time.perf_counter() - t0
            ctx.finish()
            return (time.perf_counter() - t0) * 1000, c * 1000
        with q:
            t0 = time.perf_counter()
            run()
            c = time.perf_counter() - t0
        return q.time_elapsed / 1e6, c * 1000

    try:
        game.load("packs/core_regions/scenes/lakeside__l4_night_lamps.json")
        game.step(5)
        p = game.player()
        p.center_x, p.bottom = 1000, 520
        game.window.motion_time = 0.0
        game.step(120)
        hd = game.window.hd2d_renderer
        hd.dof_allow_software = True  # (timing only: the engine bypasses DoF on software GL)
        base = hd.settings
        bloom = Bloom("warm")
        variants = {"off": base, "bloom": dataclasses.replace(base, bloom=bloom),
                    "bloom+haze+graded": dataclasses.replace(base, bloom=bloom, haze=Haze("evening"), post=Post("natural")),
                    "haze+graded": dataclasses.replace(base, haze=Haze("evening"), post=Post("natural")),
                    "dof": dataclasses.replace(base, depth_of_field=SUBTLE),
                    "all": dataclasses.replace(base, depth_of_field=SUBTLE, bloom=bloom, haze=Haze("evening"),
                                               post=Post("natural"))}

        def mode(settings):
            def run() -> None:
                hd.settings = settings
                fbo.use()
                hd.draw()
            return run

        modes = {n: mode(s) for n, s in variants.items()}
        for f in modes.values():
            f()
            f()
        ctx.finish()
        gpu: dict[str, list[float]] = {n: [] for n in modes}
        cpu: dict[str, list[float]] = {n: [] for n in modes}
        before = clocks()
        names = list(modes)
        for r in range(ROUNDS):
            for n in names[r % len(names):] + names[:r % len(names)]:
                modes[n]()  # (untimed: a mode's first frame after another makes or frees what it needs; steady state)
                g, c = timed(modes[n])
                gpu[n].append(g)
                cpu[n].append(c)
        res["whole_frame"] = {n: {"gpu": stats(gpu[n]), "cpu": stats(cpu[n])} for n in modes}
        res["whole_frame_clocks"] = [before, clocks()]
        # bloom's own pass and the final stage alone, on the world the last draw left
        hd.settings = variants["bloom"]
        fbo.use()
        hd.draw()
        comp, bp = hd._composite, hd._bloom
        colour, depth = hd._fbo_parts
        glow = bp._chain[2][0][1]

        def blit() -> None:
            fbo.use()
            colour.use(0)
            with ctx.enabled_only():
                hd._blit.render(hd.blit_prog)

        def bloom_pass() -> None:
            bp.render(hd._blit, depth, bloom, None, False)

        def composite_glow() -> None:
            comp.configure(None, None, bloom.values.strength)
            fbo.use()
            with ctx.enabled_only():
                comp.render(hd._blit, colour, depth, glow)

        passes = {"blit": blit, "bloom_pass": bloom_pass, "composite_with_glow": composite_glow}
        pg: dict[str, list[float]] = {n: [] for n in passes}
        for f in passes.values():
            f()
        for r in range(ROUNDS * 2):
            pn = list(passes)
            for n in pn[r % len(pn):] + pn[:r % len(pn)]:
                pg[n].append(timed(passes[n])[0])
        res["passes"] = {n: stats(v) for n, v in pg.items()}
        comp.configure(None)
        # moving: the player walks right then left, haze on and off alternating, each frame drawn
        key = game.arcade.key
        mg: dict[str, list[float]] = {"off": [], "bloom": []}
        mc: dict[str, list[float]] = {"off": [], "bloom": []}
        frames = 120 if not MESA else 30
        for direction in (key.RIGHT, key.LEFT):
            game.window.dispatch_event("on_key_press", direction, 0)
            for i in range(frames):
                game.step(1)
                n = "bloom" if i % 2 else "off"
                modes[n]()  # (untimed, as above)
                g, c = timed(modes[n])
                mg[n].append(g)
                mc[n].append(c)
            game.window.dispatch_event("on_key_release", direction, 0)
            game.step(2)
        res["moving"] = {n: {"gpu": stats(mg[n]), "cpu": stats(mc[n])} for n in mg}
        # turning it on (its programs compiled, its targets made) and off (all freed): one-time costs, timed alone
        on_t, off_t = [], []
        for _ in range(5 if MESA else 20):
            modes["off"]()
            modes["off"]()
            ctx.finish()
            on_t.append(timed(modes["bloom"])[1 if MESA else 1])
            modes["bloom"]()
            ctx.finish()
            off_t.append(timed(modes["off"])[1])
        res["toggle_cpu_ms"] = {"first_frame_on": stats(on_t + on_t[:1]), "first_frame_off": stats(off_t + off_t[:1])}
        # objects, memory and draw calls: off, on, off again
        def held(name: str) -> dict:
            modes[name]()
            st = hd.stats()
            return {"draw_calls": hd.draw_calls, "bloom_passes": (hd.last_bloom or {}).get("passes", 0),
                    "gl_objects": len(hd.gl_objects()), "bloom_bytes": st["bloom_bytes"],
                    "target_bytes": st["target_bytes"], "bloom_made": hd._bloom is not None}
        res["objects"] = {"off": held("off"), "bloom": held("bloom"), "all": held("all"), "off_again": held("off")}
    finally:
        game.close()
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
