"""M17-L3 E2 timing, interleaved in one process (so both see the same GPU clock state): per shot, the game's E2
renderer and a twin built from the same settings with no lamp head found (E1's batches: nothing split, no glow),
drawn alternately A B A B ... 600 times each (first 60 of each dropped), the same settled frame, GPU timer query.
The twin shares E2's shader (with no glow its only difference from E1's is one uniform compare; the base / E2
process runs bound that). Clocks read before and after (nvidia-smi, read only).

    py -3.13 perf_pair.py <E2 worktree> <glow project> <stage-1 lakeside project> <out.json>
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

WT, GLOW, LAKE, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
sys.path.insert(0, str(WT))
sys.path.insert(0, str(WT / "tooling"))
os.chdir(WT)
import engine.optional_arcade  # noqa: E402,F401
import engine.hd2d.renderer as R  # noqa: E402
from hd2d_demo import HiddenGame  # noqa: E402

SC = "packs/core_regions/scenes"
GLOW_SHOTS = {"village_on_night": "glow_on_night.json", "lakeside_replica_night": "ev_lakeside.json",
              "fixtures_night": "ev_fixtures.json", "village_off_night": "glow_off_night.json"}
LAKE_SHOTS = {"lk_lamps12": ("lakeside__l3_night", (870, 300)), "lk_lamps34": ("lakeside__l3_night", (860, 640)),
              "lk_l1b_lamps_off": ("lakeside", (860, 640))}


def clocks() -> str:
    return subprocess.run(["nvidia-smi", "--query-gpu=clocks.gr,clocks.mem,pstate", "--format=csv,noheader"],
                          capture_output=True, text=True).stdout.strip()


def measure(game: HiddenGame, feet: tuple[float, float] | None) -> dict:
    game.step(5)
    if feet:
        p = game.player()
        p.center_x, p.bottom = feet
    game.window.motion_time = 0.0
    if hasattr(game.window, "water_time"):
        game.window.water_time = 0.0
    game.step(120)
    game.draw()
    e2 = game.window.hd2d_renderer
    original = R.lamp_head
    R.lamp_head = lambda *_a, **_k: None
    try:
        e1 = R.Hd2dRenderer(game.window, e2.settings, e2._resolve, models=e2.models)
    finally:
        R.lamp_head = original
    e1.camera, e1._camera_ready, e1._aspect = e2.camera, True, e2._aspect
    q = game.window.ctx.query(samples=False, time=True, primitives=False)
    draw = R.Hd2dRenderer.draw
    for r in (e1, e2):  # (each renderer's lamp shadow maps drawn once, before timing)
        draw(r)
    before = clocks()
    times: dict[str, list[float]] = {"e1": [], "e2": []}
    for _ in range(600):
        for name, r in (("e1", e1), ("e2", e2)):
            with q:
                draw(r)
            times[name].append(q.time_elapsed / 1e6)
    after = clocks()
    out: dict = {"clocks": [before, after], "draw_calls": {}, "lamp_head_draws": e2.stats()["lamp_head_draws"]}
    for name, r in (("e1", e1), ("e2", e2)):
        draw(r)
        out["draw_calls"][name] = r.draw_calls
        out[f"{name}_shadow_draws"] = r.lighting.shadow_draws
        out[f"{name}_buffer_bytes"] = r.stats()["buffer_bytes"]
    diffs = sorted(b - a for a, b in zip(times["e1"][60:], times["e2"][60:]))
    for name in ("e1", "e2"):
        t = sorted(times[name][60:])
        out[name] = {"p10_ms": round(t[len(t) // 10], 4), "p50_ms": round(statistics.median(t), 4)}
    out["paired_diff_ms"] = {"p25": round(diffs[len(diffs) // 4], 4), "median": round(statistics.median(diffs), 4),
                             "p75": round(diffs[(3 * len(diffs)) // 4], 4)}
    e1.release()
    return out


res: dict = {"worktree": str(WT)}
for project, shots in ((GLOW, GLOW_SHOTS), (LAKE, LAKE_SHOTS)):
    game = HiddenGame(project, size=(1280, 720))
    game.window.audio.set_muted(True)
    try:
        for name, spec in shots.items():
            scene, feet = (spec, None) if isinstance(spec, str) else (spec[0] + ".json", spec[1])
            game.load(f"{SC}/{scene}")
            res[name] = measure(game, feet)
    finally:
        game.close()
OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
for k, v in res.items():
    if isinstance(v, dict):
        print(f"{k:24} e1 {v['e1']} e2 {v['e2']} diff {v['paired_diff_ms']} draws {v['draw_calls']} "
              f"shadow {v['e1_shadow_draws']}->{v['e2_shadow_draws']} heads {v['lamp_head_draws']} {v['clocks']}")
