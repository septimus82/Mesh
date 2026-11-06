"""Scratch: is the ~1.3 ms step GPU work, or the GPU idle inside the timer while Python prepares the composite?
Lakeside shop + bridge, 1080p, product shader at 16 and 24 samples. Two phases (timer queries can't nest):
  A: the renderer's whole draw timed (GPU), paired off/on, plus its CPU wall time (perf_counter around hd.draw);
  B: only the composite timed, inside the frame (GPU), plus the CPU time from the draw's start to the composite's.
Usage: bubble.py PROJECT OUT CYCLES
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, r"D:\Games\Mesh-dof")
sys.path.insert(0, r"D:\Games\Mesh-dof\tooling")
import dof_study  # noqa: E402
from dof_study import Study  # noqa: E402

import engine.hd2d.dof as dof  # noqa: E402
import engine.hd2d.renderer as rmod  # noqa: E402

project, out, cycles = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "MESH_USER_DIR", "MESH_PROJECTS_DIR"):
    os.environ[name] = str(out / "env" / name.lower())
    Path(os.environ[name]).mkdir(parents=True, exist_ok=True)


def q(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(p * len(xs)))], 4) if xs else None


st = Study(project, out, (1920, 1080))
qc = st.ctx.query(samples=False, time=True, primitives=False)
original_composite = rmod.Hd2dRenderer._composite_dof
original_draw = rmod.Hd2dRenderer.draw
state = {"composite_ns": [], "cpu_draw_ms": [], "cpu_to_composite_ms": [], "t0": 0.0}


def timed_draw(self, *a, **k):
    state["t0"] = time.perf_counter()
    r = original_draw(self, *a, **k)
    state["cpu_draw_ms"].append((time.perf_counter() - state["t0"]) * 1000)
    return r


def timed_composite(self, frame, cam, viewport):
    state["cpu_to_composite_ms"].append((time.perf_counter() - state["t0"]) * 1000)
    with qc:
        original_composite(self, frame, cam, viewport)
    state["composite_ns"].append(qc.time_elapsed)


res = {}
try:
    with dof_study.warnings.catch_warnings():
        dof_study.warnings.filterwarnings("ignore", message="draw_text is an extremely slow function")
        for view, place in (("lakeside_shop", (1168.0, 456.0)), ("lakeside_bridge", (1040.0, 900.0))):
            st._timing = False
            rmod.Hd2dRenderer.draw = original_draw
            st.game.load("packs/core_regions/scenes/lakeside.json")
            st.game.step(5)
            p = st.game.player()
            p.center_x, p.center_y = place
            st.game.step(90)
            for cap in (16, 24):
                dof.TAPS_MAX = cap
                # A: whole draw GPU (the study's wrapper) + CPU wall time of the draw
                rmod.Hd2dRenderer.draw = timed_draw
                st.hd._dof_study = False
                st.hd.__dict__.pop("draw", None)
                st._timed_draw()
                st._timing = True
                gpu = {"off": [], "on": []}
                cpu = {"off": [], "on": []}
                for c in range(30 + cycles):
                    st.game.step(1)
                    for label, setting in (("off", None), ("on", dof.SUBTLE)):
                        st.set_dof(setting)
                        st.draw_ns = []
                        state["cpu_draw_ms"] = []
                        st.window.dispatch_event("on_draw")
                        if c >= 30:
                            gpu[label].append(st.draw_ns[-1] / 1e6)
                            cpu[label].append(state["cpu_draw_ms"][-1])
                st._timing = False
                inc = [b - a for a, b in zip(gpu["off"], gpu["on"])]
                cinc = [b - a for a, b in zip(cpu["off"], cpu["on"])]
                # B: only the composite timed in the frame
                st.hd.__dict__.pop("draw", None)
                st.hd._dof_study = False
                rmod.Hd2dRenderer._composite_dof = timed_composite
                state["composite_ns"], state["cpu_to_composite_ms"] = [], []
                for c in range(30 + cycles):
                    st.game.step(1)
                    st.set_dof(dof.SUBTLE)
                    st.window.dispatch_event("on_draw")
                rmod.Hd2dRenderer._composite_dof = original_composite
                comp = [x / 1e6 for x in state["composite_ns"][30:]]
                res[f"{view}/taps{cap}"] = {
                    "A_whole_draw_gpu_incremental_ms": {"p50": q(inc, .5), "p95": q(inc, .95),
                                                        "over_1ms": sum(1 for x in inc if x > 1)},
                    "A_whole_draw_cpu_ms": {"off_p50": q(cpu["off"], .5), "on_p50": q(cpu["on"], .5),
                                            "incremental_p50": q(cinc, .5), "incremental_p95": q(cinc, .95)},
                    "B_composite_gpu_in_frame_ms": {"p50": q(comp, .5), "p95": q(comp, .95), "max": q(comp, 1.0)},
                    "B_cpu_from_draw_start_to_composite_ms_p50": q(state["cpu_to_composite_ms"][30:], .5)}
                (out / "bubble.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
finally:
    dof.TAPS_MAX = 24
    rmod.Hd2dRenderer._composite_dof = original_composite
    rmod.Hd2dRenderer.draw = original_draw
    st.close()
print(json.dumps(res, indent=1))
