"""Post-M20 repository health checkpoint, Part F: one representative, heavy HD-2D room, measured (hidden windows only;
Studio through its own events).

    py -3.13 tooling/health_stress_study.py run OUT      # run it alone: timings

The room: 128 x 128 m of sculpted ground (Stage 20B's scale room), painted (stone, earth paths, mud and sand, as
Stage 20C's brush paints), 8,000 scattered things (Stage 20E's mix: swaying plants, torches, banners, trees), a pond
with full reflections, rain and snow, six lamps (two casting shadows), a gusty wind. Measured with its decoration
still and moving: room load; frame wall time (update, draw and the GPU finishing) and the CPU's share (the frame
issued, before waiting for the GPU); draw and shadow draws; GPU memory by kind; the process's memory. Then GPU objects
and process memory over five room changes and five Studio Play/Stop cycles, and Studio's latencies: opening the room,
a scatter stroke's commit, its undo, the save.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import random
import statistics
import sys
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
import hd2d_visual_study as study  # noqa: E402
import m20b_sculpt_study as m20b  # noqa: E402
import m20e_motion_study as m20e  # noqa: E402
from hd2d_demo import SCENES, HiddenGame, _gl_counts  # noqa: E402

PX = 32.0
SIDE = 128.0
INSTANCES = 8000


class _Counters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t), ("PrivateUsage", ctypes.c_size_t)]


def process_mb() -> float:
    """The process's private memory (MB; Windows: what it has committed)."""
    if sys.platform != "win32":
        return 0.0
    counters = _Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE  # (a 64-bit handle: the default int would truncate it)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Counters), wintypes.DWORD]
    if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        return -1.0
    return round(float(counters.PrivateUsage) / 1e6, 1)


def make_project(out: Path) -> Path:
    """The heavy room, through the checked operations (as Studio and AI would make it)."""
    from engine import project_ops as ops
    from engine.paths import get_content_roots, set_content_roots

    project: Path = m20b.scale_project(out, "stress", (SIDE, SIDE))
    path = project / SCENES / "hills.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    roots = list(get_content_roots())
    set_content_roots([project])  # (the ops read the room's models from its project, as Studio does)
    try:
        rng = random.Random(11)
        for material, strokes in (("stone", 14), ("earth", 10), ("mud", 6), ("sand", 6)):
            for _ in range(strokes):
                x, y = rng.uniform(8, SIDE - 8) * PX, rng.uniform(8, SIDE - 8) * PX
                dabs = [[x + k * 24 * rng.choice((-1, 1)), y + k * 18, 1.0] for k in range(8)]
                scene = ops.paint_terrain_stroke(scene, material, dabs, rng.uniform(48, 96))
        scene = ops.set_scatter(scene, m20e._mixed(INSTANCES, (SIDE, SIDE)))
        cx, cy = SIDE / 2 * PX, SIDE / 2 * PX
        scene, pond = ops.place_blank(scene, "hills", "Pond", cx + 10 * PX, cy + 6 * PX)
        scene = ops.set_water(scene, pond, preset="natural_pond", width=320, height=256)
        scene = ops.set_water_reflections(scene, "full")
        scene = ops.set_particles(scene, [{"preset": "rain", "count": 4000}, {"preset": "snow", "count": 1500}])
        scene = ops.set_wind(scene, speed=6.0, direction=20.0, gust=0.7)
        scene = ops.set_motion(scene, enabled=True)
        for k in range(6):
            scene, _i = ops.add_light(scene, cx + (k - 2.5) * 5 * PX, cy + (k % 2) * 6 * PX, color="Warm", radius=224)
    finally:
        set_content_roots(roots)
    path.write_text(json.dumps(scene) + "\n", encoding="utf-8")
    return project


def _centre(game: HiddenGame) -> None:
    hd = game.window.hd2d_renderer
    player = game.player()
    player.center_x = SIDE / 2 * PX
    player.center_y += SIDE / 2 * PX - player.bottom
    player.mesh_entity_data["elevation"] = hd.terrain.height(player.center_x, SIDE / 2 * PX) or 0.0


def _frames(game: HiddenGame, n: int) -> tuple[float, float]:
    """Median frame wall time and its CPU share (ms): the frame issued, then the GPU waited for."""
    walls, cpus = [], []
    for _ in range(n):
        t0 = time.perf_counter()
        game.window.dispatch_event("on_update", 1 / 60)
        game.window.dispatch_event("on_draw")
        t1 = time.perf_counter()
        game.window.ctx.finish()
        t2 = time.perf_counter()
        cpus.append((t1 - t0) * 1000)
        walls.append((t2 - t0) * 1000)
    return round(statistics.median(walls), 2), round(statistics.median(cpus), 2)


