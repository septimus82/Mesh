"""CI-422A evidence (never merged): an interleaved, warmed control-vs-sculpt measurement of Studio's terrain stroke.

One Studio session (the Hills room, Sculpt), the same camera, viewport, drawing, read-back and GL cleanup
(StudioDriver.frame) for both kinds of frame. Each trial, in ABBA order:
  control: the cursor hovers along the stroke's path (event, ground pick, brush ring, drawing, read-back; no edit)
  sculpt:  press, the same path as drags (each timed like the gate's frame), release + the next frame (timed)
Raise and lower alternate, so the ground stays about where it was. Faults are injected in-process with --mut.

    python docs/reviews/ci422a_terrain_timing/terrain_ab.py OUT.json [--mut NAME] [--ms 15] [--trials 10] [--steps 16]
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
os.chdir(REPO)

MUTS = ("none", "reload_on_release", "reload_per_flush", "rebuild_all", "cpu_frame", "cpu_dab")


def apply_mut(name: str, ms: float) -> None:
    from engine.studio_hd2d import Hd2dView

    end, flush, tick = Hd2dView.end_stroke, Hd2dView._flush_stroke, Hd2dView.tick
    busy = ms / 1000.0

    def spin() -> None:
        t = time.perf_counter()
        while time.perf_counter() - t < busy:
            pass

    if name == "reload_on_release":  # 1. a full room reload when the stroke commits
        def end_stroke(self):  # type: ignore[no-untyped-def]
            had = self.stroke is not None
            end(self)
            if had:
                self.studio._reload()
        Hd2dView.end_stroke = end_stroke
    elif name == "reload_per_flush":  # 1b. a full room reload while sculpting (it cancels the stroke)
        def _flush_stroke(self):  # type: ignore[no-untyped-def]
            pending = self.stroke is not None and bool(self.stroke.get("pending"))
            flush(self)
            if pending and self.stroke is not None:
                self.studio._reload()
        Hd2dView._flush_stroke = _flush_stroke
    elif name == "rebuild_all":  # 2. excessive terrain rebuilding: every chunk, every flush
        def _flush_stroke(self):  # type: ignore[no-untyped-def]
            s, r = self.stroke, self.renderer
            if s is not None and r is not None and r.terrain is not None and s["tool"] not in ("paint", "scatter") \
                    and s["pending"]:
                nx, ny = r.terrain.chunk_count()
                s["pending"] = {(i, j) for j in range(ny) for i in range(nx)}
            flush(self)
        Hd2dView._flush_stroke = _flush_stroke
    elif name == "cpu_frame":  # 3a. extra CPU work in every Studio frame (control frames too)
        def tick_(self, dt):  # type: ignore[no-untyped-def]
            spin()
            tick(self, dt)
        Hd2dView.tick = tick_
    elif name == "cpu_dab":  # 3b. extra CPU work in every sculpting step (only while sculpting)
        def flush_(self):  # type: ignore[no-untyped-def]
            if self.stroke is not None and self.stroke.get("pending"):
                spin()
            flush(self)
        Hd2dView._flush_stroke = flush_
    elif name != "none":
        raise ValueError(name)


def stats(v: list[float]) -> dict[str, float]:
    if not v:
        return {}
    o = sorted(v)
    return {"median": round(statistics.median(o), 3), "p95": round(o[int(0.95 * (len(o) - 1))], 3),
            "max": round(o[-1], 3), "n": len(o)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--mut", default="none", choices=MUTS)
    ap.add_argument("--ms", type=float, default=15.0)
    ap.add_argument("--trials", type=int, default=10)
    ap.add_argument("--warm", type=int, default=2)
    ap.add_argument("--steps", type=int, default=16)
    a = ap.parse_args()
    apply_mut(a.mut, a.ms)
    import m20a_terrain_study as m20a
    import m20b_sculpt_study as m20b

    tmp = Path(tempfile.mkdtemp(prefix="ci422a_"))
    project = m20a.make_project(tmp, "ab", stages=("hill",), pond=False)
    d = m20b._driver(project)
    rows: list[dict] = []
    try:
        s, view, k = d.studio, d.studio.hd2d, d.arcade.key
        d.button("Sculpt")
        d.advance(5)
        left = d.arcade.MOUSE_BUTTON_LEFT
        a_pt, b_pt = (6.5, 14.0), (12.0, 20.5)
        for t in range(a.warm + a.trials):
            ends = (a_pt, b_pt) if t % 2 == 0 else (b_pt, a_pt)
            screen = [d.screen(p) for p in m20b._path(ends[0], ends[1], a.steps)]
            lower = (t // 2) % 2 == 1  # raise, raise, lower, lower, ...: the ground stays about where it was

            def control() -> tuple[list[float], float]:
                times = []
                # hovering rewrites the status line ("Ground +0.42 m here.") as the height under the brush changes;
                # a stroke doesn't: silenced here, so a control frame is a sculpt frame without the edit
                s._say = lambda *_a, **_k: None
                try:
                    d.window.dispatch_event("on_mouse_motion", *screen[0], 0, 0)
                    d.advance()
                    last = screen[0]
                    for p in screen[1:]:
                        t0 = time.perf_counter()
                        d.window.dispatch_event("on_mouse_motion", p[0], p[1], p[0] - last[0], p[1] - last[1])
                        d.frame()
                        times.append((time.perf_counter() - t0) * 1000)
                        last = p
                    t0 = time.perf_counter()
                    d.frame()  # (the frame that would follow a release: nothing to commit)
                    release = (time.perf_counter() - t0) * 1000
                finally:
                    del s._say
                return times, release

            def sculpt() -> tuple[list[float], float, list[float], float | None, dict]:
                n_sculpt = len(view.timings["sculpt_ms"])
                n_edit = len(view.timings["edit_ms"])
                with m20b._counting_reloads(d) as reloads:
                    d.window.dispatch_event("on_mouse_motion", *screen[0], 0, 0)
                    if lower:
                        d.window.dispatch_event("on_key_press", k.LSHIFT, 0)
                    d.window.dispatch_event("on_mouse_press", *screen[0], left, 0)
                    times = []
                    last = screen[0]
                    for p in screen[1:]:
                        t0 = time.perf_counter()
                        d.window.dispatch_event("on_mouse_drag", p[0], p[1], p[0] - last[0], p[1] - last[1], left, 0)
                        d.frame()
                        times.append((time.perf_counter() - t0) * 1000)
                        last = p
                    t0 = time.perf_counter()
                    d.window.dispatch_event("on_mouse_release", *screen[-1], left, 0)
                    d.frame()
                    release = (time.perf_counter() - t0) * 1000
                    if lower:
                        d.window.dispatch_event("on_key_release", k.LSHIFT, 0)
                d.advance()
                # (sculpt_ms keeps its last 240: a stroke adds far fewer, so the new ones are at the end)
                added = len(view.timings["sculpt_ms"]) - n_sculpt
                upd = view.timings["sculpt_ms"][-added:] if added > 0 else []
                commit = view.timings["edit_ms"][-1] if len(view.timings["edit_ms"]) > n_edit else None
                return times, release, upd, commit, dict(reloads)

            if t % 2 == 0:  # ABBA
                c_times, c_rel = control()
                s_times, s_rel, upd, commit, reloads = sculpt()
            else:
                s_times, s_rel, upd, commit, reloads = sculpt()
                c_times, c_rel = control()
            if t < a.warm:
                continue
            cm, sm = statistics.median(c_times), statistics.median(s_times)
            rows.append({"control_frame_ms": round(cm, 3), "sculpt_frame_ms": round(sm, 3),
                         "incremental_ms": round(sm - cm, 3), "ratio": round(sm / cm, 4),
                         "update_terrain_ms": round(statistics.median(upd), 3) if upd else None,
                         "commit_ms": round(commit, 3) if commit is not None else None,
                         "release_ms": round(s_rel, 3), "control_release_ms": round(c_rel, 3),
                         "release_extra_ms": round(s_rel - c_rel, 3), **reloads,
                         "sculpt_frames": [round(x, 2) for x in s_times]})
        info = d.window.ctx.info
        gl = {"renderer": info.RENDERER, "vendor": info.VENDOR}
        undo = len(s.project._undo)
    finally:
        d.close()

    def med(key: str) -> float | None:
        v = [r[key] for r in rows if r[key] is not None]
        return round(statistics.median(v), 3) if v else None

    every_frame = [x for r in rows for x in r["sculpt_frames"]]
    report = {"mut": a.mut, "ms": a.ms, "trials": a.trials, "steps": a.steps, "gl": gl, "undo_steps": undo,
              "summary": {k_: med(k_) for k_ in ("control_frame_ms", "sculpt_frame_ms", "incremental_ms", "ratio",
                                                  "update_terrain_ms", "commit_ms", "release_ms", "control_release_ms",
                                                  "release_extra_ms")},
              "sculpt_frame_all": stats(every_frame),
              "reloads": {"room_reloads": sum(r["room_reloads"] for r in rows),
                          "scene_loads": sum(r["scene_loads"] for r in rows)},
              "rows": rows}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({"mut": a.mut, "gl": gl["renderer"], **report["summary"], **report["reloads"]}))


if __name__ == "__main__":
    main()
