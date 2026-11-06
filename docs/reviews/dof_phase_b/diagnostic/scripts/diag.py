"""Scratch diagnostic (#475, owner-authorised "run diagnostic"): what the ~1.2-1.4 ms in-frame step is.
Product code untouched; everything is patched in this process only. Lakeside, 1080p, product cap (24).

Per frame, GL_TIMESTAMP counters (each recorded once ALL earlier GPU work has finished):
  t0 draw start | tw world done (just before the blit / the composite) | tm mid (per variant) | t1 draw done
Variants, interleaved per cycle (off, A, off, B, ...; order rotated each cycle):
  live  the product composite, reading the world's live attachments (as shipped)
  copy    the world's colour+depth first copied (glBlitFramebuffer, as water's reflections do) into a persistent
          same-size framebuffer made once; the composite reads the copy
  stale   the composite reads the copy made in the PREVIOUS frame (not written this frame), then refreshes it
  twice   the product composite drawn twice in the frame (the second pass's cost, in the frame)
  finish  glFinish (GPU idle) just before the product composite: the "pass alone" condition, in the frame
Also: one matched frame per view: copy, twice, finish must be pixel-identical to live (the copy changes nothing visible);
read-only nvidia-smi clocks every 100 ms, and its process list at start and end.
Usage: diag.py PROJECT OUT CYCLES
"""
import atexit
import csv
import ctypes
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
import engine.hd2d.renderer as rmod  # noqa: E402

project, out, cycles = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "MESH_USER_DIR", "MESH_PROJECTS_DIR"):
    os.environ[name] = str(out / "env" / name.lower())
    Path(os.environ[name]).mkdir(parents=True, exist_ok=True)

(out / "nvidia_smi_start.txt").write_text(subprocess.run(["nvidia-smi"], capture_output=True, text=True).stdout)
smi_path = out / "nvidia_smi.csv"
smi = subprocess.Popen(["nvidia-smi", "--query-gpu=timestamp,clocks.gr,clocks.mem,power.draw,utilization.gpu,pstate",
                        "--format=csv,noheader,nounits", "-lms", "100"], stdout=open(smi_path, "w"),
                       stderr=subprocess.DEVNULL)
atexit.register(smi.terminate)

from pyglet import gl as raw  # noqa: E402

st = Study(project, out, (1920, 1080))
ctx = st.ctx
QN = 4
qids = (raw.GLuint * QN)()
raw.glGenQueries(QN, qids)
stamps: dict[str, int] = {}


def mark(slot: int, key: str) -> None:
    raw.glQueryCounter(qids[slot], raw.GL_TIMESTAMP)
    stamps[key] = slot


def read() -> dict[str, float]:
    v = raw.GLuint64()
    got = {}
    for key, slot in stamps.items():
        raw.glGetQueryObjectui64v(qids[slot], raw.GL_QUERY_RESULT, ctypes.byref(v))
        got[key] = v.value
    return got


original_draw = rmod.Hd2dRenderer.draw
original_composite = rmod.Hd2dRenderer._composite_dof
Geometry = None
original_geom_render = None
state = {"variant": "live", "off_armed": False, "copy": None}


def draw(self, *a, **k):
    stamps.clear()
    mark(0, "t0")
    state["off_armed"] = True
    r = original_draw(self, *a, **k)
    state["off_armed"] = False
    mark(3, "t1")
    return r


def geom_render(self, *a, **k):  # the off frame's blit: stamp the world done just before it
    if state["off_armed"] and self is st.hd._blit and "tw" not in stamps:
        mark(1, "tw")
    return original_geom_render(self, *a, **k)


def copy_target(size):
    c = state["copy"]
    if c is None or tuple(c[1].size) != tuple(size):
        colour, depth = ctx.texture(size, components=4), ctx.depth_texture(size)
        depth.compare_func = None
        state["copy"] = c = (ctx.framebuffer(color_attachments=[colour], depth_attachment=depth), colour, depth)
    return c