def run(out: Path) -> dict[str, Any]:
    from engine.hd2d.motion import Motion, parse_motion

    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"process_mb_before": process_mb()}
    project = make_project(out)
    report["stored_mb"] = round((project / SCENES / "hills.json").stat().st_size / 1e6, 2)
    game = HiddenGame(project, size=study.SIZE)
    try:
        t0 = time.perf_counter()
        game.load(f"{SCENES}/hills.json")
        report["room_load_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        game.step(10)
        _centre(game)
        hd = game.window.hd2d_renderer
        _frames(game, 600)  # (warm)
        rows: dict[str, list[tuple[float, float]]] = {"still": [], "moving": []}
        for _ in range(3):
            for label in ("still", "moving", "moving", "still"):
                hd.scatter.set_motion(parse_motion({}) if label == "moving" else Motion(), hd.wind)
                _frames(game, 30)
                rows[label].append(_frames(game, 120))
        stats = hd.stats()
        report["frames"] = {k: {"wall_ms": round(statistics.median(v[0] for v in r), 2),
                                "cpu_ms": round(statistics.median(v[1] for v in r), 2)} for k, r in rows.items()}
        report["draws"] = {k: stats[k] for k in ("draw_calls", "shadow_draws", "scatter_sprite_draws", "terrain_draws",
                                                 "lamps", "shadow_lamps", "particles", "water_surfaces",
                                                 "precipitation_maps", "scatter_instances")}
        report["gpu_mb"] = {k.replace("_bytes", ""): round(stats[k] / 1e6, 2) for k in stats
                            if k.endswith("_bytes") and isinstance(stats[k], int)}
        report["process_mb_playing"] = process_mb()
        counts, memory = [], []
        for _ in range(5):  # room changes: the village and back
            game.load(f"{SCENES}/start.json")
            game.step(2)
            game.window.dispatch_event("on_draw")
            game.load(f"{SCENES}/hills.json")
            game.step(2)
            game.window.dispatch_event("on_draw")
            game.window.ctx.gc()
            counts.append(_gl_counts(game.window.ctx))
            memory.append(process_mb())
        report["room_changes"] = {"gl_objects_each": counts, "stable": counts[1:] == counts[:-1],
                                  "process_mb_each": memory}
    finally:
        game.close()
    report["studio"] = studio(project)
    print(json.dumps(report, indent=1), flush=True)
    return report


def studio(project: Path) -> dict[str, Any]:
    """Mesh Studio on the heavy room: open it, a Meadow stroke (commit), its undo, the save; five Play/Stop cycles:
    GPU objects and memory after each."""
    import m20c_material_study as m20c

    d = m20b._driver(project)
    row: dict[str, Any] = {}
    try:
        s, view, k = d.studio, d.studio.hd2d, d.arcade.key
        t0 = time.perf_counter()
        s._reload()
        row["room_open_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        d.frame(5)
        d.button("Scatter")
        m20c._look_at(d, SIDE / 2, SIDE / 2, 18.0)
        m20b.RELEASES.clear()
        view.timings["edit_ms"].clear()
        m20b._stroke(d, m20c._on_ground(d, [(SIDE / 2 - 3, SIDE / 2), (SIDE / 2 + 3, SIDE / 2 + 1)], 0.1))
        row["stroke_commit_ms"] = round(view.timings["edit_ms"][-1], 1) if view.timings["edit_ms"] else None
        row["stroke_release_to_next_frame_ms"] = round(m20b.RELEASES[-1], 1) if m20b.RELEASES else None
        t0 = time.perf_counter()
        s.save()  # (the stroke: written to disk)
        row["save_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        t0 = time.perf_counter()
        d.key(k.Z, k.MOD_CTRL)
        row["undo_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        counts, memory = [], []
        for _ in range(5):
            d.key(k.F4)  # Play
            d.frame(20)
            d.key(k.F4)  # Stop
            d.frame(5)
            d.window.ctx.gc()
            counts.append(_gl_counts(d.window.ctx))
            memory.append(process_mb())
        row["play_stop"] = {"gl_objects_each": counts, "stable": counts[1:] == counts[:-1], "process_mb_each": memory}
    finally:
        d.close()
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("what", choices=["run"])
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    run(args.out)


if __name__ == "__main__":
    main()
