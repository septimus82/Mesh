"""M17-W1 timing, as L4-4's method: the same settled frame, the modes of one room interleaved in one process (the same
GPU clock state for all), the order rotated each round, an untimed frame before each timed one (a mode's first frame
after another makes or frees what it needs: steady state), the first 10% dropped.
  rooms      the glen by day (no waterfall / one / one without spray), five waterfalls (none / five), the evening glen
             with its haze and warm bloom (none / one), and the glen out of the picture (none / one)
  frames     Hd2dRenderer.draw() into an offscreen target: GPU time (timer query) and CPU time round the call, static
             camera on the fall and a moving one (panning across it every frame)
  editing    CPU: the river's geometry checked and built (ribbon + curtain), the water layer rebuilt for a point moved
             (Studio's drag), the set_waterfall op; for one fall and five
  objects    draw calls, GL objects, the water's GPU bytes, the curtain's bytes, spray particles
On Mesa llvmpipe (--mesa) wall time round ctx.finish() replaces the timer query (not trustworthy there, #460).
    py -3.13 perf_w1.py WORKTREE OUT.json W H [--mesa] [--rounds N]
"""
from __future__ import annotations

import dataclasses
import json
import math
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

WT, OUT, W, H = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
MESA = "--mesa" in sys.argv
ROUNDS = int(sys.argv[sys.argv.index("--rounds") + 1]) if "--rounds" in sys.argv else (20 if MESA else 150)
HERE = Path(__file__).resolve().parent
if MESA:
    sys.path.insert(0, str(HERE))
    import mesa_preload  # noqa: F401
sys.path.insert(0, str(WT))
sys.path.insert(1, str(WT / "tooling"))
import engine.optional_arcade  # noqa: E402,F401
import engine.hd2d.renderer as R  # noqa: E402

assert Path(R.__file__).resolve().is_relative_to(WT.resolve()), R.__file__
import w1_waterfall_checks as checks  # noqa: E402
import w1_waterfall_study as glen  # noqa: E402
from hd2d_demo import SCENES, HiddenGame  # noqa: E402


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


def project() -> Path:
    """One project, the glen's rooms as scene files beside its start room (made once; the same every run)."""
    root = HERE / "perfproj"
    proj = root / "glen"
    if not (proj / SCENES / "many.json").exists():
        proj = glen.make_project(root, "glen")
        for variant in ("many", "haze_bloom"):
            other = glen.make_project(root, f"glen_{variant}", variant=variant)
            (proj / SCENES / f"{variant}.json").write_bytes((other / SCENES / "start.json").read_bytes())
    return proj


