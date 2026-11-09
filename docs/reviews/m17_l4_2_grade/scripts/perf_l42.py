"""M17-L4-1 timing on the scratch Lakeside village (authored), same settled frame, interleaved in one process (the
same GPU clock state for all), the order rotated each round, the first 10% dropped:
  whole frame  Hd2dRenderer.draw() into an offscreen target: GPU time (timer query) and CPU time (perf_counter round
               the call: the Python that builds and submits it), per mode: off, dof (Subtle) and, on L4-1, identity
               and dof+identity
  passes       (L4-1 only) the final stage alone on the drawn world: blit, identity composite, DoF, DoF -> chain ->
               identity
On Mesa llvmpipe (--mesa) wall time round ctx.finish() replaces the timer query (not trustworthy there, #460).
    py -3.13 perf_l41.py WORKTREE OUT.json W H [--mesa] [--rounds N]
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
L4A = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\c18a071c64bbe7a7\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\l4a")
if MESA:
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

L41 = hasattr(R.Hd2dRenderer, "_final_composite")
try:
    from engine.hd2d.post import Post
    L42 = True
except ImportError:
    L42 = False


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
    return {"p50_ms": round(statistics.median(t), 4), "p95_ms": round(t[int(0.95 * len(t))], 4)}


def main() -> None:
    game = HiddenGame(L4A / "lakeside", size=(W, H))
    game.window.audio.set_muted(True)
    ctx = game.window.ctx
    res: dict = {"worktree": str(WT), "l4_1": L41, "gl": str(ctx.info.RENDERER), "size": [W, H], "rounds": ROUNDS,
                 "method": "wall round ctx.finish()" if MESA else "GL timer query; CPU perf_counter round the call"}
    tex = ctx.texture((W, H), components=4)
    fbo = ctx.framebuffer(color_attachments=[tex])
    q = ctx.query(samples=False, time=True, primitives=False)
    try:
        game.load("packs/core_regions/scenes/lakeside.json")
        game.step(5)
        p = game.player()
        p.center_x, p.bottom = 1000, 520
        game.window.motion_time = 0.0
        game.step(120)
        hd = game.window.hd2d_renderer
        hd.dof_allow_software = True  # (timing only: the engine bypasses DoF on software GL)
        base, with_dof = hd.settings, dataclasses.replace(hd.settings, depth_of_field=SUBTLE)

        graded = dataclasses.replace(base, post=Post("natural")) if L42 else base
        graded_dof = dataclasses.replace(with_dof, post=Post("natural")) if L42 else with_dof

        def mode(settings):
            def run() -> None:
                hd.settings = settings
                fbo.use()
                hd.draw()
            return run

        modes = {"off": mode(base), "dof": mode(with_dof)}
        if L42 and "--base-modes" not in sys.argv:  # (--base-modes: exactly the modes L4-1 has)
            modes |= {"graded": mode(graded), "dof+graded": mode(graded_dof)}
        gpu: dict[str, list[float]] = {n: [] for n in modes}
        cpu: dict[str, list[float]] = {n: [] for n in modes}
        for f in modes.values():
            f()
            f()
        ctx.finish()
        before = clocks()
        names = list(modes)
        for r in range(ROUNDS):
            for n in names[r % len(names):] + names[:r % len(names)]:
                if MESA:
                    ctx.finish()
                    t0 = time.perf_counter()
                    modes[n]()
                    c = time.perf_counter() - t0
                    ctx.finish()
                    gpu[n].append((time.perf_counter() - t0) * 1000)
                else:
                    with q:
                        t0 = time.perf_counter()
                        modes[n]()
                        c = time.perf_counter() - t0
                    gpu[n].append(q.time_elapsed / 1e6)
                cpu[n].append(c * 1000)
        res["whole_frame"] = {n: {"gpu": stats(gpu[n]), "cpu": stats(cpu[n])} for n in modes}
        res["whole_frame_clocks"] = [before, clocks()]
        if L42 and "--base-modes" not in sys.argv:  # the final stage alone, on the world the last draw left
            hd.settings = graded_dof
            fbo.use()
            hd.draw()
            dof_frame = hd._dof_frame(hd.camera, True, (W, H))
            comp = hd._composite
            colour, depth = hd._fbo_parts
            chain, chain_tex = comp.chain_target((W, H))

            def blit() -> None:
                fbo.use()
                colour.use(0)
                with ctx.enabled_only():
                    hd._blit.render(hd.blit_prog)

            post = graded.post

            def identity() -> None:
                comp.configure(None)
                fbo.use()
                with ctx.enabled_only():
                    comp.render(hd._blit, colour, depth)

            def grade() -> None:
                comp.configure(post)
                fbo.use()
                with ctx.enabled_only():
                    comp.render(hd._blit, colour, depth)

            def dof() -> None:
                fbo.use()
                colour.use(0)
                hd._composite_dof(dof_frame, hd.camera, None)

            def dof_grade() -> None:
                comp.configure(post)
                chain.use()
                colour.use(0)
                hd._composite_dof(dof_frame, hd.camera, None)
                fbo.use()
                with ctx.enabled_only():
                    comp.render(hd._blit, chain_tex, depth)

            passes = {"blit": blit, "identity": identity, "grade": grade, "dof": dof, "dof->grade": dof_grade}
            pg: dict[str, list[float]] = {n: [] for n in passes}
            pc: dict[str, list[float]] = {n: [] for n in passes}
            for f in passes.values():
                f()
            ctx.finish()
            names = list(passes)
            for r in range(ROUNDS * 2):
                for n in names[r % len(names):] + names[:r % len(names)]:
                    if MESA:
                        ctx.finish()
                        t0 = time.perf_counter()
                        passes[n]()
                        c = time.perf_counter() - t0
                        ctx.finish()
                        pg[n].append((time.perf_counter() - t0) * 1000)
                    else:
                        with q:
                            t0 = time.perf_counter()
                            passes[n]()
                            c = time.perf_counter() - t0
                        pg[n].append(q.time_elapsed / 1e6)
                    pc[n].append(c * 1000)
            res["passes"] = {n: {"gpu": stats(pg[n]), "cpu": stats(pc[n])} for n in passes}
            res["passes_clocks"] = clocks()
            comp.configure(post)
            hits = []
            for _ in range(2000):  # the per-frame check when nothing changed (the cache)
                t0 = time.perf_counter()
                comp.configure(post)
                hits.append((time.perf_counter() - t0) * 1e6)
            other = Post("moonlight")
            sets = []
            for i in range(400):  # a real change: every uniform set (once per edit of the room's settings)
                t0 = time.perf_counter()
                comp.configure(other if i % 2 == 0 else post)
                sets.append((time.perf_counter() - t0) * 1e6)
            res["configure_us"] = {"unchanged_p50": round(statistics.median(hits), 3),
                                   "changed_p50": round(statistics.median(sets), 2)}
            res["allocations"] = {"composite_objects": len(comp.gl_objects()),
                                  "chain_bytes": W * H * 4, "chain_allocations": comp.chain_allocations}
    finally:
        game.close()
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k in ("whole_frame", "passes")}))


main()
