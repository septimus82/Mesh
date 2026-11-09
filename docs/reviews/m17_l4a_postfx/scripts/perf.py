"""M17-L4A timing: each candidate full-screen pass on the same settled world frame, interleaved in one process (the
same GPU clock state for all), N rounds, the order rotated each round:
  blit       the renderer's existing final blit (what a post pass would REPLACE: the incremental cost is X - blit)
  grade / vignette / haze / combo   the prototype pass with that effect (combo: all three in one pass)
  dof        the existing depth-of-field composite (Subtle), in place of the blit
  dof+combo  the DoF composite into an intermediate RGBA8 target, then the combo pass (two passes)
GPU timer query per pass on a hardware GPU; on Mesa llvmpipe (--mesa) wall time around ctx.finish() (its timer query
is not trustworthy, #460 Phase A). Also the whole renderer frame (draw + final pass), blit vs combo, interleaved.
Usage: py -3.13 perf.py OUT.json W H [--mesa] [--rounds N]
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

HERE = Path(__file__).parent
WT = Path(r"D:\Games\Mesh-l4a")
OUT, W, H = Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
MESA = "--mesa" in sys.argv
ROUNDS = int(sys.argv[sys.argv.index("--rounds") + 1]) if "--rounds" in sys.argv else (40 if MESA else 400)
for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "MESH_USER_DIR", "MESH_PROJECTS_DIR"):
    os.environ[name] = str(HERE / "env" / name.lower())
if MESA:
    import mesa_preload  # noqa: F401
sys.path.insert(0, str(WT))
sys.path.insert(0, str(WT / "tooling"))
sys.path.insert(0, str(HERE))
os.chdir(WT)
import engine.optional_arcade  # noqa: E402,F401
import engine.hd2d.renderer as R  # noqa: E402

assert Path(R.__file__).resolve().is_relative_to(WT), R.__file__
from engine.hd2d.dof import SUBTLE  # noqa: E402
from hd2d_demo import HiddenGame  # noqa: E402
from presets import GRADES, HAZES  # noqa: E402
from postfx import Post, PostPass  # noqa: E402

PROJECT = HERE / "lakeside"
SHOTS = {"village_noon": ("packs/core_regions/scenes/lakeside.json", (1000, 520)),
         "village_night_lamps": ("packs/core_regions/scenes/lakeside__l4_night_lamps.json", (1000, 520))}
POSTS = {"grade": Post(**GRADES["day"]), "vignette": Post(vig=0.18), "haze": Post(**HAZES["day"]),
         "combo": Post(**{**GRADES["day"], **HAZES["day"]}, vig=0.18)}


def clocks() -> str:
    if MESA:
        return "software"
    try:
        return subprocess.run(["nvidia-smi", "--query-gpu=clocks.gr,clocks.mem,pstate", "--format=csv,noheader"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "?"


def main() -> None:
    game = HiddenGame(PROJECT, size=(W, H))
    window = game.window
    window.audio.set_muted(True)
    ctx = window.ctx
    out_tex = ctx.texture((W, H), components=4)
    out_fbo = ctx.framebuffer(color_attachments=[out_tex])
    mid_tex = ctx.texture((W, H), components=4)
    mid_fbo = ctx.framebuffer(color_attachments=[mid_tex])
    q = ctx.query(samples=False, time=True, primitives=False)
    res: dict[str, object] = {"gl": str(ctx.info.RENDERER), "size": [W, H], "rounds": ROUNDS,
                              "method": "wall around ctx.finish()" if MESA else "GL timer query per pass"}
    try:
        for shot, (scene, feet) in SHOTS.items():
            game.load(scene)
            game.step(5)
            p = game.player()
            p.center_x, p.bottom = feet
            window.motion_time = 0.0
            if hasattr(window, "water_time"):
                window.water_time = 0.0
            game.step(120)
            hd = window.hd2d_renderer
            base = hd.settings
            pp = PostPass(ctx, R.BLIT_VS, hd._blit, (W, H))
            out_fbo.use()
            hd.draw()
            focus = hd.dof_focus(hd.camera, True)[0]
            colour, depth = hd._fbo_parts
            hd.settings = dataclasses.replace(base, depth_of_field=SUBTLE)
            hd.dof_allow_software = True  # (timing only: the engine bypasses DoF on software GL)
            dof_frame = hd._dof_frame(hd.camera, True, (W, H))
            hd.settings = base

            def blit() -> None:
                out_fbo.use()
                colour.use(0)
                with ctx.enabled_only():
                    hd._blit.render(hd.blit_prog)

            def post(name: str):
                def run() -> None:
                    pp.run(colour, depth, hd, POSTS[name], focus, read=False)
                return run

            def dof() -> None:
                out_fbo.use()
                colour.use(0)
                hd._composite_dof(dof_frame, hd.camera, None)

            def dof_combo() -> None:
                mid_fbo.use()
                colour.use(0)
                hd._composite_dof(dof_frame, hd.camera, None)
                pp.run(mid_tex, depth, hd, POSTS["combo"], focus, read=False)

            passes = {"blit": blit, **{n: post(n) for n in POSTS}, "dof": dof, "dof+combo": dof_combo}
            times: dict[str, list[float]] = {n: [] for n in passes}
            cpu: dict[str, list[float]] = {n: [] for n in passes}
            for _ in range(5):  # warm every program
                for f in passes.values():
                    f()
            ctx.finish()
            before = clocks()
            names = list(passes)
            for r in range(ROUNDS):
                order = names[r % len(names):] + names[:r % len(names)]
                for n in order:
                    if MESA:
                        ctx.finish()
                        t0 = time.perf_counter()
                        passes[n]()
                        ctx.finish()
                        times[n].append((time.perf_counter() - t0) * 1000)
                    else:
                        with q:
                            c0 = time.perf_counter()
                            passes[n]()
                            cpu[n].append((time.perf_counter() - c0) * 1000)  # the CPU's submission of the pass
                        times[n].append(q.time_elapsed / 1e6)
            after = clocks()
            row: dict[str, object] = {"clocks": [before, after]}
            for n, t in times.items():
                t = sorted(t[len(t) // 10:])  # first 10% dropped
                row[n] = {"p50_ms": round(statistics.median(t), 4), "p90_ms": round(t[int(0.9 * len(t))], 4),
                          "p95_ms": round(t[int(0.95 * len(t))], 4)}
                if cpu[n]:
                    c = sorted(cpu[n][len(cpu[n]) // 10:])
                    row[n]["cpu_p50_ms"] = round(statistics.median(c), 4)
            # the whole renderer frame: draw + blit (as today) vs draw + combo pass, interleaved (on a hardware GPU the
            # timer spans the CPU's preparation between the two passes too: an upper bound, not the GPU cost)
            whole: dict[str, list[float]] = {"draw+blit": [], "draw+combo": []}
            for r in range(ROUNDS // 2 if not MESA else 10):
                for n in (("draw+blit", "draw+combo") if r % 2 == 0 else ("draw+combo", "draw+blit")):
                    if MESA:
                        ctx.finish()
                        t0 = time.perf_counter()
                    else:
                        q.__enter__()
                    out_fbo.use()
                    hd.draw()  # (its own blit into out_fbo)
                    if n == "draw+combo":
                        pp.run(colour, depth, hd, POSTS["combo"], focus, read=False)
                    if MESA:
                        ctx.finish()
                        whole[n].append((time.perf_counter() - t0) * 1000)
                    else:
                        q.__exit__(None, None, None)
                        whole[n].append(q.time_elapsed / 1e6)
            for n, t in whole.items():
                t = sorted(t[len(t) // 10:])
                row[n] = {"p50_ms": round(statistics.median(t), 4), "p95_ms": round(t[int(0.95 * len(t))], 4)}
            row["draw_calls"] = hd.draw_calls
            res[shot] = row
            pp.release()
            print(shot, json.dumps({k: (v["p50_ms"] if isinstance(v, dict) else v) for k, v in row.items()}), flush=True)
            OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    finally:
        game.close()


main()
