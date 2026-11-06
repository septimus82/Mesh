"""Scratch (#475 option b experiment): 24 vs 16 samples, whole HD-2D renderer GPU time, RTX 4070.

Per view, warmed (90 steps + 60 discarded cycles), then:
- interleaved: each cycle draws off, capA, off, capB (A/B order alternating per cycle), a GL timer around the
  renderer's whole draw each time; incremental = on - the off drawn just before it (paired);
- steady: blocks of 40 frames off, 24, off, 16 (x3), the renderer's whole draw timed each frame;
- pass alone: the composite redrawn after an idle GPU, per cap (a lower bound);
- telemetry: nvidia-smi (read-only) sampled every 100 ms in the background; per-view window summarised.
Usage: ab_timing.py PROJECT OUT SET WxH CYCLES
"""
import csv
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, r"D:\Games\Mesh-dof")
sys.path.insert(0, r"D:\Games\Mesh-dof\tooling")
import dof_study  # noqa: E402
from dof_study import VIEWS, Study  # noqa: E402

import engine.hd2d.dof as dof  # noqa: E402

project, out, which, size, cycles = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4], int(sys.argv[5])
w, h = (int(v) for v in size.split("x"))
out.mkdir(parents=True, exist_ok=True)
for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "MESH_USER_DIR", "MESH_PROJECTS_DIR"):
    os.environ[name] = str(out / "env" / name.lower())
    Path(os.environ[name]).mkdir(parents=True, exist_ok=True)

smi_path = out / "nvidia_smi.csv"
smi = subprocess.Popen(["nvidia-smi", "--query-gpu=timestamp,clocks.gr,clocks.mem,power.draw,utilization.gpu,pstate",
                        "--format=csv,noheader,nounits", "-lms", "100"], stdout=open(smi_path, "w"),
                       stderr=subprocess.DEVNULL)


def q(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(p * len(xs)))] / 1e6, 4) if xs else None


def summary(xs):
    if not xs:
        return None
    med = statistics.median(xs)
    return {"n": len(xs), "p50": q(xs, .5), "p95": q(xs, .95), "max": q(xs, 1.0),
            "over_1ms": sum(1 for x in xs if x > 1e6), "over_2x_p50": sum(1 for x in xs if x > 2 * med)}


import atexit  # noqa: E402
atexit.register(smi.terminate)  # the sampler stops however this script ends
st = Study(project, out, (w, h))
report = {"size": [w, h], "set": which, "gl": st.ctx.info.RENDERER, "cycles": cycles, "views": {}}
windows = {}


def draw_one(setting, cap):
    if cap is not None:
        dof.TAPS_MAX = cap
    st.set_dof(setting)
    st.draw_ns = []
    st.window.dispatch_event("on_draw")
    return float(st.draw_ns[-1])


try:
    with dof_study.warnings.catch_warnings():
        dof_study.warnings.filterwarnings("ignore", message="draw_text is an extremely slow function")
        st._timing = True
        for name, scene, place in VIEWS[which]:
            st._timing = False
            st.game.load(scene)
            st.game.step(5)
            if place is not None:
                p = st.game.player()
                p.center_x, p.center_y = place
            st.game.step(90)
            st._timed_draw()
            st._timing = True
            t0 = time.time()
            inc = {24: [], 16: []}
            ons = {24: [], 16: []}
            offs = []
            alone = {24: [], 16: []}
            taps_seen = {}
            for c in range(60 + cycles):
                st.game.step(1)
                order = (24, 16) if c % 2 == 0 else (16, 24)
                for cap in order:
                    off = draw_one(None, None)
                    on = draw_one(dof.SUBTLE, cap)
                    taps_seen[cap] = st.hd.last_dof["taps"]
                    if c >= 60:
                        offs.append(off)
                        ons[cap].append(on)
                        inc[cap].append(on - off)
                        if c % 5 == 0:
                            a = st.alone_ns()
                            if a is not None:
                                alone[cap].append(float(a))
            t1 = time.time()
            steady = {"off": [], 24: [], 16: []}
            for _ in range(3):
                for label, setting, cap in (("off", None, None), (24, dof.SUBTLE, 24), ("off", None, None),
                                            (16, dof.SUBTLE, 16)):
                    for _ in range(40):
                        st.game.step(1)
                        steady[label].append(draw_one(setting, cap))
            t2 = time.time()
            windows[name] = (t0, t1, t2)
            report["views"][name] = {
                "taps": taps_seen, "radius_px": round(st.hd.last_dof["radius"], 3),
                "interleaved": {"off_draw": summary(offs), "on_draw_24": summary(ons[24]), "on_draw_16": summary(ons[16]),
                                "incremental_24": summary(inc[24]), "incremental_16": summary(inc[16])},
                "steady": {"off": summary(steady["off"]), "on_24": summary(steady[24]), "on_16": summary(steady[16]),
                           "steady_diff_p50_24": round((statistics.median(steady[24]) - statistics.median(steady["off"])) / 1e6, 4),
                           "steady_diff_p50_16": round((statistics.median(steady[16]) - statistics.median(steady["off"])) / 1e6, 4),
                           "steady_diff_p95_24": round(q(steady[24], .95) - q(steady["off"], .95), 4),
                           "steady_diff_p95_16": round(q(steady[16], .95) - q(steady["off"], .95), 4)},
                "pass_alone_24": summary(alone[24]), "pass_alone_16": summary(alone[16])}
            dof.TAPS_MAX = 24
            (out / "report.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
finally:
    dof.TAPS_MAX = 24
    st.close()
    smi.terminate()
    smi.wait()

# telemetry per view window (nvidia-smi timestamps are local time "YYYY/MM/DD HH:MM:SS.mmm")
rows = []
for r in csv.reader(open(smi_path)):
    try:
        ts = time.mktime(time.strptime(r[0].strip().split(".")[0], "%Y/%m/%d %H:%M:%S")) + float("0." + r[0].strip().split(".")[1])
        rows.append((ts, float(r[1]), float(r[2]), float(r[3]), float(r[4]), r[5].strip()))
    except (ValueError, IndexError):
        pass
for name, (t0, t1, t2) in windows.items():
    for part, (a, b) in (("interleaved", (t0, t1)), ("steady", (t1, t2))):
        sel = [r for r in rows if a <= r[0] <= b]
        if sel:
            report["views"][name][f"telemetry_{part}"] = {
                "samples": len(sel),
                "gr_clock_mhz": [min(r[1] for r in sel), statistics.median(r[1] for r in sel), max(r[1] for r in sel)],
                "mem_clock_mhz_median": statistics.median(r[2] for r in sel),
                "power_w_median": statistics.median(r[3] for r in sel),
                "util_pct_median": statistics.median(r[4] for r in sel),
                "pstates": sorted({r[5] for r in sel})}
(out / "report.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
print(json.dumps(report, indent=1))