def _pass(self, frame, cam, colour, depth):
    with ctx.enabled_only():
        self._dof_pass.render(self._blit, colour, depth, ortho=cam.ortho, focus=frame["focus"],
                              band=frame["band"], dof=frame["settings"], radius=frame["radius"])


def _copy(self):
    target = ctx.active_framebuffer
    fb, colour, depth = copy_target(self._fbo.size)
    ctx.copy_framebuffer(self._fbo, fb, depth=True)
    target.use(force=True)  # (the copy left its target bound, unknown to arcade's record)
    return colour, depth


def composite(self, frame, cam, viewport):
    state["off_armed"] = False
    v = state["variant"]
    if v == "finish":  # the GPU idle first (as the "pass alone" lower bound), then the product pass
        ctx.finish()
    mark(1, "tw")
    if v in ("live", "finish"):
        original_composite(self, frame, cam, viewport)
    elif v == "copy":  # copy now, then the pass reads the copy: "copy" = tw..tm, "pass" = tm..t1
        colour, depth = _copy(self)
        mark(2, "tm")
        _pass(self, frame, cam, colour, depth)
    elif v == "stale":  # the pass reads LAST frame's copy (written frames ago, GPU idled since); then refresh it
        if state["copy"] is None:
            _copy(self)
        _, colour, depth = state["copy"]
        _pass(self, frame, cam, colour, depth)
        mark(2, "tm")
        _copy(self)
    elif v == "twice":  # the product pass twice: "pass" = the first (tw..tm), "second" = tm..t1
        original_composite(self, frame, cam, viewport)
        mark(2, "tm")
        original_composite(self, frame, cam, viewport)


def q(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(p * len(xs)))], 4) if xs else None


def summ(xs):
    return {"n": len(xs), "p50": q(xs, .5), "p95": q(xs, .95), "max": q(xs, 1.0),
            "over_1ms": sum(1 for x in xs if x > 1.0)} if xs else None


def frame_once(setting, variant):
    state["variant"] = variant
    st.set_dof(setting)
    stamps.clear()
    st.window.dispatch_event("on_draw")
    t = read()
    ms = lambda a, b: (t[b] - t[a]) / 1e6 if a in t and b in t else None  # noqa: E731
    f = {"whole": ms("t0", "t1"), "world": ms("t0", "tw"), "at": time.time()}
    if setting is None:  # off: the world, then the original blit
        f["pass"] = ms("tw", "t1")
    elif variant == "copy":
        f.update(copy=ms("tw", "tm"), **{"pass": ms("tm", "t1")})
    elif variant == "stale":
        f.update(copy=ms("tm", "t1"), **{"pass": ms("tw", "tm")})
    elif variant == "twice":
        f.update(second=ms("tm", "t1"), **{"pass": ms("tw", "tm")})
    else:
        f["pass"] = ms("tw", "t1")
    return f


