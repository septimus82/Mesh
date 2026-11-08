"""M17-L3 E2 timing: the HD-2D renderer's whole draw, GPU time (timer query), E1 base or E2, the same settled frame
drawn 660 times (first 60 dropped), per shot; also its draw calls, lamp-head draws, buffer and texture bytes and the GPU
clocks (nvidia-smi, read only). One process per run; run base / E2 alternating.

    py -3.13 perf_e2.py <worktree> <glow project> <stage-1 lakeside project> <out.json>
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

assert Path(R.__file__).resolve().is_relative_to(WT.resolve()), R.__file__
SC = "packs/core_regions/scenes"
GLOW_SHOTS = {"village_on_night": "glow_on_night.json", "village_off_night": "glow_off_night.json",
              "lakeside_replica_night": "ev_lakeside.json", "fixtures_night": "ev_fixtures.json"}
LAKE_SHOTS = {"lk_lamps12": ("lakeside__l3_night", (870, 300)), "lk_lamps34": ("lakeside__l3_night", (860, 640)),
              "lk_l1b_lamps_off": ("lakeside", (860, 640)), "cottage": ("cottage__l3_night", (294, 200))}


def clocks() -> str:
    return subprocess.run(["nvidia-smi", "--query-gpu=clocks.gr,clocks.mem,pstate,temperature.gpu",
                           "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()


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
    hd = game.window.hd2d_renderer
    q = game.window.ctx.query(samples=False, time=True, primitives=False)
    draw = type(hd).draw
    t = []
    for _ in range(660):
        with q:
            draw(hd)
        t.append(q.time_elapsed / 1e6)
    t = sorted(t[60:])
    st = hd.stats()
    return {"p10_ms": round(t[len(t) // 10], 4), "p50_ms": round(statistics.median(t), 4),
            "p95_ms": round(t[int(0.95 * len(t))], 4), "draw_calls": hd.draw_calls,
            "static_draws": st["static_draws"], "lamp_head_draws": st.get("lamp_head_draws", 0),
            "buffer_bytes": st["buffer_bytes"], "texture_bytes": st["texture_bytes"],
            "target": [round(c, 3) for c in hd.camera.target], "clocks": clocks()}


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
print({k: (v["p10_ms"], v["draw_calls"], v["lamp_head_draws"]) for k, v in res.items() if isinstance(v, dict)})