def main() -> None:
    proj = project()
    game = HiddenGame(proj, size=(W, H))
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

    def room(scene: str) -> Any:
        game.load(f"{SCENES}/{scene}")
        game.step(30)
        game.window.water_time = game.window.motion_time = 3.0
        return game.window.hd2d_renderer

    def none_of(rivers: tuple) -> tuple:
        return tuple(dataclasses.replace(r, falls=(), mouth="none") for r in rivers)

    def measure(hd: Any, variants: dict, cam_spec: tuple, moving: bool) -> dict:
        state = {"i": 0}

        def mode(rivers: tuple):
            def run() -> None:
                hd.settings = dataclasses.replace(hd.settings, rivers=rivers)
                spec = cam_spec
                if moving:  # (panning across the fall and back, a step a frame)
                    state["i"] += 1
                    (tx, ty, tz), d, p, y = cam_spec
                    spec = ((tx + 4.0 * math.sin(state["i"] * 0.05), ty, tz), d, p, y)
                fbo.use()
                hd.draw(camera=checks.camera(spec), viewport=(0, 0, W, H))
            return run

        modes = {n: mode(r) for n, r in variants.items()}
        for f in modes.values():
            f()
            f()
        ctx.finish()
        gpu: dict[str, list[float]] = {n: [] for n in modes}
        cpu: dict[str, list[float]] = {n: [] for n in modes}
        names = list(modes)
        for r in range(ROUNDS):
            for n in names[r % len(names):] + names[:r % len(names)]:
                modes[n]()
                g, c = timed(modes[n])
                gpu[n].append(g)
                cpu[n].append(c)
        out = {n: {"gpu": stats(gpu[n]), "cpu": stats(cpu[n])} for n in modes}
        for n in modes:  # objects, as each mode holds them
            modes[n]()
            out[n]["draw_calls"] = hd.draw_calls
            out[n]["gl_objects"] = len(hd.gl_objects())
            w = hd.water
            out[n]["water_bytes"] = w.memory_bytes() if w is not None else 0
            out[n]["curtain_bytes"] = sum(b.size for b in w.fall_buffers or ()) if w is not None else 0
            out[n]["curtain_indices"] = w.fall_count if w is not None else 0
            out[n]["spray_particles"] = (sum(round(f[7] * 24) for f in w.feet) if w is not None else 0)
        return out

    try:
        res["clocks_before"] = clocks()
        hd = room("start.json")
        rivers = hd.settings.rivers
        dry = tuple(dataclasses.replace(r, falls=tuple(dataclasses.replace(f, spray=0.0) for f in r.falls))
                    for r in rivers)
        day = {"none": none_of(rivers), "one": rivers, "one_no_spray": dry}
        res["day_static"] = measure(hd, day, checks.FRONT, False)
        res["day_moving"] = measure(hd, day, checks.FRONT, True)
        res["day_offscreen"] = measure(hd, {"none": none_of(rivers), "one": rivers}, checks.AWAY, False)
        res["day_game_camera"] = measure(hd, {"none": none_of(rivers), "one": rivers}, checks.WIDE, False)
        # editing: the river's geometry checked and built, and the water layer rebuilt for a moved point
        from engine import project_ops as ops
        from engine.hd2d import river as river_mod
        doc = glen.scene_of(proj)
        edit: dict = {}
        for name, scene_doc in (("one", doc), ("five", json.loads((proj / SCENES / "many.json").read_text()))):
            raw = scene_doc["settings"]["hd2d"]["rivers"]
            build, layer, op = [], [], []
            for k in range(40):
                river_mod.ribbon.cache_clear()
                t0 = time.perf_counter()
                parsed = river_mod.parse_rivers(raw)
                river_mod.vertices(parsed, 0.035)
                river_mod.fall_vertices(parsed, 0.035)
                build.append((time.perf_counter() - t0) * 1000)
                moved = [dict(r, points=[[p[0] + (1.0 + k % 3 if i == 2 else 0.0), *p[1:]]
                                         for i, p in enumerate(r["points"])]) for r in raw]
                shown = river_mod.parse_rivers(moved)
                t0 = time.perf_counter()
                hd.water.set_rivers(shown)
                layer.append((time.perf_counter() - t0) * 1000)
                t0 = time.perf_counter()
                ops.set_waterfall(scene_doc, raw[0]["id"], 2, foam=0.5 + 0.01 * (k % 7))
                op.append((time.perf_counter() - t0) * 1000)
            edit[name] = {"check_and_build_ms": stats(build), "water_layer_rebuild_ms": stats(layer),
                          "set_waterfall_op_ms": stats(op), "fall_buffers_made": hd.water.fall_allocations}
        res["editing_cpu"] = edit
        hd = room("many.json")
        res["five_static"] = measure(hd, {"none": none_of(hd.settings.rivers), "five": hd.settings.rivers},
                                     checks.WIDE, False)
        hd = room("haze_bloom.json")
        res["haze_bloom_static"] = measure(hd, {"none": none_of(hd.settings.rivers), "one": hd.settings.rivers},
                                           checks.WIDE, False)
        res["clocks_after"] = clocks()
    finally:
        game.close()
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