VARIANTS = ["live", "copy", "stale", "twice", "finish"]
report = {"cycles": cycles, "gl": ctx.info.RENDERER, "views": {}}
windows = {}
frames_by_view = {}
try:
    with dof_study.warnings.catch_warnings():
        dof_study.warnings.filterwarnings("ignore", message="draw_text is an extremely slow function")
        for name, scene, place in VIEWS["lakeside"]:
            if name == "cottage_interior":
                continue
            rmod.Hd2dRenderer.draw = original_draw
            rmod.Hd2dRenderer._composite_dof = original_composite
            st.game.load(scene)
            st.game.step(5)
            if place is not None:
                p = st.game.player()
                p.center_x, p.center_y = place
            st.game.step(90)
            hd = st.hd
            if Geometry is None:
                Geometry = type(hd._blit)
                original_geom_render = Geometry.render
            # matched frames, same state (no step between): copy / twice / finish must equal live, pixel for pixel
            st.set_dof(dof.SUBTLE)
            rmod.Hd2dRenderer._composite_dof = composite
            same = {}
            state["variant"] = "live"
            a = st.frame()
            for v in ("copy", "twice", "finish"):
                state["variant"] = v
                same[v] = bool((st.frame() == a).all())
            rmod.Hd2dRenderer.draw = draw
            Geometry.render = geom_render
            res = {"off": [], **{v: [] for v in VARIANTS}}
            t0 = time.time()
            for c in range(60 + cycles):
                st.game.step(1)
                k = c % len(VARIANTS)
                for variant in VARIANTS[k:] + VARIANTS[:k]:  # (rotated each cycle: drift falls on all)
                    off = frame_once(None, variant)
                    on = frame_once(dof.SUBTLE, variant)
                    if c >= 60:
                        res["off"].append(off)
                        res[variant].append({**on, "inc": on["whole"] - off["whole"],
                                             "world_vs_off": on["world"] - off["world"]})
            windows[name] = (t0, time.time())
            Geometry.render = original_geom_render
            row = {"identical_to_live": same, "taps": hd.last_dof["taps"] if hd.last_dof else None,
                   "off": {k: summ([f[k] for f in res["off"]]) for k in ("whole", "world", "pass")}}
            for v in VARIANTS:
                fs = res[v]
                row[v] = {k: summ([f[k] for f in fs if f.get(k) is not None])
                          for k in ("inc", "whole", "world", "world_vs_off", "copy", "pass", "second")
                          if any(f.get(k) is not None for f in fs)}
            report["views"][name] = row
            frames_by_view[name] = res
            (out / "report.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
finally:
    rmod.Hd2dRenderer.draw = original_draw
    rmod.Hd2dRenderer._composite_dof = original_composite
    if Geometry is not None:
        Geometry.render = original_geom_render
    if state["copy"] is not None:
        for obj in state["copy"]:
            obj.delete()
    raw.glDeleteQueries(QN, qids)
    st.close()
    smi.terminate()
    smi.wait()
    (out / "nvidia_smi_end.txt").write_text(subprocess.run(["nvidia-smi"], capture_output=True, text=True).stdout)

rows = []
for r in csv.reader(open(smi_path)):
    try:
        ts = time.mktime(time.strptime(r[0].strip().split(".")[0], "%Y/%m/%d %H:%M:%S")) + float("0." + r[0].strip().split(".")[1])
        rows.append((ts, float(r[1]), float(r[2]), float(r[3]), float(r[4]), r[5].strip()))
    except (ValueError, IndexError):
        pass
for name, (a, b) in windows.items():
    sel = [r for r in rows if a <= r[0] <= b]
    if sel:
        report["views"][name]["telemetry"] = {
            "samples": len(sel), "gr_clock_mhz": [min(r[1] for r in sel), statistics.median(r[1] for r in sel),
                                                  max(r[1] for r in sel)],
            "mem_clock_mhz_median": statistics.median(r[2] for r in sel),
            "util_pct_median": statistics.median(r[4] for r in sel), "pstates": sorted({r[5] for r in sel})}
# each frame joined to the nearest clock sample (within 150 ms): the pass's GPU time by graphics / memory clock
import bisect  # noqa: E402

times = [r[0] for r in rows]


def clock_at(t):
    i = bisect.bisect_left(times, t)
    best = min((j for j in (i - 1, i) if 0 <= j < len(rows)), key=lambda j: abs(times[j] - t), default=None)
    return rows[best] if best is not None and abs(times[best] - t) <= 0.15 else None


for name, res in frames_by_view.items():
    by = {}
    for v in VARIANTS + ["off"]:
        for f in res[v]:
            r = clock_at(f["at"])
            if r is None:
                continue
            d = by.setdefault(f"gr{int(r[1] // 250 * 250)}_mem{int(r[2])}", {})
            d.setdefault(v + "_pass", []).append(f["pass"])
            d.setdefault(v + "_world", []).append(f["world"])
    report["views"][name]["by_clock"] = {k: {kk: {"n": len(vv), "p50": q(vv, .5)} for kk, vv in sorted(d.items())}
                                         for k, d in sorted(by.items())}
(out / "frames.json").write_text(json.dumps(frames_by_view) + "\n", encoding="utf-8")
(out / "report.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
